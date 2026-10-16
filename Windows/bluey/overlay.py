"""Ein durchklickbares, durchsichtiges Fenster über dem ganzen Hauptbildschirm, das seinen Cursor zeigt.

Gezeichnet mit QPainter. Alles hier läuft auf dem Qt-Hauptthread.
"""
import math
import random
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QMessageBox, QWidget

from .config import settings
from .cursor_engine import CursorEngine, Mode
from .palette import BERRY1, BERRY2, BERRY3, BERRY4, GRADIENT, INK, STOPS, color

DISPLAY_FAMILY = "Fredoka"


def display_font(size, weight=QFont.Bold):
    font = QFont(DISPLAY_FAMILY)
    font.setPixelSize(int(round(size)))
    font.setWeight(weight)
    return font


def teardrop(s, r):
    """Ein Quadrat mit drei ganz runden Ecken und einer spitzen (der Spitze) im Ursprung. y nach unten."""
    path = QPainterPath()
    big = s / 2
    path.moveTo(r, 0)
    path.lineTo(s - big, 0)
    path.arcTo(QRectF(s - 2 * big, 0, 2 * big, 2 * big), 90, -90)
    path.lineTo(s, s - big)
    path.arcTo(QRectF(s - 2 * big, s - 2 * big, 2 * big, 2 * big), 0, -90)
    path.lineTo(big, s)
    path.arcTo(QRectF(0, s - 2 * big, 2 * big, 2 * big), 270, -90)
    path.lineTo(0, r)
    path.arcTo(QRectF(0, 0, 2 * r, 2 * r), 180, -90)
    path.closeSubpath()
    return path


def star_path(radius):
    path = QPainterPath()
    for i in range(8):
        r = radius if i % 2 == 0 else radius * 0.4
        a = i * math.pi / 4 - math.pi / 2
        p = QPointF(math.cos(a) * r, math.sin(a) * r)
        if i == 0:
            path.moveTo(p)
        else:
            path.lineTo(p)
    path.closeSubpath()
    return path


def ease_out(t):
    return 1 - (1 - t) ** 3


def spring_pop(t, start=0.55):
    """Federnde Skalierung von `start` auf 1 (wie CASpringAnimation)."""
    if t <= 0:
        return start
    return 1 - (1 - start) * math.exp(-t * 9) * math.cos(t * 18)


class Effect:
    def __init__(self, kind, point, life, **params):
        self.kind, self.point, self.life = kind, point, life
        self.born = time.monotonic()
        self.params = params


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowTitle("Bluey-Overlay")
        self.engine = CursorEngine()
        self.engine.on_land = self._soft_land
        self.engine.on_launch = self._puff
        self.frame_callbacks = []
        self.on_face = lambda face: None
        self.speech_target = None  # (x, y, w, h): worauf er zeigt, damit die Blase darüber sitzt
        self.door = None           # (links, rechts, Nähe 0…1): die „Tür“ zum Handy am unteren Rand
        self.phone_mouse_label = None  # (x, y): Hinweis, solange die Maus auf dem Handy ist
        self._caption = None
        self._speech_size = None
        self._speech_layout = None
        self._speech_born = 0.0
        self._speech_fade = None
        self._effects = []
        self._bubbles = []
        self._samples = []
        self._last_twinkle = 0.0
        self._look = (-0.7, -0.7)
        self._string_mid = None
        self._string_velocity = (0.0, 0.0)
        self._sprite = None
        self._sprite_key = None
        self._last_time = None
        self._dirty = QRectF()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.place()
        QGuiApplication.primaryScreen().geometryChanged.connect(lambda _: self.place())

    # Fenster

    def place(self):
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())

    def start(self):
        self.engine.set_mode(self.idle_mode)
        self.show()
        self._native_setup()
        self._timer.start(16)

    def _native_setup(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # durchklickbar, nie aktiv, nicht in der Taskleiste
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x20 | 0x80000 | 0x08000000 | 0x80)
            # nicht auf Bildschirmfotos (damit er sich beim Hinschauen nicht selbst sieht)
            user32.SetWindowDisplayAffinity(hwnd, 0x11)
        except Exception:
            pass

    # Modus

    @property
    def mode(self):
        return self.engine.mode

    def set_mode(self, mode):
        self.engine.set_mode(mode)

    @property
    def idle_mode(self):
        """Wo der Cursor ruht, wenn niemand zeigt: versteckt mit Augen auf deiner Maus, oder über dem Handy geparkt."""
        return Mode.FOLLOWING if settings.follow_mouse else Mode.DOCKED

    def go_home(self):
        self.engine.set_mode(self.idle_mode)

    def talk_test(self, seconds=3):
        self.engine.talk_until = time.monotonic() + seconds

    # Takt

    def _tick(self):
        t = time.monotonic()
        dt = 1 / 60 if self._last_time is None else min(max(t - self._last_time, 1 / 480), 1 / 20)
        self._last_time = t
        pos = QCursor.pos() - self.geometry().topLeft()
        bounds = (float(self.width()), float(self.height()))
        self.engine.step(dt, t, (float(pos.x()), float(pos.y())), bounds)
        for callback in list(self.frame_callbacks):
            try:
                callback(t)
            except Exception:
                pass
        self._frame_t, self._frame_dt = t, dt
        self._update_look(dt)
        self._update_trail(t)
        self._update_string(t, dt)
        area = self._bounds(t)
        dirty = area.united(self._dirty) if not self._dirty.isNull() else area
        self._dirty = area
        if not dirty.isNull():
            self.update(dirty.toAlignedRect().adjusted(-4, -4, 4, 4))
        self.on_face(self.engine.face(bounds, t))

    def _bounds(self, t):
        """Was diesen Frame gezeichnet wird, damit nur dieser Bereich neu gemalt werden muss."""
        area = QRectF()
        e = self.engine
        if settings.show_cursor and e.opacity > 0.01:
            s = e.size * 2.2
            area = area.united(QRectF(e.tip[0] - s, e.tip[1] - s, s * 2, s * 2))
            if self._trail_path is not None:
                area = area.united(self._trail_path.boundingRect())
            if self._string_path is not None:
                area = area.united(self._string_path.boundingRect().adjusted(-4, -4, 4, 4))
        if self.door or self.phone_mouse_label or getattr(self, "_door_drawn", False):
            area = area.united(QRectF(0, self.height() - 80, self.width(), 80))
            self._door_drawn = bool(self.door or self.phone_mouse_label)
        for effect in self._effects:
            r = effect.params.get("reach", 80)
            area = area.united(QRectF(effect.point[0] - r, effect.point[1] - r, 2 * r, 2 * r))
        for bubble in self._bubbles:
            if bubble.get("rect") is not None:
                area = area.united(bubble["rect"].adjusted(-30, -40, 30, 30))
        if self._caption or self._speech_fade:
            rect = self._speech_rect(t)
            if rect is not None:
                area = area.united(rect.adjusted(-40, -40, 40, 40))
        return area

    # Augen, Schweif, Schnur

    def _update_look(self, dt):
        e = self.engine
        vx, vy = e.velocity
        speed = math.hypot(vx, vy)
        want = (-0.7, -0.7)
        if speed > 90:
            a = -e.angle
            local = (vx * math.cos(a) - vy * math.sin(a), vx * math.sin(a) + vy * math.cos(a))
            n = max(math.hypot(*local), 1)
            want = (local[0] / n, local[1] / n)
        follow = min(1, dt * 12)
        self._look = (self._look[0] + (want[0] - self._look[0]) * follow, self._look[1] + (want[1] - self._look[1]) * follow)

    _trail_path = None
    _string_path = None

    def _update_trail(self, t):
        e = self.engine
        center = e.body_center
        self._samples.append((center, t))
        self._samples = [s for s in self._samples if t - s[1] <= 0.2]
        speed = math.hypot(*e.velocity)
        self._trail_path = None
        if not settings.show_cursor or settings.trail != "comet" or len(self._samples) <= 2 or speed <= 260:
            return
        # Ein weicher, spitz zulaufender Kometenschweif entlang des gerade geflogenen Wegs.
        head = e.size * 0.42
        left, right = [], []
        count = len(self._samples)
        for i, (p, _) in enumerate(self._samples):
            prev = self._samples[max(0, i - 1)][0]
            nxt = self._samples[min(count - 1, i + 1)][0]
            n = (-(nxt[1] - prev[1]), nxt[0] - prev[0])
            length = max(math.hypot(*n), 0.001)
            n = (n[0] / length, n[1] / length)
            w = head * (i / (count - 1)) ** 1.3 / 2
            left.append(QPointF(p[0] + n[0] * w, p[1] + n[1] * w))
            right.append(QPointF(p[0] - n[0] * w, p[1] - n[1] * w))
        path = QPainterPath(left[0])
        for p in left[1:] + right[::-1]:
            path.lineTo(p)
        path.closeSubpath()
        self._trail_path = path
        self._trail_alpha = min(1, (speed - 260) / 900) * 0.26 * e.opacity
        if speed > 900 and t - self._last_twinkle > 0.05:
            self._last_twinkle = t
            self._twinkle((center[0] + random.uniform(-10, 10), center[1] + random.uniform(-10, 10)))

    def _update_string(self, t, dt):
        e = self.engine
        if not settings.show_cursor or settings.trail != "string" or e.opacity <= 0.02:
            self._string_path, self._string_mid = None, None
            return
        # Wie eine Ballonschnur, die das Handy hält: sie hängt etwas durch und schwingt mit.
        start = (self.width() * settings.phone_position, self.height() + 4)
        end = e.body_center
        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        slack = max(0, 160 - distance * 0.12)
        goal = ((start[0] + end[0]) / 2 + math.sin(t * 1.3) * 6, (start[1] + end[1]) / 2 + slack)
        mid = self._string_mid or goal
        k = 22.0
        vx = self._string_velocity[0] + (k * (goal[0] - mid[0]) - 2 * math.sqrt(k) * 0.55 * self._string_velocity[0]) * dt
        vy = self._string_velocity[1] + (k * (goal[1] - mid[1]) - 2 * math.sqrt(k) * 0.55 * self._string_velocity[1]) * dt
        self._string_velocity = (vx, vy)
        mid = (mid[0] + vx * dt, mid[1] + vy * dt)
        self._string_mid = mid
        control = (2 * mid[0] - (start[0] + end[0]) / 2, 2 * mid[1] - (start[1] + end[1]) / 2)
        path = QPainterPath(QPointF(*start))
        path.quadTo(QPointF(*control), QPointF(*end))
        self._string_path = path

    # Effekte (abfeuern und vergessen)

    def _ring(self, point, radius, rgb, alpha, duration):
        self._effects.append(Effect("ring", point, duration, radius=radius, rgb=rgb, alpha=alpha, reach=radius + 8))

    def _star(self, point, radius, travel, rgb, duration):
        self._effects.append(Effect("star", point, duration, radius=radius, travel=travel, rgb=rgb,
                                    spin=random.uniform(-2.5, 2.5), reach=max(abs(travel[0]), abs(travel[1])) + radius + 8))

    def _twinkle(self, point):
        self._star(point, random.uniform(3, 5.5), (random.uniform(-8, 8), random.uniform(6, 18)),
                   random.choice([BERRY1, BERRY2]), 0.5)

    def _soft_land(self, point):
        """Landung auf etwas, worauf er zeigt: ein weicher Ring und ein kleines Nicken."""
        self.engine.press(0.05)
        self._ring(point, 30, BERRY2, 0.55, 0.7)

    def _puff(self, point):
        """Aus dem Handy springen (oder wieder hineintauchen), am unteren Rand."""
        if not settings.show_cursor:
            return
        self._ring(point, 26, BERRY1, 0.6, 0.55)
        for i in range(3):
            dx = (i - 1) * 14
            self._star((point[0] + dx, point[1] - 4), 4, (dx * 0.6, -28), BERRY1, 0.6)

    def click_effect(self, point, right=False):
        """Ein echter Klick: kräftiges Quetschen, ein Ring und ein kleiner Sternenregen."""
        self.engine.press(0.14)
        self._ring(point, 38, BERRY3 if right else BERRY2, 0.85, 0.65)
        for i in range(6):
            a = i / 6 * 2 * math.pi + random.uniform(-0.25, 0.25)
            distance = random.uniform(34, 58)
            self._star(point, random.uniform(4, 7), (math.cos(a) * distance, math.sin(a) * distance),
                       random.choice([BERRY1, BERRY2, BERRY3]), 0.55)

    def typed_effect(self, text):
        """Ein getipptes Zeichen schwebt vom Cursor nach oben, damit man ihn tippen sieht."""
        e = self.engine
        if not settings.show_cursor or e.opacity <= 0.1:
            return
        e.press(0.035)
        for i, ch in enumerate(text):
            if ch.isspace():
                continue
            start = (e.tip[0] + e.size * 0.55 + i * 6, e.tip[1] - 6)
            self._effects.append(Effect("glyph", start, 0.9, char=ch, drift=random.uniform(-12, 16), reach=70))

    def bubble(self, text, life=1.4):
        """Ein kleines Etikett neben dem Cursor, z. B. „Strg+T“ oder „Öffne Edge“. Das neueste ersetzt ältere."""
        if not settings.show_cursor:
            return
        self._bubbles = [{"text": text, "born": time.monotonic(), "life": life, "rect": None}]

    # Sprechblase

    @property
    def caption(self):
        return self._caption

    @caption.setter
    def caption(self, text):
        text = (text or "").strip() or None
        if text == self._caption:
            return
        if text is None:
            if self._caption:
                # Mit einem kleinen Plopp verschwinden.
                self._speech_fade = (time.monotonic(), self._speech_size, self._speech_layout)
            self._caption = None
            self._speech_size = None
            return
        appearing = self._caption is None
        self._caption = text
        self._speech_fade = None
        # Längere Antworten: etwas kleinere Schrift und breitere Blase, damit kein Turm entsteht.
        length = len(text)
        size = 21 if length <= 50 else 19 if length <= 110 else 17
        font = display_font(size)
        metrics = QFontMetricsF(font)
        max_width = min(self.width() * 0.5, 580, max(240, math.sqrt(length) * 50))
        rect = metrics.boundingRect(QRectF(0, 0, max_width, 2000), Qt.AlignHCenter | Qt.TextWordWrap, text)
        pad_w, pad_h = 24, 15
        self._speech_size = (max(math.ceil(rect.width()) + pad_w * 2, 70), math.ceil(rect.height()) + pad_h * 2)
        self._speech_layout = (font, text)
        if appearing:
            self._speech_born = time.monotonic()

    TAIL = 18

    def _speech_geometry(self, t, size):
        """Folgt seinem Cursor: über dem Ding, auf das er zeigt (oder unter dem Cursor, wenn oben kein Platz ist),
        sonst knapp über dem Handy."""
        e = self.engine
        w, h = size
        margin, tail = 14, self.TAIL
        pointing = e.opacity > 0.1 and not e.is_home
        tail_up = False
        below = (e.tip[0] + e.size * 0.5, e.tip[1] + e.size * 1.35)
        if pointing:
            thing = self.speech_target or (e.tip[0] - 12, e.tip[1] - 30, 24, 24)
            target = (thing[0] + thing[2] / 2, thing[1] - 10)
            origin = (target[0] - w / 2, target[1] - tail - h)
            if origin[1] < margin:
                target = below
                origin = (target[0] - w / 2, target[1] + tail)
                tail_up = True
        else:
            target = (self.width() * settings.phone_position, self.height() - e.size * 0.9)
            origin = (target[0] - w / 2, target[1] - tail - h)
        ox = min(max(origin[0], margin), self.width() - w - margin)
        oy = min(max(origin[1], margin), self.height() - h - margin)
        bob = math.sin((t - self._speech_born) * 2.2) * 2
        return ox, oy + bob, (target[0], target[1] + bob * 0.5), tail_up

    def _speech_rect(self, t):
        size = self._speech_size or (self._speech_fade[1] if self._speech_fade else None)
        if not size:
            return None
        ox, oy, _, _ = self._speech_geometry(t, size)
        return QRectF(ox, oy - self.TAIL, size[0], size[1] + self.TAIL * 2)

    def _paint_speech(self, p, t):
        if self._caption and self._speech_size:
            size, layout = self._speech_size, self._speech_layout
            age = t - self._speech_born
            scale, alpha = spring_pop(age), min(1, age / 0.12)
        elif self._speech_fade:
            start, size, layout = self._speech_fade
            age = t - start
            if age > 0.22 or not size:
                self._speech_fade = None
                return
            scale, alpha = 1 - 0.15 * age / 0.22, 1 - age / 0.22
        else:
            return
        ox, oy, target, tail_up = self._speech_geometry(t, size)
        w, h = size
        tail = self.TAIL
        r = min(24, h / 2)
        half = 13
        local_x = target[0] - ox
        base_x = min(max(local_x, r + half + 2), w - r - half - 2)
        lean = min(max(local_x - base_x, -tail * 1.4), tail * 1.4)
        # y nach unten: normalerweise hängt das Schwänzchen unten, bei Platzmangel oben (zum Cursor darunter).
        tip_y = -tail if tail_up else h + tail
        tip = (base_x + lean, tip_y)
        path = QPainterPath()
        path.moveTo(r, 0)
        if tail_up:
            path.lineTo(base_x - half, 0)
            path.cubicTo(base_x - half * 0.3, 0, tip[0] - 1, -tail * 0.5, tip[0], tip[1])
            path.cubicTo(tip[0] + 2, -tail * 0.45, base_x + half * 0.4, 0, base_x + half, 0)
        path.lineTo(w - r, 0)
        path.arcTo(QRectF(w - 2 * r, 0, 2 * r, 2 * r), 90, -90)
        path.lineTo(w, h - r)
        path.arcTo(QRectF(w - 2 * r, h - 2 * r, 2 * r, 2 * r), 0, -90)
        if not tail_up:
            path.lineTo(base_x + half, h)
            path.cubicTo(base_x + half * 0.3, h, tip[0] + 1, h + tail * 0.5, tip[0], tip[1])
            path.cubicTo(tip[0] - 2, h + tail * 0.45, base_x - half * 0.4, h, base_x - half, h)
        path.lineTo(r, h)
        path.arcTo(QRectF(0, h - 2 * r, 2 * r, 2 * r), 270, -90)
        path.lineTo(0, r)
        path.arcTo(QRectF(0, 0, 2 * r, 2 * r), 180, -90)
        path.closeSubpath()

        p.save()
        p.setOpacity(max(0, min(1, alpha)))
        cx, cy = ox + w / 2, oy + h / 2
        p.translate(cx, cy)
        p.scale(scale, scale)
        p.translate(-w / 2, -h / 2)
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0, QColor("white"))
        gradient.setColorAt(1, QColor("#EEF0FF"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        pen = QPen(color(BERRY2), 2.5)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
        font, text = layout
        p.setFont(font)
        p.setPen(color(INK))
        p.drawText(QRectF(24, 14, w - 48, h - 30), Qt.AlignCenter | Qt.TextWordWrap, text)
        p.restore()

    # Malen

    def _cursor_sprite(self):
        """Der Körper des Cursors, einmal gemalt (Verlauf, Glanz, weißer Rand, weiches Leuchten) und dann nur bewegt."""
        side = self.engine.size
        ratio = self.devicePixelRatioF()
        key = (side, settings.glow, ratio)
        if self._sprite_key == key:
            return self._sprite
        k = side / 96
        pad = side * 0.45
        full = side + pad * 2
        image = QImage(int(math.ceil(full * ratio)), int(math.ceil(full * ratio)), QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(pad, pad)
        path = teardrop(side, 6 * k)
        # Leuchten: viele weiche Ringe statt eines Weichzeichners.
        glow_rgb, glow_alpha, glow_size = (BERRY2, 0.7, 30 * k) if settings.glow else (BERRY4, 0.45, 16 * k)
        steps = 14
        for i in range(steps, 0, -1):
            width = glow_size * i / steps * 1.6
            c = color(glow_rgb, glow_alpha * (1 - i / steps) ** 1.6 * 0.35)
            pen = QPen(c, width)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        gradient = QLinearGradient(0.25 * side, 0.067 * side, 0.75 * side, 0.933 * side)
        for c, stop in zip(GRADIENT, STOPS):
            gradient.setColorAt(stop, color(c))
        p.fillPath(path, QBrush(gradient))
        shine = QRadialGradient(QPointF(0.3 * side, 0.24 * side), 0.38 * side)
        shine.setColorAt(0, QColor(255, 255, 255, 140))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(shine))
        p.setPen(QPen(QColor("white"), 8 * k))  # die Hälfte wird weggeschnitten: ein 4-pt-Rand
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.restore()
        p.end()
        self._sprite = (QPixmap.fromImage(image), pad)
        self._sprite_key = key
        return self._sprite

    def paintEvent(self, event):
        t = getattr(self, "_frame_t", time.monotonic())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(event.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        e = self.engine
        visible = settings.show_cursor
        if visible and self._string_path is not None:
            p.setPen(QPen(color(BERRY1, 0.7 * e.opacity), 2.5, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._string_path)
        if visible and self._trail_path is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(color(BERRY2, self._trail_alpha))
            p.drawPath(self._trail_path)
        self._paint_door(p, t)
        self._paint_effects(p, t)
        if visible and e.opacity > 0.01:
            self._paint_cursor(p, t)
        self._paint_bubbles(p, t)
        self._paint_speech(p, t)
        p.end()

    def _paint_door(self, p, t):
        """Ein leuchtender Balken unten am Rand, wo die Maus aufs Handy wechselt."""
        if self.door and self.door[2] > 0.01:
            left, right, near = self.door
            h = self.height()
            gradient = QLinearGradient(0, h - 26, 0, h)
            gradient.setColorAt(0, color(BERRY2, 0))
            gradient.setColorAt(1, color(BERRY1, 0.75 * near))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(gradient))
            p.drawRoundedRect(QRectF(left, h - 26, right - left, 30), 14, 14)
            p.setBrush(color(BERRY1, 0.9 * near))
            p.drawRoundedRect(QRectF(left + 8, h - 5, right - left - 16, 5), 2.5, 2.5)
        if self.phone_mouse_label:
            x, y = self.phone_mouse_label
            text = "Maus ist auf dem Handy · nach oben schieben zum Zurückkehren"
            font = display_font(15)
            w = QFontMetricsF(font).horizontalAdvance(text) + 28
            rect = QRectF(min(max(x - w / 2, 8), self.width() - w - 8), y, w, 30)
            p.setPen(QPen(color(BERRY2, 0.9), 2))
            p.setBrush(color(INK, 0.88))
            p.drawRoundedRect(rect, 15, 15)
            p.setFont(font)
            p.setPen(QColor("white"))
            p.drawText(rect, Qt.AlignCenter, text)

    def _paint_cursor(self, p, t):
        e = self.engine
        sprite, pad = self._cursor_sprite()
        side = e.size
        k = side / 96
        p.save()
        p.setOpacity(e.opacity)
        p.translate(e.tip[0], e.tip[1] + e.hover(t))
        p.rotate(math.degrees(e.angle))
        squish = e.press_scale(t)
        p.scale(squish, squish)
        p.drawPixmap(QPointF(-pad, -pad), sprite)
        # Seine Augen schauen, wohin er fliegt, und wieder zur Spitze, wenn er hält. Ab und zu blinzeln sie.
        blinking = t < e.blink_until
        d = 18 * k
        for i in range(2):
            x, y = (34 + i * 24) * k, 40 * k
            p.save()
            p.translate(x + d / 2, y + d / 2)
            if blinking:
                p.scale(1, 0.12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(0, 0), d / 2, d / 2)
            pr = 9 * k / 2
            p.setBrush(color(INK))
            p.drawEllipse(QPointF(self._look[0] * 3.4 * k, self._look[1] * 3.4 * k), pr, pr)
            p.restore()
        p.restore()

    def _paint_effects(self, p, t):
        alive = []
        for effect in self._effects:
            age = t - effect.born
            if age > effect.life:
                continue
            alive.append(effect)
            f = age / effect.life
            x, y = effect.point
            prm = effect.params
            if effect.kind == "ring":
                eased = 1 - (1 - f) ** 2.4
                radius = prm["radius"] * (0.3 + 0.7 * eased)
                p.setPen(QPen(color(prm["rgb"], prm["alpha"] * (1 - eased)), 3.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x, y), radius, radius)
            elif effect.kind == "star":
                eased = ease_out(f)
                fade = 1 if f < 0.45 else 1 - (f - 0.45) / 0.55
                p.save()
                p.translate(x + prm["travel"][0] * eased, y + prm["travel"][1] * eased)
                p.rotate(math.degrees(prm["spin"] * f))
                s = 1 - 0.6 * f
                p.scale(s, s)
                p.setPen(Qt.NoPen)
                p.setBrush(color(prm["rgb"], fade))
                p.drawPath(star_path(prm["radius"]))
                p.restore()
            elif effect.kind == "glyph":
                eased = ease_out(f)
                fade = f / 0.12 if f < 0.12 else 1 if f < 0.55 else 1 - (f - 0.55) / 0.45
                s = 1.1 - 0.35 * f
                p.save()
                p.translate(x + prm["drift"] * eased, y - 46 * eased)
                p.scale(s, s)
                font = display_font(22)
                path = QPainterPath()
                path.addText(QPointF(-7, 8), font, prm["char"])
                p.setOpacity(max(0, min(1, fade)))
                p.setPen(QPen(QColor("white"), 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
                p.setPen(Qt.NoPen)
                p.setBrush(color(BERRY3))
                p.drawPath(path)
                p.restore()
        self._effects = alive

    def _paint_bubbles(self, p, t):
        if not self._bubbles:
            return
        e = self.engine
        bubble = self._bubbles[0]
        age = t - bubble["born"]
        if age > bubble["life"]:
            self._bubbles = []
            return
        font = display_font(19)
        metrics = QFontMetricsF(font)
        tw = metrics.horizontalAdvance(bubble["text"])
        w, h = math.ceil(tw) + 28, math.ceil(metrics.height()) + 14
        if e.opacity > 0.1:
            anchor = (e.tip[0] + e.size * 1.05, e.tip[1] - e.size * 0.1)
        else:
            anchor = (self.width() * settings.phone_position, self.height() - e.size * 1.3)
        x = anchor[0]
        if x + w > self.width() - 12:
            x = e.tip[0] - w - e.size * 0.3
        y = anchor[1] - min(age, 0.3) * 20
        rect = QRectF(x, y - h / 2, w, h)
        bubble["rect"] = rect
        alpha = min(age / 0.12, (bubble["life"] - age) / 0.3, 1)
        scale = spring_pop(age, 0.4)
        p.save()
        p.setOpacity(max(0, alpha))
        p.translate(rect.center())
        p.scale(scale, scale)
        p.translate(-rect.center())
        p.setPen(QPen(color(BERRY2, 0.9), 2))
        p.setBrush(color(INK, 0.92))
        p.drawRoundedRect(rect, 14, 14)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(rect, Qt.AlignCenter, bubble["text"])
        p.restore()

    # Nachfragen (nur wenn "Vor jeder Aktion fragen" an ist)

    def confirm(self, name, args):
        box = QMessageBox()
        box.setWindowTitle("Bluey möchte etwas tun")
        box.setText(f"Erlauben: {name}?")
        box.setInformativeText(str(args)[:600])
        allow = box.addButton("Erlauben", QMessageBox.AcceptRole)
        box.addButton("Ablehnen", QMessageBox.RejectRole)
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        QTimer.singleShot(30000, box.reject)
        box.exec()
        return box.clickedButton() is allow
