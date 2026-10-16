import json
import os
import socket
import threading
import time
import unittest
from unittest import mock

from bluey import meeting_notes, protocol
from bluey.config import settings
from bluey.cursor_engine import CursorEngine, Mode
from bluey.host import LOCAL_TOKEN, Host
from bluey.server import PhoneServer


class Ui:
    def post(self, fn):
        fn()

    def call(self, fn):
        return fn()

    def later(self, seconds, fn):
        class H:
            def cancel(self):
                pass
        return H()


class FakeOverlay:
    def __init__(self):
        self.engine = CursorEngine()
        self.frame_callbacks = []
        self.speech_target = None
        self.caption = None
        self.bubbles = []

    @property
    def mode(self):
        return self.engine.mode

    def set_mode(self, mode):
        self.engine.set_mode(mode)

    @property
    def idle_mode(self):
        return Mode.FOLLOWING

    def go_home(self):
        self.engine.set_mode(Mode.FOLLOWING)

    def bubble(self, text, life=1.4):
        self.bubbles.append(text)


class FakeReports:
    def show_loading(self, q): pass
    def show(self, r): pass
    def show_error(self, m): pass


class HostTest(unittest.TestCase):
    def setUp(self):
        self.overlay = FakeOverlay()
        self.host = Host(Ui(), self.overlay, FakeReports())

    def test_local_token_by_default(self):
        settings.engine = "ollama"
        got = []
        self.host.handle({"command": "realtimeToken", "callID": "1"}, got.append, None)
        for _ in range(100):
            if got:
                break
            time.sleep(0.01)
        self.assertEqual(got[0], {"command": "realtimeToken", "callID": "1", "text": LOCAL_TOKEN})

    def test_pointing_queue_and_home(self):
        text, image = self.host.run_tool("point_at_spot", json.dumps({"x": 500, "y": 250}))
        self.assertEqual(text, "Zeige dorthin.")
        self.host._choreograph(time.monotonic())
        self.assertTrue(Mode.is_pinned(self.overlay.mode))
        self.assertEqual(self.host.run_tool("point_at", "{\"target_id\": \"W1\"}")[0], "Ruf zuerst look_at_screen auf.")
        self.host.run_tool("stop_pointing", "{}")
        self.host._choreograph(time.monotonic() + 10)
        self.assertEqual(self.overlay.mode, Mode.FOLLOWING)

    def test_actions_respect_the_switch(self):
        settings.computer_control = False
        try:
            text, _ = self.host.run_tool("click", "{\"x\": 1, \"y\": 1}")
            self.assertIn("ausgeschaltet", text)
        finally:
            settings.computer_control = True
        self.host.stop_actions()
        self.assertIn("Stopp", self.host.run_tool("type_text", "{\"text\": \"hi\"}")[0])

    def test_captions(self):
        self.host.caption("Hallo", False)
        self.assertEqual(self.overlay.caption, "Hallo")

    def test_notes_files(self):
        session = {"id": "ABCDEF12-3456", "started": 1_700_000_000, "ended": 1_700_003_700, "transcribing": 1,
                   "entries": [{"kind": "transcript", "speaker": "A", "text": "Hallo zusammen", "time": 1_700_000_010},
                               {"kind": "asked", "text": "Was war das?", "time": 1_700_000_020},
                               {"kind": "reply", "text": "Ein Test.", "time": 1_700_000_021},
                               {"kind": "report", "text": "Titel\n\nAbsatz", "time": 1_700_000_030}]}
        got = []
        self.host.handle({"command": "notes", "callID": "n", "text": json.dumps(session)}, got.append, None)
        folder = got[0]["text"]
        self.assertTrue(folder.endswith("abcdef12"))
        notes = open(os.path.join(folder, "notes.md"), encoding="utf-8").read()
        self.assertIn("**[", notes)
        self.assertIn("Sprecher A:** Hallo zusammen", notes)
        self.assertIn("> **Bluey:** Ein Test.", notes)
        self.assertIn("1 h 1 min", notes)
        self.assertTrue(os.path.exists(os.path.join(meeting_notes.root(), "README.md")))


class ServerTest(unittest.TestCase):
    def test_phone_round_trip(self):
        server = PhoneServer(name="Test-PC", port=0)
        names, requests = [], []
        server.on_phones_changed = names.append
        server.on_request = lambda packet, reply, phone: (requests.append(packet), reply({"command": "realtimeToken", "callID": packet["callID"], "text": LOCAL_TOKEN}))
        port = server.start()
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=3)
            decoder = protocol.Decoder()
            client.sendall(protocol.encode({"hello": "Pixel"}) + protocol.encode({"command": "realtimeToken", "callID": "x"}))
            received = []
            end = time.time() + 3
            while time.time() < end and len(received) < 2:
                received += decoder.feed(client.recv(65536))
            self.assertEqual(received[0], {"hello": "Test-PC"})
            self.assertEqual(received[1]["text"], LOCAL_TOKEN)
            server.send_face({"gazeX": 0.1, "gazeY": -0.2, "mood": "happy", "talk": 0})
            end = time.time() + 3
            while time.time() < end and not any("face" in p for p in received):
                received += decoder.feed(client.recv(65536))
            self.assertTrue(any(p.get("face", {}).get("mood") == "happy" for p in received))
            self.assertIn(["Pixel"], names)
            client.close()
            time.sleep(1.2)
            self.assertEqual(server.phone_names, [])
        finally:
            server.stop()
