$ErrorActionPreference = 'Stop'
$bridgeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $bridgeRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
}
& .venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (-not $env:BRIDGE_TOKEN) { $env:BRIDGE_TOKEN = 'local-development-token' }
if (-not $env:DATA_DIR) { $env:DATA_DIR = Join-Path $bridgeRoot 'data' }
if (-not $env:LUMA_CLI_PATH) {
    $defaultLumaCli = Join-Path $bridgeRoot 'upstream\luma-core\target\release\examples\luma.exe'
    if (Test-Path $defaultLumaCli) { $env:LUMA_CLI_PATH = $defaultLumaCli }
}
$listenHost = if ($env:BRIDGE_HOST) { $env:BRIDGE_HOST } else { '127.0.0.1' }
$listenPort = if ($env:BRIDGE_PORT) { [int]$env:BRIDGE_PORT } else { 8088 }
& .venv\Scripts\python.exe -m uvicorn bridge.main:app --host $listenHost --port $listenPort
