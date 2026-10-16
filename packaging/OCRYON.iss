; The RC uses a separate Inno product identity from public v0.1.0-beta.1.
; Installing/testing an unpublished candidate must NEVER upgrade or uninstall
; a user's existing stable/public beta installation by sharing its AppId.
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0-rc.1"
#endif

[Setup]
AppId={{ABDD822D-3437-5C3D-A322-7AE362646840}
AppName=OCRYON 0.2 RC
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\OCRYON-0.2-RC
DefaultGroupName=OCRYON 0.2 RC
OutputDir=..\dist
OutputBaseFilename=OCRYON-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=OCRYON 0.2 RC

[Files]
Source: "..\dist\OCRYON\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OCRYON RC"; Filename: "{app}\OCRYON.exe"
Name: "{userdesktop}\OCRYON RC"; Filename: "{app}\OCRYON.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut for the RC"; Flags: unchecked
