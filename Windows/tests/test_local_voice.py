import base64
import json
import math
import time
import unittest
from unittest import mock

import numpy as np

from bluey import ollama, stt
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

    def run_voice(self, replies, words, caps=frozenset({"completion", "vision"})):
        replies = iter(replies)
        seen = []

        def chat(messages, model=None, tools=None, on_delta=None, cancelled=None, num_ctx=None, format=None,
                 temperature=None, think=None):
            if not messages:
                return "", []
            self.assertIsNotNone(format)  # immer strukturierte JSON-Antworten
            seen.append([dict(m) for m in messages])
            return json.dumps(next(replies)), []

        words = iter(words)
        patches = [mock.patch.object(ollama, "chat", side_effect=chat),
                   mock.patch.object(ollama, "capabilities", return_value=set(caps)),
                   mock.patch.object(stt, "transcribe_pcm", side_effect=lambda pcm, rate: next(words)),
                   mock.patch.object(stt, "preload")]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        host, phone = FakeHost(), FakePhone()
        voice = LocalVoice(host)
        voice.command("start", phone)
        return voice, host, phone, seen

    def test_hold_ask_answers_and_uses_screen_tools(self):
        voice, host, phone, seen = self.run_voice(
            [{"say": "", "tool": "point_at_spot", "arguments": {"x": 500, "y": 500}},
             {"say": "Das ist dein Editor.", "tool": "none", "arguments": {}}],
            ["Der Film gestern war gut.", "Was ist das hier?"])
        send = lambda pcm: voice.audio(base64.b64encode(pcm).decode(), phone)
        send(tone(0.5, False) + tone(1.0) + tone(1.0, False))  # mitgehört
        self.wait(voice, phone, "words")
        voice.command("hold", phone)
        send(tone(0.3, False) + tone(1.0))
        voice.command("ask", phone)
        self.wait(voice, phone, "done")
        done = [e for e in phone.events if e["type"] == "done"][0]
        self.assertEqual(done["text"], "Das ist dein Editor.")
        # Die Frage klingt nach Bildschirm: er schaut vorher selbst hin, dann zeigt er.
        self.assertEqual([t[0] for t in host.tools], ["look_at_screen", "point_at_spot"])
        asked = [e for e in phone.events if e["type"] == "words" and e["asked"]]
        self.assertEqual(asked[0]["text"], "Was ist das hier?")
        user = seen[0][-1]
        self.assertIn("Der Film gestern war gut.", user["content"])
        self.assertIn("Frage des Nutzers: Was ist das hier?", user["content"])
        self.assertIn("images", user)  # das Bildschirmfoto geht an ein Modell mit Augen
        self.assertIn("JSON", seen[0][0]["content"])
        self.assertEqual(host.captions[-1], ("Das ist dein Editor.", True))

    def test_plain_question_gets_a_real_answer_without_tools(self):
        voice, host, phone, seen = self.run_voice(
            [{"say": "Canberra.", "tool": "none", "arguments": {}}], ["Was ist die Hauptstadt von Australien?"])
        voice.command("hold", phone)
        voice.audio(base64.b64encode(tone(1.2)).decode(), phone)
        voice.command("ask", phone)
        self.wait(voice, phone, "done")
        self.assertEqual([e for e in phone.events if e["type"] == "done"][0]["text"], "Canberra.")
        self.assertEqual(host.tools, [])

    def test_short_quiet_press_is_explained(self):
        voice, host, phone, seen = self.run_voice([], [])
        voice.command("hold", phone)
        voice.command("ask", phone)
        self.wait(voice, phone, "done")
        self.assertIn("nicht verstanden", [e for e in phone.events if e["type"] == "done"][0]["text"])
        self.assertEqual(seen, [])

    def test_sleep_and_typed_questions(self):
        voice, host, phone, seen = self.run_voice([{"say": "Tschüss!", "tool": "go_to_sleep", "arguments": {}}], [])
        answers = []
        voice.on_answer.append(lambda q, a: answers.append((q, a)))
        voice.ask_text("Gute Nacht")
        self.wait(voice, phone, "done")
        self.assertEqual([e for e in phone.events if e["type"] == "done"][0], {"type": "done", "text": "Tschüss!", "sleep": True})
        self.assertEqual(answers, [("Gute Nacht", "Tschüss!")])

    def test_missing_model_is_explained(self):
        voice, host, phone, seen = self.run_voice([], [])
        answers = []
        voice.on_answer.append(lambda q, a: answers.append(a))
        with mock.patch.object(ollama, "chat", side_effect=ollama.OllamaError('model "gemma3:4b" not found')):
            voice.ask_text("Hallo?")
            self.wait(voice, phone, "error")
        self.assertIn("nicht installiert", [e for e in phone.events if e["type"] == "error"][0]["text"])
        self.assertTrue(answers and answers[0].startswith("Fehler"))


class ParseAnswerTest(unittest.TestCase):
    def test_json_and_fallbacks(self):
        from bluey.local_voice import parse_answer, wants_screen
        self.assertEqual(parse_answer('{"say": "Hi", "tool": "none", "arguments": {}}'), ("Hi", None, {}))
        self.assertEqual(parse_answer('{"say": "", "tool": "open_app", "arguments": {"name": "Editor"}}'),
                         ("", "open_app", {"name": "Editor"}))
        self.assertEqual(parse_answer("Einfach Text."), ("Einfach Text.", None, {}))
        self.assertTrue(wants_screen("Was ist das hier?"))
        self.assertTrue(wants_screen("Öffne bitte Chrome"))
        self.assertFalse(wants_screen("Wie viel ist 17 mal 23?"))
