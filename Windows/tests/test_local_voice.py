import base64
import json
import math
import time
import unittest
from unittest import mock

import numpy as np

from bluey import local_voice, ollama, stt
from bluey.local_voice import LocalVoice, Segmenter, parse_text_tool, visible_text


def tone(seconds, loud=True):
    n = int(24000 * seconds)
    if not loud:
        return (np.random.default_rng(1).normal(0, 60, n)).astype(np.int16).tobytes()
    t = np.arange(n) / 24000
    return (np.sin(2 * math.pi * 220 * t) * 6000).astype(np.int16).tobytes()


class FakePhone:
    def __init__(self):
        self.events = []

    def send(self, packet):
        if packet.get("command") == "voiceEvent":
            self.events.append(json.loads(packet["text"]))


class FakeUi:
    def post(self, fn):
        fn()


class FakeHost:
    def __init__(self):
        self.ui = FakeUi()
        self.captions = []
        self.tools = []

    def caption(self, text, finished):
        self.captions.append((text, finished))

    def run_tool(self, name, args):
        self.tools.append((name, args))
        if name == "look_at_screen":
            return "Vorderste App: Editor\nL1 @500,500 \"Hallo\"", "SU1BR0U="
        return "Zeige dorthin.", None


class SegmenterTest(unittest.TestCase):
    def test_finds_speech_between_silence(self):
        s = Segmenter()
        out = s.feed(tone(1.0, loud=False)) + s.feed(tone(1.2)) + s.feed(tone(1.0, loud=False))
        self.assertEqual(len(out), 1)
        seconds = len(out[0]) / 2 / 24000
        self.assertTrue(1.2 < seconds < 2.4, seconds)

    def test_close_returns_open_speech(self):
        s = Segmenter()
        s.feed(tone(0.5, loud=False) + tone(0.6))
        self.assertIsNotNone(s.close())
        self.assertIsNone(s.close())


class TextToolTest(unittest.TestCase):
    def test_parses_tool_lines(self):
        before, call = parse_text_tool('Ich recherchiere kurz… TOOL {"name": "web_research", "arguments": {"question": "Wetter"}}')
        self.assertEqual(before, "Ich recherchiere kurz…")
        self.assertEqual(call, {"name": "web_research", "arguments": {"question": "Wetter"}})
        _, call = parse_text_tool('```json\n{"name": "look_at_screen", "arguments": {}}\n```')
        self.assertEqual(call["name"], "look_at_screen")
        text, call = parse_text_tool("Das ist ein Knopf.")
        self.assertIsNone(call)
        self.assertEqual(text, "Das ist ein Knopf.")

    def test_visible_text_hides_tool_lines(self):
        self.assertEqual(visible_text('Moment TOOL {"na'), "Moment")
        self.assertEqual(visible_text('{"name":'), "")
        self.assertEqual(visible_text("Hallo du"), "Hallo du")


class LocalVoiceTest(unittest.TestCase):
    def wait(self, voice, phone, kind, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            if any(e["type"] == kind for e in phone.events):
                return
            time.sleep(0.02)
        self.fail(f"kein {kind}-Ereignis: {phone.events}")

    def test_hold_ask_with_text_tools(self):
        replies = iter([('TOOL {"name": "look_at_screen", "arguments": {}}', []),
                        ('TOOL {"name": "point_at_spot", "arguments": {"x": 500, "y": 500}}', []),
                        ("Das ist dein Editor.", [])])
        seen = []

        def chat(messages, model=None, tools=None, on_delta=None, cancelled=None, num_ctx=None):
            if not messages:
                return "", []
            seen.append([dict(m) for m in messages])
            text, calls = next(replies)
            if on_delta:
                on_delta(text)
            return text, calls

        words = iter(["Der Film gestern war gut.", "Was ist das hier?"])
        with mock.patch.object(ollama, "chat", side_effect=chat), \
                mock.patch.object(ollama, "capabilities", return_value={"completion", "vision"}), \
                mock.patch.object(stt, "transcribe_pcm", side_effect=lambda pcm, rate: next(words)), \
                mock.patch.object(stt, "preload"):
            host, phone = FakeHost(), FakePhone()
            voice = LocalVoice(host)
            voice.command("start", phone)
            send = lambda pcm: voice.audio(base64.b64encode(pcm).decode(), phone)
            send(tone(0.5, False) + tone(1.0) + tone(1.0, False))  # mitgehört
            self.wait(voice, phone, "words")
            voice.command("hold", phone)
            send(tone(0.3, False) + tone(1.0))
            voice.command("ask", phone)
            self.wait(voice, phone, "done")
        done = [e for e in phone.events if e["type"] == "done"][0]
        self.assertEqual(done["text"], "Das ist dein Editor.")
        self.assertEqual([t[0] for t in host.tools], ["look_at_screen", "point_at_spot"])
        asked = [e for e in phone.events if e["type"] == "words" and e["asked"]]
        self.assertEqual(asked[0]["text"], "Was ist das hier?")
        heard = [e for e in phone.events if e["type"] == "words" and not e["asked"]]
        self.assertEqual(heard[0]["text"], "Der Film gestern war gut.")
        question = seen[0][-1]["content"]
        self.assertIn("Der Film gestern war gut.", question)
        self.assertIn("Frage des Nutzers: Was ist das hier?", question)
        self.assertIn("TOOL", seen[0][0]["content"])  # Textprotokoll, weil das Modell keine Werkzeuge kann
        self.assertTrue(any("images" in m for m in seen[1]))  # das Bildschirmfoto geht an ein Modell mit Augen
        self.assertEqual(host.captions[-1], ("Das ist dein Editor.", True))

    def test_native_tools_and_sleep(self):
        replies = iter([("Tschüss!", [{"name": "go_to_sleep", "arguments": {}}]), ("", [])])

        def chat(messages, model=None, tools=None, on_delta=None, cancelled=None, num_ctx=None):
            if not messages:
                return "", []
            self.assertTrue(tools)
            text, calls = next(replies)
            if on_delta and text:
                on_delta(text)
            return text, calls

        with mock.patch.object(ollama, "chat", side_effect=chat), \
                mock.patch.object(ollama, "capabilities", return_value={"completion", "tools"}), \
                mock.patch.object(stt, "transcribe_pcm", return_value="Gute Nacht"), \
                mock.patch.object(stt, "preload"):
            host, phone = FakeHost(), FakePhone()
            voice = LocalVoice(host)
            voice.command("start", phone)
            voice.command("hold", phone)
            voice.audio(base64.b64encode(tone(0.3, False) + tone(0.8)).decode(), phone)
            voice.command("ask", phone)
            self.wait(voice, phone, "done")
        done = [e for e in phone.events if e["type"] == "done"][0]
        self.assertEqual(done, {"type": "done", "text": "Tschüss!", "sleep": True})

    def test_missing_model_is_explained(self):
        def chat(messages, **kwargs):
            if not messages:
                return "", []
            raise ollama.OllamaError('model "gemma3:4b" not found, try pulling it first')
        with mock.patch.object(ollama, "chat", side_effect=chat), \
                mock.patch.object(ollama, "capabilities", return_value=set()), \
                mock.patch.object(stt, "transcribe_pcm", return_value="Hallo?"), \
                mock.patch.object(stt, "preload"):
            host, phone = FakeHost(), FakePhone()
            voice = LocalVoice(host)
            voice.command("start", phone)
            voice.command("hold", phone)
            voice.command("ask", phone)
            self.wait(voice, phone, "error")
        error = [e for e in phone.events if e["type"] == "error"][0]
        self.assertIn("nicht installiert", error["text"])
