"""Einstellungen aus dem Tray-Menü, über Neustarts hinweg gespeichert (%APPDATA%\\Bluey\\settings.json)."""
import json
import os
import threading

APP_NAME = "Bluey"
DEFAULT_PORT = 52700


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def documents_dir():
    """Der Dokumente-Ordner (auch wenn er umgeleitet ist, z. B. nach OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


DEFAULTS = {
    "cursor_size": 72,          # Cursorgröße in Punkten (Design-Standard 72)
    "glow": False,
    "show_cursor": True,
    "phone_position": 0.5,      # wo das Handy unter dem Bildschirm steht, 0 = links, 1 = rechts
    "follow_mouse": True,       # in Ruhe: Cursor verstecken, Augen am Handy folgen deiner Maus
    "captions": True,
    "computer_control": True,   # er darf klicken, tippen, Tasten drücken und Dinge öffnen
    "trail": "comet",
    "mood": "listening",
    "personality": "",
    # Die KI: "ollama" (lokal, kostenlos, Standard) oder "openai" (Realtime, braucht Schlüssel).
    "engine": "ollama",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "gemma3:4b",
    "whisper_model": "small",
    "whisper_device": "auto",   # auto, cuda oder cpu
    "whisper_language": "de",   # de oder auto
    "port": DEFAULT_PORT,
    "confirm_actions": False,   # vor jeder Aktion am PC nachfragen
    "phone_mouse": True,        # Maus unten am Rand aufs Handy schieben
    "welcome_done": False,      # Einstellungsfenster beim allerersten Start zeigen
}


class Settings:
    def __init__(self, path=None):
        self._path = path or os.path.join(data_dir(), "settings.json")
        self._lock = threading.Lock()
        self._values = dict(DEFAULTS)
        self.listeners = []
        try:
            with open(self._path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for key, value in saved.items():
                    if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])) or (
                            key in DEFAULTS and isinstance(DEFAULTS[key], float) and isinstance(value, (int, float))):
                        self._values[key] = value
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):
        if name.startswith("_") or name == "listeners":
            raise AttributeError(name)
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        if name.startswith("_") or name == "listeners":
            object.__setattr__(self, name, value)
            return
        if name not in DEFAULTS:
            raise AttributeError(name)
        with self._lock:
            self._values[name] = value
            self._save()
        for listener in list(self.listeners):
            try:
                listener(name)
            except Exception:
                pass

    def _save(self):
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._values, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            pass


settings = Settings()
