import unittest

from bluey import computer


class ComputerTest(unittest.TestCase):
    def test_combos(self):
        mods, key, label = computer.parse_combo("ctrl+shift+t")
        self.assertEqual(mods, [0x11, 0x10])
        self.assertEqual(key, ord("T"))
        self.assertEqual(label, "Strg+⇧+T")
        self.assertEqual(computer.parse_combo("cmd+l")[0], [0x11])  # Mac-Kürzel werden zu Strg
        self.assertEqual(computer.parse_combo("Enter")[1], 0x0D)
        self.assertEqual(computer.parse_combo("win")[1], 0x5B)
        self.assertEqual(computer.parse_combo("f5")[1], 0x74)

    def test_refused_and_unknown(self):
        for combo in ("win+l", "ctrl+alt+delete", "ctrl+shift+esc", "ctrl+alt+s"):
            with self.assertRaises(computer.ControlError):
                computer.parse_combo(combo)
        with self.assertRaises(computer.ControlError):
            computer.parse_combo("ctrl+banana")

    def test_urls(self):
        self.assertEqual(computer.open_url("javascript:alert(1)"), "Das sieht nicht nach einer Webadresse aus.")
        self.assertEqual(computer.open_url("https://user:pw@example.com"), "Das sieht nicht nach einer Webadresse aus.")

    def test_find_app(self):
        apps = {"Microsoft Edge": "a", "Editor": "b", "Spotify": "c", "Spotify Helper": "d"}
        self.assertEqual(computer.find_app("spotify", apps), "Spotify")
        self.assertEqual(computer.find_app("edge", apps), "Microsoft Edge")
        self.assertIsNone(computer.find_app("photoshop", apps))

    def test_display_conversion(self):
        computer.Display.scale, computer.Display.origin = 1.5, (0, 0)
        self.assertEqual(computer.Display.to_physical((100, 200)), (150, 300))
        self.assertEqual(computer.Display.to_logical((150, 300)), (100, 200))
        computer.Display.scale = 1.0
