; Inno Setup installer for SubtitleForEveryone.
#define MyAppName "SubtitleForEveryone"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppExeName "SubtitleForEveryone.exe"
[Setup]
AppId={{6BCA5755-0E2B-4E15-8B2C-1557B721000A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=SubtitleForEveryone
AppPublisherURL=https://github.com/tonythewizard/SubtitleForEveryone
AppUpdatesURL=https://github.com/tonythewizard/SubtitleForEveryone/releases
DefaultDirName={localappdata}\Programs\SubtitleForEveryone
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=SubtitleForEveryone-Setup-{#MyAppVersion}-x64
SetupIconFile=build\SubtitleForEveryone.ico
VersionInfoVersion={#MyAppVersion}
LicenseFile=LICENSE
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
WizardStyle=modern
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto
MinVersion=10.0.22000
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
UninstallDisplayIcon={app}\{#MyAppExeName}
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
[Files]
Source: "dist\SubtitleForEveryone\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command, Exe: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  Exe := ExpandConstant('{app}\{#MyAppExeName}');
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}', Command) then
    if (CompareText(Command, Exe) = 0) or (CompareText(Command, '"' + Exe + '"') = 0) then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
end;
