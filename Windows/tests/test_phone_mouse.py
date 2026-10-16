import json
import unittest

from bluey.config import settings
from bluey.phone_mouse import DWELL, PHONE_H, PHONE_W, PhoneMouse, zone


class PhoneMouseTest(unittest.TestCase):
    def setUp(self):
        settings.phone_mouse = True
        settings.phone_position = 0.5
        self.sent = []
        self.mouse = PhoneMouse(self.sent.append)
        self.changes = []
        self.mouse.on_change = self.changes.append
        self.bounds = (1920.0, 1080.0)

    def states(self):
        return [json.loads(p["text"])["state"] for p in self.sent]

    def test_enters_only_in_the_phone_zone_after_a_moment(self):
        left, right = zone(self.bounds)
        self.assertTrue(left < 960 < right)
        self.assertFalse(self.mouse.check((100, 1079), self.bounds, 0))       # neben dem Handy: nichts
        self.assertFalse(self.mouse.check((100, 1079), self.bounds, 1))
        self.assertFalse(self.mouse.check((960, 1079), self.bounds, 2))       # in der Zone: kurz warten
        self.assertTrue(self.mouse.check((960, 1079), self.bounds, 2 + DWELL + 0.01))
        self.assertTrue(self.mouse.active)
        self.assertEqual(self.changes, [True])
        self.assertAlmostEqual(self.mouse.x, 0.5, places=2)
        self.assertEqual(self.states(), ["enter"])

    def test_not_without_a_phone_or_when_switched_off(self):
        self.mouse.connected = lambda: False
        self.mouse.check((960, 1079), self.bounds, 0)
        self.assertFalse(self.mouse.check((960, 1079), self.bounds, 1))
        self.mouse.connected = lambda: True
        settings.phone_mouse = False
        self.mouse.check((960, 1079), self.bounds, 0)
        self.assertFalse(self.mouse.check((960, 1079), self.bounds, 1))

    def test_moves_clicks_and_leaves_upwards(self):
        self.mouse.check((960, 1079), self.bounds, 0)
        self.mouse.check((960, 1079), self.bounds, 1)
        self.mouse.move(PHONE_W * 0.25, PHONE_H * 0.5)
        self.assertAlmostEqual(self.mouse.x, 0.75, places=2)
        self.mouse.button(True)
        self.mouse.button(False)
        self.assertEqual(self.states()[-2:], ["down", "up"])
        # Mit gedrückter Taste nicht hinaus (er hält ja gerade zum Fragen).
        self.mouse.button(True)
        self.assertFalse(self.mouse.move(0, -PHONE_H))
        self.mouse.button(False)
        self.assertTrue(self.mouse.move(0, -PHONE_H))
        self.mouse.exit()
        self.assertFalse(self.mouse.active)
        self.assertEqual(self.states()[-1], "leave")
        left, right = zone(self.bounds)
        self.assertAlmostEqual(self.mouse.exit_to[0], left + 0.75 * (right - left), places=1)
        self.assertLess(self.mouse.exit_to[1], 1080 - 2)

    def test_fast_moves_are_throttled_and_flushed(self):
        self.mouse.check((960, 1079), self.bounds, 0)
        self.mouse.check((960, 1079), self.bounds, 1)
        for _ in range(20):
            self.mouse.move(2, 1)
        sent = len(self.sent)
        self.assertLess(sent, 10)
        self.mouse.flush()
        last = json.loads(self.sent[-1]["text"])
        self.assertAlmostEqual(last["x"], min(1, 0.5 + 40 / PHONE_W), places=3)
