# Start the local realtime relay that the conversation app talks to.
# Replaces the hosted HuggingFace relay, which caps an account at two sessions
# and never releases them. Credentials come from .env (SCENE_API_*).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) {
    Write-Output 'Port 8765 already in use; the realtime server is probably already running.'
    exit 0
}

New-Item -ItemType Directory -Force (Join-Path $root '.runtime') | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
# openWakeWord ships the Silero model; reuse it rather than fetching another.
$env:REACHY_SILERO_ONNX = Join-Path $root 'conv-env\Lib\site-packages\openwakeword\resources\models\silero_vad.onnx'

$proc = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -ArgumentList @('-u', '-m', 'realtime_server.server') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root '.runtime\realtime.stdout.log') -RedirectStandardError (Join-Path $root '.runtime\realtime.stderr.log')

Set-Content (Join-Path $root '.runtime\realtime.pid') $proc.Id
Write-Output "Realtime server starting, PID $($proc.Id) on ws://127.0.0.1:8765/v1/realtime"
Write-Output "Logs: .runtime\realtime.*.log"
