package io.github.anonym239.bluey;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * Was der Computer im PC-Modus übernimmt, kann das Handy im Modus ohne PC mit seinem eigenen Schlüssel:
 * Web-Recherche (Responses API mit Websuche) und Transkription mit Sprechern. Blockierend: im Hintergrund aufrufen.
 */
final class OpenAi {
    static final String RESEARCH_MODEL = "gpt-5.5";
    static final String TRANSCRIBE_MODEL = "gpt-4o-transcribe-diarize";
    static final String TRANSCRIBE_FALLBACK = "gpt-transcribe";

    static final OkHttpClient HTTP = new OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS).readTimeout(300, TimeUnit.SECONDS).writeTimeout(300, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS).build();

    /** Ein kurzer recherchierter Bericht: Titel, bis zu vier Absätze und Quellen. */
    static final class Report {
        String title;
        final List<String> paragraphs = new ArrayList<>();
        final List<String[]> sources = new ArrayList<>();  // {Titel, URL}

        String plainText() {
            StringBuilder b = new StringBuilder(title);
            for (String p : paragraphs) b.append("\n\n").append(p);
            return b.toString();
        }
    }

    static Report research(String key, String question) throws IOException {
        JSONObject body = Json.obj(
            "model", RESEARCH_MODEL,
            "reasoning", Json.obj("effort", "low"),
            "tools", Json.arr(Json.obj("type", "web_search")),
            "instructions", "Recherchiere die Frage im Web und schreib einen kurzen, freundlichen Bericht für einen "
                + "beschäftigten Menschen, auf Deutsch. Erste Zeile: ein schlichter Titel unter acht Wörtern. Dann ein "
                + "bis vier kurze Absätze (höchstens vier), zuerst die direkte Antwort, dann die nützlichsten Details. "
                + "Nur Klartext: kein Markdown, keine Überschriften, keine Aufzählungen und keine Links oder Quellenangaben im Text.",
            "input", question);
        Request request = new Request.Builder().url("https://api.openai.com/v1/responses")
            .header("Authorization", "Bearer " + key)
            .post(RequestBody.create(body.toString(), MediaType.get("application/json"))).build();
        String text;
        try (Response response = HTTP.newCall(request).execute()) {
            String data = response.body() == null ? "" : response.body().string();
            if (response.code() != 200) throw new IOException("Recherche fehlgeschlagen (" + response.code() + ")");
            text = data;
        }
        JSONObject json = Json.parse(text);
        if (json == null) throw new IOException("Leere Antwort");
        StringBuilder out = new StringBuilder();
        Report report = new Report();
        JSONArray output = json.optJSONArray("output");
        if (output != null) for (int i = 0; i < output.length(); i++) {
            JSONObject item = output.optJSONObject(i);
            if (item == null || !"message".equals(item.optString("type"))) continue;
            JSONArray content = item.optJSONArray("content");
            if (content == null) continue;
            for (int j = 0; j < content.length(); j++) {
                JSONObject part = content.optJSONObject(j);
                if (part == null) continue;
                out.append(part.optString("text", ""));
                JSONArray notes = part.optJSONArray("annotations");
                if (notes != null) for (int k = 0; k < notes.length(); k++) {
                    JSONObject note = notes.optJSONObject(k);
                    String url = note == null ? null : Json.str(note, "url");
                    if (url == null) continue;
                    url = url.replaceAll("[?&]utm_source=[^&]*$", "");
                    boolean seen = false;
                    for (String[] s : report.sources) if (s[1].equals(url)) seen = true;
                    if (!seen && report.sources.size() < 5) report.sources.add(new String[]{note.optString("title", url), url});
                }
            }
        }
        String clean = cleanMarkdown(out.toString());
        List<String> blocks = new ArrayList<>();
        for (String line : clean.split("\n")) if (!line.trim().isEmpty()) blocks.add(line.trim());
        if (blocks.isEmpty()) throw new IOException("Leere Antwort");
        report.title = blocks.get(0);
        for (int i = 1; i < blocks.size() && report.paragraphs.size() < 4; i++) report.paragraphs.add(blocks.get(i));
        return report;
    }

    /** Entfernt Quellen wie "([seite.de](https://…))" und übriges Markdown. */
    static String cleanMarkdown(String text) {
        return text.replaceAll("\\s*\\(\\[[^\\]]*\\]\\([^)]*\\)\\)", "")
            .replaceAll("\\[([^\\]]*)\\]\\([^)]*\\)", "$1")
            .replaceAll("\\s*\\[https?://[^\\]]*\\]", "")
            .replace("**", "").replace("#", "");
    }

    /** Transkribiert ein Stück mit Sprechern (oder ohne, wenn das Modell nicht will). */
    static List<SessionStore.Segment> transcribe(String key, File audio) throws IOException {
        try {
            JSONObject json = post(key, audio, TRANSCRIBE_MODEL, "diarized_json", true);
            List<SessionStore.Segment> raw = new ArrayList<>();
            JSONArray segments = json.optJSONArray("segments");
            if (segments != null) for (int i = 0; i < segments.length(); i++) {
                JSONObject s = segments.optJSONObject(i);
                if (s == null) continue;
                raw.add(new SessionStore.Segment(s.optString("speaker", "?"), s.optDouble("start", 0), s.optString("text", "").trim()));
            }
            return joinTurns(raw, segments);
        } catch (IOException e) {
            JSONObject json = post(key, audio, TRANSCRIBE_FALLBACK, "json", false);
            String text = json.optString("text", "").trim();
            List<SessionStore.Segment> list = new ArrayList<>();
            if (!text.isEmpty()) list.add(new SessionStore.Segment("?", 0, text));
            return list;
        }
    }

    /** Fügt aufeinanderfolgende Stücke eines Sprechers zu einem Beitrag zusammen. */
    static List<SessionStore.Segment> joinTurns(List<SessionStore.Segment> raw, JSONArray segments) {
        List<SessionStore.Segment> turns = new ArrayList<>();
        double lastEnd = -10;
        for (int i = 0; i < raw.size(); i++) {
            SessionStore.Segment s = raw.get(i);
            if (s.text.isEmpty()) continue;
            double end = segments == null ? s.start : segments.optJSONObject(i).optDouble("end", s.start);
            if (!turns.isEmpty()) {
                SessionStore.Segment last = turns.get(turns.size() - 1);
                if (last.speaker.equals(s.speaker) && s.start - lastEnd < 2.5) {
                    turns.set(turns.size() - 1, new SessionStore.Segment(last.speaker, last.start, last.text + " " + s.text));
                    lastEnd = end;
                    continue;
                }
            }
            turns.add(s);
            lastEnd = end;
        }
        return turns;
    }

    private static JSONObject post(String key, File audio, String model, String format, boolean chunking) throws IOException {
        MultipartBody.Builder body = new MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("model", model)
            .addFormDataPart("response_format", format)
            .addFormDataPart("file", "chunk.m4a", RequestBody.create(audio, MediaType.get("audio/mp4")));
        if (chunking) body.addFormDataPart("chunking_strategy", "auto");
        Request request = new Request.Builder().url("https://api.openai.com/v1/audio/transcriptions")
            .header("Authorization", "Bearer " + key).post(body.build()).build();
        try (Response response = HTTP.newCall(request).execute()) {
            String data = response.body() == null ? "" : response.body().string();
            JSONObject json = Json.parse(data);
            if (response.code() != 200 || json == null) throw new IOException("Transkription " + response.code());
            return json;
        }
    }

    private OpenAi() {}
}
