$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$desktopPath = [Environment]::GetFolderPath('Desktop')
$launcherPath = Join-Path $projectRoot 'tools\launch_current.py'
$workPath = Join-Path $projectRoot 'build\launcher'
$specPath = Join-Path $projectRoot 'build\launcher-spec'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Project Python was not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "Launcher source was not found: $launcherPath"
}

& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name CodeTrace `
    --distpath $desktopPath `
    --workpath $workPath `
    --specpath $specPath `
    $launcherPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$builtPath = Join-Path $desktopPath 'CodeTrace.exe'
if (-not (Test-Path -LiteralPath $builtPath -PathType Leaf)) {
    throw "Launcher EXE was not created: $builtPath"
}

Write-Output "Desktop launcher created: $builtPath"
