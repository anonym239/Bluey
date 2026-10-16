import unittest

from bluey.config import settings
from bluey.cursor_engine import LAUNCH, CursorEngine, Mode


class EngineTest(unittest.TestCase):
    def run_until(self, engine, seconds, start=0.0, mouse=(10, 10)):
        t = start
        while t < start + seconds:
            t += 1 / 60
            engine.step(1 / 60, t, mouse, (1440.0, 900.0))
        return t

    def test_timing_curve(self):
        self.assertEqual(LAUNCH.value(0), 0)
        self.assertEqual(LAUNCH.value(1), 1)
        self.assertTrue(0 < LAUNCH.value(0.5) < 1)
        self.assertLess(LAUNCH.value(0.3), LAUNCH.value(0.6))

    def test_flies_to_a_spot_and_lands(self):
        e = CursorEngine()
        landed = []
        e.on_land = landed.append
        t = self.run_until(e, 0.5)
        e.set_mode(Mode.pinned(400, 300))
        t = self.run_until(e, 2.0, t)
        self.assertAlmostEqual(e.tip[0], 400, places=3)
        self.assertAlmostEqual(e.tip[1], 300, places=3)
        self.assertEqual(len(landed), 1)
        self.assertGreater(e.opacity, 0.9)
        self.assertFalse(e.is_home)

    def test_tucks_away_when_following(self):
        e = CursorEngine()
        self.run_until(e, 3)
        self.assertLess(e.opacity, 0.05)
        self.assertGreater(e.tip[1], 900)

    def test_face_follows_the_mouse_and_gets_sleepy(self):
        settings.mood = "listening"
        e = CursorEngine()
        t = self.run_until(e, 1, mouse=(1400, 100))
        face = e.face((1440.0, 900.0), t)
        self.assertGreater(face["gazeX"], 0.5)
        self.assertLess(face["gazeY"], 0)
        t = self.run_until(e, 6, t, mouse=(1400, 100))
        self.assertEqual(e.face((1440.0, 900.0), t)["mood"], "sleepy")
        t = self.run_until(e, 10, t, mouse=(1400, 100))
        self.assertEqual(e.face((1440.0, 900.0), t)["mood"], "resting")

    def test_pointing_mood(self):
        settings.mood = "listening"
        e = CursorEngine()
        e.set_mode(Mode.pinned(100, 100))
        t = self.run_until(e, 2)
        self.assertEqual(e.face((1440.0, 900.0), t)["mood"], "pointing")
