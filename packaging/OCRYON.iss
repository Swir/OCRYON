#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-beta.1"
#endif

[Setup]
AppId={{7F17E5CF-2330-4F34-9D6A-71834D9AD3F4}
AppName=OCRYON
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\OCRYON
DefaultGroupName=OCRYON
OutputDir=..\dist
OutputBaseFilename=OCRYON-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=OCRYON

[Files]
Source: "..\dist\OCRYON\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OCRYON"; Filename: "{app}\OCRYON.exe"
Name: "{userdesktop}\OCRYON"; Filename: "{app}\OCRYON.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
