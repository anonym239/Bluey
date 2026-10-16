"""Maus aufs Handy: Schiebst du die Maus unten am Bildschirmrand dorthin, wo das Handy steht, wandert sie aufs
Handy (wie „Maus ohne Grenzen“). Klick = Tippen, Doppelklick = Aufwecken/Schlafen, gedrückt halten = Fragen.
Oben wieder hinausschieben bringt sie zurück auf den PC.

Unter Windows fängt ein Low-Level-Maus-Hook alle Bewegungen und Klicks ab, solange die Maus auf dem Handy ist,
damit am PC nichts versehentlich angeklickt wird. Die Rechnung selbst ist systemunabhängig und testbar.
"""
import json
import sys
import threading
import time

from .config import settings

# Wie groß das Handy für die Maus ist (logische Punkte): ein Querformat-Handy, etwa 844 × 390.
PHONE_W, PHONE_H = 520.0, 240.0
# Wie lange die Maus unten am Rand stehen muss, bevor sie aufs Handy wechselt.
DWELL = 0.12
EDGE = 2.0


def zone(bounds):
    """Der Bereich am unteren Rand, über dem das Handy steht: (links, rechts)."""
    width = bounds[0]
    half = min(260.0, width * 0.16)
    center = width * settings.phone_position
    return max(0.0, center - half), min(width, center + half)


class PhoneMouse:
    def __init__(self, send):
        """`send(packet)` schickt ein Paket an das Handy (thread-sicher)."""
        self.send = send
        self.active = False
        self.x = self.y = 0.5     # Zeiger auf dem Handy, 0…1
        self.down = False
        self.anchor = (0, 0)      # physische Position, an der der echte Zeiger parkt
        self.scale = 1.0
        self.exit_to = None       # wohin der echte Zeiger beim Zurückkehren kommt (logisch)
        self.on_change = lambda active: None
        self.connected = lambda: True
        self._edge_since = None
        self._pending = None
        self._last_sent = 0.0
        self._lock = threading.Lock()
        self._zone = (0.0, 0.0)
        self._bounds = (1.0, 1.0)
        self._hook_thread = None
        self.near = 0.0           # 0…1: wie nah die Maus der „Tür“ zum Handy ist (fürs Overlay)

    # Rein und raus (Hauptthread)

    def check(self, mouse, bounds, t):
        """Jeden Frame: steht die Maus lange genug unten in der Handy-Zone, wechselt sie aufs Handy."""
        self._bounds = bounds
        if self.active or not settings.phone_mouse or not self.connected():
            self._edge_since = None
            self.near = 0.0
            return False
        left, right = zone(bounds)
        inside = left <= mouse[0] <= right
        distance = bounds[1] - 1 - mouse[1]
        self.near = max(0.0, 1 - distance / 60) if inside else 0.0
        if inside and distance <= EDGE:
            if self._edge_since is None:
                self._edge_since = t
            elif t - self._edge_since >= DWELL:
                self._edge_since = None
                self.enter((mouse[0] - left) / max(1.0, right - left))
                return True
        else:
            self._edge_since = None
        return False

    def enter(self, u):
        left, right = zone(self._bounds)
        self._zone = (left, right)
        with self._lock:
            self.active = True
            self.x, self.y, self.down = min(max(u, 0.0), 1.0), 0.02, False
        self._post("enter")
        self.on_change(True)

    def exit(self):
        """Zurück auf den PC: der echte Zeiger taucht oben über dem Handy wieder auf."""
        with self._lock:
            if not self.active:
                return
            was_down = self.down
            self.active = False
            self.down = False
            left, right = self._zone
            self.exit_to = (left + self.x * (right - left), self._bounds[1] - 8)
        if was_down:
            self._post("up")
        self._post("leave")
        self.on_change(False)

    # Bewegungen und Tasten (vom Hook-Thread oder aus Tests)

    def move(self, dx, dy):
        """Relative Bewegung in logischen Punkten. Gibt True zurück, wenn die Maus oben hinaus ist."""
        with self._lock:
            if not self.active:
                return False
            self.x = min(max(self.x + dx / PHONE_W, 0.0), 1.0)
            self.y = self.y + dy / PHONE_H
            if self.y < 0 and not self.down:
                return True
            self.y = min(max(self.y, 0.0), 1.0)
        self._post("move", throttle=True)
        return False

    def button(self, pressed):
        with self._lock:
            if not self.active or self.down == pressed:
                return
            self.down = pressed
        self._post("down" if pressed else "up")

    def flush(self):
        """Schickt eine zurückgehaltene Bewegung (vom Overlay-Takt aufgerufen)."""
        with self._lock:
            pending = self._pending
            self._pending = None
        if pending:
            self.send(pending)

    def _post(self, state, throttle=False):
        with self._lock:
            packet = {"command": "pointer", "text": json.dumps({"x": round(self.x, 4), "y": round(min(max(self.y, 0), 1), 4),
                                                                "state": state, "down": self.down})}
            now = time.monotonic()
            if throttle and now - self._last_sent < 0.012:
                self._pending = packet
                return
            self._pending = None
            self._last_sent = now
        self.send(packet)

    # Windows: Low-Level-Maus-Hook

    def start_hook(self, post, warp):
        """`post(fn)` führt fn auf dem Hauptthread aus; `warp((x, y))` setzt den echten Zeiger (physisch)."""
        if sys.platform != "win32" or self._hook_thread:
            return
        self._post_main, self._warp = post, warp
        self._hook_thread = threading.Thread(target=self._hook_loop, name="Bluey Handy-Maus", daemon=True)
        self._hook_thread.start()

    def _hook_loop(self):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = LRESULT
        user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
        LLMHF_INJECTED = 0x01

        def proc(code, wparam, lparam):
            if code < 0 or not self.active:
                return user32.CallNextHookEx(None, code, wparam, lparam)
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if info.flags & LLMHF_INJECTED:  # eigene Bewegungen (z. B. Zeiger parken) durchlassen
                return user32.CallNextHookEx(None, code, wparam, lparam)
            if wparam == WM_MOUSEMOVE:
                dx = (info.pt.x - self.anchor[0]) / self.scale
                dy = (info.pt.y - self.anchor[1]) / self.scale
                if self.move(dx, dy):
                    self._post_main(self._leave)
            elif wparam == WM_LBUTTONDOWN:
                self.button(True)
            elif wparam == WM_LBUTTONUP:
                self.button(False)
            # Alles schlucken: Solange die Maus auf dem Handy ist, passiert am PC nichts.
            return 1

        self._proc = HOOKPROC(proc)  # Referenz halten, sonst räumt Python den Rückruf weg
        hook = user32.SetWindowsHookExW(14, self._proc, kernel32.GetModuleHandleW(None), 0)  # WH_MOUSE_LL
        if not hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _leave(self):
        self.exit()
        if self.exit_to and hasattr(self, "_warp"):
            self._warp(self.exit_to)
