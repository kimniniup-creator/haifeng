param(
    [string]$Python = '',
    [int]$Port = 8091,
    [switch]$EnableDevices,
    [switch]$EnableMotion,
    [string]$VoiceUrl = ''
)
$ErrorActionPreference = 'Stop'
$petRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $Python) { $Python = Join-Path $petRoot '.runtime/pet-env/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Create the isolated pet environment from requirements-pet.txt, or pass -Python explicitly. No daemon or audio process has been started.'
}
if ($EnableMotion -and -not $EnableDevices) { throw '-EnableMotion requires -EnableDevices' }
if ($VoiceUrl -and -not $EnableDevices) { throw '-VoiceUrl requires -EnableDevices' }
$petRuntime = Join-Path $petRoot '.runtime'
New-Item -ItemType Directory -Path $petRuntime -Force | Out-Null
$petTokenFile = Join-Path $petRuntime 'pet-local-tokens.json'
if (-not (Test-Path -LiteralPath $petTokenFile)) {
    # Generate local credentials without echoing them or passing them as command arguments.
    & $Python -c 'import json,secrets,sys; from pathlib import Path; p=Path(sys.argv[1]); p.write_text(json.dumps({"operator":secrets.token_urlsafe(32),"vision":secrets.token_urlsafe(32)}),encoding="utf-8")' $petTokenFile
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate local credentials' }
}
$petTokens = Get-Content -LiteralPath $petTokenFile -Raw | ConvertFrom-Json
$oldOperatorToken = $env:PET_API_TOKEN
$oldVisionToken = $env:PET_VISION_TOKEN
try {
    $env:PET_API_TOKEN = $petTokens.operator
    $env:PET_VISION_TOKEN = $petTokens.vision
    $petArguments = @('-m', 'pet_interaction', '--port', "$Port")
    if ($EnableDevices) { $petArguments += '--enable-devices' }
    if ($EnableMotion) { $petArguments += '--enable-motion' }
    if ($VoiceUrl) { $petArguments += @('--voice-url', $VoiceUrl) }
    Push-Location -LiteralPath $petRoot
    try { & $Python @petArguments } finally { Pop-Location }
} finally {
    $env:PET_API_TOKEN = $oldOperatorToken
    $env:PET_VISION_TOKEN = $oldVisionToken
}
