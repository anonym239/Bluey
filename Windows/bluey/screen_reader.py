"""Fotografiert den Hauptbildschirm (ohne Blueys eigene Fenster) und liest jedes Wort mit seinem Kasten.

Texterkennung: die eingebaute Windows-Texterkennung (Windows.Media.Ocr). Bedienelemente der vordersten App:
Windows UI Automation. Alle Koordinaten in Snapshot und Target sind logische Punkte des Hauptbildschirms.
"""
import asyncio
import base64
import io
import math
import re
import sys
import time

from .computer import Display

IS_WINDOWS = sys.platform == "win32"


class Target:
    """Ein Ding auf dem Bildschirm, auf das er zeigen oder klicken kann: ein Bedienelement, eine Zeile oder ein Wort."""

    def __init__(self, id, text, rect):
        self.id, self.text = id, text
        self.rect = rect  # (x, y, w, h)

    @property
    def mid(self):
        x, y, w, h = self.rect
        return (x + w / 2, y + h / 2)

    def contains(self, point, pad=0):
        x, y, w, h = self.rect
        return x - pad <= point[0] <= x + w + pad and y - pad <= point[1] <= y + h + pad

    def distance(self, point):
        x, y, w, h = self.rect
        return math.hypot(max(x - point[0], 0, point[0] - x - w), max(y - point[1], 0, point[1] - y - h))


class Control:
    def __init__(self, id, kind, label, rect):
        self.id, self.kind, self.label, self.rect = id, kind, label, rect


class Snapshot:
    def __init__(self, jpeg, lines, size, app=None, controls=()):
        self.jpeg = jpeg
        self.lines = lines  # [(Target Zeile, [Target Wort])]
        self.size = size
        self.app = app
        self.controls = list(controls)

    def _candidates(self):
        items = [Target(c.id, c.label or c.kind, c.rect) for c in self.controls]
        for line, words in self.lines:
            items.append(line)
            items += words
        return items

    def target(self, id):
        id = (id or "").strip().upper()
        for c in self.controls:
            if c.id == id:
                return Target(c.id, c.label or c.kind, c.rect)
        for line, words in self.lines:
            if line.id == id:
                return line
            for word in words:
                if word.id == id:
                    return word
        return None

    def target_near(self, point):
        """Was unter (oder direkt neben) einem Punkt ist: das kleinste Wort, die Zeile oder das Bedienelement dort."""
        candidates = self._candidates()
        hits = [t for t in candidates if t.contains(point, 6)]
        if hits:
            return min(hits, key=lambda t: t.rect[2] * t.rect[3])
        near = [t for t in candidates if t.distance(point) < 60]
        return min(near, key=lambda t: t.distance(point)) if near else None

    def grid(self, rect):
        x, y, w, h = rect
        return f"@{int((x + w / 2) / self.size[0] * 1000)},{int((y + h / 2) / self.size[1] * 1000)}"

    @property
    def target_list(self):
        """Die Liste, aus der die KI wählt. Koordinaten auf einem 0-1000-Raster, passend zum Bild."""
        out = []
        if self.app:
            out.append(f"Vorderste App: {self.app}")
        if self.controls:
            out.append("Bedienelemente (per ID anklicken):")
            out += [f"{c.id} {c.kind} {self.grid(c.rect)}" + (f' "{c.label}"' if c.label else "") for c in self.controls]
        out.append("Text auf dem Bildschirm (L = Zeile, W = Wort, @x,y auf einem 0-1000-Raster):")
        if not self.lines:
            out.append("(kein Text gefunden)")
        for line, words in self.lines:
            extra = " | " + " ".join(f"{w.id}={w.text}" for w in words) if len(words) > 1 else ""
            out.append(f'{line.id} {self.grid(line.rect)} "{line.text}"{extra}')
        return "\n".join(out)

    @property
    def jpeg_base64(self):
        return base64.b64encode(self.jpeg).decode("ascii")


# Bildschirmfoto

def capture():
    """Das Bild des Hauptbildschirms (PIL, physische Pixel). Blueys Fenster sind per WDA_EXCLUDEFROMCAPTURE ausgenommen."""
    import mss
    from PIL import Image
    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def jpeg(image, max_edge=1280, quality=72):
    from PIL import Image
    w, h = image.size
    scale = min(1.0, max_edge / max(w, h))
    if scale < 1:
        image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    out = io.BytesIO()
    image.convert("RGB").save(out, format="JPEG", quality=quality)
    return out.getvalue()


# Texterkennung

_word_split = re.compile(r"\S+")


def recognize(image):
    """Liest Zeilen und Wörter. Gibt [(Target Zeile, [Target Wort])] in logischen Punkten zurück."""
    if not IS_WINDOWS:
        return []
    try:
        return asyncio.run(_recognize(image))
    except Exception:
        return []


async def _recognize(image):
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return []
    # Die Texterkennung hat eine Höchstgröße; große Bildschirme werden passend verkleinert.
    limit = OcrEngine.max_image_dimension or 2600
    w, h = image.size
    scale = min(1.0, limit / max(w, h))
    work = image if scale >= 1 else image.resize((int(w * scale), int(h * scale)))
    rgba = work.convert("RGBA")
    r, g, b, a = rgba.split()
    from PIL import Image
    bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
    writer = DataWriter()
    writer.write_bytes(bgra)
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                    work.size[0], work.size[1], BitmapAlphaMode.PREMULTIPLIED)
    result = await engine.recognize_async(bitmap)

    def to_logical(rect):
        x, y = rect.x / scale, rect.y / scale
        return Display.rect_to_logical((Display.origin[0] + x, Display.origin[1] + y, rect.width / scale, rect.height / scale))

    lines, word_count = [], 0
    for i, line in enumerate(list(result.lines)[:400]):
        words = []
        boxes = []
        for word in line.words:
            box = to_logical(word.bounding_rect)
            boxes.append(box)
            if word_count < 600:
                word_count += 1
                words.append(Target(f"W{word_count}", word.text, box))
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        lines.append((Target(f"L{len(lines) + 1}", line.text, (x0, y0, x1 - x0, y1 - y0)), words))
    # Lesereihenfolge: von oben nach unten, dann von links nach rechts.
    lines.sort(key=lambda e: (round(e[0].rect[1] / 8), e[0].rect[0]))
    for i, (line, _) in enumerate(lines):
        line.id = f"L{i + 1}"
    return lines


# Bedienelemente (UI Automation)

KINDS = {
    "ButtonControl": "Knopf", "SplitButtonControl": "Knopf", "CheckBoxControl": "Kontrollkästchen",
    "RadioButtonControl": "Option", "EditControl": "Textfeld", "ComboBoxControl": "Auswahlfeld",
    "HyperlinkControl": "Link", "SliderControl": "Regler", "TabItemControl": "Tab", "MenuItemControl": "Menü",
    "ListItemControl": "Listeneintrag", "TreeItemControl": "Eintrag", "SpinnerControl": "Zahlenfeld",
    "DocumentControl": "Dokument",
}
FIELD_KINDS = {"Textfeld", "Auswahlfeld", "Dokument"}


def read_controls(size, limit=140, budget=0.6):
    """Name der vordersten App und ihre sichtbaren Bedienelemente in Lesereihenfolge, in einem kleinen Zeitbudget."""
    if not IS_WINDOWS:
        return None, []
    try:
        import uiautomation as auto
    except Exception:
        return None, []
    found, seen = [], set()
    app = None
    with auto.UIAutomationInitializerInThread(debug=False):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            window = auto.ControlFromHandle(hwnd) if hwnd else None
        except Exception:
            window = None
        if window is None:
            return None, []
        try:
            app = window.Name or None
        except Exception:
            app = None
        deadline = time.monotonic() + budget
        queue = [(window, 0)]
        visited = 0
        screen = (0, 0, size[0], size[1])
        while queue and visited < 4000 and time.monotonic() < deadline:
            control, depth = queue.pop(0)
            visited += 1
            try:
                kind = KINDS.get(control.ControlTypeName)
                if kind:
                    r = control.BoundingRectangle
                    rect = Display.rect_to_logical((r.left, r.top, r.width(), r.height()))
                    if rect[2] > 3 and rect[3] > 3 and _intersects(rect, screen) and not control.IsOffscreen:
                        label = (control.Name or "").strip().replace("\n", " ")
                        if kind in FIELD_KINDS:
                            try:
                                value = control.GetValuePattern().Value if kind != "Dokument" else ""
                                if value:
                                    label = (label + ", " if label else "") + "enthält: " + value.strip()[:40]
                            except Exception:
                                pass
                        if label or kind in FIELD_KINDS:
                            key = tuple(int(v) for v in rect)
                            if key not in seen:
                                seen.add(key)
                                found.append((kind, label[:80], rect))
                if depth < 25:
                    for child in control.GetChildren()[:400]:
                        queue.append((child, depth + 1))
            except Exception:
                continue
    found.sort(key=lambda f: (round(f[2][1] / 6), f[2][0]))
    return app, [Control(f"C{i + 1}", kind, label, rect) for i, (kind, label, rect) in enumerate(found[:limit])]


def _intersects(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def focused_field():
    """Das fokussierte Element: wohin getippt wird, und ob es ein Passwortfeld ist. (Rahmen oder None, Passwort?)"""
    if not IS_WINDOWS:
        return None, False
    try:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread(debug=False):
            control = auto.GetFocusedControl()
            if control is None:
                return None, False
            secure = False
            try:
                secure = bool(control.IsPassword)
            except Exception:
                secure = False
            r = control.BoundingRectangle
            return Display.rect_to_logical((r.left, r.top, r.width(), r.height())), secure
    except Exception:
        return None, False


def snapshot():
    image = capture()
    size = Display.size
    app, controls = read_controls(size)
    lines = recognize(image)
    return Snapshot(jpeg(image), lines, size, app, controls)
