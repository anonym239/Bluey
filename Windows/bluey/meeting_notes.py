"""Macht aus aufgenommenem Audio ein richtiges Transkript und hält die Meeting-Notizen jeder Sitzung als einfache
Dateien, die jeder Agent lesen kann: Dokumente\\Bluey Notizen\\<Datum> <ID>\\.

Transkription: mit OpenAI-Schlüssel und KI "OpenAI" mit Sprechern (gpt-4o-transcribe-diarize), sonst lokal mit Whisper.
"""
import datetime
import json
import os
import uuid
import urllib.request

from . import keys, stt
from .config import documents_dir, settings

MODEL = "gpt-4o-transcribe-diarize"
FALLBACK_MODEL = "gpt-transcribe"


def root():
    return os.path.join(documents_dir(), "Bluey Notizen")


class Segment:
    def __init__(self, speaker, start, end, text):
        self.speaker, self.start, self.end, self.text = speaker, start, end, text


def folder(session, started):
    """Der Ordner der Sitzung, beim ersten Bedarf angelegt."""
    base = root()
    os.makedirs(base, exist_ok=True)
    _write_readme(base)
    tag = session[:8].lower()
    for name in os.listdir(base):
        if name.endswith(tag) and os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    name = datetime.datetime.fromtimestamp(started).strftime("%Y-%m-%d %H.%M") + " " + tag
    path = os.path.join(base, name)
    os.makedirs(os.path.join(path, "audio"), exist_ok=True)
    return path


def _write_readme(base):
    path = os.path.join(base, "README.md")
    if os.path.exists(path):
        return
    text = (
        "# Bluey Notizen\n\n"
        "Meeting-Notizen, aufgenommen mit der Bluey-App (die Blaubeere auf dem Handy). Ein Ordner pro Sitzung, "
        "benannt nach der Startzeit.\n\n"
        "In jedem Sitzungsordner:\n"
        "- `notes.md`: das ganze Transkript mit Uhrzeiten und Sprechern, dazu die Fragen an Bluey, seine Antworten und "
        "Rechercheberichte, in zeitlicher Reihenfolge. Fang hier an.\n"
        "- `session.json`: dieselben Daten, strukturiert.\n"
        "- `audio/`: die Rohaufnahme in Fünf-Minuten-Stücken (AAC).\n\n"
        "Sprecherbuchstaben (A, B, …) werden pro Fünf-Minuten-Stück vergeben; derselbe Buchstabe kann in verschiedenen "
        "Stücken verschiedene Menschen meinen. „?“ heißt: ohne Sprechererkennung transkribiert (lokal). Zeilen mit "
        "„(live)“ sind ein grobes Live-Transkript für Audio, das noch nicht fertig transkribiert ist.\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def transcribe(audio, session, index, session_started):
    """Speichert das Audio im Sitzungsordner und transkribiert es. Gibt (Segmente, Ordner) zurück."""
    path = folder(session, session_started)
    audio_dir = os.path.join(path, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    file = os.path.join(audio_dir, f"chunk-{index:03d}.m4a")
    with open(file, "wb") as f:
        f.write(audio)
    if settings.engine == "openai" and keys.get("openai"):
        try:
            return _diarized(audio), path
        except Exception:
            try:
                return _plain(audio), path
            except Exception:
                pass
    return [Segment("?", start, end, text) for start, end, text in stt.transcribe_file(file)], path


def _post(audio, fields):
    key = keys.get("openai")
    boundary = "bluey-" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.m4a"\r\n'
             "Content-Type: audio/mp4\r\n\r\n").encode() + audio + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def _diarized(audio):
    data = _post(audio, {"model": MODEL, "response_format": "diarized_json", "chunking_strategy": "auto"})
    raw = [Segment(s.get("speaker", "?"), s.get("start", 0), s.get("end", 0), (s.get("text") or "").strip())
           for s in data.get("segments", [])]
    return join_turns(raw)


def join_turns(raw):
    """Fügt aufeinanderfolgende Stücke eines Sprechers zu einem Beitrag zusammen."""
    turns = []
    for segment in raw:
        if not segment.text:
            continue
        if turns and turns[-1].speaker == segment.speaker and segment.start - turns[-1].end < 2.5:
            turns[-1].text += " " + segment.text
            turns[-1].end = segment.end
        else:
            turns.append(Segment(segment.speaker, segment.start, segment.end, segment.text))
    return turns


def _plain(audio):
    data = _post(audio, {"model": FALLBACK_MODEL, "response_format": "json"})
    text = (data.get("text") or "").strip()
    return [Segment("?", 0, 0, text)] if text else []


# Notizdateien

def write(session):
    """Schreibt session.json und notes.md aus der Kopie der Sitzung vom Handy. Gibt den Ordner zurück."""
    sid, started = session.get("id"), session.get("started")
    if not isinstance(sid, str) or not isinstance(started, (int, float)):
        return None
    path = folder(sid, started)
    with open(os.path.join(path, "session.json"), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, sort_keys=True, ensure_ascii=False)
    with open(os.path.join(path, "notes.md"), "w", encoding="utf-8") as f:
        f.write(markdown(session))
    return path


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _day(when):
    return f"{WEEKDAYS[when.weekday()]}, {when.day}. {MONTHS[when.month - 1]} {when.year}, {when:%H:%M}"


def markdown(session):
    started = datetime.datetime.fromtimestamp(session["started"])
    ended = session.get("ended")
    entries = session.get("entries") or []
    pending = session.get("transcribing") or 0
    out = [f"# Bluey-Sitzung: {_day(started)}", ""]
    if isinstance(ended, (int, float)):
        minutes = int((ended - session["started"]) / 60)
        out.append(f"Beendet {datetime.datetime.fromtimestamp(ended):%H:%M:%S} ({minutes // 60} h {minutes % 60} min).")
    else:
        out.append("Nimmt noch auf.")
    if pending:
        out.append(f"{pending} Aufnahmestück(e) werden noch transkribiert; diese Datei aktualisiert sich, wenn sie fertig sind.")
    asked = sum(1 for e in entries if e.get("kind") == "asked")
    if asked:
        out.append(f"Bluey wurde {asked} Frage(n) gestellt; sie sind unten markiert.")
    out += ["", "## Transkript", ""]
    for entry in entries:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        stamp = entry.get("time")
        clock = datetime.datetime.fromtimestamp(stamp).strftime("%H:%M:%S") if isinstance(stamp, (int, float)) else ""
        kind = entry.get("kind")
        if kind == "transcript":
            out.append(f"**[{clock}] Sprecher {entry.get('speaker', '?')}:** {text}")
        elif kind == "heard":
            out.append(f"[{clock}] (live) {text}")
        elif kind == "asked":
            out.append(f"> **[{clock}] Frage an Bluey:** {text}")
        elif kind == "reply":
            out.append(f"> **Bluey:** {text}")
        elif kind == "report":
            quoted = "\n".join("> " + line for line in text.split("\n"))
            out.append("> **Recherchebericht:**\n" + quoted)
        else:
            out.append(f"[{clock}] {text}")
        out.append("")
    return "\n".join(out)
