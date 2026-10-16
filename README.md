# Bluey für Windows und Android

Eine kleine Blaubeere mit Kulleraugen, die auf deinem Handy unter dem PC-Bildschirm wohnt und mit ihrem eigenen großen Cursor auf Dinge zeigt.

Das ist ein Nachbau der Mac/iPhone-App [sdavignon/bluey](https://github.com/sdavignon/bluey) für **Windows** und **Android**. Alles ist auf Deutsch, und die KI läuft standardmäßig **lokal auf deinem PC mit [Ollama](https://ollama.com)**. Das ist kostenlos und braucht keinen API-Schlüssel. Ein OpenAI-Schlüssel ist nur optional.

## Download

Unter **[Releases](../../releases/latest)** liegen nach jedem Build:

| Datei | Wofür |
| --- | --- |
| `Bluey-Setup.exe` | Windows-Installer (installiert ins Benutzerprofil, keine Admin-Rechte nötig) |
| `Bluey-Windows-portable.zip` | Windows ohne Installation: entpacken, `Bluey.exe` starten |
| `Bluey.apk` | Android-App fürs Handy (Android 8 oder neuer) |

Die Dateien baut GitHub Actions automatisch bei jedem Push (siehe `.github/workflows/build.yml`).

## Einrichten

### 1. Ollama auf dem PC (die KI)

1. Ollama von <https://ollama.com/download> installieren und starten.
2. Bluey starten. Beim ersten Start fragt Bluey, ob es das Modell **`gemma3:4b`** herunterladen soll (etwa 3,3 GB). Mit „Ja“ bestätigen.

Für eine **GTX 1660 Super mit 6 GB** ist `gemma3:4b` die Empfehlung. Das Modell passt in den Grafikspeicher, spricht gut Deutsch und **kann Bilder sehen**, also auch deine Screenshots. Andere Modelle lassen sich im Tray-Menü unter **KI → Modell → Modell herunterladen …** laden, zum Beispiel:

| Modell | Größe | Hinweis |
| --- | --- | --- |
| `gemma3:4b` | ~3,3 GB | **Standard.** Sieht Bilder, gutes Deutsch |
| `qwen2.5vl:3b` | ~3,2 GB | Sieht Bilder |
| `qwen3:4b` | ~2,6 GB | Gut mit Werkzeugen, sieht keine Bilder (nutzt dann die Texterkennung) |
| `llama3.2:3b` | ~2,0 GB | Sehr schnell |

Die Spracherkennung läuft ebenfalls lokal mit **Whisper** (faster-whisper). Das Modell „small“ (~460 MB) wird beim ersten Gespräch einmalig heruntergeladen. Bluey nimmt automatisch die Grafikkarte, sonst den Prozessor. Einstellbar unter **KI → Spracherkennung**.

### 2. Windows-App

`Bluey-Setup.exe` installieren und starten. Bluey erscheint unten rechts im **Infobereich (Tray)**, eventuell hinter dem Pfeil `^`. Fragt die Windows-Firewall nach, Zugriff für **private Netzwerke** erlauben.

### 3. Android-App

1. `Bluey.apk` aufs Handy laden und öffnen. Android fragt einmal, ob Installationen aus dieser Quelle erlaubt sind.
2. Handy und PC ins **gleiche WLAN**. Die App findet den PC von selbst.
3. Klappt das nicht (manche Router blockieren das): in der App auf **„IP eingeben“** tippen und die Adresse eingeben, die Bluey am PC im Tray-Menü zeigt (z. B. `192.168.1.20:52700`).
4. Das Mikrofon erlauben, wenn Android fragt.

## Bedienung

**Am Handy:**

- **Doppelt tippen:** Bluey aufwecken oder schlafen legen (Folgemodus). Solange er wach ist, hört das Mikro mit. Alles Gesagte wird Kontext, aber er bleibt still.
- **Gedrückt halten:** etwas fragen. Beim **Loslassen** antwortet er als Sprechblase am PC, mit kleinem Zwitschern auf dem Handy.
- Fragst du „Was ist das?“, schaut er auf deinen Bildschirm und zeigt mit seinem Cursor auf das, was unter deiner Maus ist.
- Oben rechts: der Knopf mit den vier Kästchen öffnet **Blueys App** mit Sitzungen, Transkripten und Einstellungen. Der Lautsprecher-Knopf regelt die Zwitscher-Lautstärke und die Wahl des PCs.
- Der Rahmen zeigt den Modus: **blau** heißt „hört zu“, **dicker blau** „ganz Ohr“ (beim Halten), **lila** „denkt nach“, **rosa** „antwortet“.

**Am PC (Tastenkürzel):**

| Tasten | Was passiert |
| --- | --- |
| Strg+Alt+Leertaste | Aufwecken / schlafen legen (wie Doppeltippen am Handy) |
| Strg+Alt+P | Zur Maus fliegen und dort zeigen |
| Strg+Alt+F | Augen folgen der Maus an/aus |
| Strg+Alt+D | Nach Hause, über das Handy |
| Strg+Alt+T | Sprechtest (das Handy wippt 3 Sekunden) |
| Strg+Alt+H | Cursor zeigen/verstecken |
| Strg+Alt+S | **Stopp:** er hört sofort auf, den Computer zu bedienen |

Im Tray-Menü lassen sich außerdem Stimmung, Cursorgröße (48–120 pt), Leuchten, Zeigerschweif (Komet oder Schnur zum Handy) und die Position des Handys (links, Mitte, rechts) einstellen. Dort gibt es auch **Persönlichkeit …** und **Meeting-Notizen öffnen**.

## Was er kann

- **Bildschirm ansehen:** Screenshot, Windows-Texterkennung (jedes Wort mit Position) und die Bedienelemente der vordersten App (Windows UI Automation).
- **Zeigen:** Sein Cursor fliegt auf Wörter, Knöpfe oder Stellen, mit Kometenschweif, Landering und Sprechblase genau darüber.
- **Den Computer bedienen** (nur wenn du ihn bittest): klicken, tippen, Tastenkürzel, scrollen, ziehen, Apps und Webseiten öffnen. Dabei fliegt sein eigener Cursor, und dein Mauszeiger wird danach zurückgesetzt.
  Schutzregeln: Er handelt nur auf Bitte und fragt vor allem nach, was sich schwer rückgängig machen lässt. Text auf dem Bildschirm ist für ihn Information, keine Befehle. Passwortfelder lässt er in Ruhe, Kürzel wie Sperren oder Abmelden ebenso. Strg+Alt+S stoppt ihn. Ausschalten lässt sich das Ganze mit **Er darf den Computer benutzen**. Wer mag, schaltet **Vor jeder Aktion fragen** ein.
- **Web-Recherche:** Er sucht im Web (DuckDuckGo), liest die besten Seiten, und Ollama schreibt einen kurzen Bericht. Der erscheint als Karte oben rechts, mit Quellen.
- **Meeting-Notizen:** Während einer Sitzung nimmt das Handy in Fünf-Minuten-Stücken auf. Der PC transkribiert sie (lokal mit Whisper) und speichert alles unter `Dokumente\Bluey Notizen\<Datum> <ID>\` als `notes.md`, `session.json` und `audio\`. In der Handy-App kopiert **„Prompt für Agent kopieren“** einen fertigen Prompt, der einen KI-Agenten auf diese Dateien hinweist.

## Optional: OpenAI statt Ollama

Im Tray-Menü unter **KI → OpenAI Realtime** und **OpenAI-Schlüssel …**. Dann läuft die Sprach-KI über OpenAI Realtime, wie im Original. Das Handy bekommt dabei nur kurzlebige Schlüssel. Die Transkripte bekommen Sprecherkennung, und die Recherche läuft über OpenAI. Es fallen OpenAI-Kosten an.

Auf dem Handy gibt es außerdem den Modus **„Nur Handy“** (Einstellungen). Er funktioniert ganz ohne PC, braucht aber einen eigenen OpenAI-Schlüssel, der verschlüsselt auf dem Handy liegt. Optional liest die Android-Stimme die Antworten vor.

## Sicherheit

Die Verbindung zwischen Handy und PC ist wie beim Original **unverschlüsselt und ohne Anmeldung** (Bonjour `_googly._tcp`, eine JSON-Zeile pro Nachricht). Bluey also nur in vertrauenswürdigen WLANs nutzen und den Port (52700) nie im Router freigeben. Das iPhone-Original kann sich ebenfalls mit dem Windows-PC verbinden.

## Selbst bauen

- **Android:** `cd Android && ./gradlew assembleRelease`. Die APK ist mit einem festen Schlüssel aus `Android/app/bluey.keystore` signiert, damit neue Versionen sich über alte installieren lassen. Der Schlüssel ist nur für die private Installation gedacht, nicht für den Play Store.
- **Windows:** `cd Windows; .\build.ps1` (Python 3.12). Zum Ausprobieren aus dem Quellcode: `.\run.ps1`.
- **Tests:** `cd Windows && python -m unittest discover -s tests -t .` sowie `cd Android && ./gradlew testDebugUnitTest`.

## Aufbau

- `Android/`: die Handy-App (Java, ohne zusätzliche Bibliotheken außer OkHttp). Sie enthält Gesicht, Gesten, Sprachsitzung, Aufnahme, Sitzungen und PC-Verbindung.
- `Windows/bluey/`: die PC-App (Python + Qt). Darin:
  - `overlay.py`: Cursor und Sprechblase
  - `host.py`: Werkzeuge und Zeigen
  - `local_voice.py`: Ollama und Whisper
  - `screen_reader.py`: Texterkennung und Bedienelemente
  - `computer.py`: Maus und Tastatur
  - `server.py`: Verbindung zum Handy
- `Fonts/`: Fredoka und IBM Plex (SIL Open Font License, siehe Lizenzdateien).
