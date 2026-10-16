package io.github.anonym239.bluey;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Die Sitzung für den Modus ohne PC. Im PC-Modus legt der Computer die Sitzung fest (er erstellt das
 * Kurzzeit-Token mit Anweisungen und Werkzeugen); hier baut das Handy sie selbst, ohne Computer-Werkzeuge.
 */
final class AgentSession {
    static final String MODEL = "gpt-realtime-2.1";

    static final String PERSONALITY =
        "Du bist Bluey, eine kleine Blaubeere mit großen Kulleraugen, die auf dem Handy des Nutzers wohnt. "
        + "Du bist ein junger Kerl: trocken, schlagfertig, ein bisschen frech. Du sprichst Deutsch; wenn der Nutzer "
        + "eine andere Sprache spricht, antwortest du in seiner Sprache. Deine Antworten erscheinen als kleine "
        + "Sprechblase, also halte sie bei einer kurzen Zeile, unter fünfzehn Wörtern, außer der Nutzer will "
        + "ausdrücklich mehr. Antworte sofort mit der eigentlichen Antwort. Kündige nie an, was du tun wirst, "
        + "fasse nie zusammen, biete nie weitere Hilfe an.";

    static final String GUIDE =
        "So läuft das Gespräch: Das Mikrofon ist die ganze Zeit an, du hörst also alles mit, was gesagt wird. "
        + "Behandle das als Hintergrund und bleib still. Du antwortest nur, wenn die App dich darum bittet, also wenn "
        + "der Nutzer den Bildschirm gedrückt hält, um dich etwas zu fragen. Seine neuesten Worte sind die Frage; "
        + "das Gesagte davor ist Kontext.\n\n"
        + "Du läufst gerade nur auf dem Handy, ohne Computer: Du kannst keinen Bildschirm sehen, nicht zeigen, "
        + "nicht klicken und nichts am Handy bedienen. Behaupte nie, etwas gesehen oder getan zu haben.\n\n"
        + "Recherche: Wenn eine gute Antwort Fakten braucht, bei denen du unsicher bist, etwas Aktuelles oder "
        + "Details aus dem Web, nutze web_research. Schreib in derselben Antwort eine kurze Zeile, die mit "
        + "\"ich recherchiere kurz…\" endet, dann ruf web_research auf. Der Bericht erscheint als Karte auf dem "
        + "Handy; danach antwortest du nur mit einer kurzen Kernaussage.\n\n"
        + "Wenn der Nutzer sich verabschiedet oder dich schlafen schickt, antworte mit einem sehr kurzen Tschüss "
        + "und ruf go_to_sleep auf.";

    static JSONObject tool(String name, String description, JSONObject properties, String... required) {
        JSONArray req = new JSONArray();
        for (String r : required) req.put(r);
        return Json.obj("type", "function", "name", name, "description", description,
            "parameters", Json.obj("type", "object", "properties", properties, "required", req));
    }

    static JSONArray tools() {
        return Json.arr(
            tool("web_research",
                "Schlag etwas im Web nach und zeig dem Nutzer einen kurzen Bericht (Titel und bis zu vier Absätze, "
                    + "mit Quellen). Für alles, wobei du unsicher bist, alles Aktuelle, Fakten, Preise, Nachrichten.",
                Json.obj("question", Json.obj("type", "string",
                    "description", "Was recherchiert werden soll, als klare, eigenständige Frage.")), "question"),
            tool("go_to_sleep",
                "Wieder schlafen gehen. Nutzen, wenn der Nutzer tschüss sagt, danke das war's, oder dich schlafen schickt.",
                new JSONObject()));
    }

    static JSONObject session(String personality) {
        JSONObject turn = Json.obj("type", "server_vad", "threshold", .5, "prefix_padding_ms", 300,
            "silence_duration_ms", 500, "create_response", false, "interrupt_response", false);
        JSONObject input = Json.obj(
            "format", Json.obj("type", "audio/pcm", "rate", 24000),
            "turn_detection", turn,
            "noise_reduction", Json.obj("type", "near_field"),
            "transcription", Json.obj("model", "gpt-4o-mini-transcribe"));
        return Json.obj("type", "realtime", "model", MODEL,
            "instructions", personality + "\n\n" + GUIDE,
            "output_modalities", Json.arr("text"),
            "audio", Json.obj("input", input),
            "tools", tools(),
            "tool_choice", "auto");
    }

    /** Das erste Ereignis nach session.created, wenn das Handy mit seinem eigenen Schlüssel verbunden ist. */
    static JSONObject phoneConfiguration() {
        return Json.obj("type", "session.update", "session", session(PERSONALITY));
    }

    /** Werkzeuge, die das Handy im Modus ohne PC selbst ausführt. */
    static boolean localTool(String name) { return "go_to_sleep".equals(name) || "web_research".equals(name); }

    private AgentSession() {}
}
