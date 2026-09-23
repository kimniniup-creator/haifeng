$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.env')) { throw 'Run install.ps1 and configure .env first.' }
& '.\.venv\Scripts\python.exe' -m agent_app
exit $LASTEXITCODE
