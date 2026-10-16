package io.github.anonym239.bluey;

import android.content.Context;
import android.graphics.Typeface;

/** Fredoka und IBM Plex liegen in der App (variable Schriften); Fallback sind die Systemschriften. */
final class Fonts {
    static Typeface display = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD);
    static Typeface sans = Typeface.SANS_SERIF;
    static Typeface sansBold = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD);
    static Typeface mono = Typeface.MONOSPACE;
    static Typeface monoMedium = Typeface.MONOSPACE;
    private static boolean loaded;

    static void load(Context context) {
        if (loaded) return;
        loaded = true;
        display = font(context, "Fredoka.ttf", 600, display);
        sans = font(context, "IBMPlexSans.ttf", 400, sans);
        sansBold = font(context, "IBMPlexSans.ttf", 600, sansBold);
        mono = font(context, "IBMPlexMono-Regular.ttf", 0, mono);
        monoMedium = font(context, "IBMPlexMono-Medium.ttf", 0, monoMedium);
    }

    private static Typeface font(Context context, String file, int weight, Typeface fallback) {
        try {
            Typeface.Builder builder = new Typeface.Builder(context.getAssets(), "fonts/" + file);
            if (weight > 0) builder.setFontVariationSettings("'wght' " + weight).setWeight(weight);
            Typeface typeface = builder.build();
            return typeface != null ? typeface : fallback;
        } catch (RuntimeException e) {
            return fallback;
        }
    }

    private Fonts() {}
}
