"""Der „Testen“-Knopf: prüft Verbindung, Ollama, Modell, Spracherkennung und Bildschirm, Schritt für Schritt."""
import json
import time
import traceback

from . import ollama, pc_mic, screen_reader, stt
from .config import settings
from .server import lan_addresses


def run(server, report):
    """`report(Name, ok, Text)` wird für jeden Schritt aufgerufen (ok: True, False oder None = Hinweis)."""
    # 1. Verbindung zum Handy
    ips = lan_addresses()
    if server.port:
        report("PC-Server", True, f"läuft auf Port {server.port} · Adresse fürs Handy: "
               + (", ".join(f"{ip}:{server.port}" for ip in ips) or "keine WLAN-Adresse gefunden"))
    else:
        report("PC-Server", False, "läuft nicht – Bluey neu starten.")
    phones = server.phone_names
    if phones:
        report("Handy", True, "verbunden: " + ", ".join(phones))
    else:
        report("Handy", None, "kein Handy verbunden. Bluey-App öffnen, gleiches WLAN, ggf. „IP eingeben“ mit der "
               "Adresse oben. Fragt die Windows-Firewall, „Private Netzwerke“ erlauben.")

    # Mikrofon
    if settings.mic_source == "pc":
        found = pc_mic.devices()
        if not found:
            report("Mikrofon", False, "kein PC-Mikrofon gefunden – Bluey nimmt das Handy-Mikrofon.")
        else:
            mic, levels = pc_mic.PcMic(), []
            if mic.start(lambda pcm: levels.append(mic.level), settings.mic_device or None):
                time.sleep(1.0)
                mic.stop()
                report("Mikrofon", True, f"PC-Mikrofon „{mic.device_name}“ nimmt auf (Pegel {int(max(levels or [0]) * 100)} %)."
                       " Weiter unten „Mikrofon testen“ zeigt, was er versteht.")
            else:
                report("Mikrofon", False, f"PC-Mikrofon lässt sich nicht öffnen: {mic.error}")
    else:
        report("Mikrofon", None, "es hört das Handy-Mikrofon (in den Einstellungen auf PC umstellbar).")

    # 2. Ollama und Modell
    if settings.engine == "openai":
        report("KI", None, "eingestellt ist OpenAI Realtime (nicht Ollama).")
    version = ollama.running()
    if not version:
        report("Ollama", False, f"nicht erreichbar unter {settings.ollama_url}. Ollama installieren (ollama.com) und starten.")
        return
    report("Ollama", True, f"läuft (Version {version})")
    model = settings.ollama_model
    models = ollama.models()
    if model not in models:
        report("Modell", False, f"{model} ist nicht installiert. Oben unter „Neues Modell herunterladen“ laden."
               + (f" Installiert: {', '.join(models)}" if models else ""))
        return
    caps = ollama.capabilities(model)
    extra = [c for c in ("vision", "tools", "thinking") if c in caps]
    report("Modell", True, f"{model} installiert" + (f" · kann: {', '.join(extra)}" if extra else ""))

    # 3. Eine echte Testfrage
    started = time.monotonic()
    try:
        schema = {"type": "object", "properties": {"say": {"type": "string"}}, "required": ["say"]}
        text, _ = ollama.chat([{"role": "system", "content": "Antworte als JSON {\"say\": \"…\"} auf Deutsch, kurz."},
                               {"role": "user", "content": "Wie viel ist 17 mal 3? Antworte nur mit der Zahl."}],
                              model=model, format=schema, temperature=0, think=False if "thinking" in caps else None)
        seconds = time.monotonic() - started
        say = str(json.loads(text).get("say", "")).strip()
        if "51" in say:
            report("KI antwortet", True, f"„{say}“ in {seconds:.1f} s" + (" (beim ersten Mal lädt das Modell, danach schneller)"
                                                                         if seconds > 8 else ""))
        else:
            report("KI antwortet", None, f"antwortet, aber falsch: „{say}“ ({seconds:.1f} s). Ein größeres Modell wäre klüger.")
    except Exception as error:
        report("KI antwortet", False, f"Fehler: {error}")

    # 4. Spracherkennung
    try:
        import numpy as np
        started = time.monotonic()
        stt.transcribe_pcm((np.zeros(24000, dtype=np.int16)).tobytes(), 24000)
        report("Spracherkennung", True, f"{stt.status} ({time.monotonic() - started:.1f} s)")
    except Exception as error:
        report("Spracherkennung", False, f"lädt nicht: {error}. Beim ersten Mal braucht sie Internet zum Herunterladen.")

    # 5. Bildschirm
    try:
        shot = screen_reader.snapshot()
        words = sum(len(w) for _, w in shot.lines)
        report("Bildschirm", True if words else None,
               f"{len(shot.lines)} Textzeilen, {words} Wörter, {len(shot.controls)} Bedienelemente erkannt"
               + ("" if words else " – keine Texterkennung? Unter Windows-Einstellungen → Zeit und Sprache → Sprache "
                  "das Paket „Deutsch“ mit Texterkennung installieren."))
    except Exception as error:
        traceback.print_exc()
        report("Bildschirm", False, f"Bildschirmfoto ging nicht: {error}")
