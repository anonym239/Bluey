package io.github.anonym239.bluey;

import android.graphics.Color;

/** Blaubeerfarben aus dem Design. */
final class Palette {
    static final int BERRY1 = 0xFFA9BCFF;  // helles Immergrün
    static final int BERRY2 = 0xFF6C86F5;
    static final int BERRY3 = 0xFF4254D6;
    static final int BERRY4 = 0xFF2B2F8F;  // tiefes Indigo
    static final int NOSE = 0xFF1C1F66;
    static final int INK = 0xFF17151F;
    static final int INK_SOFT = 0xFFB9B2CC;
    static final int PANEL = 0xFF1E1B29;
    static final int GREEN = 0xFF5BE49B;
    static final int RED = 0xFFE5547A;
    static final int CARD = 0xFFEEF0FF;

    static final int[] GRADIENT = {BERRY1, BERRY2, BERRY3, BERRY4};
    static final float[] STOPS = {0f, 0.34f, 0.68f, 1f};

    static int alpha(int color, double opacity) {
        int a = (int) Math.round(Math.max(0, Math.min(1, opacity)) * 255);
        return Color.argb(a, Color.red(color), Color.green(color), Color.blue(color));
    }

    private Palette() {}
}
