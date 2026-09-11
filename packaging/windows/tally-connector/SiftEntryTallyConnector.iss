#define AppName "SiftEntry Tally Connector"
#define AppVersion "0.4.0"
#define AppPublisher "SiftEntry"
#define AppExeName "SiftEntry Tally Connector.exe"
#define BuildRoot "."

[Setup]
AppId={{7A9A4D73-09E0-4E16-9D86-62D8B28F4B47}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\SiftEntry\Tally Connector
DefaultGroupName=SiftEntry
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=SiftEntry-Tally-Connector-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\..\..\apps\web\src\app\favicon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start connector when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "{#BuildRoot}\dist\SiftEntry Tally Connector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SiftEntry Tally Connector"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall SiftEntry Tally Connector"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SiftEntry Tally Connector"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SiftEntry Tally Connector"; ValueData: """{app}\{#AppExeName}"" --minimized --autostart"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SiftEntry Tally Connector"; Flags: nowait postinstall skipifsilent
