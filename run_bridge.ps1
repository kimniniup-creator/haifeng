$ErrorActionPreference = 'Stop'
$bridgeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $bridgeRoot

$envFile = Join-Path $bridgeRoot '.env'
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -notmatch '^\s*(?:#|$)' -and $line -match '^\s*([^=]+?)\s*=\s*(.*)\s*$') {
            $name = $matches[1]
            $value = $matches[2].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if (-not (Test-Path "Env:$name")) { Set-Item -Path "Env:$name" -Value $value }
        }
    }
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
}
& .venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (-not $env:BRIDGE_TOKEN) { $env:BRIDGE_TOKEN = 'local-development-token' }
if (-not $env:DATA_DIR) { $env:DATA_DIR = Join-Path $bridgeRoot 'data' }
if (-not $env:LUMA_CLI_PATH) {
    $defaultLumaCli = Join-Path $bridgeRoot 'upstream\luma-core\target\release\examples\luma.exe'
    if (-not (Test-Path $defaultLumaCli)) { & (Join-Path $bridgeRoot 'build_luma.ps1') }
    if (Test-Path $defaultLumaCli) { $env:LUMA_CLI_PATH = $defaultLumaCli }
}
$listenHost = if ($env:BRIDGE_HOST) { $env:BRIDGE_HOST } else { '127.0.0.1' }
$listenPort = if ($env:BRIDGE_PORT) { [int]$env:BRIDGE_PORT } else { 8088 }
& .venv\Scripts\python.exe -m uvicorn bridge.main:app --host $listenHost --port $listenPort
