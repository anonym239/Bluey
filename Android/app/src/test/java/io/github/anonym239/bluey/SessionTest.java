package io.github.anonym239.bluey;

import static org.junit.Assert.*;

import org.json.JSONObject;
import org.junit.Test;

public class SessionTest {
    private static BlueySession sample() {
        BlueySession s = new BlueySession(1000);
        s.entries.add(new BlueySession.Entry(BlueySession.Entry.Kind.HEARD, "rough words", 1010));
        BlueySession.Entry proper = new BlueySession.Entry(BlueySession.Entry.Kind.TRANSCRIPT, "proper words", 1012);
        proper.speaker = "A";
        s.entries.add(proper);
        s.entries.add(new BlueySession.Entry(BlueySession.Entry.Kind.ASKED, "Was ist das?", 1020));
        s.entries.add(new BlueySession.Entry(BlueySession.Entry.Kind.REPLY, "Ein Knopf.", 1021));
        s.entries.add(new BlueySession.Entry(BlueySession.Entry.Kind.HEARD, "later rough", 1030));
        s.entries.add(new BlueySession.Entry(BlueySession.Entry.Kind.HEARD, "", 1031));
        return s;
    }

    @Test public void properTranscriptReplacesRoughLinesBeforeIt() {
        BlueySession s = sample();
        StringBuilder texts = new StringBuilder();
        for (BlueySession.Entry e : s.displayEntries()) texts.append(e.text).append('|');
        assertEquals("proper words|Was ist das?|Ein Knopf.|later rough|", texts.toString());
        assertEquals(1, s.questionCount());
        assertEquals("Was ist das?", s.summary());
    }

    @Test public void roundTripsThroughJson() {
        BlueySession s = sample();
        s.ended = 2000.0;
        s.notesPath = "C:\\Notizen";
        s.pending.add(new BlueySession.Pending(2, 1300));
        BlueySession copy = BlueySession.fromJson(new JSONObject(s.toJson().toString()));
        assertEquals(s.id, copy.id);
        assertEquals(6, copy.entries.size());
        assertEquals("A", copy.entries.get(1).speaker);
        assertEquals(2000.0, copy.ended, 0);
        assertEquals(1, copy.transcribing());
        assertEquals("C:\\Notizen", copy.notesPath);
    }

    @Test public void notesJsonHasTheFieldsTheDesktopReads() {
        JSONObject json = sample().notesJson();
        assertTrue(json.has("id"));
        assertEquals(1000, json.getDouble("started"), 0);
        assertEquals("transcript", json.getJSONArray("entries").getJSONObject(0).getString("kind"));
        assertEquals("A", json.getJSONArray("entries").getJSONObject(0).getString("speaker"));
    }

    @Test public void durations() {
        assertEquals("1:05", BlueySession.formatDuration(65));
        assertEquals("1:01:01", BlueySession.formatDuration(3661));
    }
}
