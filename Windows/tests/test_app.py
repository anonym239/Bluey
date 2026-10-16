import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOllama(BaseHTTPRequestHandler):
    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._json({"version": "0.12.3"})
        elif self.path == "/api/tags":
            self._json({"models": [{"name": "gemma3:4b"}, {"name": "qwen3:4b"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        self._json({"capabilities": ["completion", "vision"]})

    def log_message(self, *args):
        pass


class AppStartTest(unittest.TestCase):
    """Startet die ganze App (offscreen) mit laufendem Ollama, baut das Menü und beendet sie wieder."""

    def test_starts_and_builds_menu(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        home = tempfile.mkdtemp(prefix="bluey-app-")
        os.makedirs(os.path.join(home, "Bluey"))
        with open(os.path.join(home, "Bluey", "settings.json"), "w") as f:
            json.dump({"ollama_url": f"http://127.0.0.1:{server.server_port}", "port": 0}, f)
        code = ("import bluey.app as a, bluey.ollama as o\n"
                "from PySide6.QtCore import QTimer\n"
                "orig = a.main\n"
                "a.main()\n")
        env = dict(os.environ, APPDATA=home, QT_QPA_PLATFORM="offscreen", BLUEY_QUIT_AFTER="3", BLUEY_MENU_TEST="1")
        result = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
                                env=env, capture_output=True, text=True, timeout=60)
        server.shutdown()
        log = open(os.path.join(home, "Bluey", "bluey.log"), encoding="utf-8").read() if os.path.exists(
            os.path.join(home, "Bluey", "bluey.log")) else ""
        self.assertEqual(result.returncode, 0, result.stderr + log)
        self.assertNotIn("Traceback", result.stderr + log)
        self.assertIn("MENU OK", result.stdout + log)
