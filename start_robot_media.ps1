# Start the project's own Reachy daemon (SDK 1.11.0) WITH media enabled.
# This is the client-free path: REST expressions + audio + microphone.
# start_robot.ps1 stays as-is (--no-media) for the bridge-only case.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

try {
    $existing = Invoke-RestMethod 'http://127.0.0.1:8000/api/daemon/status' -TimeoutSec 2
    Write-Output "A daemon is already listening on 8000 (state=$($existing.state), version=$($existing.version)). Refusing to start a second one."
    exit 0
} catch {}

if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    throw 'Port 8000 is already in use; refusing to start a second daemon.'
}
if (-not (Test-Path 'reachy-env\Scripts\reachy-mini-daemon.exe')) {
    throw 'reachy-env is missing. Run start_robot.ps1 once to create it.'
}

New-Item -ItemType Directory -Force .runtime | Out-Null
$env:PYTHONIOENCODING = 'utf-8'

$args = @(
    '--no-wake-up-on-start',
    '--no-goto-sleep-on-stop',
    '--no-preload-datasets',
    '--fastapi-host', '127.0.0.1',
    '--log-level', 'INFO'
)
$proc = Start-Process -FilePath (Join-Path $root 'reachy-env\Scripts\reachy-mini-daemon.exe') -ArgumentList $args -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root '.runtime\daemon.stdout.log') -RedirectStandardError (Join-Path $root '.runtime\daemon.stderr.log')

Set-Content .runtime/daemon.pid $proc.Id
Write-Output "Reachy daemon starting, PID $($proc.Id). Logs in .runtime\daemon.*.log"
