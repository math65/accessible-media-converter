#ifndef AppName
  #define AppName "Accessible Media Converter"
#endif
#ifndef AppVersion
  #define AppVersion "1.9.4"
#endif
#ifndef AppDistDirName
  #define AppDistDirName "AccessibleMediaConverter"
#endif
#ifndef AppExeName
  #define AppExeName "AccessibleMediaConverter.exe"
#endif
#ifndef AppOutputBaseFilename
  #define AppOutputBaseFilename "AccessibleMediaConverter-Setup"
#endif
#ifndef AppId
  #define AppId "{{7E285383-842B-4F3B-8455-DF3F9F74F4F7}"
#endif
#ifndef AppInstallDirName
  #define AppInstallDirName "Accessible Media Converter"
#endif
#ifndef AppPublisher
  #define AppPublisher "Accessible Media Converter"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppInstallDirName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\dist
OutputBaseFilename={#AppOutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=yes
; Permet à une mise à jour silencieuse (/SILENT, lancée par l'updater) de fermer
; proprement l'app et de remplacer les fichiers même si une instance traîne encore.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppDistDirName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
