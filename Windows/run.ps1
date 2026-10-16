# Startet Bluey aus dem Quellcode (für Entwickler). Normale Nutzer nehmen Bluey-Setup.exe.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Bitte Python 3.12 von python.org installieren (mit „py“-Starter).' }
}
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installation der Pakete fehlgeschlagen.' }
& .venv\Scripts\python.exe -m bluey
