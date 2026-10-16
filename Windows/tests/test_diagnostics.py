import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from bluey import diagnostics, screen_reader, stt
from bluey.config import settings


class Ollama(BaseHTTPRequestHandler):
    def _json(self, data, stream=False):
        body = (json.dumps(data) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._json({"version": "0.12.3"})
        else:
            self._json({"models": [{"name": "gemma3:4b"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/show":
            self._json({"capabilities": ["completion", "vision"]})
        else:
            assert body.get("format"), "Testfrage muss strukturiert sein"
            self._json({"message": {"content": json.dumps({"say": "51"})}, "done": True})

    def log_message(self, *a):
        pass


class FakeServer:
    port = 52700
    phone_names = ["Pixel 8"]


class DiagnosticsTest(unittest.TestCase):
    def test_all_green(self):
        http = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        old_url, old_model = settings.ollama_url, settings.ollama_model
        settings.ollama_url, settings.ollama_model, settings.engine = f"http://127.0.0.1:{http.server_port}", "gemma3:4b", "ollama"
        settings.mic_source = "phone"
        results = []
        shot = screen_reader.Snapshot(b"", [(screen_reader.Target("L1", "Hallo Welt", (0, 0, 10, 10)),
                                             [screen_reader.Target("W1", "Hallo", (0, 0, 5, 10))])], (100, 100))
        try:
            with mock.patch.object(stt, "transcribe_pcm", return_value=""), \
                    mock.patch.object(screen_reader, "snapshot", return_value=shot):
                diagnostics.run(FakeServer(), lambda name, ok, text: results.append((name, ok, text)))
        finally:
            settings.ollama_url, settings.ollama_model = old_url, old_model
            http.shutdown()
        settings.mic_source = "pc"
        status = {name: ok for name, ok, _ in results}
        self.assertEqual(status, {"PC-Server": True, "Handy": True, "Mikrofon": None, "Ollama": True, "Modell": True,
                                  "KI antwortet": True, "Spracherkennung": True, "Bildschirm": True}, results)

    def test_ollama_missing(self):
        settings.ollama_url = "http://127.0.0.1:9"
        results = []
        try:
            diagnostics.run(FakeServer(), lambda name, ok, text: results.append((name, ok)))
        finally:
            settings.ollama_url = "http://127.0.0.1:11434"
        self.assertIn(("Ollama", False), results)
