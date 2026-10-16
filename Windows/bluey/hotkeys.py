"""Systemweite Tastenkürzel über RegisterHotKey, auf einem eigenen Thread mit Nachrichtenschleife."""
import sys
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
WM_HOTKEY = 0x0312


class HotKeys:
    def __init__(self, post):
        """`post(fn)` führt fn auf dem Qt-Hauptthread aus."""
        self.post = post
        self.actions = {}
        self.wanted = []
        self.failed = []
        self._thread = None

    def register(self, key, action, modifiers=MOD_CONTROL | MOD_ALT):
        """`key` ist ein Buchstabe ("P") oder ein virtueller Tastencode (0x20 = Leertaste)."""
        code = ord(key.upper()) if isinstance(key, str) else key
        self.wanted.append((len(self.wanted) + 1, modifiers | MOD_NOREPEAT, code, action))

    def start(self):
        if sys.platform != "win32" or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="Bluey Tastenkürzel", daemon=True)
        self._thread.start()

    def _loop(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        for ident, modifiers, code, action in self.wanted:
            if user32.RegisterHotKey(None, ident, modifiers, code):
                self.actions[ident] = action
            else:
                self.failed.append(code)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                action = self.actions.get(msg.wParam)
                if action:
                    self.post(action)
