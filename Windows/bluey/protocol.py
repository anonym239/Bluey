"""Kompatibel mit dem Original (GooglyLink): eine JSON-Zeile pro Paket über TCP, Bonjour-Dienst _googly._tcp."""
import json

SERVICE_TYPE = "_googly._tcp.local."
MAX_PACKET = 32 * 1024 * 1024


def encode(packet):
    return (json.dumps(packet, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


class Decoder:
    def __init__(self, maximum=MAX_PACKET):
        self.buffer = bytearray()
        self.maximum = maximum

    def feed(self, data):
        self.buffer.extend(data)
        packets = []
        while True:
            end = self.buffer.find(b"\n")
            if end < 0:
                break
            line = bytes(self.buffer[:end])
            del self.buffer[:end + 1]
            if not line.strip():
                continue
            try:
                packet = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(packet, dict):
                packets.append(packet)
        if len(self.buffer) > self.maximum:
            self.buffer.clear()
            raise ValueError("Paket zu groß")
        return packets
