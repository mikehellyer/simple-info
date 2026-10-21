; Inno Setup script for Simple-Info.
; Built with: iscc packaging\windows\installer.iss
; Expects dist\Simple-Info\ (PyInstaller onedir output) to already
; exist, and the version passed in via /DAppVersion=x.y.z (the release
; workflow does this so the .iss file never has to be hand-edited per
; release).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Simple-Info"
#define RepoRoot AddBackslash(SourcePath) + "..\.."

[Setup]
AppId={{306C1324-B401-4AD4-AD62-0B000FB284D8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Mike Hellyer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\Simple-Info.exe
OutputDir={#RepoRoot}\dist
OutputBaseFilename=Simple-Info-{#AppVersion}-Windows-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#RepoRoot}\packaging\icons\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#RepoRoot}\dist\Simple-Info\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Simple-Info.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Simple-Info.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Simple-Info.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
