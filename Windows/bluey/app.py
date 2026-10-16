"""Bluey für Windows: Symbol im Infobereich (Tray) mit Menü, Tastenkürzel, Cursor-Overlay und Handy-Verbindung.

Start: `python -m bluey` (aus dem Ordner Windows) oder Bluey.exe.
"""
import os
import sys
import threading
import time
import traceback

from .config import APP_NAME, data_dir, settings


def _log_to_file():
    """Ohne Konsole (als .exe) landen Meldungen in %APPDATA%\\Bluey\\bluey.log."""
    if sys.stdout is None or getattr(sys, "frozen", False):
        try:
            log = open(os.path.join(data_dir(), "bluey.log"), "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = log
            print(f"\n--- Bluey gestartet {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        except OSError:
            pass


def _single_instance():
    if sys.platform != "win32":
        return True
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BlueyDesktopApp")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def selftest():
    """Für die automatische Prüfung der .exe: alles Wichtige laden und mit 0 beenden."""
    import importlib
    failed = []
    for name in ("PySide6.QtWidgets", "zeroconf", "mss", "PIL.Image", "numpy", "faster_whisper", "ctranslate2",
                 "bluey.overlay", "bluey.host", "bluey.local_voice", "bluey.report_panel"):
        try:
            importlib.import_module(name)
        except Exception as error:
            failed.append(f"{name}: {error}")
    if sys.platform == "win32":
        for name in ("keyring", "uiautomation", "winrt.windows.media.ocr", "winrt.windows.graphics.imaging",
                     "winrt.windows.storage.streams"):
            try:
                importlib.import_module(name)
            except Exception as error:
                failed.append(f"{name}: {error}")
    with open(os.path.join(data_dir(), "selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(failed) or "OK")
    sys.exit(1 if failed else 0)


def main():
    if "--selftest" in sys.argv:
        selftest()
    _log_to_file()
    from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal, Slot
    from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFontDatabase, QGuiApplication, QIcon,
                               QLinearGradient, QPainter, QPixmap)
    from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QInputDialog, QLabel, QLineEdit, QMenu,
                                   QMessageBox, QPlainTextEdit, QProgressDialog, QSystemTrayIcon, QVBoxLayout)

    from . import computer, keys, meeting_notes, ollama, prompts, stt
    from .computer import Display
    from .cursor_engine import TRAILS, Mode
    from .hotkeys import HotKeys
    from .host import Host
    from .overlay import Overlay
    from .phone_mouse import PhoneMouse, zone
    from .palette import GRADIENT, INK, color
    from .report_panel import ReportPanel
    from .server import PhoneServer, lan_addresses
    from .settings_window import SettingsWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if not _single_instance():
        QMessageBox.information(None, "Bluey", "Bluey läuft schon. Du findest ihn unten rechts im Infobereich (Tray).")
        return

    fonts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
    if os.path.isdir(fonts):
        for name in os.listdir(fonts):
            if name.endswith(".ttf"):
                QFontDatabase.addApplicationFont(os.path.join(fonts, name))

    screen = QGuiApplication.primaryScreen()

    def update_display():
        geometry = screen.geometry()
        Display.scale = screen.devicePixelRatio()
        Display.origin = (geometry.x() * Display.scale, geometry.y() * Display.scale)
        Display.size = (float(geometry.width()), float(geometry.height()))
    update_display()
    screen.geometryChanged.connect(lambda _: update_display())

    class Bridge(QObject):
        """Bringt Aufrufe aus anderen Threads auf den Qt-Hauptthread."""
        run = Signal(object)

        def __init__(self):
            super().__init__()
            self.run.connect(self._run, Qt.QueuedConnection)
            self.main = threading.current_thread()

        @Slot(object)
        def _run(self, fn):
            try:
                fn()
            except Exception:
                traceback.print_exc()

        def post(self, fn):
            self.run.emit(fn)

        def call(self, fn):
            if threading.current_thread() is self.main:
                return fn()
            done, result = threading.Event(), {}

            def wrapped():
                try:
                    result["value"] = fn()
                finally:
                    done.set()
            self.run.emit(wrapped)
            done.wait(60)
            return result.get("value")

        def later(self, seconds, fn):
            class Handle:
                cancelled = False

                def cancel(self):
                    self.cancelled = True
            handle = Handle()

            def fire():
                if not handle.cancelled:
                    fn()
            self.post(lambda: QTimer.singleShot(int(seconds * 1000), fire))
            return handle

    ui = Bridge()
    overlay = Overlay()
    reports = ReportPanel()
    server = PhoneServer(port=settings.port)
    host = Host(ui, overlay, reports, broadcast=server.broadcast)
    overlay.on_face = server.send_face

    # Maus aufs Handy: unten am Rand, wo das Handy steht, hinausschieben.
    phone_mouse = PhoneMouse(server.broadcast)
    phone_mouse.connected = lambda: bool(server.phone_names)

    def phone_mouse_changed(active):
        if active:
            # Den echten Zeiger knapp über dem Rand parken; seine Bewegungen gehen jetzt ans Handy.
            pos = QCursor.pos() - overlay.geometry().topLeft()
            park = (pos.x(), overlay.height() - 40)
            phone_mouse.scale = Display.scale
            phone_mouse.anchor = Display.to_physical(park)
            computer.warp(phone_mouse.anchor)
            overlay.phone_mouse_label = (park[0], overlay.height() - 76)
        else:
            overlay.phone_mouse_label = None
    phone_mouse.on_change = phone_mouse_changed

    def phone_mouse_frame(t):
        pos = QCursor.pos() - overlay.geometry().topLeft()
        bounds = (float(overlay.width()), float(overlay.height()))
        phone_mouse.check((float(pos.x()), float(pos.y())), bounds, t)
        phone_mouse.flush()
        if phone_mouse.near > 0.01 and not phone_mouse.active:
            left, right = zone(bounds)
            overlay.door = (left, right, phone_mouse.near)
        else:
            overlay.door = None
    overlay.frame_callbacks.append(phone_mouse_frame)

    # Symbol im Infobereich: die kleine Blaubeere mit Augen.

    def make_icon(dim=False):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        if dim:
            p.setOpacity(0.55)
        gradient = QLinearGradient(16, 6, 48, 60)
        for c, stop in zip(GRADIENT, [0, .34, .68, 1]):
            gradient.setColorAt(stop, color(c))
        p.setPen(Qt.NoPen)
        p.setBrush(gradient)
        p.drawEllipse(QRectF(3, 8, 58, 48))
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(15, 20, 15, 15))
        p.drawEllipse(QRectF(34, 20, 15, 15))
        p.setBrush(color(INK))
        p.drawEllipse(QRectF(19, 23, 8, 8))
        p.drawEllipse(QRectF(38, 23, 8, 8))
        p.end()
        return QIcon(pixmap)

    icon_on, icon_off = make_icon(False), make_icon(True)
    tray = QSystemTrayIcon(icon_off)
    tray.setToolTip("Bluey")
    menu = QMenu()
    tray.setContextMenu(menu)
    app.setWindowIcon(icon_on)

    def address():
        ips = lan_addresses()
        return f"{ips[0]}:{server.port}" if ips else f"Port {server.port}"

    def refresh_icon():
        tray.setIcon(icon_on if server.phone_names else icon_off)
        tray.setToolTip("Bluey – " + (("verbunden: " + ", ".join(server.phone_names)) if server.phone_names
                                      else "wartet aufs Handy (" + address() + ")"))

    def phones_changed(names):
        def update():
            refresh_icon()
            if not names and host.awake:
                host.set_awake(False)
            if not names and phone_mouse.active:
                phone_mouse._leave()
        ui.post(update)

    server.on_phones_changed = phones_changed
    server.on_request = host.handle
    host.on_change = lambda: refresh_icon()

    # Aktionen

    def point_here():
        pos = QCursor.pos() - overlay.geometry().topLeft()
        overlay.set_mode(Mode.pinned(pos.x(), pos.y()))

    def toggle_follow():
        settings.follow_mouse = not settings.follow_mouse
        overlay.go_home()

    def toggle_awake():
        server.broadcast({"command": "sleep" if host.awake else "wake"})

    def restart_if_awake():
        """Weckt ihn neu, damit eine neue Persönlichkeit oder neue Werkzeuge gleich wirken."""
        if not host.awake:
            return
        server.broadcast({"command": "sleep"})
        QTimer.singleShot(1000, lambda: server.broadcast({"command": "wake"}))

    def toggle_control():
        settings.computer_control = not settings.computer_control
        restart_if_awake()

    def open_notes():
        os.makedirs(meeting_notes.root(), exist_ok=True)
        if sys.platform == "win32":
            os.startfile(meeting_notes.root())

    def edit_personality():
        dialog = QDialog()
        dialog.setWindowTitle("Seine Persönlichkeit")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Beschreib, wer er ist und wie er redet. Wie er auf deinen Bildschirm schaut und zeigt, bleibt eingebaut."))
        text = QPlainTextEdit(prompts.personality())
        text.setMinimumSize(520, 240)
        layout.addWidget(text)
        buttons = QDialogButtonBox()
        save = buttons.addButton("Speichern", QDialogButtonBox.AcceptRole)
        buttons.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        reset = buttons.addButton("Standard wiederherstellen", QDialogButtonBox.ResetRole)
        layout.addWidget(buttons)
        choice = {}
        save.clicked.connect(lambda: (choice.update(v="save"), dialog.accept()))
        reset.clicked.connect(lambda: (choice.update(v="reset"), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        if dialog.exec() != QDialog.Accepted:
            return
        settings.personality = text.toPlainText().strip() if choice.get("v") == "save" else ""
        restart_if_awake()

    def edit_key():
        current = keys.get("openai")
        value, ok = QInputDialog.getText(None, "OpenAI-API-Schlüssel (optional)",
                                         "Nur nötig für die KI „OpenAI Realtime“. Gespeichert in der Windows-Anmeldeinformationsverwaltung.\n"
                                         "Das Handy bekommt nur kurzlebige Schlüssel. Leer lassen und OK, um den Schlüssel zu löschen.",
                                         QLineEdit.Password, "")
        if not ok:
            return
        if value.strip() or (current and QMessageBox.question(None, "Bluey", "Gespeicherten Schlüssel löschen?") == QMessageBox.Yes):
            keys.set("openai", value.strip())

    def set_engine(engine):
        if engine == "openai" and not keys.get("openai"):
            edit_key()
            if not keys.get("openai"):
                return
        settings.engine = engine
        restart_if_awake()

    def set_model(name):
        settings.ollama_model = name
        restart_if_awake()

    def download_model(name=None):
        if not name:
            name, ok = QInputDialog.getText(None, "Modell herunterladen",
                                            "Name des Ollama-Modells (Empfehlung für 6 GB Grafikspeicher: gemma3:4b – sieht auch Bilder;\n"
                                            "Alternativen: qwen2.5vl:3b, qwen3:4b, llama3.2:3b):", QLineEdit.Normal, settings.ollama_model)
            if not ok or not name.strip():
                return
            name = name.strip()
        progress = QProgressDialog(f"Lade {name} …", "Im Hintergrund", 0, 100)
        progress.setWindowTitle("Bluey – Modell herunterladen")
        progress.setWindowFlags(progress.windowFlags() | Qt.WindowStaysOnTopHint)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        state = {"text": "", "value": 0, "done": None}

        def work():
            try:
                ollama.pull(name, lambda text, part: state.update(text=text, value=int((part or 0) * 100)))
                state["done"] = "ok"
            except Exception as error:
                state["done"] = str(error)
        threading.Thread(target=work, daemon=True).start()
        timer = QTimer(progress)

        def poll():
            progress.setLabelText(f"{name}: {state['text']}")
            progress.setValue(state["value"])
            if state["done"]:
                timer.stop()
                progress.close()
                if state["done"] == "ok":
                    settings.ollama_model = name
                    settings.engine = "ollama"
                    window.refresh()
                    tray.showMessage("Bluey", f"{name} ist bereit.", QSystemTrayIcon.Information, 4000)
                else:
                    QMessageBox.warning(None, "Bluey", f"Download fehlgeschlagen: {state['done']}")
        timer.timeout.connect(poll)
        timer.start(300)
        progress.show()

    def stop_actions():
        host.stop_actions()
        if phone_mouse.active:
            phone_mouse._leave()

    def set_setting(name, value):
        setattr(settings, name, value)

    def show_info():
        ips = lan_addresses()
        box = QMessageBox()
        box.setWindowTitle("Bluey")
        box.setIcon(QMessageBox.Information)
        box.setText("Bluey läuft im Infobereich (unten rechts, ggf. hinter dem Pfeil ^).")
        engine = (f"Ollama, Modell {settings.ollama_model}" + ("" if ollama.running() else " – Ollama läuft gerade NICHT")
                  if settings.engine == "ollama" else "OpenAI Realtime")
        box.setInformativeText(
            "Öffne die Bluey-App auf dem Handy im selben WLAN, dann findet sie den PC von selbst.\n\n"
            f"Falls nicht, gib im Handy diese Adresse ein: {', '.join(f'{ip}:{server.port}' for ip in ips) or server.port}\n\n"
            f"KI: {engine}\nSpracherkennung: {stt.status or 'Whisper ' + settings.whisper_model}\n\n"
            "Erlaube Bluey in der Windows-Firewall für private Netzwerke. Die Verbindung ist unverschlüsselt: nur in "
            "vertrauenswürdigen WLANs nutzen.")
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        box.exec()

    window = SettingsWindow({
        "download_model": download_model, "edit_personality": edit_personality, "edit_key": edit_key,
        "open_notes": open_notes, "quit": app.quit, "address": address, "phones": lambda: server.phone_names,
        "set_engine": set_engine, "restart": restart_if_awake, "open_url": computer.open_url,
    }, icon_on)

    # Menü (wird bei jedem Öffnen neu gebaut, wie beim Mac)

    def add(parent, title, action=None, checked=None, shortcut=None, enabled=True):
        item = QAction(title + (f"\t{shortcut}" if shortcut else ""), parent)
        if checked is not None:
            item.setCheckable(True)
            item.setChecked(bool(checked))
        item.setEnabled(bool(enabled))
        if action:
            item.triggered.connect(lambda _=False: action())
        parent.addAction(item)
        return item

    def choices(parent, title, options, current, setter):
        sub = parent.addMenu(title)
        group = QActionGroup(sub)
        for label, value in options:
            item = add(sub, label, lambda v=value: setter(v), checked=current == value)
            group.addAction(item)
        return sub

    def build_menu():
        menu.clear()
        phones = server.phone_names
        add(menu, ("Handy verbunden: " + ", ".join(phones)) if phones else "Warte auf die Handy-App …", enabled=False)
        add(menu, "Einstellungen und KI-Modell …", window.open)
        add(menu, f"Adresse fürs Handy: {address()}", show_info)
        add(menu, "Schlafen legen (Folgemodus)" if host.awake else "Aufwecken und reden", toggle_awake,
            shortcut="Strg+Alt+Leertaste", enabled=bool(phones))
        menu.addSeparator()
        add(menu, "Er darf den Computer benutzen", toggle_control, checked=settings.computer_control)
        add(menu, "Vor jeder Aktion fragen", lambda: set_setting("confirm_actions", not settings.confirm_actions),
            checked=settings.confirm_actions, enabled=settings.computer_control)
        add(menu, "Stopp", stop_actions, shortcut="Strg+Alt+S")
        add(menu, "Maus aufs Handy (unten am Rand hinausschieben)",
            lambda: set_setting("phone_mouse", not settings.phone_mouse), checked=settings.phone_mouse)
        menu.addSeparator()
        add(menu, "Hier zeigen", point_here, shortcut="Strg+Alt+P")
        add(menu, "Augen folgen meiner Maus", toggle_follow, checked=settings.follow_mouse, shortcut="Strg+Alt+F")
        add(menu, "Zeigen beenden", overlay.go_home, shortcut="Strg+Alt+D")
        add(menu, "Sprechtest", overlay.talk_test, shortcut="Strg+Alt+T")
        menu.addSeparator()

        ai = menu.addMenu("KI")
        running = bool(ollama.running())
        group = QActionGroup(ai)
        group.addAction(add(ai, "Ollama (lokal auf dem PC, kostenlos)", lambda: set_engine("ollama"), checked=settings.engine == "ollama"))
        group.addAction(add(ai, "OpenAI Realtime (API-Schlüssel nötig)", lambda: set_engine("openai"), checked=settings.engine == "openai"))
        ai.addSeparator()
        add(ai, "Ollama läuft" if running else "Ollama läuft nicht – ollama.com installieren/starten", enabled=False)
        models = ollama.models() if running else []
        model_menu = ai.addMenu(f"Modell: {settings.ollama_model}")
        model_group = QActionGroup(model_menu)
        for name in models or [settings.ollama_model]:
            model_group.addAction(add(model_menu, name, lambda n=name: set_model(n), checked=name == settings.ollama_model))
        model_menu.addSeparator()
        add(model_menu, "Modell herunterladen …", download_model, enabled=running)
        speech = ai.addMenu("Spracherkennung (Whisper)")
        choices(speech, "Modell", [("base (schnell, ~140 MB)", "base"), ("small (empfohlen, ~460 MB)", "small"),
                                   ("medium (genauer, ~1,5 GB)", "medium")], settings.whisper_model,
                lambda v: set_setting("whisper_model", v))
        choices(speech, "Gerät", [("Automatisch", "auto"), ("Grafikkarte (CUDA)", "cuda"), ("Prozessor", "cpu")],
                settings.whisper_device, lambda v: set_setting("whisper_device", v))
        choices(speech, "Sprache", [("Deutsch", "de"), ("Automatisch erkennen", "auto")], settings.whisper_language,
                lambda v: set_setting("whisper_language", v))
        if stt.status:
            add(speech, stt.status, enabled=False)

        moods = [("Hört zu", "listening"), ("Ruht", "resting"), ("Denkt nach", "thinking"), ("Fröhlich", "happy")]
        choices(menu, "Stimmung", moods, settings.mood, lambda v: set_setting("mood", v))
        choices(menu, "Cursorgröße", [("Klein (48 pt)", 48), ("Mittel (72 pt)", 72), ("Groß (96 pt)", 96), ("Riesig (120 pt)", 120)],
                int(settings.cursor_size), lambda v: set_setting("cursor_size", v))
        choices(menu, "Handy steht unter", [("Links", 0.2), ("Mitte", 0.5), ("Rechts", 0.8)],
                round(settings.phone_position, 2), lambda v: set_setting("phone_position", v))
        add(menu, "Meeting-Notizen öffnen", open_notes)
        add(menu, "Persönlichkeit …", edit_personality)
        add(menu, "OpenAI-Schlüssel (optional) …", edit_key)
        menu.addSeparator()
        choices(menu, "Zeigerschweif", [(title, value) for value, title in TRAILS], settings.trail,
                lambda v: set_setting("trail", v))
        add(menu, "Cursor-Leuchten", lambda: set_setting("glow", not settings.glow), checked=settings.glow)
        add(menu, "Cursor zeigen", lambda: set_setting("show_cursor", not settings.show_cursor),
            checked=settings.show_cursor, shortcut="Strg+Alt+H")
        menu.addSeparator()
        add(menu, "Bluey beenden", app.quit)

    menu.aboutToShow.connect(build_menu)
    build_menu()
    if os.environ.get("BLUEY_MENU_TEST"):
        print("MENU OK", len(menu.actions()), flush=True)
    # Klick auf die Beere öffnet das Einstellungsfenster (Rechtsklick: Menü).
    tray.activated.connect(lambda reason: window.open() if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)

    # Tastenkürzel: Strg+Alt + Taste (Strg+Alt+Leertaste weckt ihn, wie Doppeltippen auf dem Handy).
    hotkeys = HotKeys(ui.post)
    hotkeys.register(0x20, toggle_awake)
    hotkeys.register("P", point_here)
    hotkeys.register("F", toggle_follow)
    hotkeys.register("D", overlay.go_home)
    hotkeys.register("H", lambda: set_setting("show_cursor", not settings.show_cursor))
    hotkeys.register("T", overlay.talk_test)
    hotkeys.register("S", stop_actions)  # Strg+Alt+S hält ihn sofort auf
    hotkeys.start()
    phone_mouse.start_hook(ui.post, lambda point: computer.warp(Display.to_physical(point)))

    def on_setting(name):
        if name == "follow_mouse":
            ui.post(overlay.go_home)
    settings.listeners.append(on_setting)

    server.start()
    overlay.start()
    tray.show()
    refresh_icon()
    app.aboutToQuit.connect(server.stop)

    def first_checks():
        if not settings.welcome_done:
            settings.welcome_done = True
            window.open()
        tray.showMessage("Bluey läuft", f"Öffne Bluey auf dem Handy (gleiches WLAN). Adresse: {address()}",
                         QSystemTrayIcon.Information, 6000)
        if settings.engine != "ollama":
            return
        if not ollama.running():
            box = QMessageBox()
            box.setWindowTitle("Bluey braucht Ollama")
            box.setText("Die KI läuft lokal mit Ollama, aber Ollama läuft gerade nicht.")
            box.setInformativeText("Installiere Ollama von https://ollama.com (kostenlos) und starte es. Bluey findet es "
                                   "dann automatisch. Alternativ: im Menü unter „KI“ OpenAI mit eigenem Schlüssel wählen.")
            open_site = box.addButton("ollama.com öffnen", QMessageBox.AcceptRole)
            box.addButton("Später", QMessageBox.RejectRole)
            box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
            box.exec()
            if box.clickedButton() is open_site:
                computer.open_url("https://ollama.com/download")
            return
        if settings.ollama_model not in ollama.models():
            answer = QMessageBox.question(None, "Bluey", f"Das KI-Modell {settings.ollama_model} ist noch nicht da "
                                          "(etwa 3,3 GB). Jetzt herunterladen?")
            if answer == QMessageBox.Yes:
                download_model(settings.ollama_model)
        stt.preload()

    QTimer.singleShot(800, first_checks)
    if os.environ.get("BLUEY_QUIT_AFTER"):  # für den automatischen Starttest
        QTimer.singleShot(int(float(os.environ["BLUEY_QUIT_AFTER"]) * 1000), app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
