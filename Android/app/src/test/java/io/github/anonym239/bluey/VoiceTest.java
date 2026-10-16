package io.github.anonym239.bluey;

import static org.junit.Assert.*;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import java.util.List;
import java.util.Random;

public class VoiceTest {
    @Test public void phoneSessionOnlyListensUntilAsked() throws Exception {
        JSONObject session = AgentSession.phoneConfiguration().getJSONObject("session");
        JSONObject turn = session.getJSONObject("audio").getJSONObject("input").getJSONObject("turn_detection");
        assertFalse(turn.getBoolean("create_response"));
        assertFalse(turn.getBoolean("interrupt_response"));
        assertEquals("text", session.getJSONArray("output_modalities").getString(0));
        assertEquals(24000, session.getJSONObject("audio").getJSONObject("input").getJSONObject("format").getInt("rate"));
    }

    @Test public void phoneSessionHasNoComputerTools() throws Exception {
        JSONArray tools = AgentSession.phoneConfiguration().getJSONObject("session").getJSONArray("tools");
        for (int i = 0; i < tools.length(); i++) {
            String name = tools.getJSONObject(i).getString("name");
            assertTrue(name, AgentSession.localTool(name));
        }
        assertFalse(AgentSession.localTool("click"));
        assertFalse(AgentSession.phoneConfiguration().toString().contains("Authorization"));
    }

    @Test public void resamplerKeepsTheDuration() throws Exception {
        LiveVoice.Resampler down = new LiveVoice.Resampler(48000, 24000);
        int total = 0;
        for (int i = 0; i < 10; i++) total += down.convert(new short[4800], 4800).length;
        assertEquals(24000, total, 2);
        LiveVoice.Resampler up = new LiveVoice.Resampler(16000, 24000);
        total = 0;
        for (int i = 0; i < 10; i++) total += up.convert(new short[1600], 1600).length;
        assertEquals(24000, total, 2);
        short[] same = new LiveVoice.Resampler(24000, 24000).convert(new short[]{1, 2, 3}, 3);
        assertArrayEquals(new short[]{1, 2, 3}, same);
    }

    @Test public void chirpIsShortAndQuiet() throws Exception {
        float[] samples = Chirp.make(3, new Random(1));
        assertTrue(samples.length > 24000 * .2 && samples.length < 24000 * .6);
        for (float s : samples) assertTrue(Math.abs(s) < .4f);
    }

    @Test public void researchTextLosesMarkdownAndCitations() throws Exception {
        String clean = OpenAi.cleanMarkdown("**Antwort** ist ja ([heise.de](https://heise.de/x?utm_source=openai)). Siehe [Seite](https://a.b).");
        assertEquals("Antwort ist ja. Siehe Seite.", clean);
    }

    @Test public void speechChunksKeepAllText() throws Exception {
        String text = "Hallo Welt, das ist ein längerer Satz mit 🫐 Blaubeeren drin.";
        List<String> parts = SpeechChunks.split(text, 12);
        assertEquals(text, String.join("", parts));
        for (String p : parts) assertTrue(p.length() <= 12);
    }
}
