package io.github.anonym239.bluey;

/** Gleiche Namen wie im Protokoll (`mood` im Face-Paket). */
enum Mood {
    LISTENING, RESTING, THINKING, TALKING, POINTING, HAPPY, SLEEPY;

    String wire() { return name().toLowerCase(java.util.Locale.ROOT); }

    static Mood from(String value) {
        if (value == null) return LISTENING;
        for (Mood mood : values()) if (mood.wire().equals(value)) return mood;
        return LISTENING;
    }
}
