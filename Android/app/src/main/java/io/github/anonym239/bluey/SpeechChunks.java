package io.github.anonym239.bluey;

import java.util.ArrayList;
import java.util.List;

/** Teilt Antworttext für die Android-Stimme in erlaubte Längen, ohne Zeichen oder Ersatzpaare zu zerreißen. */
final class SpeechChunks {
    static List<String> split(String text, int maximum) {
        if (maximum < 2) throw new IllegalArgumentException("Grenze muss mindestens zwei sein");
        List<String> parts = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int end = Math.min(text.length(), start + maximum);
            if (end < text.length() && Character.isHighSurrogate(text.charAt(end - 1)) && Character.isLowSurrogate(text.charAt(end))) end--;
            if (end < text.length()) {
                for (int i = end - 1; i > start + maximum / 2; i--) {
                    if (Character.isWhitespace(text.charAt(i))) { end = i + 1; break; }
                }
            }
            parts.add(text.substring(start, end));
            start = end;
        }
        return parts;
    }

    private SpeechChunks() {}
}
