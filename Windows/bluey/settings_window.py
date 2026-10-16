"""Das Einstellungsfenster: öffnet sich mit Klick auf die Beere im Infobereich.

Hier wählst du die KI (Ollama oder OpenAI), das Modell, die Spracherkennung und alles andere aus dem Menü.
"""
import sys
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from . import diagnostics, hardware, ollama, stt
from .config import settings


STYLE = """
QWidget#root { background: #17151F; }
QLabel { color: #E8E4F2; font-family: 'IBM Plex Sans'; font-size: 13px; }
QLabel[role="title"] { color: #FFFFFF; font-family: Fredoka; font-size: 26px; font-weight: 700; }
QLabel[role="section"] { color: #A9BCFF; font-family: 'IBM Plex Mono'; font-size: 11px; letter-spacing: 1px; }
QLabel[role="soft"] { color: #B9B2CC; font-size: 12px; }
QLabel[role="ok"] { color: #5BE49B; font-size: 12px; }
QLabel[role="bad"] { color: #FF9AA8; font-size: 12px; }
QFrame[role="card"] { background: #1E1B29; border-radius: 14px; }
QComboBox, QPushButton { font-family: 'IBM Plex Sans'; font-size: 13px; color: white; background: #2B2840;
    border: 1px solid #3A3654; border-radius: 9px; padding: 6px 10px; }
QComboBox QAbstractItemView { background: #2B2840; color: white; selection-background-color: #4254D6; }
QPushButton:hover, QComboBox:hover { border-color: #6C86F5; }
QPushButton[role="primary"] { background: #4254D6; border-color: #6C86F5; font-weight: 600; }
QPushButton:disabled { color: #8A85A0; }
QLineEdit { font-family: 'IBM Plex Sans'; font-size: 13px; color: white; background: #2B2840;
    border: 1px solid #3A3654; border-radius: 9px; padding: 7px 10px; }
QCheckBox, QRadioButton { color: #E8E4F2; font-family: 'IBM Plex Sans'; font-size: 13px; spacing: 8px; }
QScrollArea { border: none; background: transparent; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 8px; border: 2px solid #6C86F5; background: #17151F; }
QRadioButton::indicator:checked { background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 #A9BCFF, stop:0.55 #A9BCFF, stop:0.6 #17151F, stop:1 #17151F); }
"""


def _label(text, role=None):
    label = QLabel(text)
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    return label


def _card():
    frame = QFrame()
    frame.setProperty("role", "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(9)
    return frame, layout


class SettingsWindow(QWidget):
    _from_thread = Signal(object)

    def __init__(self, actions, icon=None):
        """`actions`: download_model(name), edit_personality(), edit_key(), open_notes(), quit(), address(),
        phones(), set_engine(name), restart()"""
        super().__init__(None, Qt.Window)
        self.actions = actions
        self.setWindowTitle("Bluey – Einstellungen")
        if icon:
            self.setWindowIcon(icon)
        self.setObjectName("root")
        self.setStyleSheet(STYLE)
        self.resize(560, 760)
        self._updating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("root")
        scroll.setWidget(body)
        main = QVBoxLayout(body)
        main.setContentsMargins(22, 20, 22, 22)
        main.setSpacing(14)

        main.addWidget(_label("Bluey", "title"))
        self.status = _label("", "soft")
        main.addWidget(self.status)
        self._from_thread.connect(lambda fn: fn())

        # Testen
        card, box = _card()
        box.addWidget(_label("TESTEN", "section"))
        row = QHBoxLayout()
        self.test_button = QPushButton("Verbindung und KI testen")
        self.test_button.setProperty("role", "primary")
        self.test_button.clicked.connect(self.run_test)
        row.addWidget(self.test_button)
        row.addStretch(1)
        box.addLayout(row)
        self.test_results = _label("Prüft Handy-Verbindung, Ollama, Modell, Spracherkennung und Bildschirm.", "soft")
        self.test_results.setTextFormat(Qt.RichText)
        box.addWidget(self.test_results)
        box.addWidget(_label("Frag Bluey direkt (wie übers Handy, mit Zeigen und PC-Bedienung):", "soft"))
        row = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText("z. B. Was ist die Hauptstadt von Australien?  oder  Öffne den Editor")
        self.question.returnPressed.connect(self.ask)
        row.addWidget(self.question, 1)
        self.ask_button = QPushButton("Fragen")
        self.ask_button.clicked.connect(self.ask)
        row.addWidget(self.ask_button)
        box.addLayout(row)
        self.answer = _label("", None)
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.answer)
        main.addWidget(card)
        if "on_answer" in actions:
            actions["on_answer"](lambda q, a: self._from_thread.emit(lambda: self._show_answer(q, a)))

        # KI
        card, box = _card()
        box.addWidget(_label("KI", "section"))
        self.use_ollama = QRadioButton("Ollama – lokal auf deinem PC, kostenlos")
        self.use_openai = QRadioButton("OpenAI Realtime – braucht einen API-Schlüssel")
        self.use_ollama.toggled.connect(lambda on: on and self._set_engine("ollama"))
        self.use_openai.toggled.connect(lambda on: on and self._set_engine("openai"))
        box.addWidget(self.use_ollama)
        box.addWidget(self.use_openai)
        self.ollama_state = _label("")
        box.addWidget(self.ollama_state)
        row = QHBoxLayout()
        row.addWidget(_label("Modell:"))
        self.model = QComboBox()
        self.model.setMinimumWidth(220)
        self.model.currentIndexChanged.connect(self._model_chosen)
        row.addWidget(self.model, 1)
        refresh = QPushButton("↻")
        refresh.setToolTip("Liste neu laden")
        refresh.setFixedWidth(40)
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        box.addLayout(row)
        self.model_hint = _label("", "soft")
        box.addWidget(self.model_hint)
        box.addWidget(_label("Neues Modell herunterladen (passend zu deinem PC sortiert):", "soft"))
        self.hardware = _label("", "soft")
        box.addWidget(self.hardware)
        row = QHBoxLayout()
        self.download_choice = QComboBox()
        self.download_choice.setMinimumWidth(240)
        self.download_choice.currentIndexChanged.connect(self._download_hint)
        row.addWidget(self.download_choice, 1)
        download = QPushButton("Herunterladen")
        download.setProperty("role", "primary")
        download.clicked.connect(self._download)
        row.addWidget(download)
        box.addLayout(row)
        self.download_detail = _label("", "soft")
        box.addWidget(self.download_detail)
        self.get_ollama = QPushButton("Ollama installieren (ollama.com)")
        self.get_ollama.clicked.connect(lambda: self.actions["open_url"]("https://ollama.com/download"))
        box.addWidget(self.get_ollama)
        key = QPushButton("OpenAI-Schlüssel (optional) …")
        key.clicked.connect(lambda: (self.actions["edit_key"](), self.refresh()))
        box.addWidget(key)
        main.addWidget(card)

        # Spracherkennung
        card, box = _card()
        box.addWidget(_label("SPRACHERKENNUNG (WHISPER, LOKAL)", "section"))
        grid = QGridLayout()
        self.whisper_model = self._combo([("base – schnell (~140 MB)", "base"), ("small – empfohlen (~460 MB)", "small"),
                                          ("medium – genauer (~1,5 GB)", "medium")], "whisper_model")
        self.whisper_device = self._combo([("Automatisch", "auto"), ("Grafikkarte (CUDA)", "cuda"), ("Prozessor", "cpu")],
                                          "whisper_device")
        self.whisper_language = self._combo([("Deutsch", "de"), ("Automatisch erkennen", "auto")], "whisper_language")
        for i, (label, combo) in enumerate([("Modell", self.whisper_model), ("Gerät", self.whisper_device),
                                            ("Sprache", self.whisper_language)]):
            grid.addWidget(_label(label), i, 0)
            grid.addWidget(combo, i, 1)
        box.addLayout(grid)
        self.whisper_state = _label("", "soft")
        box.addWidget(self.whisper_state)
        main.addWidget(card)

        # Computer und Cursor
        card, box = _card()
        box.addWidget(_label("COMPUTER UND CURSOR", "section"))
        self.checks = {}
        for key_name, text in [("computer_control", "Er darf den Computer benutzen (klicken, tippen, öffnen)"),
                               ("confirm_actions", "Vor jeder Aktion fragen"),
                               ("phone_mouse", "Maus aufs Handy (unten am Bildschirmrand hinausschieben)"),
                               ("follow_mouse", "Augen folgen meiner Maus"),
                               ("show_cursor", "Cursor zeigen"), ("glow", "Cursor-Leuchten")]:
            check = QCheckBox(text)
            check.toggled.connect(lambda on, k=key_name: self._set(k, on))
            self.checks[key_name] = check
            box.addWidget(check)
        grid = QGridLayout()
        self.phone_position = self._combo([("Links", 0.2), ("Mitte", 0.5), ("Rechts", 0.8)], "phone_position")
        self.cursor_size = self._combo([("Klein (48 pt)", 48), ("Mittel (72 pt)", 72), ("Groß (96 pt)", 96),
                                        ("Riesig (120 pt)", 120)], "cursor_size")
        self.trail = self._combo([("Kometenschweif", "comet"), ("Schnur zum Handy", "string"), ("Kein Schweif", "none")], "trail")
        self.mood = self._combo([("Hört zu", "listening"), ("Ruht", "resting"), ("Denkt nach", "thinking"),
                                 ("Fröhlich", "happy")], "mood")
        for i, (label, combo) in enumerate([("Handy steht unter", self.phone_position), ("Cursorgröße", self.cursor_size),
                                            ("Zeigerschweif", self.trail), ("Stimmung", self.mood)]):
            grid.addWidget(_label(label), i, 0)
            grid.addWidget(combo, i, 1)
        box.addLayout(grid)
        main.addWidget(card)

        # Weiteres
        row = QHBoxLayout()
        for text, action in [("Persönlichkeit …", "edit_personality"), ("Meeting-Notizen öffnen", "open_notes")]:
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, a=action: self.actions[a]())
            row.addWidget(button)
        main.addLayout(row)
        main.addWidget(_label("Tastenkürzel: Strg+Alt+Leertaste aufwecken · Strg+Alt+P hier zeigen · Strg+Alt+S Stopp · "
                              "Strg+Alt+H Cursor zeigen/verstecken", "soft"))
        row = QHBoxLayout()
        row.addStretch(1)
        quit_button = QPushButton("Bluey beenden")
        quit_button.clicked.connect(self.actions["quit"])
        row.addWidget(quit_button)
        close = QPushButton("Schließen")
        close.setProperty("role", "primary")
        close.clicked.connect(self.hide)
        row.addWidget(close)
        main.addLayout(row)
        main.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(2000)

    def run_test(self):
        self.test_button.setEnabled(False)
        self.test_button.setText("Teste …")
        lines = []

        def show():
            self.test_results.setText("<br>".join(lines) or "Teste …")

        def report(name, ok, text):
            mark = {True: "<span style='color:#5BE49B'>✓</span>", False: "<span style='color:#FF9AA8'>✗</span>",
                    None: "<span style='color:#FFD66B'>!</span>"}[ok]
            lines.append(f"{mark} <b>{_html(name)}</b>: {_html(text)}")
            self._from_thread.emit(show)

        def work():
            try:
                diagnostics.run(self.actions["server"](), report)
            except Exception as error:
                report("Test", False, str(error))

            def done():
                self.test_button.setEnabled(True)
                self.test_button.setText("Nochmal testen")
                self.refresh()
            self._from_thread.emit(done)
        show()
        threading.Thread(target=work, name="Bluey Test", daemon=True).start()

    def ask(self):
        question = self.question.text().strip()
        if not question:
            return
        self.answer.setText(f"<span style='color:#B9B2CC'>Bluey denkt nach über „{_html(question)}“ …</span>")
        self.ask_button.setEnabled(False)
        self.actions["ask"](question)

    def _show_answer(self, question, answer):
        self.ask_button.setEnabled(True)
        self.answer.setText(f"<span style='color:#B9B2CC'>Du: {_html(question)}</span><br><b>Bluey:</b> {_html(answer)}")

    def _combo(self, items, key):
        combo = QComboBox()
        for text, value in items:
            combo.addItem(text, value)
        combo.currentIndexChanged.connect(lambda _i, c=combo, k=key: self._set(k, c.currentData()))
        return combo

    def _set(self, key, value):
        if self._updating or value is None:
            return
        if getattr(settings, key) != value:
            setattr(settings, key, value)
            if key in ("computer_control",):
                self.actions["restart"]()
            if key == "computer_control":
                self.checks["confirm_actions"].setEnabled(bool(value))

    def _set_engine(self, engine):
        if self._updating:
            return
        self.actions["set_engine"](engine)
        self.refresh()

    def _model_chosen(self, _index):
        if self._updating:
            return
        name = self.model.currentData()
        if name and name != settings.ollama_model:
            settings.ollama_model = name
            self.actions["restart"]()
        self._update_model_hint()

    def _download_hint(self, _index=None):
        name = self.download_choice.currentData()
        self.download_detail.setText(getattr(self, "_details", {}).get(name, "Jedes Modell von ollama.com/library, z. B. mistral:7b"))

    def _download(self):
        name = self.download_choice.currentData()
        self.actions["download_model"](name or None)  # ohne Namen: fragt nach einem

    def _update_model_hint(self):
        name = settings.ollama_model
        caps = ollama.capabilities(name) if bool(ollama.running()) and name in ollama.models() else set()
        parts = []
        if "vision" in caps:
            parts.append("sieht Bildschirmfotos")
        if "tools" in caps:
            parts.append("eingebaute Werkzeuge")
        self.model_hint.setText(("Aktiv: " + name + (" · " + ", ".join(parts) if parts else "")) if name else "")

    def _select(self, combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _refresh_status(self):
        if not self.isVisible():
            return
        phones = self.actions["phones"]()
        self.status.setText(("Handy verbunden: " + ", ".join(phones)) if phones else
                            f"Warte auf die Handy-App … Adresse fürs Handy: {self.actions['address']()}")
        self.whisper_state.setText(stt.status or "Wird beim ersten Gespräch geladen.")

    def _fill_downloads(self, installed):
        hw = hardware.detect()
        self.hardware.setText("Dein PC: " + hw.summary)
        current = self.download_choice.currentData()
        self.download_choice.clear()
        self._details = {}
        for name, text, fits, best in hardware.recommend(hw):
            done = " ✓ installiert" if name in installed else ""
            mark = "★ " if best else "" if fits else "⚠ "
            self.download_choice.addItem(f"{mark}{name}{done}", name)
            self._details[name] = text + (" · schon installiert" if done else "")
        self.download_choice.addItem("Anderes Modell (Name eingeben) …", "")
        if current:
            self._select(self.download_choice, current)
        else:
            self.download_choice.setCurrentIndex(0)
        self._download_hint()

    def refresh(self):
        """Liest alles neu ein (Modelle, Status)."""
        self._updating = True
        try:
            self.use_ollama.setChecked(settings.engine == "ollama")
            self.use_openai.setChecked(settings.engine == "openai")
            running = bool(ollama.running())
            models = ollama.models() if running else []
            self.ollama_state.setProperty("role", "ok" if running else "bad")
            self.ollama_state.setText("Ollama läuft." if running else
                                      "Ollama läuft nicht. Installiere und starte Ollama, dann ↻ drücken.")
            self.ollama_state.style().unpolish(self.ollama_state)
            self.ollama_state.style().polish(self.ollama_state)
            self.get_ollama.setVisible(not running)
            self.model.clear()
            for name in models:
                self.model.addItem(name, name)
            if settings.ollama_model not in models:
                self.model.addItem(f"{settings.ollama_model} (nicht installiert)", settings.ollama_model)
            self._select(self.model, settings.ollama_model)
            self.model.setEnabled(bool(models))
            self._fill_downloads(models)
            for key_name, check in self.checks.items():
                check.setChecked(bool(getattr(settings, key_name)))
            self.checks["confirm_actions"].setEnabled(bool(settings.computer_control))
            for combo, key_name in [(self.whisper_model, "whisper_model"), (self.whisper_device, "whisper_device"),
                                    (self.whisper_language, "whisper_language"), (self.phone_position, "phone_position"),
                                    (self.cursor_size, "cursor_size"), (self.trail, "trail"), (self.mood, "mood")]:
                value = getattr(settings, key_name)
                if key_name == "phone_position":
                    value = min((0.2, 0.5, 0.8), key=lambda v: abs(v - value))
                self._select(combo, value)
        finally:
            self._updating = False
        self._update_model_hint()
        self._refresh_status()

    def open(self):
        self.refresh()
        self.show()
        self._refresh_status()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass


def _html(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
