import unittest
from unittest import mock

from bluey import web_research

PAGE = '''<div><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.de%2Fwetter&amp;rut=1">Wetter <b>Berlin</b></a>
<a class="result__snippet" href="x">Heute <b>sonnig</b>, 21 Grad.</a></div>
<div><a rel="nofollow" class="result__a" href="https://zwei.de/seite">Zweite Seite</a><a class="result__snippet" href="y">Mehr.</a></div>'''


class ResearchTest(unittest.TestCase):
    def test_clean_and_report(self):
        report = web_research.to_report("Wetter?", "**Sonnig in Berlin**\n\nHeute 21 Grad ([wetter.de](https://wetter.de)).\n- Morgen Regen",
                                        [("Wetter", "https://wetter.de")])
        self.assertEqual(report.title, "Sonnig in Berlin")
        self.assertEqual(report.paragraphs, ["Heute 21 Grad.", "Morgen Regen"])
        self.assertIn("Heute 21 Grad.", report.plain_text)

    def test_duckduckgo_results(self):
        class Response:
            def __init__(self, data): self.data = data
            def read(self, *_): return self.data.encode()
            def __enter__(self): return self
            def __exit__(self, *_): return False
        with mock.patch("urllib.request.urlopen", return_value=Response(PAGE)):
            results = web_research.search("wetter berlin")
        self.assertEqual(results[0], ("Wetter Berlin", "https://example.de/wetter", "Heute sonnig, 21 Grad."))
        self.assertEqual(results[1][1], "https://zwei.de/seite")

    def test_local_research_uses_ollama(self):
        with mock.patch.object(web_research, "search", return_value=[("A", "https://a.de", "x")]), \
                mock.patch.object(web_research, "fetch", return_value="Inhalt"), \
                mock.patch("bluey.ollama.generate", return_value="Titel hier\nAbsatz eins.\nAbsatz zwei.") as generate:
            report = web_research._local("Frage?", None)
        self.assertEqual(report.title, "Titel hier")
        self.assertEqual(report.sources, [("A", "https://a.de")])
        self.assertIn("Inhalt", generate.call_args[0][0])
