# Start Reachy's diary: the page visitors read at the booth.
# Reads the glasses photos in .runtime\glasses and the readings in data\diary.json.
# Nothing here touches the robot, the bridge or the realtime relay.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = if ($env:REACHY_DIARY_PORT) { $env:REACHY_DIARY_PORT } else { '8800' }

if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    Write-Output "Port $port already in use; the diary is probably already up at http://127.0.0.1:$port"
    exit 0
}

New-Item -ItemType Directory -Force (Join-Path $root '.runtime') | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$env:REACHY_DIARY_PORT = $port

$proc = Start-Process -FilePath (Join-Path $root '.venv\Scripts\python.exe') -ArgumentList @('-u', (Join-Path $root 'diary\server.py')) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root '.runtime\diary.stdout.log') -RedirectStandardError (Join-Path $root '.runtime\diary.stderr.log')

# The venv's python.exe is a launcher: the process that actually holds the port
# is its child. Record both, or Stop-Process kills the launcher and leaves the
# diary serving happily on a port nobody can take back.
$pids = @($proc.Id)
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    $owner = (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
    if ($owner) { if ($owner -ne $proc.Id) { $pids += $owner }; break }
}

Set-Content (Join-Path $root '.runtime\diary.pid') $pids
if ($owner) {
    Write-Output "Reachy's diary is up: http://127.0.0.1:$port"
} else {
    Write-Output "Reachy's diary did not answer on port $port; see .runtime\diary.stderr.log"
}
Write-Output "Logs: .runtime\diary.*.log"
Write-Output "Stop it with: Get-Content .runtime\diary.pid | ForEach-Object { Stop-Process -Id `$_ -Force -ErrorAction SilentlyContinue }"
