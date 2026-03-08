#ifndef AppName
  #define AppName "Universal Transcoder"
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppExeName
  #define AppExeName "UniversalTranscoder.exe"
#endif
#ifndef AppOutputBaseFilename
  #define AppOutputBaseFilename "UniversalTranscoder-Setup-1.0.0"
#endif
#ifndef AppId
  #define AppId "{{7E285383-842B-4F3B-8455-DF3F9F74F4F7}"
#endif
#ifndef AppInstallDirName
  #define AppInstallDirName "Universal Transcoder"
#endif
#ifndef AppPublisher
  #define AppPublisher "Universal Transcoder"
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
