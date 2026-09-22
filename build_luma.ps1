$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$lumaRoot = Join-Path $projectRoot 'upstream\luma-core'
$patchPath = Join-Path $projectRoot 'patches\luma-core-e06-device-selector.patch'
$sourcePath = Join-Path $lumaRoot 'src\client\ble.rs'

if (-not (Test-Path (Join-Path $lumaRoot 'Cargo.toml'))) {
    & git -C $projectRoot submodule update --init upstream/luma-core
    if ($LASTEXITCODE -ne 0) { throw 'Unable to initialize the luma-core submodule.' }
}

$patchAppliedHere = $false
$sourceAlreadyPatched = Select-String -Path $sourcePath -Pattern 'std::env::var\("LUMA_DEVICE"\)' -Quiet
if (-not $sourceAlreadyPatched) {
    & git -C $lumaRoot apply --check $patchPath
    if ($LASTEXITCODE -ne 0) { throw 'The E06 compatibility patch does not apply to this luma-core revision.' }
    & git -C $lumaRoot apply $patchPath
    if ($LASTEXITCODE -ne 0) { throw 'Unable to apply the E06 compatibility patch.' }
    $patchAppliedHere = $true
}

try {
    & cargo build --locked --release --example luma --features ble --manifest-path (Join-Path $lumaRoot 'Cargo.toml')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to build the Luma BLE client.' }
}
finally {
    if ($patchAppliedHere) {
        & git -C $lumaRoot apply --reverse $patchPath
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'The client built successfully, but the temporary source patch could not be reverted.'
        }
    }
}
