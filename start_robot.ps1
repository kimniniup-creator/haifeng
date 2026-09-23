$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$existing = $null
try { $existing = Invoke-RestMethod 'http://127.0.0.1:8000/api/daemon/status' -TimeoutSec 2 } catch {}
if ($existing) {
    Write-Output "Existing Reachy daemon state: $($existing.state)."
    if ($existing.state -eq 'error' -or $existing.state -eq 'stopped') {
        try {
            $null = Invoke-RestMethod 'http://127.0.0.1:8000/api/daemon/start?wake_up=false' -Method Post -TimeoutSec 20
            Write-Output 'Connection retry requested without waking motors. Refresh Haifeng after a few seconds.'
        } catch { Write-Output 'Existing daemon could not reconnect. Check its independent power supply and daemon log.' }
    }
    exit 0
}
if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) { throw 'Port 8000 is already in use; refusing to start a second daemon.' }
if (-not (Test-Path 'reachy-env\Scripts\reachy-mini-daemon.exe')) {
    & uv venv --python 3.12 reachy-env
    & uv pip install --python reachy-env\Scripts\python.exe 'reachy-mini==1.11.0'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install the Reachy daemon.' }
}
New-Item -ItemType Directory -Force .runtime | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$process = Start-Process -FilePath (Join-Path $root 'reachy-env\Scripts\reachy-mini-daemon.exe') -ArgumentList @('--no-media','--no-wake-up-on-start','--no-goto-sleep-on-stop','--fastapi-host','127.0.0.1') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root '.runtime\daemon.stdout.log') -RedirectStandardError (Join-Path $root '.runtime\daemon.stderr.log') -PassThru
Set-Content .runtime/daemon.pid $process.Id
Write-Output 'Reachy daemon starting. Check the device state in Haifeng.'
