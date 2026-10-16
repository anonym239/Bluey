package io.github.anonym239.bluey;

import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

/** Hält alle Sitzungen auf dem Handy, als eine JSON-Datei im App-Ordner. Nur vom UI-Thread benutzen. */
final class SessionStore {
    /** Neueste zuerst. */
    final List<BlueySession> sessions = new ArrayList<>();
    String currentID;

    private final File file;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable saveWork = this::save;
    private final Runnable syncWork = this::sync;
    private final Set<String> dirty = new HashSet<>();
    private final List<Runnable> observers = new ArrayList<>();

    /** Wird mit geänderten Sitzungen aufgerufen, ein paar Sekunden nachdem sich die Änderungen gelegt haben. */
    Consumer<List<BlueySession>> onSync;

    SessionStore(File folder) {
        file = new File(folder, "sessions.json");
        try {
            if (file.exists()) {
                JSONArray saved = new JSONArray(new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
                for (int i = 0; i < saved.length(); i++) {
                    BlueySession s = BlueySession.fromJson(saved.getJSONObject(i));
                    // Eine durch Absturz offene Sitzung endet bei ihrer letzten Zeile.
                    if (s.ended == null) s.ended = s.entries.isEmpty() ? s.started : s.entries.get(s.entries.size() - 1).time;
                    sessions.add(s);
                }
            }
        } catch (Exception ignored) {}
    }

    static double now() { return System.currentTimeMillis() / 1000.0; }

    void observe(Runnable observer) { observers.add(observer); }
    void unobserve(Runnable observer) { observers.remove(observer); }
    private void changed() { for (Runnable r : new ArrayList<>(observers)) r.run(); }

    BlueySession find(String id) {
        if (id == null) return null;
        for (BlueySession s : sessions) if (s.id.equals(id)) return s;
        return null;
    }

    BlueySession current() { return find(currentID); }

    void start() {
        end();
        BlueySession session = new BlueySession(now());
        sessions.add(0, session);
        currentID = session.id;
        save();
        changed();
    }

    void end() {
        BlueySession session = current();
        if (session == null) return;
        currentID = null;
        boolean empty = true;
        for (BlueySession.Entry e : session.entries) if (e.text != null && !e.text.isEmpty()) { empty = false; break; }
        if (empty && session.transcribing() == 0 && now() - session.started < 20) {
            sessions.remove(session);  // ein paar Sekunden, nichts gesagt: nicht behalten
        } else {
            session.ended = now();
            session.entries.removeIf(e -> e.text == null || e.text.isEmpty());
            dirty.add(session.id);
            scheduleSync();
        }
        save();
        changed();
    }

    /** Hält einen Platz für etwas, das du gesagt hast, in der richtigen Reihenfolge. Die Worte kommen kurz danach. */
    void placeholder(String itemID, boolean asked) {
        update(currentID, s -> {
            for (BlueySession.Entry e : s.entries) if (itemID.equals(e.itemID)) return;
            BlueySession.Entry e = new BlueySession.Entry(asked ? BlueySession.Entry.Kind.ASKED : BlueySession.Entry.Kind.HEARD, "", now());
            e.itemID = itemID;
            s.entries.add(e);
        });
    }

    void heard(String itemID, String text, boolean asked) {
        String clean = text.trim();
        update(currentID, s -> {
            for (BlueySession.Entry e : s.entries) {
                if (itemID.equals(e.itemID)) {
                    e.text = clean;
                    if (asked) e.kind = BlueySession.Entry.Kind.ASKED;
                    return;
                }
            }
            if (!clean.isEmpty()) {
                BlueySession.Entry e = new BlueySession.Entry(asked ? BlueySession.Entry.Kind.ASKED : BlueySession.Entry.Kind.HEARD, clean, now());
                e.itemID = itemID;
                s.entries.add(e);
            }
        });
    }

    void reply(String text) { add(BlueySession.Entry.Kind.REPLY, text); }
    void report(String text) { add(BlueySession.Entry.Kind.REPORT, text); }

    private void add(BlueySession.Entry.Kind kind, String text) {
        String clean = text.trim();
        if (clean.isEmpty()) return;
        update(currentID, s -> s.entries.add(new BlueySession.Entry(kind, clean, now())));
    }

    // Richtiges Transkript (aufgenommenes Audio, auf dem Computer oder bei OpenAI transkribiert)

    void addPending(String session, int index, double started) {
        update(session, s -> {
            for (BlueySession.Pending p : s.pending) if (p.index == index) return;
            s.pending.add(new BlueySession.Pending(index, started));
        });
    }

    /** Ein Segment: Sprecher, Startsekunde im Stück, Text. */
    static final class Segment {
        final String speaker; final double start; final String text;
        Segment(String speaker, double start, String text) { this.speaker = speaker; this.start = start; this.text = text; }
    }

    /** Fügt ein transkribiertes Stück hinzu: eine Zeile pro Sprecherwechsel, zur echten Uhrzeit. */
    void transcribed(String session, int index, double started, List<Segment> segments) {
        update(session, s -> {
            s.pending.removeIf(p -> p.index == index);
            for (Segment segment : segments) {
                String text = segment.text.trim();
                if (text.isEmpty()) continue;
                BlueySession.Entry e = new BlueySession.Entry(BlueySession.Entry.Kind.TRANSCRIPT, text, started + segment.start);
                e.speaker = segment.speaker;
                s.entries.add(e);
            }
            Collections.sort(s.entries, (a, b) -> Double.compare(a.time, b.time));
        });
    }

    void setNotesPath(String session, String path) {
        BlueySession s = find(session);
        if (s == null || path.equals(s.notesPath)) return;
        s.notesPath = path;
        scheduleSave();
        changed();
    }

    /** Neueste Worte dieser Sitzung, damit eine neue Verbindung weiß, worum es ging. */
    String recentText(int limit) {
        BlueySession s = current();
        if (s == null) return null;
        StringBuilder text = new StringBuilder();
        for (BlueySession.Entry e : s.displayEntries()) {
            if (e.kind == BlueySession.Entry.Kind.REPORT) continue;
            if (text.length() > 0) text.append('\n');
            if (e.kind == BlueySession.Entry.Kind.REPLY) text.append("Bluey: ");
            text.append(e.text);
        }
        if (text.length() == 0) return null;
        return text.length() > limit ? text.substring(text.length() - limit) : text.toString();
    }

    /** Schickt die letzten Sitzungen erneut (nachdem das Handy wieder verbunden ist). */
    void resyncRecent() {
        double cutoff = now() - 3 * 86_400;
        for (BlueySession s : sessions) if (s.started > cutoff) dirty.add(s.id);
        scheduleSync();
    }

    void delete(String id) {
        if (id.equals(currentID)) currentID = null;
        sessions.removeIf(s -> s.id.equals(id));
        save();
        changed();
    }

    private void scheduleSync() {
        ui.removeCallbacks(syncWork);
        ui.postDelayed(syncWork, 6000);
    }

    private void sync() {
        List<BlueySession> changed = new ArrayList<>();
        for (BlueySession s : sessions) if (dirty.contains(s.id)) changed.add(s);
        dirty.clear();
        if (!changed.isEmpty() && onSync != null) onSync.accept(changed);
    }

    private interface Change { void apply(BlueySession s); }

    private void update(String id, Change change) {
        BlueySession s = find(id);
        if (s == null) return;
        change.apply(s);
        dirty.add(s.id);
        scheduleSync();
        scheduleSave();
        changed();
    }

    private void scheduleSave() {
        ui.removeCallbacks(saveWork);
        ui.postDelayed(saveWork, 1000);
    }

    void save() {
        ui.removeCallbacks(saveWork);
        JSONArray all = new JSONArray();
        for (BlueySession s : sessions) all.put(s.toJson());
        File temp = new File(file.getPath() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(temp)) {
            out.write(all.toString().getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        } catch (Exception e) {
            return;
        }
        if (!temp.renameTo(file)) temp.delete();
    }
}
