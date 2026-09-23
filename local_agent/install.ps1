$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.\.venv\Scripts\python.exe')) {
    # Prefer the documented 3.11 runtime, but make the installer usable on
    # hosts that only have the supported 3.12 runtime available.
    $pythonVersion = $null
    foreach ($candidate in @('3.11', '3.12')) {
        try { & py "-$candidate" -c "import sys" 2>$null } catch { }
        if ($LASTEXITCODE -eq 0) { $pythonVersion = $candidate; break }
    }
    if (!$pythonVersion) { throw 'Python 3.11 or 3.12 is required to create the virtual environment.' }
    & py "-$pythonVersion" -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python $pythonVersion venv creation failed." }
}
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt -c constraints-tested.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (!(Test-Path '.env')) {
    $settings = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '.env.example'))
    $randomBytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($randomBytes) } finally { $rng.Dispose() }
    $bridgeSecret = [Convert]::ToBase64String($randomBytes)
    $settings = $settings.Replace('BRIDGE_TOKEN=', ('BRIDGE_TOKEN=' + $bridgeSecret))
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $settings, (New-Object Text.UTF8Encoding($false)))
}
Write-Host 'Installed. Edit .env, then run doctor checks and start.ps1.'
