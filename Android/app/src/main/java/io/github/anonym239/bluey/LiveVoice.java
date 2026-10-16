package io.github.anonym239.bluey;

import android.annotation.SuppressLint;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.NoiseSuppressor;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.function.Supplier;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * Eine Live-Sitzung mit der OpenAI Realtime API, direkt auf dem Handy. Ist er wach, bleibt das Mikro die ganze
 * Zeit an: Alles, was du sagst, wird Kontext, aber er bleibt still, bis du den Bildschirm hältst und fragst.
 * Er spricht nicht laut (außer du schaltest die Android-Stimme ein): Antworten sind Text (Sprechblasen am PC)
 * mit einem kleinen Zwitschern hier. Werkzeuge (Bildschirm ansehen, zeigen, bedienen) laufen auf dem PC.
 * Alles hier läuft auf dem UI-Thread, außer dem Mikrofon-Thread.
 */
final class LiveVoice {
    enum State { ASLEEP, WAKING, LISTENING, ASKING, THINKING, SPEAKING }

    interface ToolDone { void done(String output, String image); }
    interface ToolRunner { void run(String name, String arguments, ToolDone done); }

    State state = State.ASLEEP;

    /** Holt beim PC einen Kurzzeit-Schlüssel. Ruft mit null zurück, wenn es nicht klappt. */
    Consumer<Consumer<String>> requestToken;
    /** Führt ein Werkzeug auf dem PC aus: (Name, JSON-Argumente) → (Ausgabe, optionales JPEG als Base64). */
    ToolRunner runTool;
    /** Was er sagt, während es hereinströmt. `done` ist true, wenn die Antwort fertig ist. */
    java.util.function.BiConsumer<String, Boolean> onCaption = (t, d) -> {};
    Consumer<State> onStateChange = s -> {};
    Runnable onSessionStart = () -> {}, onSessionEnd = () -> {};
    java.util.function.BiConsumer<String, Boolean> onUserTurn = (i, a) -> {};
    interface Words { void heard(String itemID, String text, boolean asked); }
    Words onUserWords = (i, t, a) -> {};
    Consumer<String> onReply = t -> {}, onReport = t -> {};
    /** Ein Recherchebericht für die Karte auf dem Handy (nur im Modus ohne PC). */
    Consumer<OpenAi.Report> onReportCard = r -> {};
    Consumer<String> onResearchStart = q -> {};
    /** Kurze Fehlermeldungen für die Anzeige. */
    Consumer<String> onProblem = t -> {};
    /** Neueste Worte, für eine frische Verbindung, damit er in langen Sitzungen den Faden behält. */
    Supplier<String> resumeContext = () -> null;
    /** Schickt ein Paket an den PC (für die lokale KI: Audio und Halten/Loslassen). */
    Consumer<JSONObject> desktopSend = p -> {};

    /** Antwort des PCs auf realtimeToken, wenn er die KI selbst mit Ollama betreibt. */
    static final String LOCAL_TOKEN = "local:ollama";

    /** Nimmt das Audio der ganzen Sitzung auf, für eine richtige Transkription (Meeting-Notizen). */
    final ChunkRecorder recorder;
    final Chirp chirp = new Chirp();
    private final PhoneCredentials settings;
    private final SpeechOutput speech;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final OkHttpClient http = new OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS).build();

    /** True vom Aufwachen bis zum Beenden. Abgebrochene Verbindungen verbinden sich dann von selbst neu. */
    private boolean wantAwake, reconnecting;
    private volatile WebSocket socket;
    private boolean phoneSession, ready;
    /** Lokale KI auf dem PC (Ollama + Whisper): das Handy schickt nur Audio, der PC macht den Rest. */
    private volatile boolean local;
    private int generation;
    private String transcript = "";
    private boolean responseActive, sleepAfterReply, holding, askWhenReady, chirped, awaitingQuestion, speakingReply;
    private int toolsRunning;
    private final Set<String> askedItems = new HashSet<>();
    private volatile boolean recording;
    private Thread micThread;

    LiveVoice(ChunkRecorder recorder, PhoneCredentials settings, SpeechOutput speech) {
        this.recorder = recorder;
        this.settings = settings;
        this.speech = speech;
        chirp.volume = (float) settings.volume();
    }

    /** Lautstärke seines Zwitscherns gerade, 0…1. */
    double level() {
        // Liest die Android-Stimme gerade vor, bewegt er den Mund dazu.
        if (speakingReply && speech.speaking()) {
            double t = FaceView.now();
            return Math.max(chirp.level(), .35 + .3 * Math.sin(t * 17) * Math.sin(t * 5.3));
        }
        return chirp.level();
    }

    boolean phoneSession() { return phoneSession; }
    /** True, wenn die KI dieser Sitzung auf dem PC läuft (dann zeigt der PC die Sprechblasen selbst). */
    boolean localSession() { return local; }

    private void setState(State next) {
        if (next == state) return;
        state = next;
        onStateChange.accept(next);
    }

    // Aufwachen und Schlafen

    void toggle() { if (state == State.ASLEEP) wake(); else sleep(); }

    /** Die Aufrufer prüfen vorher die Mikrofon-Berechtigung. */
    void wake() {
        if (state != State.ASLEEP) return;
        wantAwake = true;
        phoneSession = settings.phoneMode();
        int run = ++generation;
        setState(State.WAKING);
        fetchToken(token -> {
            if (run != generation || state != State.WAKING) return;
            if (token == null || token.isEmpty()) {
                wantAwake = false;
                setState(State.ASLEEP);
                return;
            }
            if (token.equals(LOCAL_TOKEN)) connectLocal();
            else connect(token, run);
        });
    }

    private void fetchToken(Consumer<String> done) {
        if (phoneSession) {
            String key = settings.readOrEmpty();
            if (key.isEmpty()) onProblem.accept("Ohne PC brauche ich deinen OpenAI-Schlüssel. Trag ihn in den Einstellungen ein.");
            done.accept(key.isEmpty() ? null : key);
        } else if (requestToken == null) {
            done.accept(null);
        } else {
            requestToken.accept(token -> {
                if (token == null) onProblem.accept("Der PC hat keinen Sprach-Schlüssel geschickt. Ist dort ein OpenAI-Schlüssel eingetragen?");
                done.accept(token);
            });
        }
    }

    void sleep() {
        boolean wasRunning = wantAwake || socket != null;
        wantAwake = false;
        reconnecting = false;
        generation++;
        recorder.finish();
        if (wasRunning) onSessionEnd.run();
        askedItems.clear();
        awaitingQuestion = false;
        WebSocket old = socket;
        socket = null;
        if (old != null) old.close(1000, "Schlafen");
        if (local) desktopSend.accept(Json.obj("command", "voice", "text", "stop"));
        local = false;
        stopAudio();
        speech.stop();
        transcript = "";
        responseActive = sleepAfterReply = holding = askWhenReady = speakingReply = ready = false;
        toolsRunning = 0;
        setState(State.ASLEEP);
    }

    /** Ein schnelles Hallo (zum Testen der Lautstärke). */
    void sayHi() {
        if (local && ready) { desktopSend.accept(Json.obj("command", "voice", "text", "hi")); return; }
        if (socket == null || !ready) { if (state == State.ASLEEP) wake(); return; }
        send(Json.obj("type", "response.create",
            "response", Json.obj("instructions", "Antworte mit einem kurzen, fröhlichen Hallo in unter acht Wörtern.")));
    }

    // Halten zum Fragen

    /** Du hältst den Bildschirm gedrückt: Was du jetzt sagst, ist die Frage. */
    void beginAsk() {
        holding = true;
        onCaption.accept("", false);  // löscht seine letzte Blase
        if (speakingReply) { speech.stop(); speakingReply = false; }
        if (state == State.ASLEEP) { wake(); return; }
        if (local && ready) desktopSend.accept(Json.obj("command", "voice", "text", "hold"));
        if ((socket == null && !local) || !ready) return;
        if (state == State.LISTENING || state == State.SPEAKING) setState(State.ASKING);
    }

    /** Du lässt los: Er antwortet (oder tut es) mit allem Gehörten als Kontext. */
    void endAsk() {
        if (!holding) return;
        holding = false;
        if ((socket == null && !local) || !ready || state == State.WAKING) { askWhenReady = true; return; }
        ask();
    }

    private void ask() {
        askWhenReady = false;
        setState(State.THINKING);
        if (local) {
            desktopSend.accept(Json.obj("command", "voice", "text", "ask"));
            return;
        }
        awaitingQuestion = true;
        // Was du gerade gesagt hast abschließen (vielleicht mitten im Satz) und um eine Antwort bitten.
        send(Json.obj("type", "input_audio_buffer.commit"));
        send(Json.obj("type", "response.create"));
    }

    // Lokale KI auf dem PC (Ollama)

    private void connectLocal() {
        local = true;
        desktopSend.accept(Json.obj("command", "voice", "text", "start"));
        ready = false;
        opened();
    }

    /** Der PC ist (wieder) verbunden: eine laufende lokale Sitzung dort neu anmelden. */
    void desktopReconnected() {
        if (local && wantAwake) desktopSend.accept(Json.obj("command", "voice", "text", "start"));
    }

    /** Ereignisse der lokalen KI vom PC (Befehl "voiceEvent", Text = JSON). */
    void handleLocal(JSONObject event) {
        if (!local || event == null) return;
        String type = event.optString("type");
        switch (type) {
            case "turn": {
                String item = event.optString("item");
                onUserTurn.accept(item, event.optBoolean("asked"));
                break;
            }
            case "words":
                onUserWords.heard(event.optString("item"), event.optString("text"), event.optBoolean("asked"));
                break;
            case "thinking":
                setState(State.THINKING);
                break;
            case "delta": {
                transcript = event.optString("text", "");
                responseActive = true;
                if (!chirped && !transcript.trim().isEmpty()) {
                    chirped = true;
                    setState(State.SPEAKING);
                    int words = transcript.trim().split("\\s+").length;
                    chirp.play(Math.min(Math.max(words, 3), 5), this::finishIfQuiet);
                }
                onCaption.accept(transcript, false);
                break;
            }
            case "done": {
                transcript = event.optString("text", transcript);
                responseActive = false;
                chirped = false;
                if (!transcript.isEmpty()) {
                    onCaption.accept(transcript, true);
                    onReply.accept(transcript);
                    speakReply(transcript);
                }
                transcript = "";
                if (event.optBoolean("sleep")) sleepAfterReply = true;
                finishIfQuiet();
                break;
            }
            case "report":
                onReport.accept(event.optString("text"));
                break;
            case "error":
                responseActive = false;
                chirped = false;
                onProblem.accept(event.optString("text", "Die lokale KI hatte ein Problem."));
                finishIfQuiet();
                if (state == State.THINKING) setState(holding ? State.ASKING : State.LISTENING);
                break;
            case "sleep":
                sleepAfterReply = true;
                finishIfQuiet();
                break;
            default:
                break;
        }
    }

    // Verbindung

    private void connect(String token, int run) {
        Request request = new Request.Builder()
            .url("wss://api.openai.com/v1/realtime?model=" + AgentSession.MODEL)
            .header("Authorization", "Bearer " + token).build();
        ready = false;
        WebSocket[] mine = new WebSocket[1];
        mine[0] = http.newWebSocket(request, new WebSocketListener() {
            @Override public void onOpen(WebSocket ws, Response response) {
                ui.post(() -> {
                    if (run != generation || socket != ws) return;
                    if (phoneSession) ws.send(AgentSession.phoneConfiguration().toString());
                    else opened();
                });
            }
            @Override public void onMessage(WebSocket ws, String text) {
                JSONObject event = Json.parse(text);
                if (event != null) ui.post(() -> { if (run == generation && socket == ws) handle(event); });
            }
            @Override public void onFailure(WebSocket ws, Throwable error, Response response) {
                int code = response == null ? 0 : response.code();
                ui.post(() -> { if (run == generation && socket == ws) dropped(code); });
            }
            @Override public void onClosing(WebSocket ws, int code, String reason) { ws.close(code, reason); }
            @Override public void onClosed(WebSocket ws, int code, String reason) {
                ui.post(() -> { if (run == generation && socket == ws) dropped(0); });
            }
        });
        socket = mine[0];
    }

    /** Die Sitzung steht: Mikro an (beim ersten Mal), oder nach einem Neuaufbau einfach weitermachen. */
    private void opened() {
        if (ready) return;
        ready = true;
        if (reconnecting) {
            // Gleiche Sitzung, neue Verbindung: Mikro und Aufnahme liefen weiter. Erinnere ihn, was gesagt wurde.
            reconnecting = false;
            String context = resumeContext.get();
            if (context != null && !context.isEmpty()) {
                send(Json.obj("type", "conversation.item.create",
                    "item", Json.obj("type", "message", "role", "user", "content", Json.arr(Json.obj("type", "input_text",
                        "text", "(Kontext: was ich vorhin in dieser Sitzung gesagt habe, aus meinen Notizen. Nicht darauf antworten.)\n" + context)))));
            }
            if (askWhenReady) ask(); else setState(holding ? State.ASKING : State.LISTENING);
            return;
        }
        if (!startAudio()) {
            onProblem.accept("Ich konnte das Mikrofon nicht starten.");
            sleep();
            return;
        }
        onSessionStart.run();
        chirp.play(2, this::finishIfQuiet);
        if (askWhenReady) ask(); else setState(holding ? State.ASKING : State.LISTENING);
    }

    /** Die Verbindung ist weg. Mitten in einer Sitzung: neuen Schlüssel holen und weitermachen. */
    private void dropped(int code) {
        if (!wantAwake) { sleep(); return; }
        if (code == 401 || code == 403) {
            onProblem.accept(phoneSession ? "OpenAI hat den Schlüssel abgelehnt. Prüf ihn in den Einstellungen."
                : "OpenAI hat den Schlüssel vom PC abgelehnt.");
            sleep();
            return;
        }
        if (code == 429) {
            onProblem.accept("OpenAI-Limit erreicht. Prüf Guthaben und Abrechnung deines Kontos.");
            sleep();
            return;
        }
        if (!ready && state == State.WAKING) {
            onProblem.accept("Keine Verbindung zu OpenAI. Prüf das Internet.");
            sleep();
            return;
        }
        reconnect(0);
    }

    private void reconnect(int attempt) {
        socket = null;
        ready = false;
        responseActive = false;
        toolsRunning = 0;
        if (!wantAwake) return;
        reconnecting = true;
        int run = ++generation;
        fetchToken(token -> {
            if (run != generation || !wantAwake || socket != null) return;
            if (token != null && !token.isEmpty()) {
                connect(token, run);
            } else {
                // Der PC ist vielleicht kurz weg; weiter versuchen (die Aufnahme läuft solange weiter).
                ui.postDelayed(() -> { if (run == generation) reconnect(attempt + 1); }, (long) (Math.min(30, 2 + attempt * 3) * 1000));
            }
        });
    }

    private void send(JSONObject event) {
        WebSocket ws = socket;
        if (ws != null) ws.send(event.toString());
    }

    // Ereignisse

    private void handle(JSONObject event) {
        String type = event.optString("type");
        switch (type) {
            case "session.updated":
                if (phoneSession) opened();
                break;

            case "response.created":
                responseActive = true;
                transcript = "";
                chirped = false;
                break;

            case "response.output_text.delta":
            case "response.output_audio_transcript.delta": {
                String delta = event.optString("delta", "");
                transcript += delta;
                if (!chirped && !transcript.trim().isEmpty()) {
                    chirped = true;
                    setState(State.SPEAKING);
                    int words = transcript.trim().split("\\s+").length;
                    chirp.play(Math.min(Math.max(words, 3), 5), this::finishIfQuiet);
                }
                onCaption.accept(transcript, false);
                break;
            }

            case "input_audio_buffer.committed": {
                String item = Json.str(event, "item_id");
                if (item != null) {
                    boolean asked = holding || awaitingQuestion;
                    if (asked) askedItems.add(item);
                    if (awaitingQuestion && !holding) awaitingQuestion = false;
                    onUserTurn.accept(item, asked);
                }
                break;
            }

            case "conversation.item.input_audio_transcription.completed": {
                String item = Json.str(event, "item_id");
                String text = Json.str(event, "transcript");
                if (item != null && text != null) onUserWords.heard(item, text, askedItems.contains(item));
                break;
            }

            case "response.done": {
                responseActive = false;
                JSONObject response = event.optJSONObject("response");
                String status = response == null ? "" : response.optString("status");
                if (!transcript.isEmpty()) {
                    onCaption.accept(transcript, true);
                    onReply.accept(transcript);
                }
                if ("failed".equals(status)) {
                    JSONObject details = response.optJSONObject("status_details");
                    JSONObject error = details == null ? null : details.optJSONObject("error");
                    onProblem.accept("Antwort fehlgeschlagen" + (error != null ? ": " + error.optString("message", "") : "."));
                }
                JSONArray output = response == null ? null : response.optJSONArray("output");
                JSONArray calls = new JSONArray();
                if (output != null) for (int i = 0; i < output.length(); i++) {
                    JSONObject item = output.optJSONObject(i);
                    if (item != null && "function_call".equals(item.optString("type"))) calls.put(item);
                }
                if (calls.length() > 0) {
                    if (state != State.SPEAKING) setState(State.THINKING);
                    runTools(calls);
                } else {
                    speakReply(transcript);
                }
                finishIfQuiet();
                break;
            }

            case "error": {
                JSONObject error = event.optJSONObject("error");
                String code = error == null ? "" : error.optString("code");
                if ("input_audio_buffer_commit_empty".equals(code)) {
                    awaitingQuestion = false;
                    break;
                }
                if ("session_expired".equals(code)) { reconnect(0); break; }
                if (error != null && !"response_cancel_not_active".equals(code)) {
                    android.util.Log.w("Bluey", "Realtime-Fehler: " + error.optString("message"));
                }
                break;
            }

            default:
                break;
        }
    }

    private void speakReply(String reply) {
        if (reply.isEmpty() || !settings.spokenReplies()) return;
        int run = generation;
        speakingReply = true;
        boolean started = speech.speak(reply, ok -> {
            if (run != generation) return;
            speakingReply = false;
            finishIfQuiet();
        });
        if (!started) {
            speakingReply = false;
            onProblem.accept("Keine Android-Stimme verfügbar. Prüf die Sprachausgabe in den Android-Einstellungen.");
        }
    }

    private void runTools(JSONArray calls) {
        int[] remaining = {calls.length()};
        toolsRunning++;
        java.util.List<String> images = new java.util.ArrayList<>();
        int run = generation;
        for (int i = 0; i < calls.length(); i++) {
            JSONObject call = calls.optJSONObject(i);
            String name = call.optString("name");
            String callID = call.optString("call_id");
            String arguments = call.optString("arguments", "{}");
            if (name.equals("go_to_sleep")) sleepAfterReply = true;
            ToolDone finish = (output, image) -> ui.post(() -> {
                if (run != generation || socket == null) return;
                int marker = output.indexOf("\n---REPORT---\n");
                if (name.equals("web_research") && marker >= 0) onReport.accept(output.substring(marker + 14));
                send(Json.obj("type", "conversation.item.create",
                    "item", Json.obj("type", "function_call_output", "call_id", callID, "output", output)));
                if (image != null && !image.isEmpty()) images.add(image);
                remaining[0]--;
                if (remaining[0] == 0) {
                    toolsRunning = Math.max(0, toolsRunning - 1);
                    // Bildschirmfotos kommen als Bild vom Nutzer, damit er den Bildschirm wirklich sieht.
                    for (String jpeg : images) {
                        send(Json.obj("type", "conversation.item.create",
                            "item", Json.obj("type", "message", "role", "user",
                                "content", Json.arr(Json.obj("type", "input_image", "image_url", "data:image/jpeg;base64," + jpeg)))));
                    }
                    send(Json.obj("type", "response.create"));
                }
            });
            if (phoneSession) runLocalTool(name, arguments, finish);
            else if (runTool != null) runTool.run(name, arguments, finish);
            else finish.done("Der PC ist nicht verbunden.", null);
        }
    }

    /** Werkzeuge im Modus ohne PC. */
    private void runLocalTool(String name, String arguments, ToolDone done) {
        if (name.equals("go_to_sleep")) { done.done("Schlafe ein. Sag ein ganz kurzes Tschüss.", null); return; }
        if (!name.equals("web_research")) { done.done("Das geht ohne PC nicht.", null); return; }
        JSONObject args = Json.parse(arguments);
        String question = args == null ? "" : args.optString("question", "").trim();
        if (question.isEmpty()) { done.done("Was soll ich recherchieren?", null); return; }
        onResearchStart.accept(question);
        String key = settings.readOrEmpty();
        new Thread(() -> {
            try {
                OpenAi.Report report = OpenAi.research(key, question);
                ui.post(() -> onReportCard.accept(report));
                done.done("Der ganze Bericht ist jetzt als Karte auf dem Handy. Antworte mit EINER kurzen Zeile: die "
                    + "Kernaussage in deinen Worten. Wiederhol den Bericht nicht.\n---REPORT---\n" + report.plainText(), null);
            } catch (Exception e) {
                ui.post(() -> onReportCard.accept(null));
                done.done("Die Recherche ist fehlgeschlagen: " + e.getMessage() + ". Sag es dem Nutzer in ein paar Worten.", null);
            }
        }, "Bluey Recherche").start();
    }

    /** Zurück zum Zuhören, wenn er geantwortet und gezwitschert hat (oder schlafen, wenn er tschüss gesagt hat). */
    private void finishIfQuiet() {
        if (chirp.busy() || responseActive || toolsRunning > 0 || speakingReply) return;
        if (sleepAfterReply) { sleep(); return; }
        if (state == State.SPEAKING || state == State.THINKING) setState(holding ? State.ASKING : State.LISTENING);
    }

    // Audio

    @SuppressLint("MissingPermission")
    private boolean startAudio() {
        if (recording) return true;
        int[] rates = {24000, 48000, 16000, 44100};
        AudioRecord record = null;
        int rate = 0;
        for (int candidate : rates) {
            int minimum = AudioRecord.getMinBufferSize(candidate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if (minimum <= 0) continue;
            try {
                // Sprachkommunikation: mit Echounterdrückung, damit er sein Zwitschern nicht hört.
                AudioRecord r = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, candidate,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minimum, candidate / 5 * 2));
                if (r.getState() == AudioRecord.STATE_INITIALIZED) { record = r; rate = candidate; break; }
                r.release();
            } catch (Exception ignored) {}
        }
        if (record == null) return false;
        try {
            if (AcousticEchoCanceler.isAvailable()) { AcousticEchoCanceler aec = AcousticEchoCanceler.create(record.getAudioSessionId()); if (aec != null) aec.setEnabled(true); }
            if (NoiseSuppressor.isAvailable()) { NoiseSuppressor ns = NoiseSuppressor.create(record.getAudioSessionId()); if (ns != null) ns.setEnabled(true); }
            record.startRecording();
        } catch (Exception e) {
            record.release();
            return false;
        }
        recording = true;
        AudioRecord audio = record;
        int sampleRate = rate;
        micThread = new Thread(() -> micLoop(audio, sampleRate), "Bluey Mikrofon");
        micThread.start();
        return true;
    }

    private void micLoop(AudioRecord audio, int rate) {
        short[] buffer = new short[rate / 10];  // 100 ms
        Resampler resampler = new Resampler(rate, 24000);
        try {
            while (recording) {
                int count = audio.read(buffer, 0, buffer.length);
                if (count < 0) break;
                if (count == 0) continue;
                recorder.append(buffer, count, rate);
                WebSocket ws = socket;
                if ((ws == null && !local) || !ready || speech.speaking()) continue;
                short[] wire = resampler.convert(buffer, count);
                byte[] bytes = new byte[wire.length * 2];
                for (int i = 0; i < wire.length; i++) {
                    bytes[2 * i] = (byte) (wire[i] & 0xFF);
                    bytes[2 * i + 1] = (byte) ((wire[i] >> 8) & 0xFF);
                }
                if (local) {
                    String audio64 = Base64.encodeToString(bytes, Base64.NO_WRAP);
                    ui.post(() -> { if (local) desktopSend.accept(Json.obj("command", "audio", "audio", audio64)); });
                } else if (ws != null && ws.queueSize() < 2 * 1024 * 1024) {
                    ws.send(Json.obj("type", "input_audio_buffer.append", "audio", Base64.encodeToString(bytes, Base64.NO_WRAP)).toString());
                }
            }
        } catch (Exception ignored) {
        } finally {
            try { audio.stop(); } catch (Exception ignored) {}
            audio.release();
        }
    }

    private void stopAudio() {
        recording = false;
        micThread = null;
    }

    void setVolume(double volume) {
        settings.setVolume(volume);
        chirp.volume = (float) volume;
    }

    void destroy() {
        sleep();
        http.dispatcher().executorService().shutdown();
        http.connectionPool().evictAll();
    }

    /** Einfache lineare Umrechnung der Abtastrate (Mikro-Rate → 24 kHz für OpenAI). */
    static final class Resampler {
        private final double step;
        private double position;
        private short previous;

        Resampler(int from, int to) { step = (double) from / to; }

        short[] convert(short[] input, int count) {
            if (step == 1) return java.util.Arrays.copyOf(input, count);
            int capacity = (int) Math.ceil((count - position) / step) + 1;
            short[] out = new short[Math.max(0, capacity)];
            int n = 0;
            while (position < count && n < out.length) {
                int i = (int) Math.floor(position);
                double frac = position - i;
                short a = i == 0 ? (i < count ? input[0] : previous) : input[i - 1];
                short b = input[Math.min(i, count - 1)];
                if (i == 0) a = previous;
                out[n++] = (short) Math.round(a + (b - a) * frac);
                position += step;
            }
            position -= count;
            previous = input[count - 1];
            return java.util.Arrays.copyOf(out, n);
        }
    }
}
