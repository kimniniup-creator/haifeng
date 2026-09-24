# Start the official Reachy Mini conversation app standalone (no desktop client).
# It connects to whatever daemon is listening on 127.0.0.1:8000.
# Personality and .env live in D:\海风\conversation (not committed).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$instance = Join-Path $root 'conversation'

try {
    $d = Invoke-RestMethod 'http://127.0.0.1:8000/api/daemon/status' -TimeoutSec 3
} catch {
    throw 'No daemon on 127.0.0.1:8000. Run start_robot_media.ps1 first.'
}
if ($d.state -ne 'running') { throw "Daemon state is '$($d.state)', expected 'running'." }
if ($d.no_media) { throw 'Daemon was started with --no-media; the app needs mic and speaker.' }

if (Get-NetTCPConnection -State Listen -LocalPort 7860 -ErrorAction SilentlyContinue) {
    Write-Output 'Port 7860 already in use; the conversation app is probably already running.'
    exit 0
}

New-Item -ItemType Directory -Force (Join-Path $root '.runtime') | Out-Null
$env:PYTHONIOENCODING = 'utf-8'

$proc = Start-Process -FilePath (Join-Path $root 'conv-env\Scripts\python.exe') -ArgumentList @('-u', '-m', 'reachy_mini_conversation_app.main') -WorkingDirectory $instance -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root '.runtime\conversation.stdout.log') -RedirectStandardError (Join-Path $root '.runtime\conversation.stderr.log')

Set-Content (Join-Path $root '.runtime\conversation.pid') $proc.Id
Write-Output "Conversation app starting, PID $($proc.Id). UI at http://127.0.0.1:7860"
Write-Output "Logs: .runtime\conversation.*.log"
