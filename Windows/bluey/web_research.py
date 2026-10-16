"""Schlägt Dinge im Web nach und schreibt einen kurzen Bericht.

Lokal (Standard): DuckDuckGo-Suche, die besten Seiten lesen, Ollama schreibt den Bericht.
Mit OpenAI-Schlüssel und KI "OpenAI": Responses API mit eingebauter Websuche.
"""
import html
import json
import re
import urllib.parse
import urllib.request

from . import keys, ollama
from .config import settings

RESEARCH_MODEL = "gpt-5.5"
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

INSTRUCTIONS = (
    "Schreib einen kurzen, freundlichen Bericht für einen beschäftigten Menschen, auf Deutsch. Erste Zeile: ein schlichter "
    "Titel unter acht Wörtern. Dann ein bis vier kurze Absätze (höchstens vier), zuerst die direkte Antwort, dann die "
    "nützlichsten Details. Nur Klartext: kein Markdown, keine Überschriften, keine Aufzählungen und keine Links oder "
    "Quellenangaben im Text."
)


class ResearchError(Exception):
    pass


class Report:
    def __init__(self, question, title, paragraphs, sources):
        self.question, self.title, self.paragraphs, self.sources = question, title, paragraphs, sources  # sources: [(Titel, URL)]

    @property
    def plain_text(self):
        return "\n\n".join([self.title] + self.paragraphs)


def clean(text):
    """Entfernt Quellen wie "([seite.de](https://…))" und übriges Markdown."""
    text = re.sub(r"\s*\(\[[^\]]*\]\([^)]*\)\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\s*\[https?://[^\]]*\]", "", text)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    return text.replace("**", "").replace("#", "")


def to_report(question, text, sources):
    blocks = [b.strip() for b in clean(text).split("\n") if b.strip()]
    if not blocks:
        raise ResearchError("leere Antwort")
    title = blocks[0].rstrip(".:")
    return Report(question, title[:120], blocks[1:5], sources[:5])


def research(question, context=None):
    if settings.engine == "openai" and keys.get("openai"):
        return _openai(question, context)
    return _local(question, context)


def _openai(question, context):
    key = keys.get("openai")
    prompt = question + (f"\n\nWas auf dem Bildschirm des Nutzers steht, als Kontext: {context}" if context else "")
    body = {"model": RESEARCH_MODEL, "reasoning": {"effort": "low"}, "tools": [{"type": "web_search"}],
            "instructions": "Recherchiere die Frage im Web. " + INSTRUCTIONS, "input": prompt}
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
    except Exception as error:
        raise ResearchError(str(error)[:160]) from None
    text, sources = "", []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            text += part.get("text", "")
            for note in part.get("annotations", []):
                url = note.get("url")
                if url:
                    url = re.sub(r"[?&]utm_source=[^&]*$", "", url)
                    if all(s[1] != url for s in sources):
                        sources.append((note.get("title") or urllib.parse.urlparse(url).hostname or url, url))
    return to_report(question, text, sources)


def search(query, count=5):
    """DuckDuckGo (HTML-Version, ohne Schlüssel): [(Titel, URL, Ausschnitt)]."""
    data = urllib.parse.urlencode({"q": query, "kl": "de-de"}).encode()
    request = urllib.request.Request("https://html.duckduckgo.com/html/", data=data, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", "replace")
    results = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                             page, re.S):
        href, title, rest = match.groups()
        if "uddg=" in href:
            href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com" in href or not href.startswith("http"):
            continue
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        results.append((_text(title), href, _text(snippet.group(1)) if snippet else ""))
        if len(results) >= count:
            break
    return results


def _text(fragment):
    fragment = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)<(br|/?p|/?div|/?li|/?h[1-6]|/?tr|/?td|/?section|/?article)[^>]*>", " ", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return " ".join(html.unescape(fragment).split())


def fetch(url, limit=2500):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Language": "de,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=12) as response:
        kind = response.headers.get("Content-Type", "")
        if "html" not in kind and "text" not in kind:
            return ""
        page = response.read(800_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
    body = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", page)
    return _text(body.group(2) if body else page)[:limit]


def _local(question, context):
    try:
        results = search(question)
    except Exception as error:
        raise ResearchError(f"Die Websuche ging nicht ({type(error).__name__}).") from None
    if not results:
        raise ResearchError("Die Websuche hat nichts gefunden.")
    notes = []
    for title, url, snippet in results[:5]:
        page = ""
        if len(notes) < 3:
            try:
                page = fetch(url)
            except Exception:
                page = ""
        notes.append(f"Quelle: {title} ({url})\nAusschnitt: {snippet}\n{page}")
    prompt = (f"Frage: {question}\n\n" + (f"Auf dem Bildschirm des Nutzers: {context}\n\n" if context else "")
              + "Suchergebnisse und Seiteninhalte:\n\n" + "\n\n---\n\n".join(notes)
              + "\n\nBeantworte die Frage nur mit dem, was in diesen Quellen steht. " + INSTRUCTIONS)
    try:
        text = ollama.generate(prompt, system="Du bist ein sorgfältiger Rechercheur.", num_ctx=12288)
    except ollama.OllamaError as error:
        raise ResearchError(str(error)) from None
    return to_report(question, text, [(t, u) for t, u, _ in results])
