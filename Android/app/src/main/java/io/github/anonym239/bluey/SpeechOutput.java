package io.github.anonym239.bluey;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;

/** Optional: liest Antworten mit der Android-Stimme vor (braucht keinen zweiten Schlüssel). */
final class SpeechOutput {
    private TextToSpeech tts;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private volatile boolean ready, speaking;
    private volatile long muteUntil;
    private String current = "", last = "";
    private long next;
    private Consumer<Boolean> completion;

    SpeechOutput(Context context) {
        tts = new TextToSpeech(context.getApplicationContext(), status -> {
            if (status != TextToSpeech.SUCCESS) return;
            int result = tts.setLanguage(Locale.GERMANY);
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) result = tts.setLanguage(Locale.getDefault());
            ready = result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED;
        });
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) {}
            @Override public void onDone(String id) { ui.post(() -> finished(id, true)); }
            @Override @Deprecated public void onError(String id) { ui.post(() -> finished(id, false)); }
            @Override public void onError(String id, int code) { ui.post(() -> finished(id, false)); }
            @Override public void onStop(String id, boolean interrupted) { ui.post(() -> finished(id, false)); }
        });
    }

    /** True, solange er spricht (plus ein kurzes Echo danach), damit das Mikro sich nicht selbst hört. */
    boolean speaking() { return speaking || SystemClock.elapsedRealtime() < muteUntil; }

    boolean speak(String text, Consumer<Boolean> done) {
        stop();
        if (!ready || text.isEmpty()) return false;
        current = "bluey-" + (++next);
        completion = done;
        speaking = true;
        List<String> parts = SpeechChunks.split(text, TextToSpeech.getMaxSpeechInputLength());
        last = current + "-" + (parts.size() - 1);
        for (int i = 0; i < parts.size(); i++) {
            if (tts.speak(parts.get(i), i == 0 ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD, new Bundle(), current + "-" + i) != TextToSpeech.SUCCESS) {
                stop();
                return false;
            }
        }
        String utterance = last;
        ui.postDelayed(() -> finished(utterance, false), Math.min(600_000L, 10_000L + text.length() * 100L));
        return true;
    }

    private void finished(String id, boolean success) {
        if (current.isEmpty() || (success ? !id.equals(last) : !id.startsWith(current + "-"))) return;
        current = last = "";
        speaking = false;
        if (!success) tts.stop();
        muteUntil = SystemClock.elapsedRealtime() + 300;
        Consumer<Boolean> done = completion;
        completion = null;
        if (done != null) done.accept(success);
    }

    void stop() {
        current = last = "";
        completion = null;
        speaking = false;
        muteUntil = 0;
        tts.stop();
    }

    void destroy() {
        stop();
        tts.shutdown();
    }
}
