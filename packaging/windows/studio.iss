#ifndef AppVersion
  #define AppVersion "0.3.0-beta.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\OpenLipsStudio"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\release_assets"
#endif

[Setup]
AppId={{68C8FD2C-BC7D-453E-9FD1-1D658E247AEA}
AppName=OpenLips Studio
AppVersion={#AppVersion}
AppPublisher=OpenLips contributors
AppPublisherURL=https://github.com/gerrit117/OpenLips-Studio
DefaultDirName={localappdata}\Programs\OpenLips Studio
DefaultGroupName=OpenLips Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=OpenLips-Studio-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\studio\assets\app-icon.ico
UninstallDisplayIcon={app}\OpenLipsStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\OpenLips Studio"; Filename: "{app}\OpenLipsStudio.exe"
Name: "{autodesktop}\OpenLips Studio"; Filename: "{app}\OpenLipsStudio.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.olp\OpenWithProgids"; ValueType: string; ValueName: "OpenLipsStudio.Project"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\OpenLipsStudio.Project"; ValueType: string; ValueName: ""; ValueData: "OpenLips Studio Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\OpenLipsStudio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\OpenLipsStudio.exe,0"
Root: HKA; Subkey: "Software\Classes\OpenLipsStudio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\OpenLipsStudio.exe"" --project ""%1"""

[Run]
Filename: "{app}\OpenLipsStudio.exe"; Description: "{cm:LaunchProgram,OpenLips Studio}"; Flags: nowait postinstall skipifsilent
