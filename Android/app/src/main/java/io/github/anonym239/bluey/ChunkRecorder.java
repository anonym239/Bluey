package io.github.anonym239.bluey;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import java.io.File;
import java.nio.ByteBuffer;
import java.util.Locale;
import java.util.function.Consumer;

/**
 * Nimmt alles, was das Mikro während einer Sitzung hört, in kleine AAC-Dateien auf (je fünf Minuten),
 * damit eine ganztägige Sitzung nie eine riesige Datei baut und jedes Stück gleich transkribiert werden kann.
 */
final class ChunkRecorder {
    static final class Chunk {
        final String sessionID; final int index; final File file;
        /** Wann das Stück begann, damit seine Transkriptzeilen echte Uhrzeiten bekommen. */
        final double started;
        Chunk(String sessionID, int index, File file, double started) {
            this.sessionID = sessionID; this.index = index; this.file = file; this.started = started;
        }
    }

    static final double CHUNK_LENGTH = 300;

    /** Wird auf dem UI-Thread aufgerufen, wenn ein Stück fertig ist. */
    Consumer<Chunk> onChunk;

    private final File root;
    private final HandlerThread thread = new HandlerThread("Bluey Aufnahme");
    private final Handler queue;
    private final Handler ui = new Handler(Looper.getMainLooper());

    // Nur auf dem Aufnahme-Thread benutzt.
    private String sessionID;
    private int chunkIndex;
    private int sampleRate;
    private MediaCodec encoder;
    private MediaMuxer muxer;
    private int track = -1;
    private boolean muxing;
    private long samplesWritten;
    private double chunkStarted;
    private File chunkFile;

    ChunkRecorder(File filesDir) {
        root = new File(filesDir, "audio");
        thread.start();
        queue = new Handler(thread.getLooper());
    }

    static File folder(File filesDir, String session) { return new File(new File(filesDir, "audio"), session); }

    static String name(int index) { return String.format(Locale.ROOT, "chunk-%03d.m4a", index); }

    void start(String session) {
        queue.post(() -> {
            closeChunk();
            sessionID = session;
            chunkIndex = 0;
        });
    }

    /** Füttert 16-Bit-Mono-PCM vom Mikro (beliebiger Thread). */
    void append(short[] samples, int count, int rate) {
        short[] copy = java.util.Arrays.copyOf(samples, count);
        queue.post(() -> write(copy, rate));
    }

    void finish() {
        queue.post(() -> {
            closeChunk();
            sessionID = null;
        });
    }

    private void write(short[] samples, int rate) {
        if (sessionID == null) return;
        if (encoder != null && (SessionStore.now() - chunkStarted >= CHUNK_LENGTH || rate != sampleRate)) closeChunk();
        if (encoder == null && !openChunk(rate)) return;
        try {
            int offset = 0;
            while (offset < samples.length) {
                int inIndex = encoder.dequeueInputBuffer(10_000);
                if (inIndex < 0) { drain(false); continue; }
                ByteBuffer input = encoder.getInputBuffer(inIndex);
                if (input == null) break;
                input.clear();
                input.order(java.nio.ByteOrder.nativeOrder());
                int room = input.remaining() / 2;
                int n = Math.min(room, samples.length - offset);
                for (int i = 0; i < n; i++) input.putShort(samples[offset + i]);
                long time = samplesWritten * 1_000_000L / sampleRate;
                encoder.queueInputBuffer(inIndex, 0, n * 2, time, 0);
                samplesWritten += n;
                offset += n;
                drain(false);
            }
        } catch (RuntimeException e) {
            abandonChunk();
        }
    }

    private boolean openChunk(int rate) {
        File folder = new File(root, sessionID);
        if (!folder.isDirectory() && !folder.mkdirs()) return false;
        chunkIndex++;
        chunkFile = new File(folder, name(chunkIndex));
        sampleRate = rate;
        try {
            MediaFormat format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, rate, 1);
            format.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
            format.setInteger(MediaFormat.KEY_BIT_RATE, 48_000);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384);
            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC);
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            encoder.start();
            muxer = new MediaMuxer(chunkFile.getPath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            track = -1;
            muxing = false;
            samplesWritten = 0;
            chunkStarted = SessionStore.now();
            return true;
        } catch (Exception e) {
            abandonChunk();
            return false;
        }
    }

    private void drain(boolean endOfStream) {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        int waits = 0;
        while (true) {
            int outIndex = encoder.dequeueOutputBuffer(info, endOfStream ? 10_000 : 0);
            if (outIndex == MediaCodec.INFO_TRY_AGAIN_LATER) {
                if (!endOfStream || ++waits > 200) return;
                continue;
            }
            if (outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                track = muxer.addTrack(encoder.getOutputFormat());
                muxer.start();
                muxing = true;
                continue;
            }
            if (outIndex < 0) continue;
            ByteBuffer output = encoder.getOutputBuffer(outIndex);
            boolean config = (info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0;
            if (output != null && info.size > 0 && muxing && !config) {
                output.position(info.offset);
                output.limit(info.offset + info.size);
                muxer.writeSampleData(track, output, info);
            }
            encoder.releaseOutputBuffer(outIndex, false);
            if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) return;
        }
    }

    private void closeChunk() {
        if (encoder == null) return;
        boolean ok = false;
        try {
            int inIndex = encoder.dequeueInputBuffer(50_000);
            if (inIndex >= 0) {
                encoder.queueInputBuffer(inIndex, 0, 0, samplesWritten * 1_000_000L / Math.max(1, sampleRate),
                    MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                drain(true);
            }
            ok = muxing && samplesWritten > sampleRate;  // weniger als eine Sekunde lohnt sich nicht
        } catch (RuntimeException ignored) {}
        File file = chunkFile;
        int index = chunkIndex;
        double started = chunkStarted;
        String session = sessionID;
        release();
        if (ok && session != null) {
            Chunk chunk = new Chunk(session, index, file, started);
            ui.post(() -> { if (onChunk != null) onChunk.accept(chunk); });
        } else if (file != null) {
            file.delete();
            chunkIndex = Math.max(0, chunkIndex - 1);
        }
    }

    private void abandonChunk() {
        File file = chunkFile;
        release();
        if (file != null) file.delete();
    }

    private void release() {
        try { if (encoder != null) encoder.stop(); } catch (RuntimeException ignored) {}
        try { if (encoder != null) encoder.release(); } catch (RuntimeException ignored) {}
        try { if (muxer != null && muxing) muxer.stop(); } catch (RuntimeException ignored) {}
        try { if (muxer != null) muxer.release(); } catch (RuntimeException ignored) {}
        encoder = null;
        muxer = null;
        muxing = false;
        chunkFile = null;
    }
}
