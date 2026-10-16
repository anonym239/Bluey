; Inno-Setup-Skript: baut Bluey-Setup.exe aus dist\Bluey (siehe .github/workflows/build.yml).
#define AppVersion GetEnv("BLUEY_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{6C86F5A9-BCFF-4254-D62B-2F8F1C1F6601}
AppName=Bluey
AppVersion={#AppVersion}
AppPublisher=Bluey
DefaultDirName={localappdata}\Programs\Bluey
DefaultGroupName=Bluey
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Bluey-Setup
SetupIconFile=bluey.ico
UninstallDisplayIcon={app}\Bluey.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "autostart"; Description: "Bluey beim Anmelden automatisch starten"; GroupDescription: "Zusätzlich:"
Name: "desktopicon"; Description: "Symbol auf dem Desktop"; GroupDescription: "Zusätzlich:"

[Files]
Source: "dist\Bluey\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Bluey"; Filename: "{app}\Bluey.exe"
Name: "{group}\Bluey deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Bluey"; Filename: "{app}\Bluey.exe"; Tasks: desktopicon
Name: "{userstartup}\Bluey"; Filename: "{app}\Bluey.exe"; Tasks: autostart

[Run]
; Firewall: Bluey muss im privaten WLAN für das Handy erreichbar sein (fragt einmal nach Admin-Rechten).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Bluey"" dir=in action=allow program=""{app}\Bluey.exe"" enable=yes profile=private"; Flags: runhidden runascurrentuser; StatusMsg: "Firewall-Regel für das private Netzwerk …"; Check: IsAdminInstallMode
Filename: "{app}\Bluey.exe"; Description: "Bluey jetzt starten"; Flags: nowait postinstall skipifsilent
