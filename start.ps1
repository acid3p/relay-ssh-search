$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create the environment first: py -m venv .venv; then install requirements. See README.md.'
}
& $projectPython manage.py runserver 127.0.0.1:8000
exit $LASTEXITCODE
