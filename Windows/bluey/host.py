"""Die PC-Hälfte der Live-Stimme.

Mit OpenAI: Das Handy führt die Realtime-Sitzung (Mikro); der PC gibt ihm einen Kurzzeit-Schlüssel, führt seine
Werkzeuge aus (schauen, zeigen, den Computer bedienen) und zeigt Sprechblasen.
Mit Ollama (Standard): Das Handy schickt nur Audio; der PC erkennt die Sprache, fragt die lokale KI und macht den Rest.
"""
import json
import math
import queue
import threading
import time
import traceback
import urllib.request

from . import computer, keys, meeting_notes, prompts, screen_reader, web_research
from .computer import Display
from .config import settings
from .cursor_engine import Mode

REPORT_MARKER = "\n---REPORT---\n"
ACTION_NAMES = {"click", "type_text", "press_keys", "scroll", "drag", "open_app", "open_url"}
LOCAL_TOKEN = "local:ollama"


class TokenError(Exception):
    pass


def mint_token():
    """Ein Kurzzeit-Schlüssel fürs Handy, damit der echte Schlüssel den PC nie verlässt."""
    key = keys.get("openai")
    if not key:
        raise TokenError("Für OpenAI brauche ich einen API-Schlüssel. Trag ihn im Bluey-Menü unter „OpenAI-Schlüssel…“ ein.")
    body = {"expires_after": {"anchor": "created_at", "seconds": 600}, "session": prompts.realtime_session()}
    request = urllib.request.Request("https://api.openai.com/v1/realtime/client_secrets", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["value"]
    except Exception as error:
        raise TokenError(f"OpenAI wollte keine Sprachsitzung starten: {str(error)[:160]}") from None


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class Host:
    """`ui` stellt post(fn) und call(fn) für den Qt-Hauptthread bereit; `overlay` ist das Cursor-Overlay."""

    def __init__(self, ui, overlay, reports, broadcast=lambda packet: None):
        self.ui, self.overlay, self.reports = ui, overlay, reports
        self.broadcast = broadcast
        self.snapshot = None
        self.awake = False
        self.on_change = lambda: None
        self._stopped_until = 0.0
        self._tools = queue.Queue()
        self._caption_clear = None
        self._reading_done = None
        threading.Thread(target=self._tool_loop, name="Bluey Werkzeuge", daemon=True).start()
        # Zeige-Choreografie (nur auf dem Hauptthread benutzt).
        self._queue = []
        self._hold_until = 0.0
        self._home_requested = False
        self._speaking = False
        self._quiet_since = 0.0
        self._choreographing = False
        overlay.frame_callbacks.append(self._choreograph)
        from .local_voice import LocalVoice
        self.local = LocalVoice(self)

    @property
    def engine(self):
        return self.overlay.engine

    # Anfragen vom Handy

    def handle(self, packet, reply, phone):
        command = packet.get("command")
        call_id = packet.get("callID")
        if command == "realtimeToken":
            def work():
                if settings.engine != "openai":
                    reply({"command": "realtimeToken", "callID": call_id, "text": LOCAL_TOKEN})
                    return
                try:
                    reply({"command": "realtimeToken", "callID": call_id, "text": mint_token()})
                except TokenError as error:
                    reply({"command": "realtimeToken", "callID": call_id, "text": None})
                    message = str(error)
                    self.ui.post(lambda: self.show_caption(message, 6))
            threading.Thread(target=work, daemon=True).start()
        elif command == "transcribe":
            threading.Thread(target=self._transcribe, args=(packet, reply), daemon=True).start()
        elif command == "notes":
            try:
                session = json.loads(packet.get("text") or "")
                path = meeting_notes.write(session) if isinstance(session, dict) else None
            except (ValueError, OSError):
                path = None
            reply({"command": "notes", "callID": call_id, "text": path})
        elif command == "awake":
            self.ui.post(lambda: self.set_awake(True))
        elif command == "asleep":
            self.ui.post(lambda: self.set_awake(False))
        elif command == "caption":
            text = (packet.get("text") or "").strip()
            self.ui.post(lambda: self.caption(text, False))
        elif command == "captionDone":
            text = packet.get("text") or ""
            self.ui.post(lambda: self.caption(text, True))
        elif command == "tool":
            self._tools.put((packet.get("tool") or "", packet.get("text") or "{}", call_id, reply))
        elif command == "voice":
            self.local.command(packet.get("text"), phone)
        elif command == "audio":
            self.local.audio(packet.get("audio"), phone)
        elif call_id:
            reply({"command": command, "callID": call_id, "text": None})

    def _transcribe(self, packet, reply):
        """Ein aufgenommenes Stück vom Handy: speichern, mit Sprechern transkribieren, Zeilen zurückschicken."""
        call_id = packet.get("callID")
        try:
            import base64
            meta = json.loads(packet.get("text") or "{}")
            audio = base64.b64decode(packet.get("audio") or "")
            segments, folder = meeting_notes.transcribe(audio, meta["session"], int(meta["index"]), float(meta["sessionStarted"]))
            body = {"segments": [{"speaker": s.speaker, "start": s.start, "text": s.text} for s in segments], "notesPath": folder}
            reply({"command": "transcribed", "callID": call_id, "text": json.dumps(body, ensure_ascii=False)})
        except Exception:
            traceback.print_exc()
            reply({"command": "transcribed", "callID": call_id, "text": None})

    def _tool_loop(self):
        # Werkzeuge laufen nacheinander, in der Reihenfolge, in der er sie wollte.
        while True:
            name, arguments, call_id, reply = self._tools.get()
            text, image = self.run_tool(name, arguments)
            reply({"command": "toolResult", "callID": call_id, "text": text, "image": image})

    # Zustand (Hauptthread)

    def set_awake(self, on):
        self.awake = on
        self.engine.awake = on
        self.engine.brain_mood = None
        self.engine.gaze_override = None  # seine Augen folgen deiner Maus, während er zuhört
        if not on:
            self._queue = []
            self._choreographing = False
            self.overlay.go_home()
            self.overlay.speech_target = None
            self.show_caption(None)
        self.on_change()

    def stop_actions(self):
        """Die Stopp-Taste: weitere Aktionen kurz verweigern und den Cursor heimholen."""
        self._stopped_until = time.monotonic() + 6
        self._queue = []
        self.engine.dragging = False
        self._go_home()
        self.overlay.bubble("Gestoppt", 1.6)

    def caption(self, text, finished):
        """Seine Antwort, während sie hereinströmt; fertig: lang genug zum Lesen stehen lassen, dann aufräumen."""
        if not finished:
            if self._reading_done:
                self._reading_done.cancel()
            self.show_caption(text or None)
            if text:
                self._set_speaking(True)
            return
        if text:
            self.show_caption(text)
        words = len(text.split())
        read_time = min(max(2.8, 1.2 + words * 0.32), 12) + 3
        if self._reading_done:
            self._reading_done.cancel()

        def done():
            self._set_speaking(False)
            self.show_caption(None)
        self._reading_done = self.ui.later(read_time, done)

    def show_caption(self, text, seconds=0):
        if self._caption_clear:
            self._caption_clear.cancel()
            self._caption_clear = None
        self.overlay.caption = text
        if text and seconds > 0:
            self._caption_clear = self.ui.later(seconds, lambda: setattr(self.overlay, "caption", None))

    # Werkzeuge (Werkzeug-Thread)

    def run_tool(self, name, arguments):
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
            if not isinstance(args, dict):
                args = {}
        except ValueError:
            args = {}
        try:
            if name in ACTION_NAMES:
                refusal = self._action_refusal()
                if refusal:
                    return refusal, None
                return self._run_action(name, args)
            if name == "look_at_screen":
                return self.look()
            if name == "point_at":
                target_id = str(args.get("target_id", "")).strip()
                if not self.snapshot:
                    return "Ruf zuerst look_at_screen auf.", None
                target = self.snapshot.target(target_id)
                if not target:
                    return f"Kein Ziel {target_id}. Nimm eine ID vom letzten look_at_screen.", None
                x, y, w, h = target.rect
                queued = self.ui.call(lambda: self._point((x + w / 2, y + h + 3), target.rect))
                return (f'In der Warteschlange: dein Cursor zeigt nach den früheren Stellen auf "{target.text}".' if queued > 1
                        else f'Zeige auf "{target.text}".'), None
            if name == "point_at_spot":
                x, y = number(args.get("x")), number(args.get("y"))
                if x is None or y is None:
                    return "Gib x und y an.", None
                spot = self._grid_point(x, y)
                self.ui.call(lambda: self._point(spot, (spot[0] - 16, spot[1] - 16, 32, 32)))
                return "Zeige dorthin.", None
            if name == "stop_pointing":
                self.ui.call(self._request_home)
                return "Dein Cursor fliegt heim, sobald du fertig geredet hast.", None
            if name == "web_research":
                return self._research(args)
            if name == "go_to_sleep":
                return "Schlafe ein. Sag ein ganz kurzes Tschüss.", None
            return f"Unbekanntes Werkzeug {name}.", None
        except Exception as error:
            traceback.print_exc()
            return f"Das Werkzeug ist fehlgeschlagen ({type(error).__name__}).", None

    def _research(self, args):
        question = str(args.get("question", "")).strip()
        if not question:
            return "Was soll ich recherchieren?", None
        self.ui.post(lambda: self.reports.show_loading(question))
        try:
            context = " / ".join(line.text for line, _ in (self.snapshot.lines[:40] if self.snapshot else []))
            report = web_research.research(question, context or None)
            self.ui.post(lambda: self.reports.show(report))
            return ("Der ganze Bericht ist jetzt als Karte auf dem Bildschirm des Nutzers. Antworte mit EINER kurzen Zeile: "
                    "die Kernaussage in deinen Worten. Wiederhol den Bericht nicht." + REPORT_MARKER + report.plain_text), None
        except Exception as error:
            message = str(error) or type(error).__name__
            self.ui.post(lambda: self.reports.show_error(f"Die Recherche kam nicht zurück: {message[:160]}"))
            return f"Die Recherche ist fehlgeschlagen: {message}. Sag es dem Nutzer in ein paar Worten.", None

    def look(self, prefix=None):
        try:
            shot = screen_reader.snapshot()
        except Exception:
            traceback.print_exc()
            problem = "Ich kann den Bildschirm gerade nicht sehen."
            return (prefix + " " + problem if prefix else problem), None
        self.snapshot = shot
        text = shot.target_list
        mouse = Display.to_logical(computer.mouse_location())
        mx = int(min(max(mouse[0] / shot.size[0], 0), 1) * 1000)
        my = int(min(max(mouse[1] / shot.size[1], 0), 1) * 1000)
        text += f"\nDer Mauszeiger des Nutzers ist bei @{mx},{my}"
        under = shot.target_near(mouse)
        if under:
            text += f', auf {under.id} "{under.text}"'
        text += ". Wenn er „das“, „dies“ oder „hier“ sagt, meint er, was an seinem Mauszeiger ist."
        if prefix:
            text = prefix + "\nSo sieht der Bildschirm jetzt aus (die IDs haben sich geändert):\n" + text
        return text, shot.jpeg_base64

    @property
    def screen_size(self):
        return self.snapshot.size if self.snapshot else Display.size

    def _grid_point(self, x, y):
        w, h = self.screen_size
        return (min(max(x, 0), 1000) / 1000 * w, min(max(y, 0), 1000) / 1000 * h)

    def _spot(self, args, id_key, x_key, y_key):
        """Die Stelle, die eine Aktion meint: Mitte eines Ziels (ID) oder eine Rasterposition."""
        target_id = args.get(id_key)
        if isinstance(target_id, str) and target_id and self.snapshot:
            target = self.snapshot.target(target_id)
            if target:
                return target.mid, target.text
        x, y = number(args.get(x_key)), number(args.get(y_key))
        if x is not None and y is not None:
            return self._grid_point(x, y), "die Stelle"
        return None

    # Den Computer bedienen

    def _action_refusal(self):
        if not settings.computer_control:
            return "Der Nutzer hat die Computersteuerung im Menü ausgeschaltet. Schauen und zeigen geht trotzdem."
        if time.monotonic() < self._stopped_until:
            return "Der Nutzer hat Stopp gedrückt. Tu nichts mehr, bis er wieder fragt."
        return None

    def _confirm(self, name, args):
        if not settings.confirm_actions:
            return True
        return self.ui.call(lambda: self.overlay.confirm(name, args))

    def _run_action(self, name, args):
        if not self._confirm(name, args):
            return "Der Nutzer hat die Aktion abgelehnt.", None
        self.ui.call(self._take_control)
        try:
            return self._action(name, args)
        finally:
            self.ui.call(self._after_action)

    def _fly(self, point):
        """Fliegt den Cursor zu einer Stelle und wartet, bis er gelandet ist."""
        self.ui.call(lambda: self.overlay.set_mode(Mode.pinned(*point)))
        time.sleep(0.05)  # der nächste Frame plant die Reise
        wait = self.ui.call(lambda: self.engine.time_to_arrive(time.monotonic()))
        if wait > 0:
            time.sleep(wait + 0.05)

    def _dock_if_home(self):
        self.ui.call(lambda: self.overlay.set_mode(Mode.DOCKED) if self.engine.is_home else None)

    def _action(self, name, args):
        if name == "click":
            spot = self._spot(args, "target_id", "x", "y")
            if not spot:
                return "Sag mir, was ich anklicken soll: eine Ziel-ID aus look_at_screen, oder x und y.", None
            point, label = spot
            right = bool(args.get("right"))
            count = 2 if args.get("double") else 1
            saved = computer.mouse_location()
            self._fly(point)
            self.ui.call(lambda: self.overlay.click_effect(point, right))
            time.sleep(0.09)  # der Klick landet unten in der Quetschung
            computer.click(Display.to_physical(point), right, count)
            time.sleep(0.06)
            computer.warp(saved)  # deinen Zeiger dahin zurück, wo du ihn gelassen hast
            time.sleep(0.38)
            verb = "Rechtsklick auf" if right else "Doppelklick auf" if count == 2 else "Geklickt auf"
            return self.look(f'{verb} {"die Stelle" if label == "die Stelle" else chr(34) + label + chr(34)}.')

        if name == "type_text":
            text = args.get("text")
            if not isinstance(text, str) or not text:
                return "Nichts zu tippen.", None
            frame, secure = screen_reader.focused_field()
            if secure:
                return "Das ist ein Passwortfeld. Bitte den Nutzer, es selbst einzutippen.", None
            w, h = self.screen_size
            if frame and frame[0] < w and frame[1] < h and frame[0] + frame[2] > 0 and frame[1] + frame[3] > 0 and frame[3] < h * 0.6:
                self._fly((frame[0] + min(28, frame[2] * 0.2), frame[1] + frame[3] + 2))
            else:
                self._dock_if_home()
            stopped = lambda: time.monotonic() < self._stopped_until or not settings.computer_control
            computer.type_text(text, lambda chunk: self.ui.post(lambda: self.overlay.typed_effect(chunk)), stopped)
            if stopped():
                return "Beim Tippen gestoppt.", None
            if args.get("press_return"):
                time.sleep(0.12)
                computer.press("enter")
                self.ui.post(lambda: self.overlay.bubble("↵"))
                time.sleep(0.55)
                return self.look("Getippt und Enter gedrückt.")
            return "Getippt.", None

        if name == "press_keys":
            combo = str(args.get("keys", "")).strip()
            self._dock_if_home()
            try:
                label = computer.press(combo)
            except computer.ControlError as error:
                return str(error), None
            self.ui.post(lambda: self.overlay.bubble(label))
            time.sleep(0.38)
            return self.look(f"{combo} gedrückt.")

        if name == "scroll":
            direction = str(args.get("direction", "down")).lower()
            amount = min(max(number(args.get("amount")) or 3, 1), 10)
            spot = self._spot(args, "target_id", "x", "y")
            point = spot[0] if spot else (self.screen_size[0] / 2, self.screen_size[1] / 2)
            pixels = int(amount * 120)
            dx, dy, arrow = {"up": (0, -pixels, "↑"), "left": (-pixels, 0, "←"),
                             "right": (pixels, 0, "→")}.get(direction, (0, pixels, "↓"))
            saved = computer.mouse_location()
            self._fly(point)
            self.ui.post(lambda: self.overlay.bubble(arrow))
            computer.scroll(dx, dy, Display.to_physical(point))
            computer.warp(saved)
            time.sleep(0.28)
            return self.look(f"Nach {dict(up='oben', down='unten', left='links', right='rechts').get(direction, 'unten')} gescrollt.")

        if name == "drag":
            start = self._spot(args, "from_id", "from_x", "from_y")
            end = self._spot(args, "to_id", "to_x", "to_y")
            if not start or not end:
                return "Sag mir, von wo nach wo ich ziehen soll (IDs oder x und y).", None
            saved = computer.mouse_location()
            self._fly(start[0])
            self.ui.call(lambda: self.engine.press(0.1))
            computer.drag_begin(Display.to_physical(start[0]))
            time.sleep(0.12)

            def begin():
                self.engine.dragging = True
                self.overlay.set_mode(Mode.pinned(*end[0]))
            self.ui.call(begin)
            time.sleep(0.04)
            # Das echte Ziehen folgt dem animierten Cursor: Was du siehst, passiert auch.
            while self.ui.call(lambda: self.engine.time_to_arrive(time.monotonic())) > 0:
                computer.drag_move(Display.to_physical(self.ui.call(lambda: self.engine.tip)))
                time.sleep(0.016)
            computer.drag_move(Display.to_physical(end[0]))
            time.sleep(0.08)
            computer.drag_end(Display.to_physical(end[0]))
            self.ui.call(lambda: setattr(self.engine, "dragging", False))
            time.sleep(0.06)
            computer.warp(saved)
            time.sleep(0.28)
            return self.look("Gezogen.")

        if name == "open_app":
            app = str(args.get("name", "")).strip()
            if not app:
                return "Welche App?", None
            self._dock_if_home()
            self.ui.post(lambda: self.overlay.bubble(f"Öffne {app}"))
            result = computer.open_app(app)
            time.sleep(1.2)
            return self.look(result)

        if name == "open_url":
            url = str(args.get("url", "")).strip()
            self._dock_if_home()
            result = computer.open_url(url)
            self.ui.post(lambda: self.overlay.bubble(result.removesuffix(" geöffnet.") if result.endswith(" geöffnet.") else "Hmm"))
            time.sleep(1.1)
            return self.look(result)

        return f"Unbekannte Aktion {name}.", None

    # Zeige-Choreografie (Hauptthread)
    #
    # Oft will er auf mehrere Dinge auf einmal zeigen. Jede Stelle bekommt ihren eigenen Flug und genug Zeit, um
    # darüber zu reden, und der Cursor fliegt erst heim, wenn er fertig geredet hat.

    MINIMUM_HOLD = 2.2
    IDLE_HOME = 5.0

    def _take_control(self):
        """Aktionen übernehmen den Cursor: geplantes Zeigen fällt weg."""
        self._queue = []
        self._hold_until = 0.0
        self._home_requested = False
        self.engine.gaze_override = None
        self.overlay.speech_target = None

    def _after_action(self):
        t = time.monotonic()
        self._hold_until = t + 1.5
        if not self._speaking:
            self._quiet_since = t
        self._choreographing = True

    def _point(self, spot, thing):
        self._queue.append((spot, thing))
        self._home_requested = False
        self._choreographing = True
        return len(self._queue)

    def _request_home(self):
        self._home_requested = True
        self._choreographing = True

    def _choreograph(self, t):
        if not self._choreographing:
            return
        if t >= self._hold_until and self._queue:
            spot, thing = self._queue.pop(0)
            self.overlay.speech_target = thing
            if not self._speaking:
                self._quiet_since = t  # Zeit lassen, um darüber zu reden
            self.engine.gaze_override = None
            self.overlay.set_mode(Mode.pinned(*spot))
            self._hold_until = t + 1.0 + self.MINIMUM_HOLD
            return
        if self._queue or t < self._hold_until:
            return
        if self.overlay.mode == self.overlay.idle_mode:
            self._choreographing = False
            return
        quiet_for = 0 if self._speaking else t - self._quiet_since
        if (self._home_requested and quiet_for > 1.2) or quiet_for > self.IDLE_HOME:
            self._go_home()

    def _go_home(self):
        self.overlay.go_home()
        self.engine.gaze_override = None
        self.overlay.speech_target = None
        self._home_requested = False
        self._choreographing = False

    def _set_speaking(self, on):
        if self._speaking and not on:
            self._quiet_since = time.monotonic()
        self._speaking = on
