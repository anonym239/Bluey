package io.github.anonym239.bluey;

import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Schickt aufgenommene Stücke zum PC (der sie transkribiert und als Meeting-Notizen speichert) und hält
 * dessen Notizdateien aktuell. Im Modus ohne PC transkribiert das Handy selbst, wenn ein Schlüssel da ist.
 */
final class NotesSync {
    private final File filesDir;
    private final SessionStore store;
    private final DesktopLink link;
    private final PhoneCredentials settings;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Set<String> inFlight = new HashSet<>();

    NotesSync(File filesDir, SessionStore store, DesktopLink link, PhoneCredentials settings) {
        this.filesDir = filesDir;
        this.store = store;
        this.link = link;
        this.settings = settings;
    }

    private File chunkFile(String session, int index) {
        return new File(ChunkRecorder.folder(filesDir, session), ChunkRecorder.name(index));
    }

    void upload(String session, int index, double started) {
        String key = session + "-" + index;
        BlueySession s = store.find(session);
        if (inFlight.contains(key) || s == null) return;
        File file = chunkFile(session, index);
        if (!file.exists()) {
            store.transcribed(session, index, started, new ArrayList<>());  // nichts zu schicken
            return;
        }
        if (link.connected) {
            sendToDesktop(key, s, index, started, file);
        } else if (settings.phoneMode() && settings.hasKey()) {
            transcribeHere(key, session, index, started, file);
        }
    }

    private void sendToDesktop(String key, BlueySession session, int index, double started, File file) {
        byte[] audio;
        try { audio = Files.readAllBytes(file.toPath()); } catch (Exception e) { return; }
        inFlight.add(key);
        JSONObject meta = Json.obj("session", session.id, "index", index, "started", started, "sessionStarted", session.started);
        JSONObject packet = Json.obj("command", "transcribe", "audio", Base64.encodeToString(audio, Base64.NO_WRAP), "text", meta.toString());
        link.request(packet, reply -> {
            inFlight.remove(key);
            JSONObject json = reply == null ? null : Json.parse(Json.str(reply, "text"));
            if (json == null) {
                // Der PC konnte gerade nicht: gleich nochmal versuchen.
                ui.postDelayed(() -> upload(session.id, index, started), 30_000);
                return;
            }
            store.transcribed(session.id, index, started, segments(json.optJSONArray("segments")));
            String path = Json.str(json, "notesPath");
            if (path != null) store.setNotesPath(session.id, path);
            file.delete();  // der PC behält das Audio
        });
    }

    private void transcribeHere(String key, String session, int index, double started, File file) {
        inFlight.add(key);
        String apiKey = settings.readOrEmpty();
        new Thread(() -> {
            List<SessionStore.Segment> segments = null;
            try { segments = OpenAi.transcribe(apiKey, file); } catch (Exception ignored) {}
            List<SessionStore.Segment> result = segments;
            ui.post(() -> {
                inFlight.remove(key);
                if (result == null) {
                    ui.postDelayed(() -> upload(session, index, started), 60_000);
                    return;
                }
                store.transcribed(session, index, started, result);
                file.delete();
            });
        }, "Bluey Transkription").start();
    }

    static List<SessionStore.Segment> segments(JSONArray list) {
        List<SessionStore.Segment> out = new ArrayList<>();
        if (list == null) return out;
        for (int i = 0; i < list.length(); i++) {
            JSONObject s = list.optJSONObject(i);
            if (s != null) out.add(new SessionStore.Segment(s.optString("speaker", "?"), s.optDouble("start", 0), s.optString("text", "")));
        }
        return out;
    }

    void retryPending() {
        for (BlueySession s : new ArrayList<>(store.sessions)) {
            for (BlueySession.Pending p : new ArrayList<>(s.pending)) upload(s.id, p.index, p.started);
        }
    }

    /** Schickt Sitzungen an den PC, der daraus notes.md und session.json schreibt. */
    void send(List<BlueySession> sessions) {
        if (!link.connected) return;
        for (BlueySession s : sessions) {
            link.request(Json.obj("command", "notes", "text", s.notesJson().toString()), reply -> {
                String path = reply == null ? null : Json.str(reply, "text");
                if (path != null) store.setNotesPath(s.id, path);
            });
        }
    }
}
