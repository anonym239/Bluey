"""Ein schlanker Ollama-Client (http://127.0.0.1:11434). Läuft auf der Grafikkarte des PCs, kostenlos und lokal."""
import json
import urllib.error
import urllib.request

from .config import settings


class OllamaError(Exception):
    pass


def _url(path):
    return settings.ollama_url.rstrip("/") + path


def _post(path, body, timeout=600, stream=False):
    request = urllib.request.Request(_url(path), data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read().decode("utf-8", "replace")).get("error", "")
        except Exception:
            pass
        raise OllamaError(detail or f"Ollama antwortet mit {error.code}") from None
    except (urllib.error.URLError, OSError) as error:
        raise OllamaError("Ollama läuft nicht. Starte Ollama (ollama.com) und versuch es nochmal.") from error
    if stream:
        return response
    with response:
        return json.loads(response.read().decode("utf-8"))


def running():
    try:
        with urllib.request.urlopen(_url("/api/version"), timeout=2) as response:
            return json.loads(response.read().decode("utf-8")).get("version") or True
    except Exception:
        return False


def models():
    """Die installierten Modelle, nach Namen."""
    try:
        with urllib.request.urlopen(_url("/api/tags"), timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    except Exception:
        return []


_capabilities = {}


def capabilities(model):
    """Was das Modell kann, z. B. {"completion", "vision", "tools"}. Gemerkt pro Modell."""
    if model in _capabilities:
        return _capabilities[model]
    caps = set()
    try:
        info = _post("/api/show", {"model": model}, timeout=10)
        caps = set(info.get("capabilities") or [])
        if not caps:
            families = (info.get("details") or {}).get("families") or []
            if any(f in ("clip", "mllama") for f in families):
                caps.add("vision")
    except OllamaError:
        pass
    _capabilities[model] = caps
    return caps


def pull(model, progress=None):
    """Lädt ein Modell herunter. `progress(Text, Anteil 0…1 oder None)`."""
    response = _post("/api/pull", {"model": model, "stream": True}, timeout=3600, stream=True)
    with response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise OllamaError(data["error"])
            if progress:
                total, done = data.get("total"), data.get("completed")
                progress(data.get("status", ""), (done / total) if total and done else None)
    _capabilities.pop(model, None)


def chat(messages, model=None, tools=None, on_delta=None, cancelled=lambda: False, num_ctx=8192, format=None,
         temperature=0.6, think=None):
    """Ein Chat-Aufruf mit Streaming. Gibt (Text, Werkzeugaufrufe) zurück; `on_delta(bisheriger Text)` beim Streamen.
    `format`: ein JSON-Schema, an das sich das Modell halten muss (strukturierte Ausgabe)."""
    body = {"model": model or settings.ollama_model, "messages": messages, "stream": True,
            "options": {"num_ctx": num_ctx, "temperature": temperature}, "keep_alive": "30m"}
    if tools:
        body["tools"] = tools
    if format:
        body["format"] = format
    if think is not None:
        body["think"] = think
    response = _post("/api/chat", body, stream=True)
    text, calls = "", []
    with response:
        for raw in response:
            if cancelled():
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise OllamaError(data["error"])
            message = data.get("message") or {}
            piece = message.get("content") or ""
            if piece:
                text += piece
                if on_delta:
                    on_delta(text)
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                calls.append({"name": fn.get("name", ""), "arguments": args})
            if data.get("done"):
                break
    return text, calls


def generate(prompt, system=None, model=None, num_ctx=8192):
    """Ein einfacher Aufruf ohne Streaming (z. B. für Rechercheberichte)."""
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    text, _ = chat(messages, model=model, num_ctx=num_ctx)
    return text
