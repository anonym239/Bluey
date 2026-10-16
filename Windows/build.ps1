# Baut dist\Bluey\Bluey.exe und (falls Inno Setup installiert ist) Output\Bluey-Setup.exe.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt pyinstaller==6.15.0
python -m PyInstaller --noconfirm bluey.spec
$test = Start-Process dist\Bluey\Bluey.exe -ArgumentList "--selftest" -Wait -PassThru
if ($test.ExitCode -ne 0) { Get-Content "$env:APPDATA\Bluey\selftest.txt"; throw "Selbsttest fehlgeschlagen" }
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) { & $iscc installer.iss }
