; OCRYON 0.2 has its own product identity and directory, separate from
; public v0.1.0-beta.1 and the development RC.
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif

[Setup]
AppId={{573CF662-76A6-4D06-95D2-230D617919A3}
AppName=OCRYON
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\OCRYON-0.2
DefaultGroupName=OCRYON
OutputDir=..\dist
OutputBaseFilename=OCRYON-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=OCRYON 0.2
UninstallDisplayIcon={app}\OCRYON.exe
SetupIconFile=..\build\ocryon.ico
VersionInfoVersion=0.2.0.0

[Files]
Source: "..\dist\OCRYON\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OCRYON"; Filename: "{app}\OCRYON.exe"
Name: "{userdesktop}\OCRYON"; Filename: "{app}\OCRYON.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
