param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$env:PYTHONIOENCODING = 'utf-8'
$runtime = Join-Path $root '.runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) { & uv venv --python 3.12 .venv }
    else { & py -3.12 -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install uv or Python 3.12 and retry.' }
}
$stamp = Join-Path $runtime 'dependencies.sha256'
$hash = (Get-FileHash requirements.lock.txt -Algorithm SHA256).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $hash) {
    if (Get-Command uv -ErrorAction SilentlyContinue) { & uv pip install --python $python -r requirements.lock.txt }
    else { & $python -m pip install -r requirements.lock.txt }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. See terminal output.' }
    Set-Content -LiteralPath $stamp -Value $hash
}
$healthy = $false
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8088/v1/health' -TimeoutSec 2
    if ($health.service -eq 'luma-reachy-bridge') { $healthy = $true }
    else { throw 'Port 8088 belongs to another service.' }
} catch { if ($_.Exception.Message -like '*belongs*') { throw } }
if (-not $healthy) {
    $process = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','bridge.main:app','--host','127.0.0.1','--port','8088') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'bridge.stdout.log') -RedirectStandardError (Join-Path $runtime 'bridge.stderr.log') -PassThru
    Set-Content -LiteralPath (Join-Path $runtime 'bridge.pid') -Value $process.Id
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $health = Invoke-RestMethod 'http://127.0.0.1:8088/v1/health' -TimeoutSec 1; $healthy = $health.service -eq 'luma-reachy-bridge'; if($healthy){break} } catch {}
        if ($process.HasExited) { break }
    }
    if (-not $healthy) { throw "Bridge did not start. Read $runtime\bridge.stderr.log" }
}
if ($null -eq $health.legacy_robot_output_enabled) {
    throw 'An older bridge is already running without the output gate. Ask the maintenance owner to replace that process; this launcher will not restart it or touch the robot.'
}
Write-Output "Haifeng is ready at http://127.0.0.1:8088 (legacy robot output: $($health.legacy_robot_output_enabled))"
if ($health.legacy_robot_output_enabled -eq $true -and (Test-Path (Join-Path $root 'reachy-env\Scripts\reachy-mini-daemon.exe'))) { & (Join-Path $root 'start_robot.ps1') }
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8088' }
