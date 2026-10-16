"""Die lokale KI: Das Handy schickt Mikrofon-Audio, der PC macht den Rest.

1. Sprachabschnitte erkennen (Lautstärke-Schwelle mit mitlaufendem Grundrauschen).
2. Jeden Abschnitt mit Whisper in Text verwandeln: Mitgehörtes wird Kontext, beim Halten Gesagtes die Frage.
3. Beim Loslassen fragt er Ollama, mit Werkzeugen (Bildschirm ansehen, zeigen, bedienen, recherchieren).
4. Die Antwort strömt als Sprechblase auf den PC und als Ereignisse ans Handy (Zwitschern, Transkript).
"""
import base64
import json
import queue
import re
import threading
import time
import traceback
import uuid

from . import ollama, prompts, stt
from .config import settings

RATE = 24000
FRAME = 480  # 20 ms
PREROLL_FRAMES = 15  # 300 ms vor dem Sprechbeginn mitnehmen
END_SILENCE = 0.7
MAX_SEGMENT = 25.0
MAX_STEPS = 8
CONTEXT_LINES = 40


class Segmenter:
    """Zerlegt einen Audiostrom in Sprachabschnitte. Reine Rechnung, damit sie testbar ist."""

    def __init__(self):
        self.floor = 300.0
        self.in_speech = False
        self.buffer = bytearray()
        self.preroll = []
        self.silence = 0.0
        self.voiced = 0.0
        self._rest = b""

    @staticmethod
    def rms(frame):
        import numpy as np
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0

    def feed(self, pcm):
        """Gibt fertige Abschnitte (bytes) zurück."""
        done = []
        data = self._rest + pcm
        usable = len(data) - len(data) % (FRAME * 2)
        self._rest = data[usable:]
        for i in range(0, usable, FRAME * 2):
            frame = data[i:i + FRAME * 2]
            level = self.rms(frame)
            loud = level > max(420.0, self.floor * 2.6)
            if not self.in_speech:
                self.floor = self.floor * 0.97 + level * 0.03 if level < self.floor * 4 else self.floor
                self.preroll.append(frame)
                if len(self.preroll) > PREROLL_FRAMES:
                    self.preroll.pop(0)
                if loud:
                    self.in_speech = True
                    self.buffer = bytearray(b"".join(self.preroll))
                    self.preroll = []
                    self.silence = 0.0
                    self.voiced = 0.0
                continue
            self.buffer += frame
            seconds = FRAME / RATE
            if loud:
                self.silence = 0.0
                self.voiced += seconds
            else:
                self.silence += seconds
            if self.silence >= END_SILENCE or len(self.buffer) / 2 / RATE >= MAX_SEGMENT:
                segment = self.close()
                if segment:
                    done.append(segment)
        return done

    def close(self):
        """Schließt den laufenden Abschnitt (z. B. beim Loslassen). None, wenn kaum etwas gesprochen wurde."""
        segment = bytes(self.buffer) if self.in_speech and self.voiced >= 0.25 else None
        self.in_speech = False
        self.buffer = bytearray()
        self.silence = self.voiced = 0.0
        return segment


TOOL_LINE = re.compile(r"TOOL\s*(\{.*\})", re.S)


def parse_text_tool(text):
    """Findet einen Werkzeugaufruf im Textprotokoll. Gibt (Text davor, {name, arguments}) oder (Text, None) zurück."""
    match = TOOL_LINE.search(text)
    candidate = match.group(1) if match else None
    before = text[:match.start()] if match else text
    if not candidate:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if fenced:
            candidate, before = fenced.group(1), text[:fenced.start()]
        elif text.strip().startswith("{") and '"name"' in text:
            candidate, before = text.strip(), ""
    if not candidate:
        return text, None
    # Das erste vollständige JSON-Objekt nehmen.
    depth, end = 0, None
    for i, ch in enumerate(candidate):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    try:
        data = json.loads(candidate[:end] if end else candidate)
    except ValueError:
        return text, None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return text, None
    args = data.get("arguments") or data.get("parameters") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    return before.strip(), {"name": data["name"], "arguments": args if isinstance(args, dict) else {}}


def visible_text(text):
    """Was während des Streamens gezeigt werden darf (ohne angefangene Werkzeugzeile)."""
    cut = text.find("TOOL")
    if cut >= 0:
        text = text[:cut]
    fence = text.find("```")
    if fence >= 0:
        text = text[:fence]
    if text.lstrip().startswith("{"):
        return ""
    return text.strip()


class LocalVoice:
    def __init__(self, host):
        self.host = host
        self.phone = None
        self.active = False
        self.holding = False
        self.segmenter = Segmenter()
        self.lock = threading.Lock()
        self.jobs = queue.Queue()
        self.context = []      # mitgehörte Sätze
        self.question = []     # beim Halten gesagt
        self.history = []      # bisherige Fragen und Antworten (Ollama-Nachrichten)
        self.generation = 0
        threading.Thread(target=self._worker, name="Bluey lokale KI", daemon=True).start()

    # Vom Handy (Lese-Thread)

    def command(self, what, phone):
        if what == "start":
            with self.lock:
                if self.phone is not phone or not self.active:
                    self.generation += 1
                    self.context, self.question, self.history = [], [], []
                self.phone, self.active, self.holding = phone, True, False
                self.segmenter = Segmenter()
            self._warm_up()
        elif what == "stop":
            with self.lock:
                if self.phone is phone:
                    self.active = False
                    self.generation += 1
                    self.segmenter = Segmenter()
        elif what == "hold":
            with self.lock:
                if self.phone is phone:
                    self.holding = True
                    self.question = []
        elif what == "ask":
            with self.lock:
                if self.phone is not phone or not self.active:
                    return
                self.holding = False
                tail = self.segmenter.close()
                gen = self.generation
            if tail:
                self.jobs.put(("segment", tail, True, gen))
            self.jobs.put(("ask", None, True, gen))
        elif what == "hi":
            self.jobs.put(("hi", None, False, self.generation))

    def audio(self, data, phone):
        if not data or phone is not self.phone or not self.active:
            return
        try:
            pcm = base64.b64decode(data)
        except (ValueError, TypeError):
            return
        with self.lock:
            segments = self.segmenter.feed(pcm)
            asked, gen = self.holding, self.generation
        for segment in segments:
            self.jobs.put(("segment", segment, asked, gen))

    def _warm_up(self):
        stt.preload()

        def load_model():
            try:
                ollama.chat([], num_ctx=8192)  # lädt das Modell in die Grafikkarte
            except Exception:
                pass
        threading.Thread(target=load_model, daemon=True).start()

    def _send(self, event):
        phone = self.phone
        if phone:
            phone.send({"command": "voiceEvent", "text": json.dumps(event, ensure_ascii=False)})

    # Arbeiter (nacheinander: erst alles transkribieren, dann antworten)

    def _worker(self):
        while True:
            kind, data, asked, gen = self.jobs.get()
            if gen != self.generation:
                continue
            try:
                if kind == "segment":
                    self._segment(data, asked, gen)
                elif kind == "ask":
                    self._answer(gen)
                elif kind == "hi":
                    self._reply([{"role": "system", "content": prompts.personality()},
                                 {"role": "user", "content": "Sag ein kurzes, fröhliches Hallo in unter acht Wörtern."}], gen, tools=False)
            except Exception as error:
                traceback.print_exc()
                self._send({"type": "error", "text": f"Die lokale KI hatte ein Problem: {error}"})

    def _segment(self, pcm, asked, gen):
        item = "local-" + uuid.uuid4().hex[:12]
        self._send({"type": "turn", "item": item, "asked": asked})
        try:
            text = stt.transcribe_pcm(pcm, RATE)
        except stt.SpeechError as error:
            self._send({"type": "error", "text": str(error)})
            return
        if gen != self.generation:
            return
        self._send({"type": "words", "item": item, "text": text, "asked": asked})
        if not text:
            return
        if asked:
            self.question.append(text)
        else:
            self.context.append(text)
            del self.context[:-CONTEXT_LINES]

    def _answer(self, gen):
        question = " ".join(self.question).strip()
        self.question = []
        self._send({"type": "thinking"})
        heard = "\n".join(self.context[-CONTEXT_LINES:])
        user = ""
        if heard:
            user += "Vorher mitgehört (nur Kontext, nicht darauf antworten):\n" + heard + "\n\n"
        user += "Frage des Nutzers: " + (question or "(Er hat beim Halten nichts gesagt; antworte auf das zuletzt Gesagte.)")
        if question:
            self.context.append(question)
        messages = [{"role": "system", "content": self._system()}] + self.history[-16:] + [{"role": "user", "content": user}]
        answer = self._reply(messages, gen, tools=True)
        self.history += [{"role": "user", "content": "Frage des Nutzers: " + (question or "…")},
                         {"role": "assistant", "content": answer or "…"}]
        del self.history[:-16]

    def _system(self):
        model = settings.ollama_model
        caps = ollama.capabilities(model)
        text = prompts.instructions() + "\n\n" + prompts.LOCAL_GUIDE
        if "tools" not in caps:
            text += "\n\n" + prompts.text_tool_protocol(prompts.tools())
        if "vision" not in caps:
            text += "\n\nDu kannst keine Bilder sehen; nutze die Text- und Bedienelement-Listen von look_at_screen."
        return text

    def _reply(self, messages, gen, tools):
        """Fragt Ollama, führt Werkzeuge aus, bis eine Antwort steht. Gibt die letzte Antwort zurück."""
        model = settings.ollama_model
        caps = ollama.capabilities(model)
        native = tools and "tools" in caps
        vision = "vision" in caps
        tool_list = prompts.ollama_tools(prompts.tools()) if native else None
        final, sleep = "", False
        for _ in range(MAX_STEPS):
            if gen != self.generation:
                return final
            shown = [""]

            def on_delta(text):
                visible = visible_text(text) if tools and not native else text.strip()
                if visible and visible != shown[0]:
                    shown[0] = visible
                    self._send({"type": "delta", "text": visible})
                    self.host.ui.post(lambda v=visible: self.host.caption(v, False))
            try:
                text, calls = ollama.chat(messages, model=model, tools=tool_list, on_delta=on_delta,
                                          cancelled=lambda: gen != self.generation)
            except ollama.OllamaError as error:
                message = str(error)
                if "not found" in message:
                    message = f"Das Modell {model} ist nicht installiert. Im Bluey-Menü unter „KI-Modell“ herunterladen."
                self._send({"type": "error", "text": message})
                return ""
            if tools and not native:
                before, call = parse_text_tool(text)
                calls = [call] if call else []
                text = before
            text = text.strip()
            if text:
                final = text
            if not calls:
                break
            # Werkzeuge ausführen und die Ergebnisse zurückgeben.
            if native:
                messages.append({"role": "assistant", "content": text,
                                 "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
            else:
                messages.append({"role": "assistant", "content": (text + "\n" if text else "")
                                 + "TOOL " + json.dumps({"name": calls[0]["name"], "arguments": calls[0]["arguments"]}, ensure_ascii=False)})
            images = []
            for call in calls:
                name = call["name"]
                if name == "go_to_sleep":
                    sleep = True
                output, image = self.host.run_tool(name, call["arguments"])
                if name == "web_research" and "---REPORT---" in output:
                    self._send({"type": "report", "text": output.split("\n---REPORT---\n", 1)[1]})
                    output = output.split("\n---REPORT---\n", 1)[0]
                if image:
                    images.append(image)
                if native:
                    messages.append({"role": "tool", "content": output, "tool_name": name})
                else:
                    messages.append({"role": "user", "content": f"Ergebnis von {name}: {output}"})
            if images and vision:
                messages.append({"role": "user", "content": "Das Bildschirmfoto dazu.", "images": images[-1:]})
            if text:
                # Text vor einem Werkzeug (z. B. „ich recherchiere kurz…“) zählt als eigene kleine Antwort.
                self.host.ui.post(lambda v=text: self.host.caption(v, False))
        self._send({"type": "done", "text": final, "sleep": sleep})
        self.host.ui.post(lambda: self.host.caption(final, True))
        return final
