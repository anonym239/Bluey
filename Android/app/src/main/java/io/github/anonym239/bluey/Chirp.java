package io.github.anonym239.bluey;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.util.Random;

/**
 * Ein winziges Cartoon-Zwitschern: ein paar weiche, runde, glockenartige Töne aus einer fröhlichen
 * Pentatonik, jeder mit einem kleinen „Boop“ nach oben am Anfang, wie ein kleines summendes Wesen.
 */
final class Chirp {
    private static final int RATE = 24000;
    private final Random random = new Random();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private float[] playing = new float[0];
    private long startedAt;
    private int pending;
    float volume = 1;

    /** Läuft ein Zwitschern? */
    boolean busy() { return pending > 0; }

    /** Lautstärke des Zwitscherns gerade, 0…1 (lässt den Mund mitwackeln). */
    double level() {
        float[] samples = playing;
        if (pending == 0 || samples.length == 0) return 0;
        int at = (int) ((SystemClock.elapsedRealtime() - startedAt) * RATE / 1000);
        if (at >= samples.length) return 0;
        double sum = 0;
        int n = 0;
        for (int i = Math.max(0, at - 512); i < Math.min(samples.length, at + 512); i++, n++) sum += samples[i] * samples[i];
        return n == 0 ? 0 : Math.min(1, Math.sqrt(sum / n) * 5 * volume);
    }

    static float[] make(int syllables, Random random) {
        // C-Dur-Pentatonik, zwei Oktaven hoch (C6…E7), damit es zusammen immer süß klingt.
        double[] scale = {1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0, 2349.3, 2637.0};
        int[] steps = {-1, 1, 1, 2};
        int index = 1 + random.nextInt(3);
        java.util.ArrayList<Float> out = new java.util.ArrayList<>();
        for (int i = 0; i < syllables; i++) {
            if (i > 0) index = Math.min(Math.max(index + steps[random.nextInt(steps.length)], 0), scale.length - 1);
            double note = scale[index] * .5;  // eine Oktave runter: runder, weniger schrill
            double duration = i == syllables - 1 ? .13 : .07 + random.nextDouble() * .02;
            int count = (int) (duration * RATE);
            double phase = 0;
            for (int n = 0; n < count; n++) {
                double time = (double) n / RATE;
                double t = (double) n / count;
                // Gleitet in den ersten 25 ms in den Ton, mit sanftem Wackeln auf dem letzten.
                double scoop = 1 - .18 * Math.exp(-time / .012);
                double wobble = i == syllables - 1 ? 1 + .012 * Math.sin(time * 2 * Math.PI * 18) : 1;
                phase += 2 * Math.PI * note * scoop * wobble / RATE;
                double attack = Math.min(1, time / .006);
                double envelope = attack * Math.exp(-t * 3.2) * (1 - Math.pow(t, 6));
                double wave = Math.sin(phase) + .12 * Math.sin(2 * phase);
                out.add((float) (wave * envelope * .26));
            }
            for (int n = 0; n < (int) (RATE * .028); n++) out.add(0f);
        }
        float[] samples = new float[out.size()];
        for (int i = 0; i < samples.length; i++) samples[i] = out.get(i);
        return samples;
    }

    /** Spielt ein Zwitschern; `done` läuft auf dem UI-Thread, wenn es fertig ist. */
    void play(int syllables, Runnable done) {
        float[] samples = make(syllables, random);
        short[] pcm = new short[samples.length];
        for (int i = 0; i < samples.length; i++) pcm[i] = (short) Math.max(-32767, Math.min(32767, samples[i] * 32767));
        AudioTrack track;
        try {
            track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setTransferMode(AudioTrack.MODE_STATIC)
                .setBufferSizeInBytes(pcm.length * 2).build();
            track.write(pcm, 0, pcm.length);
            track.setVolume(volume);
            track.play();
        } catch (Exception e) {
            if (done != null) ui.post(done);
            return;
        }
        playing = samples;
        startedAt = SystemClock.elapsedRealtime();
        pending++;
        long ms = samples.length * 1000L / RATE + 60;
        ui.postDelayed(() -> {
            pending = Math.max(0, pending - 1);
            try { track.release(); } catch (Exception ignored) {}
            if (done != null) done.run();
        }, ms);
    }
}
