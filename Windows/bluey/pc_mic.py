"""Das PC-Mikrofon als Ohr für Bluey (statt des Handy-Mikros, wenn das Handy weiter weg steht).

Nimmt 16-Bit-Mono-Audio mit 24 kHz auf (dasselbe Format wie vom Handy) und reicht es weiter. Kann das Gerät keine
24 kHz, wird mit seiner eigenen Rate aufgenommen und umgerechnet.
"""
import threading

RATE = 24000


def devices():
    """Eingabegeräte: [(Index, Name)], ohne Doppelte (Windows listet jedes Gerät pro Audio-Schnittstelle)."""
    try:
        import sounddevice as sd
        apis = sd.query_hostapis()
        preferred = next((i for i, api in enumerate(apis) if "MME" in api["name"]), None)
        result, seen = [], set()
        for index, device in enumerate(sd.query_devices()):
            if device["max_input_channels"] < 1:
                continue
            if preferred is not None and device["hostapi"] != preferred:
                continue
            name = device["name"].strip()
            if name in seen or "Mapper" in name or "Primärer" in name:
                continue
            seen.add(name)
            result.append((index, name))
        return result
    except Exception:
        return []


def default_name():
    try:
        import sounddevice as sd
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return None


def _resample(samples, rate):
    import numpy as np
    if rate == RATE or not len(samples):
        return samples
    count = int(round(len(samples) * RATE / rate))
    return np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples).astype(np.int16)


class PcMic:
    def __init__(self):
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0          # 0…1, für die Pegelanzeige
        self.error = None
        self.device_name = None

    @property
    def running(self):
        return self._stream is not None

    def start(self, on_audio, device=None):
        """Startet die Aufnahme. `device`: Gerätename oder None (Windows-Standard). Gibt True zurück, wenn es läuft."""
        self.stop()
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as error:
            self.error = f"Audio-Bibliothek fehlt: {error}"
            return False
        index = None
        if device:
            for i, name in devices():
                if name == device:
                    index = i
                    break

        def callback(data, frames, time_info, status):
            samples = np.frombuffer(data, dtype=np.int16)
            if rate != RATE:
                samples = _resample(samples, rate)
            if len(samples):
                level = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) / 6000
                self.level = min(1.0, self.level * 0.6 + level * 0.4)
                on_audio(samples.tobytes())

        for rate in (RATE, None):
            try:
                if rate is None:
                    rate = int(sd.query_devices(index if index is not None else sd.default.device[0])["default_samplerate"])
                stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", blocksize=int(rate / 10),
                                           device=index, callback=callback)
                stream.start()
                with self._lock:
                    self._stream = stream
                self.device_name = device or default_name()
                self.error = None
                return True
            except Exception as error:
                self.error = str(error)
        return False

    def stop(self):
        with self._lock:
            stream, self._stream = self._stream, None
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.level = 0.0
