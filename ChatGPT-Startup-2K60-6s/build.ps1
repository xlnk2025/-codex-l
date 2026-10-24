$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$frameworkPath = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319'
$compilerPath = Join-Path $frameworkPath 'csc.exe'
if (-not (Test-Path -LiteralPath $compilerPath)) {
    $frameworkPath = Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319'
    $compilerPath = Join-Path $frameworkPath 'csc.exe'
}
if (-not (Test-Path -LiteralPath $compilerPath)) { throw 'Windows .NET Framework 4.x is required.' }

$filmPath = Join-Path $projectRoot 'output/chatgpt-startup-2k60-6s.mp4'
$posterPath = Join-Path $projectRoot 'output/chatgpt-startup-2k60-6s-firstframe.jpg'
$iconPath = Join-Path $projectRoot 'assets/chatgpt.ico'
if (-not (Test-Path -LiteralPath $filmPath)) { throw 'Generate output/chatgpt-startup-2k60-6s.mp4 first.' }
if (-not (Test-Path -LiteralPath $posterPath)) { throw 'Generate output/chatgpt-startup-2k60-6s-firstframe.jpg first.' }

$outputPath = Join-Path $projectRoot 'ChatGPT-Startup-2K60-6s.exe'
$buildArguments = @(
    '/nologo',
    '/target:winexe',
    '/optimize+',
    '/codepage:65001',
    '/warn:4',
    '/warnaserror+',
    ('/out:' + $outputPath),
    ('/win32icon:' + $iconPath),
    ('/win32manifest:' + (Join-Path $projectRoot 'app.manifest')),
    ('/resource:' + $filmPath + ',ChatGPTStartup.mp4'),
    ('/resource:' + $posterPath + ',ChatGPTPoster.jpg'),
    ('/r:' + (Join-Path $frameworkPath 'WPF/PresentationCore.dll')),
    ('/r:' + (Join-Path $frameworkPath 'WPF/PresentationFramework.dll')),
    ('/r:' + (Join-Path $frameworkPath 'WPF/WindowsBase.dll')),
    ('/r:' + (Join-Path $frameworkPath 'System.Xaml.dll')),
    (Join-Path $projectRoot 'src/ChatGptStartupOptimized.cs')
)
& $compilerPath @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
Write-Output ('Built: ' + $outputPath)
