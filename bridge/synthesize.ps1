param([Parameter(Mandatory=$true)][string]$TextPath, [Parameter(Mandatory=$true)][string]$WavePath)
$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$stream = New-Object -ComObject SAPI.SpFileStream
try {
    $chinese = @($voice.GetVoices() | Where-Object { $_.GetDescription() -match 'Huihui|Chinese|中文' })
    if ($chinese.Count -gt 0) { $voice.Voice = $chinese[0] }
    $voice.Rate = 0
    $voice.Volume = 75
    $stream.Open($WavePath, 3, $false)
    $voice.AudioOutputStream = $stream
    $text = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
    [void]$voice.Speak($text, 0)
} finally { $stream.Close() }
