"""Lokale Spracherkennung mit faster-whisper (Whisper). Lädt das Modell beim ersten Gebrauch (einmalig aus dem Internet).

Standard ist "small" auf "auto": mit CUDA auf der Grafikkarte, sonst auf dem Prozessor (int8, schnell genug
für kurze Sätze). So bleibt der Grafikspeicher größtenteils für Ollama frei.
"""
import os
import threading

from .config import data_dir, settings

_model = None
_model_key = None
_lock = threading.Lock()
status = ""


class SpeechError(Exception):
    pass


def available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _model, _model_key, status
    key = (settings.whisper_model, settings.whisper_device)
    if _model is not None and _model_key == key:
        return _model
    try:
        from faster_whisper import WhisperModel
    except Exception as error:
        raise SpeechError("Die Spracherkennung (faster-whisper) fehlt.") from error
    cache = os.path.join(data_dir(), "whisper")
    os.makedirs(cache, exist_ok=True)
    attempts = [("cuda", "int8_float16"), ("cpu", "int8")] if settings.whisper_device == "auto" else \
        [("cuda", "int8_float16")] if settings.whisper_device == "cuda" else [("cpu", "int8")]
    last = None
    for device, compute in attempts:
        try:
            status = f"Lade Spracherkennung ({settings.whisper_model}, {device}) …"
            model = WhisperModel(settings.whisper_model, device=device, compute_type=compute, download_root=cache,
                                 cpu_threads=max(2, (os.cpu_count() or 4) - 2))
            if device == "cuda":
                # CUDA-Bibliotheken fehlen oft erst beim ersten echten Durchlauf: kurz testen.
                import numpy as np
                list(model.transcribe(np.zeros(16000, dtype=np.float32), language="de")[0])
            _model, _model_key = model, key
            status = f"Spracherkennung bereit ({settings.whisper_model}, {device})"
            return model
        except Exception as error:
            last = error
    status = "Spracherkennung konnte nicht laden"
    raise SpeechError(f"Die Spracherkennung konnte nicht laden: {last}")


def preload():
    """Im Hintergrund vorladen, damit die erste Frage nicht warten muss."""
    def work():
        try:
            with _lock:
                _load()
        except Exception:
            pass
    threading.Thread(target=work, name="Whisper laden", daemon=True).start()


def _language():
    return None if settings.whisper_language == "auto" else settings.whisper_language


def transcribe_pcm(pcm16, rate=24000):
    """Text aus 16-Bit-Mono-PCM (bytes)."""
    import numpy as np
    samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != 16000 and len(samples):
        # Lineare Umrechnung auf 16 kHz (Whisper).
        count = int(len(samples) * 16000 / rate)
        samples = np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples).astype(np.float32)
    if len(samples) < 16000 * 0.3:
        return ""
    with _lock:
        model = _load()
        segments, _ = model.transcribe(samples, language=_language(), beam_size=1, vad_filter=False,
                                       condition_on_previous_text=False, no_speech_threshold=0.6)
        text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.8)
    return _clean(text)


# Whisper erfindet bei Stille gern diese Sätze.
_HALLUCINATIONS = {"untertitel im auftrag des zdf", "untertitel der amara.org-community", "vielen dank fürs zuschauen",
                   "danke fürs zuschauen", "untertitelung im auftrag des zdf, 2017", "thank you for watching", "you"}


def _clean(text):
    text = " ".join(text.split())
    if text.lower().strip(" .!") in _HALLUCINATIONS:
        return ""
    return text


def transcribe_file(path):
    """Segmente einer Audiodatei (z. B. ein Fünf-Minuten-Stück vom Handy): [(Start, Ende, Text)]."""
    with _lock:
        model = _load()
        segments, _ = model.transcribe(path, language=_language(), beam_size=2, vad_filter=True)
        return [(s.start, s.end, _clean(s.text)) for s in segments if _clean(s.text)]
