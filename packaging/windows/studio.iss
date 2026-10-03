#ifndef AppVersion
  #define AppVersion "0.3.1-beta.1"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\OpenLipsStudio"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\release_assets"
#endif
#ifndef BuildCompression
  #define BuildCompression "lzma2"
#endif

[Setup]
AppId={{68C8FD2C-BC7D-453E-9FD1-1D658E247AEA}
AppName=OpenLips Studio
AppVersion={#AppVersion}
AppPublisher=OpenLips contributors
AppPublisherURL=https://github.com/gerrit117/OpenLips-Studio
DefaultDirName={autopf}\OpenLips Studio
UsePreviousAppDir=no
DefaultGroupName=OpenLips Studio
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=OpenLips-Studio-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\studio\assets\app-icon.ico
UninstallDisplayIcon={app}\OpenLipsStudio.exe
Compression={#BuildCompression}
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
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "ai\*,ai-amd\*"; Flags: ignoreversion recursesubdirs createallsubdirs
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

[CustomMessages]
english.LegacyCleanup=The previous per-user installation will be uninstalled before installing in the new location. Projects and plugin settings are kept.
german.LegacyCleanup=Die bisherige Benutzerinstallation wird vor der Installation am neuen Ort deinstalliert. Projekte und Plugin-Einstellungen bleiben erhalten.
english.LegacyFailed=The previous installation could not be uninstalled. Setup stopped without removing your projects.
german.LegacyFailed=Die bisherige Installation konnte nicht deinstalliert werden. Setup wurde angehalten; Ihre Projekte wurden nicht entfernt.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Key, OldDir, OldVersion, Uninstaller: String;
  ExitCode: Integer;
begin
  Result := '';
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{68C8FD2C-BC7D-453E-9FD1-1D658E247AEA}_is1';
  { Only migrate the known 0.3.0 per-user install, never recursively delete folders. }
  if RegQueryStringValue(HKCU, Key, 'InstallLocation', OldDir) and
     RegQueryStringValue(HKCU, Key, 'DisplayVersion', OldVersion) and
     (OldVersion = '0.3.0-beta.1') and
     (CompareText(RemoveBackslashUnlessRoot(OldDir),
       ExpandConstant('{localappdata}\Programs\OpenLips Studio')) = 0) and
     (CompareText(RemoveBackslashUnlessRoot(OldDir), ExpandConstant('{app}')) <> 0) then
  begin
    Uninstaller := AddBackslash(OldDir) + 'unins000.exe';
    if not FileExists(Uninstaller) then
    begin
      Result := CustomMessage('LegacyFailed');
      Exit;
    end;
    if not WizardSilent then
      if MsgBox(CustomMessage('LegacyCleanup'), mbConfirmation, MB_OKCANCEL) <> IDOK then
      begin
        Result := CustomMessage('LegacyFailed');
        Exit;
      end;
    { A user-writable old uninstaller must NOT run with the new installer's elevation. }
    if not ExecAsOriginalUser(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
        OldDir, SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := CustomMessage('LegacyFailed')
    else if ExitCode <> 0 then
      Result := CustomMessage('LegacyFailed');
  end;
end;
