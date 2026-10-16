package io.github.anonym239.bluey;

import static org.junit.Assert.*;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.Test;

public class ProtocolTest {
    @Test public void framerSplitsLinesAcrossReads() {
        PacketFramer framer = new PacketFramer();
        byte[] first = "{\"hello\":\"PC\"}\n{\"face\":".getBytes(StandardCharsets.UTF_8);
        byte[] second = "{\"gazeX\":0.5}}\n".getBytes(StandardCharsets.UTF_8);
        List<String> a = framer.feed(first, first.length);
        assertEquals(1, a.size());
        assertEquals("{\"hello\":\"PC\"}", a.get(0));
        List<String> b = framer.feed(second, second.length);
        assertEquals("{\"face\":{\"gazeX\":0.5}}", b.get(0));
    }

    @Test public void framerKeepsMultibyteCharactersWhole() {
        PacketFramer framer = new PacketFramer();
        byte[] bytes = "{\"text\":\"Grüße 🫐\"}\n".getBytes(StandardCharsets.UTF_8);
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < bytes.length; i++) for (String line : framer.feed(new byte[]{bytes[i]}, 1)) out.append(line);
        assertEquals("{\"text\":\"Grüße 🫐\"}", out.toString());
    }

    @Test(expected = IllegalArgumentException.class)
    public void framerRejectsHugeLines() {
        PacketFramer framer = new PacketFramer(10);
        byte[] bytes = "01234567890123".getBytes(StandardCharsets.UTF_8);
        framer.feed(bytes, bytes.length);
    }

    @Test public void moodsMatchTheWireNames() {
        assertEquals(Mood.POINTING, Mood.from("pointing"));
        assertEquals(Mood.LISTENING, Mood.from("unknown"));
        assertEquals("sleepy", Mood.SLEEPY.wire());
    }

    @Test public void jsonNullsReadAsNull() {
        assertNull(Json.str(Json.parse("{\"text\":null}"), "text"));
        assertEquals("x", Json.str(Json.parse("{\"text\":\"x\"}"), "text"));
    }
}
