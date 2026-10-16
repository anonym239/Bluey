"""Wo der große Cursor ist und wie er sich bewegt. Koordinaten: logische Punkte, Ursprung oben links, y nach unten.

Reine Rechnung ohne Fenster, damit sie sich auf jedem System testen lässt.
"""
import math
import random
import time

from .config import settings


class Mode:
    """Wohin der große Charakter-Cursor will."""
    DOCKED = "docked"        # unten am Bildschirmrand geparkt, lugt über dem Handy hervor
    FOLLOWING = "following"  # unter den Rand gesteckt; die Augen am Handy folgen deiner Maus

    @staticmethod
    def pinned(x, y):
        return ("pinned", float(x), float(y))

    @staticmethod
    def is_pinned(mode):
        return isinstance(mode, tuple) and mode[0] == "pinned"


TRAILS = [("comet", "Kometenschweif"), ("string", "Schnur zum Handy"), ("none", "Kein Schweif")]


class TimingCurve:
    """Eine CSS-artige cubic-bezier-Kurve: bildet Zeit (0…1) auf Fortschritt (0…1) ab."""

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    @staticmethod
    def _coordinate(t, a, b):
        u = 1 - t
        return 3 * u * u * t * a + 3 * u * t * t * b + t * t * t

    @staticmethod
    def _derivative(t, a, b):
        u = 1 - t
        return 3 * u * u * a + 6 * u * t * (b - a) + 3 * t * t * (1 - b)

    def _parameter(self, x):
        t = x
        for _ in range(8):
            error = self._coordinate(t, self.x1, self.x2) - x
            if abs(error) < 1e-7:
                return t
            d = self._derivative(t, self.x1, self.x2)
            if abs(d) < 1e-7:
                break
            t -= error / d
        low, high, t = 0.0, 1.0, x
        for _ in range(40):
            value = self._coordinate(t, self.x1, self.x2)
            if abs(value - x) < 1e-7:
                break
            if value < x:
                low = t
            else:
                high = t
            t = (low + high) / 2
        return t

    def value(self, x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        return self._coordinate(self._parameter(x), self.y1, self.y2)

    def rate(self, x):
        """Wie schnell sich der Fortschritt bei `x` mit der Zeit ändert."""
        t = self._parameter(min(max(x, 0), 1))
        dx, dy = self._derivative(t, self.x1, self.x2), self._derivative(t, self.y1, self.y2)
        return dy / dx if dx > 1e-7 else 0.0


# Startet sanft, dann eine lange, weiche Landung.
LAUNCH = TimingCurve(0.42, 0, 0.22, 1)
# Behält das Tempo, das er schon hatte (Planwechsel im Flug), und landet genauso.
REDIRECT = TimingCurve(0.25, 0.25, 0.22, 1)
# Gleichmäßig und bedächtig, für Ziehen.
STEADY = TimingCurve(0.42, 0, 0.38, 1)


class Flight:
    """Eine geplante Reise: eine weiche kubische Kurve, abgelaufen mit einer Easing-Kurve."""

    def __init__(self, start_point, c1, c2, to, start, duration, timing, pointing):
        self.from_ = start_point
        self.c1, self.c2, self.to = c1, c2, to
        self.start, self.duration = start, duration
        self.timing = timing
        self.pointing = pointing
        self.landed = False

    def progress(self, now):
        return 1.0 if self.duration <= 0 else min(1.0, max(0.0, (now - self.start) / self.duration))

    def position(self, e):
        u = 1 - e
        a, b, c, d = u * u * u, 3 * u * u * e, 3 * u * e * e, e * e * e
        return (a * self.from_[0] + b * self.c1[0] + c * self.c2[0] + d * self.to[0],
                a * self.from_[1] + b * self.c1[1] + c * self.c2[1] + d * self.to[1])

    def tangent(self, e):
        u = 1 - e
        a, b, c = 3 * u * u, 6 * u * e, 3 * e * e
        return (a * (self.c1[0] - self.from_[0]) + b * (self.c2[0] - self.c1[0]) + c * (self.to[0] - self.c2[0]),
                a * (self.c1[1] - self.from_[1]) + b * (self.c2[1] - self.c1[1]) + c * (self.to[1] - self.c2[1]))


def now():
    return time.monotonic()


class CursorEngine:
    def __init__(self):
        self.mode = Mode.FOLLOWING
        self.tip = (-1000.0, -1000.0)
        self.velocity = (0.0, 0.0)
        self.angle = math.pi / 4
        self._angle_velocity = 0.0
        self.opacity = 0.0
        self.flight = None
        self._placed = False
        self.bounds = (1440.0, 900.0)
        self.dragging = False
        self.on_land = None    # Landung auf einem Punkt, auf den er zeigen sollte
        self.on_launch = None  # er springt aus dem Handy oder taucht wieder hinein (Punkt am unteren Rand)
        self.landed_at = -10.0
        self._press_start = -10.0
        self._press_depth = 0.0
        self.talk_until = 0.0
        self.brain_mood = None      # gesetzt, solange er zuhört, nachdenkt oder redet
        self.gaze_override = None   # wohin die Augen am Handy schauen sollen statt zum Cursor
        self.awake = False
        self._mouse = (0.0, 0.0)
        self._last_mouse_move = now()
        self.talk_level = lambda: 0.0
        self.blink_until = 0.0
        self._next_blink = now() + 3

    @property
    def size(self):
        return float(settings.cursor_size)

    def set_mode(self, mode):
        self.mode = mode

    @property
    def is_home(self):
        return not Mode.is_pinned(self.mode)

    def phone_point(self, b):
        """Wo das Handy steht, knapp unter dem unteren Bildschirmrand."""
        return (b[0] * settings.phone_position, b[1] + b[1] * 0.18)

    def dock_point(self, b):
        """Lugt vom unteren Rand hervor, direkt über dem Handy."""
        return (b[0] * settings.phone_position, b[1] - self.size * 0.42)

    def tucked_point(self, b):
        """Knapp unter dem unteren Rand, außer Sicht, als stecke er im Handy."""
        return (b[0] * settings.phone_position, b[1] + self.size * 0.35)

    def _goal(self):
        if self.mode == Mode.DOCKED:
            return self.dock_point(self.bounds)
        if self.mode == Mode.FOLLOWING:
            return self.tucked_point(self.bounds)
        return (self.mode[1], self.mode[2])

    def time_to_arrive(self, t):
        if not self.flight:
            return 0.0
        return max(0.0, self.flight.start + self.flight.duration - t)

    def press(self, depth, at=None):
        """Ein kleines Zusammendrücken Richtung Spitze, wie beim Drücken eines Knopfes."""
        self._press_start = now() if at is None else at
        self._press_depth = depth

    def step(self, dt, t, mouse, bounds):
        self.bounds = bounds
        if math.hypot(mouse[0] - self._mouse[0], mouse[1] - self._mouse[1]) > 1.5:
            self._last_mouse_move = t
        self._mouse = mouse
        if not self._placed:
            self.tip = self.tucked_point(bounds)
            self._placed = True

        target = self._goal()
        if self.flight:
            needs_plan = math.hypot(self.flight.to[0] - target[0], self.flight.to[1] - target[1]) > 0.5
        else:
            needs_plan = math.hypot(self.tip[0] - target[0], self.tip[1] - target[1]) > 0.5
        if needs_plan:
            self._plan(target, t)
        self._advance(t)

        # Blendet ein, sobald er losfliegt; im Folgemodus aus, wenn er sich versteckt hat.
        settled = (self.flight.progress(t) if self.flight else 1) >= 1
        want = 0.0 if (self.mode == Mode.FOLLOWING and settled) else 1.0
        rate = 12.0 if want > self.opacity else 6.0
        self.opacity += (want - self.opacity) * min(1.0, dt * rate)

        # Aufrecht wie ein normaler Cursor unterwegs (gekippt, wenn geparkt), leicht in die Bewegung gelehnt.
        lean = max(-0.2, min(0.2, self.velocity[0] / 2800))
        target_angle = (math.pi / 4 if self.is_home else 0) + lean
        k = 24.0
        self._angle_velocity += (k * (target_angle - self.angle) - 2 * math.sqrt(k) * self._angle_velocity) * dt
        self.angle += self._angle_velocity * dt

        if t > self._next_blink:
            self.blink_until = t + 0.13
            self._next_blink = t + random.uniform(2.5, 6)

    def _plan(self, goal, t):
        """Plant eine natürlich wirkende Reise: eine sanfte Kurve, getaktet wie eine echte Handbewegung."""
        start = self.tip
        dx, dy = goal[0] - start[0], goal[1] - start[1]
        distance = math.hypot(dx, dy)
        pointing = not self.is_home
        dock = self.dock_point(self.bounds)
        from_home = math.hypot(start[0] - dock[0], start[1] - dock[1]) < self.size * 1.2 or start[1] > self.bounds[1] - 2
        if distance <= 0.5:
            self.flight = Flight(start, start, goal, goal, t, 0, LAUNCH, pointing)
            return

        duration = min(1.2, max(0.45, 0.4 + 0.12 * math.log2(1 + distance / 24)))
        if self.dragging:
            duration = min(1.6, max(0.6, duration * 1.45))

        direction = (dx / distance, dy / distance)
        normal = (-direction[1], direction[0])
        if abs(direction[0]) > 0.4:
            if normal[1] > 0:
                normal = (-normal[0], -normal[1])  # seitliche Reisen wölben sich leicht nach oben
        else:
            toward_middle = 1 if self.bounds[0] / 2 - (start[0] + goal[0]) / 2 >= 0 else -1
            if normal[0] * toward_middle < 0:
                normal = (-normal[0], -normal[1])  # senkrechte Reisen wölben sich zur Mitte
        bow = 0 if self.dragging else min(distance * 0.1, 70) * 0.75
        reach = distance * 0.3
        c2 = (goal[0] - direction[0] * reach + normal[0] * bow, goal[1] - direction[1] * reach + normal[1] * bow)

        speed = math.hypot(*self.velocity)
        if speed > 60:
            # Planwechsel im Flug: mit aktuellem Tempo und Kurs weiter, ohne Knick.
            carry = (self.velocity[0] * duration / 3, self.velocity[1] * duration / 3)
            length = math.hypot(*carry)
            if length > distance * 0.6:
                carry = (carry[0] / length * distance * 0.6, carry[1] / length * distance * 0.6)
            c1 = (start[0] + carry[0], start[1] + carry[1])
            timing = REDIRECT
        else:
            c1 = (start[0] + direction[0] * reach + normal[0] * bow, start[1] + direction[1] * reach + normal[1] * bow)
            timing = STEADY if self.dragging else LAUNCH
        self.flight = Flight(start, c1, c2, goal, t, duration, timing, pointing)
        if pointing and from_home and self.on_launch:
            self.on_launch((dock[0], self.bounds[1]))

    def _advance(self, t):
        flight = self.flight
        if not flight:
            self.velocity = (0.0, 0.0)
            return
        p = flight.progress(t)
        e = flight.timing.value(p)
        self.tip = flight.position(e)
        if p >= 1:
            self.velocity = (0.0, 0.0)
            if not flight.landed:
                flight.landed = True
                if flight.pointing:
                    self.landed_at = t
                    if self.on_land:
                        self.on_land(self.tip)
                elif self.mode == Mode.FOLLOWING and self.on_launch:
                    self.on_launch((self.tip[0], self.bounds[1]))
        else:
            rate = flight.timing.rate(p) / flight.duration
            d = flight.tangent(e)
            self.velocity = (d[0] * rate, d[1] * rate)

    def press_scale(self, t):
        """Skalierung fürs Drücken: schnell rein, dann federnd zurück mit winzigem Rückprall."""
        s = t - self._press_start
        if s < 0 or s >= 0.42:
            return 1.0
        if s < 0.12:
            return 1 - self._press_depth * math.sin(s / 0.12 * math.pi / 2)
        r = (s - 0.12) / 0.3
        return 1 - self._press_depth * math.cos(r * math.pi * 1.5) * math.exp(-r * 3.2)

    def hover(self, t):
        """Ein langsames, sanftes Schweben, während er auf etwas zeigt."""
        if self.is_home or (self.flight.progress(t) if self.flight else 1) < 1:
            return 0.0
        since = t - self.landed_at
        amount = min(1.0, max(0.0, (since - 0.35) / 0.6))
        return math.sin(since * 2.4) * 1.6 * amount

    @property
    def body_center(self):
        r = self.size * 0.5 * math.sqrt(2)
        return (self.tip[0] + math.cos(self.angle + math.pi / 4) * r, self.tip[1] + math.sin(self.angle + math.pi / 4) * r)

    def face(self, bounds, t):
        """Was das Gesicht am Handy tun soll: zum Cursor schauen (oder im Folgemodus zu deiner Maus)."""
        phone = self.phone_point(bounds)
        c = self._mouse if self.mode == Mode.FOLLOWING else self.body_center
        gx = max(-1.0, min(1.0, (c[0] - phone[0]) / (bounds[0] * 0.5)))
        gy = -max(0.15, min(1.0, (phone[1] - c[1]) / (bounds[1] * 1.1)))
        if self.gaze_override:
            gx, gy = self.gaze_override

        testing = t < self.talk_until
        talk = 0.5 + 0.5 * math.sin(t * 19) * math.sin(t * 7.3) if testing else self.talk_level()
        mood = settings.mood
        if self.brain_mood:
            mood = self.brain_mood
        elif testing:
            mood = "talking"
        elif Mode.is_pinned(self.mode) and mood == "listening":
            mood = "pointing"
        elif self.mode == Mode.FOLLOWING and not self.awake and mood == "listening":
            # Deine Maus steht still: nach 5 Sekunden wird er müde, nach 15 nickt er ein.
            idle = t - self._last_mouse_move
            if idle > 15:
                mood = "resting"
            elif idle > 5:
                mood = "sleepy"
        return {"gazeX": gx, "gazeY": gy, "mood": mood, "talk": talk}
