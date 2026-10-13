; Values are supplied by build.py from project metadata and the verified bundle.
#define AppName "Game Assets Maker"

[Setup]
AppId={{8A8F173F-8BCB-47DA-8E4C-4F9C763B313A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ForFuner
DefaultDirName={localappdata}\Programs\Game Assets Maker
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UsePreviousAppDir=yes
OutputDir={#OutputDir}
OutputBaseFilename=GameAssetsMaker-{#AppVersion}-windows-x64-Setup
SetupIconFile={#RepoRoot}\icon\app-icon.ico
UninstallDisplayIcon={app}\game-assets-maker.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
InfoAfterFile={#RepoRoot}\scripts\windows-installation.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\windows-installation.txt"; DestDir: "{app}"; DestName: "Installation.txt"; Flags: ignoreversion
Source: "{#WebViewBootstrapper}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\game-assets-maker.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\game-assets-maker.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Register the stable CLI entry without opening the application.
Filename: "{app}\gam-agent.exe"; Parameters: "--version"; Flags: runhidden waituntilterminated
Filename: "{app}\game-assets-maker.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
english.WebViewFailed=Microsoft WebView2 could not be installed. Check your internet connection, install WebView2 from Microsoft, and retry setup.
chinesesimplified.WebViewFailed=Microsoft WebView2 安装失败。请检查网络连接，安装微软 WebView2 运行库后重试。

[Code]
function HasWebView2: Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
      Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then
  begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := CustomMessage('WebViewFailed')
    else if not HasWebView2 then
      Result := CustomMessage('WebViewFailed');
  end;
end;
