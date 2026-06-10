; Inno Setup script for EVE Local Intel Scanner
; Build output: installer_output\EVE_Local_Intel_Scanner_Setup.exe

#define MyAppName "EVE Local Intel Scanner"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "EVE Local Intel Scanner"
#define MyAppExeName "EVE Local Intel Scanner.exe"

[Setup]
AppId={{EVE-LOCAL-INTEL-SCANNER}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

; User can install to Program Files or choose another folder.
; Mutable data is stored in:
; %LOCALAPPDATA%\EVE Local Intel Scanner\
DefaultDirName={autopf}\{#MyAppName}
PrivilegesRequired=admin

DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=EVE_Local_Intel_Scanner_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#ifexist "assets\icons\app.ico"
SetupIconFile=assets\icons\app.ico
#endif
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\EVE Local Intel Scanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
