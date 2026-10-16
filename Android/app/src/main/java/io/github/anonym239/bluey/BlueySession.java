package io.github.anonym239.bluey;

import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

/** Alles aus einer Sitzung vom Aufwachen bis zum Einschlafen. Zeiten in Sekunden seit 1970. */
final class BlueySession {
    /** Eine Zeile: das richtige Transkript (mit Sprechern), das grobe Live-Transkript, eine Frage, seine Antworten und Rechercheberichte. */
    static final class Entry {
        enum Kind { HEARD, ASKED, REPLY, REPORT, TRANSCRIPT }

        String id = UUID.randomUUID().toString();
        Kind kind;
        String text;
        double time;
        /** Das Realtime-Element, aus dem die Zeile kommt, damit die Worte nachgetragen werden können. */
        String itemID;
        /** Wer sprach, für richtige Transkriptzeilen ("A", "B", … je Fünf-Minuten-Stück). */
        String speaker;

        Entry(Kind kind, String text, double time) {
            this.kind = kind;
            this.text = text;
            this.time = time;
        }

        JSONObject toJson() {
            JSONObject o = Json.obj("id", id, "kind", kind.name().toLowerCase(Locale.ROOT), "text", text, "time", time);
            if (itemID != null) Json.put(o, "itemID", itemID);
            if (speaker != null) Json.put(o, "speaker", speaker);
            return o;
        }

        static Entry fromJson(JSONObject o) {
            Kind kind;
            try { kind = Kind.valueOf(o.optString("kind", "heard").toUpperCase(Locale.ROOT)); } catch (IllegalArgumentException e) { kind = Kind.HEARD; }
            Entry e = new Entry(kind, o.optString("text", ""), o.optDouble("time", 0));
            e.id = o.optString("id", e.id);
            e.itemID = Json.str(o, "itemID");
            e.speaker = Json.str(o, "speaker");
            return e;
        }
    }

    /** Ein aufgenommenes Stück, das noch transkribiert werden muss. */
    static final class Pending {
        int index;
        double started;
        Pending(int index, double started) { this.index = index; this.started = started; }
    }

    String id = UUID.randomUUID().toString();
    double started;
    Double ended;
    final List<Entry> entries = new ArrayList<>();
    /** Wo der Computer die Meeting-Notizen dieser Sitzung gespeichert hat. */
    String notesPath;
    final List<Pending> pending = new ArrayList<>();

    BlueySession(double started) { this.started = started; }

    int questionCount() {
        int n = 0;
        for (Entry e : entries) if (e.kind == Entry.Kind.ASKED) n++;
        return n;
    }

    int transcribing() { return pending.size(); }

    double duration(double now) { return (ended != null ? ended : now) - started; }

    /** Was angezeigt wird: das richtige Transkript, wo es existiert, danach die groben Live-Zeilen, plus Fragen, Antworten und Berichte. */
    List<Entry> displayEntries() {
        double properUntil = Double.NEGATIVE_INFINITY;
        for (Entry e : entries) if (e.kind == Entry.Kind.TRANSCRIPT) properUntil = Math.max(properUntil, e.time);
        List<Entry> out = new ArrayList<>();
        for (Entry e : entries) {
            if (e.text == null || e.text.isEmpty()) continue;
            if (e.kind == Entry.Kind.HEARD && e.time <= properUntil) continue;
            out.add(e);
        }
        Collections.sort(out, (a, b) -> Double.compare(a.time, b.time));
        return out;
    }

    /** Eine kurze Zeile für die Liste: die erste Frage oder das Erste, was gesagt wurde. */
    String summary() {
        for (Entry e : entries) if (e.kind == Entry.Kind.ASKED && e.text != null && !e.text.isEmpty()) return e.text;
        for (Entry e : displayEntries()) if (e.kind == Entry.Kind.TRANSCRIPT || e.kind == Entry.Kind.HEARD) return e.text;
        return "Noch nichts gesagt";
    }

    /** Klartext zum Teilen. */
    String exportText() {
        SimpleDateFormat clock = new SimpleDateFormat("HH:mm:ss", Locale.GERMANY);
        List<String> lines = new ArrayList<>();
        lines.add("Bluey-Sitzung, " + formatDate(started));
        lines.add("");
        for (Entry e : displayEntries()) {
            String who;
            switch (e.kind) {
                case TRANSCRIPT: who = "Sprecher " + (e.speaker == null ? "?" : e.speaker); break;
                case HEARD: who = "Du"; break;
                case ASKED: who = "Du hast gefragt"; break;
                case REPLY: who = "Bluey"; break;
                default: who = "Recherche"; break;
            }
            lines.add("[" + clock.format(new Date((long) (e.time * 1000))) + "] " + who + ": " + e.text);
        }
        return String.join("\n", lines);
    }

    static String formatDate(double time) {
        return new SimpleDateFormat("d. MMM yyyy, HH:mm", Locale.GERMANY).format(new Date((long) (time * 1000)));
    }

    static String formatDuration(double seconds) {
        int s = (int) Math.max(0, seconds);
        return s >= 3600 ? String.format(Locale.ROOT, "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
            : String.format(Locale.ROOT, "%d:%02d", s / 60, s % 60);
    }

    /** Das Format, das der Computer für notes.md und session.json erwartet. */
    JSONObject notesJson() {
        JSONArray list = new JSONArray();
        for (Entry e : displayEntries()) {
            JSONObject o = Json.obj("kind", e.kind.name().toLowerCase(Locale.ROOT), "text", e.text, "time", e.time);
            if (e.speaker != null) Json.put(o, "speaker", e.speaker);
            list.put(o);
        }
        JSONObject json = Json.obj("id", id, "started", started, "transcribing", transcribing(), "entries", list);
        if (ended != null) Json.put(json, "ended", ended);
        return json;
    }

    JSONObject toJson() {
        JSONArray list = new JSONArray();
        for (Entry e : entries) list.put(e.toJson());
        JSONArray chunks = new JSONArray();
        for (Pending p : pending) chunks.put(Json.obj("index", p.index, "started", p.started));
        JSONObject o = Json.obj("id", id, "started", started, "entries", list, "pending", chunks);
        if (ended != null) Json.put(o, "ended", ended);
        if (notesPath != null) Json.put(o, "notesPath", notesPath);
        return o;
    }

    static BlueySession fromJson(JSONObject o) {
        BlueySession s = new BlueySession(o.optDouble("started", 0));
        s.id = o.optString("id", s.id);
        if (o.has("ended") && !o.isNull("ended")) s.ended = o.optDouble("ended");
        s.notesPath = Json.str(o, "notesPath");
        JSONArray list = o.optJSONArray("entries");
        if (list != null) for (int i = 0; i < list.length(); i++) {
            JSONObject e = list.optJSONObject(i);
            if (e != null) s.entries.add(Entry.fromJson(e));
        }
        JSONArray chunks = o.optJSONArray("pending");
        if (chunks != null) for (int i = 0; i < chunks.length(); i++) {
            JSONObject p = chunks.optJSONObject(i);
            if (p != null) s.pending.add(new Pending(p.optInt("index"), p.optDouble("started")));
        }
        return s;
    }
}
