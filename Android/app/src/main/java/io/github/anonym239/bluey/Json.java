package io.github.anonym239.bluey;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Kurze Helfer, damit org.json ohne geprüfte Ausnahmen lesbar bleibt. */
final class Json {
    static JSONObject obj(Object... pairs) {
        JSONObject o = new JSONObject();
        for (int i = 0; i + 1 < pairs.length; i += 2) put(o, (String) pairs[i], pairs[i + 1]);
        return o;
    }

    static JSONObject put(JSONObject o, String key, Object value) {
        try {
            o.put(key, value == null ? JSONObject.NULL : value);
        } catch (JSONException e) {
            throw new IllegalArgumentException(e);
        }
        return o;
    }

    static JSONArray arr(Object... items) {
        JSONArray a = new JSONArray();
        for (Object item : items) a.put(item);
        return a;
    }

    static JSONObject parse(String text) {
        if (text == null) return null;
        try { return new JSONObject(text); } catch (JSONException e) { return null; }
    }

    /** optString liefert bei JSON-null "null"; das hier liefert null. */
    static String str(JSONObject o, String key) {
        if (o == null || !o.has(key) || o.isNull(key)) return null;
        return o.optString(key, null);
    }

    private Json() {}
}
