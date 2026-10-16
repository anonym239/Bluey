package io.github.anonym239.bluey;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Zeilenweises JSON über TCP (wie GooglyLink im Original). UTF-8 wird erst je ganze Zeile dekodiert. */
final class PacketFramer {
    private final int maximum;
    private final ByteArrayOutputStream line = new ByteArrayOutputStream();

    PacketFramer() { this(32 * 1024 * 1024); }
    PacketFramer(int maximum) { this.maximum = maximum; }

    List<String> feed(byte[] bytes, int count) {
        List<String> lines = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < count; i++) {
            if (bytes[i] == '\n') {
                line.write(bytes, start, i - start);
                if (line.size() > 0) lines.add(new String(line.toByteArray(), StandardCharsets.UTF_8));
                line.reset();
                start = i + 1;
            }
        }
        line.write(bytes, start, count - start);
        if (line.size() > maximum) {
            line.reset();
            throw new IllegalArgumentException("Paket zu groß");
        }
        return lines;
    }
}
