"""Hände an Tastatur und Maus, nur genutzt, wenn der Nutzer ihn um etwas bittet.

Alle Positionen hier sind physische Pixel (die Prozess-DPI ist "per Monitor"). Die Umrechnung von seinen
logischen Punkten macht `display`.
"""
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.parse import urlparse

IS_WINDOWS = sys.platform == "win32"


class Display:
    """Hauptbildschirm: Umrechnung zwischen logischen Punkten (Overlay) und physischen Pixeln (Windows-API)."""
    origin = (0, 0)       # physischer Ursprung des Hauptbildschirms
    scale = 1.0           # physische Pixel pro logischem Punkt
    size = (1920.0, 1080.0)  # logische Größe

    @classmethod
    def to_physical(cls, point):
        return (int(round(cls.origin[0] + point[0] * cls.scale)), int(round(cls.origin[1] + point[1] * cls.scale)))

    @classmethod
    def to_logical(cls, point):
        return ((point[0] - cls.origin[0]) / cls.scale, (point[1] - cls.origin[1]) / cls.scale)

    @classmethod
    def rect_to_logical(cls, rect):
        x, y, w, h = rect
        lx, ly = cls.to_logical((x, y))
        return (lx, ly, w / cls.scale, h / cls.scale)


class ControlError(Exception):
    pass


if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    for _name in ("IsWindowVisible", "GetWindowTextLengthW", "IsIconic", "SetForegroundWindow"):
        getattr(user32, _name).argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x01000
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004

VK = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "space": 0x20, "spacebar": 0x20, "leertaste": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "entf": 0x2E, "forwarddelete": 0x2E, "insert": 0x2D, "einfg": 0x2D,
    "escape": 0x1B, "esc": 0x1B, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "pos1": 0x24, "end": 0x23, "ende": 0x23, "pageup": 0x21, "pagedown": 0x22, "bildauf": 0x21, "bildab": 0x22,
    "-": 0xBD, "minus": 0xBD, "=": 0xBB, "plus": 0xBB, "+": 0xBB, ",": 0xBC, "comma": 0xBC, ".": 0xBE, "period": 0xBE,
    "printscreen": 0x2C, "druck": 0x2C, "capslock": 0x14, "menu": 0x5D, "apps": 0x5D,
}
for _i in range(26):
    VK[chr(ord("a") + _i)] = 0x41 + _i
for _i in range(10):
    VK[str(_i)] = 0x30 + _i
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i
EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E, 0x5D}
MODIFIERS = {
    "ctrl": 0x11, "control": 0x11, "strg": 0x11, "cmd": 0x11, "command": 0x11, "⌘": 0x11,
    "alt": 0x12, "option": 0x12, "opt": 0x12, "⌥": 0x12,
    "shift": 0x10, "⇧": 0x10, "umschalt": 0x10,
    "win": 0x5B, "windows": 0x5B, "meta": 0x5B, "super": 0x5B,
}
MOD_LABELS = {0x11: "Strg", 0x12: "Alt", 0x10: "⇧", 0x5B: "⊞"}
KEY_LABELS = {
    "enter": "↵", "return": "↵", "tab": "⇥", "space": "Leertaste", "spacebar": "Leertaste", "backspace": "⌫",
    "delete": "Entf", "del": "Entf", "escape": "Esc", "esc": "Esc", "left": "←", "right": "→", "up": "↑", "down": "↓",
    "home": "Pos1", "end": "Ende", "pageup": "Bild↑", "pagedown": "Bild↓",
}

# Kürzel, die abmelden, sperren oder den Task-Manager öffnen, überlässt er dem Nutzer (dazu sein eigener Stopp).
REFUSED_SHORTCUTS = [{"win", "l"}, {"ctrl", "alt", "delete"}, {"ctrl", "shift", "escape"}, {"ctrl", "alt", "s"},
                     {"win", "x"}, {"alt", "tab"}]


def _norm(part):
    part = part.strip().lower()
    return {"strg": "ctrl", "control": "ctrl", "cmd": "ctrl", "command": "ctrl", "⌘": "ctrl", "option": "alt",
            "opt": "alt", "⌥": "alt", "windows": "win", "meta": "win", "super": "win", "umschalt": "shift", "⇧": "shift",
            "esc": "escape", "del": "delete", "entf": "delete", "return": "enter"}.get(part, part)


def parse_combo(combo):
    """Zerlegt "ctrl+shift+t" in (Modifikator-Codes, Tastencode, Beschriftung). Wirft ControlError."""
    if not isinstance(combo, str) or not combo.strip():
        raise ControlError("Welche Taste?")
    raw = combo.replace(" ", "")
    parts = [p for p in raw.split("+") if p] or ["+"]
    if raw.endswith("++"):
        parts.append("+")
    names = {_norm(p) for p in parts}
    for refused in REFUSED_SHORTCUTS:
        if refused <= names and len(names) == len(refused):
            raise ControlError("Das drücke ich nicht (es sperrt, meldet ab oder stoppt mich). Bitte den Nutzer, es selbst zu tun.")
    mods, key, key_name = [], None, ""
    for part in parts:
        name = part.strip().lower()
        if name in MODIFIERS:
            code = MODIFIERS[name]
            if code not in mods:
                mods.append(code)
        elif name in VK:
            key, key_name = VK[name], name
        elif _norm(name) in VK:
            key, key_name = VK[_norm(name)], _norm(name)
        else:
            raise ControlError(f'Die Taste "{part}" kenne ich nicht.')
    if key is None:
        if len(mods) == 1 and mods[0] == 0x5B:  # nur die Windows-Taste: Startmenü
            return [], 0x5B, "⊞"
        raise ControlError(f'Die Taste "{combo}" kenne ich nicht.')
    label = "".join(MOD_LABELS[m] + "+" for m in mods) + KEY_LABELS.get(key_name, key_name.upper())
    return mods, key, label


def _send(*inputs):
    if not IS_WINDOWS:
        return
    array = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def _key(code, up=False, scan=0, unicode=False):
    flags = (KEYEVENTF_KEYUP if up else 0)
    if unicode:
        flags |= KEYEVENTF_UNICODE
        code = 0
    elif code in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(wVk=code, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def _mouse(flags, data=0):
    inp = INPUT(type=INPUT_MOUSE)
    inp.union.mi = MOUSEINPUT(dx=0, dy=0, mouseData=ctypes.c_ulong(data & 0xFFFFFFFF).value, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def mouse_location():
    """Wo der echte Mauszeiger gerade ist (physische Pixel)."""
    if not IS_WINDOWS:
        return (0, 0)
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)


def warp(point):
    """Setzt den echten Zeiger zurück, wo der Nutzer ihn gelassen hat."""
    if IS_WINDOWS:
        user32.SetCursorPos(int(point[0]), int(point[1]))


def click(point, right=False, count=1):
    warp(point)
    time.sleep(0.03)
    down, up = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if right else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    for i in range(max(1, count)):
        _send(_mouse(down))
        time.sleep(0.035)
        _send(_mouse(up))
        if i < count - 1:
            time.sleep(0.08)


def drag_begin(point):
    warp(point)
    time.sleep(0.02)
    _send(_mouse(MOUSEEVENTF_LEFTDOWN))


def drag_move(point):
    warp(point)
    _send(_mouse(MOUSEEVENTF_MOVE))


def drag_end(point):
    warp(point)
    _send(_mouse(MOUSEEVENTF_LEFTUP))


def scroll(dx, dy, point):
    """Scrollt sanft an einem Punkt. Positives dy scrollt die Seite nach unten, positives dx nach rechts."""
    warp(point)
    steps = 12
    for _ in range(steps):
        if dy:
            _send(_mouse(MOUSEEVENTF_WHEEL, int(-dy / steps)))
        if dx:
            _send(_mouse(MOUSEEVENTF_HWHEEL, int(dx / steps)))
        time.sleep(0.016)


def press_key(code):
    _send(_key(code), _key(code, up=True))


def press(combo):
    """Drückt eine Taste oder ein Kürzel wie "ctrl+t", "enter" oder "ctrl+shift+n". Gibt eine kurze Beschriftung zurück."""
    mods, key, label = parse_combo(combo)
    downs = [_key(m) for m in mods] + [_key(key)]
    ups = [_key(key, up=True)] + [_key(m, up=True) for m in reversed(mods)]
    _send(*downs)
    time.sleep(0.02)
    _send(*ups)
    return label


def type_unicode(text):
    units = text.encode("utf-16-le")
    events = []
    for i in range(0, len(units), 2):
        code = units[i] | (units[i + 1] << 8)
        events += [_key(0, scan=code, unicode=True), _key(0, up=True, scan=code, unicode=True)]
    if events:
        _send(*events)


def type_text(text, on_chunk=None, cancelled=lambda: False):
    """Tippt Text wie auf einer Tastatur und meldet jedes Stück (für die Tipp-Animation)."""
    chunk_size, pause = (6, 0.012) if len(text) > 160 else (1, 0.022)
    chunk = ""
    for character in text:
        if cancelled():
            return False
        if character in "\n\r\t":
            if chunk:
                type_unicode(chunk)
                if on_chunk:
                    on_chunk(chunk)
                chunk = ""
                time.sleep(pause)
            if character != "\r":
                press_key(0x09 if character == "\t" else 0x0D)
            time.sleep(pause)
            continue
        chunk += character
        if len(chunk) >= chunk_size:
            type_unicode(chunk)
            if on_chunk:
                on_chunk(chunk)
            chunk = ""
            time.sleep(pause)
    if chunk:
        type_unicode(chunk)
        if on_chunk:
            on_chunk(chunk)
    return True


# Apps und Links

ALIASES = {
    "editor": "notepad.exe", "notepad": "notepad.exe", "texteditor": "notepad.exe",
    "rechner": "calc.exe", "calculator": "calc.exe", "taschenrechner": "calc.exe",
    "paint": "mspaint.exe", "explorer": "explorer.exe", "datei-explorer": "explorer.exe", "dateien": "explorer.exe",
    "einstellungen": "ms-settings:", "settings": "ms-settings:", "terminal": "wt.exe",
}

_start_apps = None
_start_lock = threading.Lock()


def start_apps():
    """Alle Apps aus dem Startmenü (Name → AppID), einmal per PowerShell gelesen und gemerkt."""
    global _start_apps
    with _start_lock:
        if _start_apps is not None:
            return _start_apps
        apps = {}
        if IS_WINDOWS:
            try:
                out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                      "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                                     capture_output=True, timeout=20, creationflags=0x08000000)
                data = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    if item.get("Name") and item.get("AppID"):
                        apps[item["Name"]] = item["AppID"]
            except Exception:
                pass
        _start_apps = apps
        return apps


def find_app(wanted, apps):
    wanted = wanted.lower().strip()
    names = sorted(apps, key=len)
    for test in (lambda n: n.lower() == wanted, lambda n: n.lower().startswith(wanted), lambda n: wanted in n.lower()):
        for name in names:
            if test(name):
                return name
    return None


def _activate_window(wanted):
    """Holt ein offenes Fenster nach vorn, dessen Titel den Namen enthält."""
    if not IS_WINDOWS:
        return None
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if re.search(r"(^|[\s\-–—|])" + re.escape(wanted) + r"($|[\s\-–—|.])", title.lower()) and title.lower() != "bluey":
                    found.append((hwnd, title))
                    return False
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return None
    hwnd, title = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Windows lässt SetForegroundWindow nur zu, wenn gerade eine Taste gedrückt wurde: kurz Alt antippen.
    _send(_key(0x12), _key(0x12, up=True))
    user32.SetForegroundWindow(hwnd)
    return title


def open_app(name):
    wanted = name.strip().lower().removesuffix(".exe")
    if not wanted:
        return "Welche App?"
    title = _activate_window(wanted)
    if title:
        return f"Zu {title} gewechselt."
    if wanted in ALIASES:
        target = ALIASES[wanted]
        try:
            os.startfile(target) if IS_WINDOWS else None
            return f"{name} geöffnet."
        except OSError as error:
            return f"Ich konnte {name} nicht öffnen: {error}"
    apps = start_apps()
    match = find_app(wanted, apps)
    if not match:
        return f"Ich habe keine App namens {name} gefunden."
    try:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + apps[match]], creationflags=0x08000000)
        return f"{match} geöffnet."
    except OSError as error:
        return f"Ich konnte {name} nicht öffnen: {error}"


def open_url(text):
    address = (text or "").strip()
    scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", address)
    if scheme and "://" not in address and not re.match(r"^[^/:]+:\d+", address):
        return "Das sieht nicht nach einer Webadresse aus."  # z. B. javascript: oder file:
    if "://" not in address:
        address = "https://" + address
    parsed = urlparse(address)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return "Das sieht nicht nach einer Webadresse aus."
    webbrowser.open(address)
    return f"{parsed.hostname} geöffnet."
