param([string]$RuntimeRoot = (Join-Path $PSScriptRoot '..\..\.runtime'))
$ErrorActionPreference = 'Stop'
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$voiceEnvironment = Join-Path $RuntimeRoot 'voice-env'
$voicePython = Join-Path $voiceEnvironment 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $voicePython)) {
    uv venv $voiceEnvironment --python 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Could not create voice environment' }
}
uv pip install --python $voicePython -r (Join-Path $PSScriptRoot 'requirements-pet.txt')
if ($LASTEXITCODE -ne 0) { throw 'Voice dependency installation failed' }
$models = Join-Path $RuntimeRoot 'voice-models'
New-Item -ItemType Directory -Path $models -Force | Out-Null
$assets = @(
    @('sensevoice.tar.bz2', 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2', '7D1EFA2138A65B0B488DF37F8B89E3D91A60676E416F515B952358D83DFD347E'),
    @('silero_vad.onnx', 'silero_vad.onnx', '9E2449E1087496D8D4CABA907F23E0BD3F78D91FA552479BB9C23AC09CBB1FD6')
)
foreach ($asset in $assets) {
    $target = Join-Path $models $asset[0]
    if (-not (Test-Path -LiteralPath $target)) {
        curl.exe --fail -L --retry 2 -o $target ('https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/' + $asset[1])
        if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $asset[2]) { throw "Model hash mismatch: $target" }
}
& $voicePython -c 'import pathlib,sys,tarfile; p=pathlib.Path(sys.argv[1]); t=tarfile.open(p/"sensevoice.tar.bz2"); t.extractall(p,filter="data"); t.close()' $models
if ($LASTEXITCODE -ne 0) { throw 'Model extraction failed' }
Write-Output "Ready. Stop the existing Conversation App before starting pet_companion.py --models `"$models`"."
