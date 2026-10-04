[Setup]
AppId={{B9E55BFE-55D0-4709-9828-41D3A2DA1B98}
AppName=AnimeDialog
AppVersion=1.1.2
AppPublisher=AnimeDialog
DefaultDirName={localappdata}\Programs\AnimeDialog
DefaultGroupName=AnimeDialog
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=AnimeDialog-1.1.2-Windows-x64-Setup
SetupIconFile=..\animedialog\assets\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AnimeDialog.exe
MinVersion=10.0.22000
CloseApplications=yes
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"; Flags: unchecked
[Files]
Source: "..\dist\AnimeDialog\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\使用说明.html"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\AnimeDialog"; Filename: "{app}\AnimeDialog.exe"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.html"
Name: "{autodesktop}\AnimeDialog"; Filename: "{app}\AnimeDialog.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\AnimeDialog.exe"; Description: "启动 AnimeDialog"; Flags: nowait postinstall skipifsilent
