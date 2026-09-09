$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'The project virtual environment was not found. Create .venv and install requirements first.'
}

Push-Location $PSScriptRoot
try {
    & $pythonPath -m app.main
}
finally {
    Pop-Location
}
