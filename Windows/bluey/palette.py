"""Blaubeerfarben aus dem Design, als 0xRRGGBB."""
from PySide6.QtGui import QColor

BERRY1 = 0xA9BCFF  # helles Immergrün
BERRY2 = 0x6C86F5
BERRY3 = 0x4254D6
BERRY4 = 0x2B2F8F  # tiefes Indigo
NOSE = 0x1C1F66
INK = 0x17151F
INK_SOFT = 0xB9B2CC
PANEL = 0x1E1B29

GRADIENT = [BERRY1, BERRY2, BERRY3, BERRY4]
STOPS = [0, 0.34, 0.68, 1]


def color(rgb, alpha=1.0):
    c = QColor((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c
