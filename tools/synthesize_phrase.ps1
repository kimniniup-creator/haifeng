param([string]$Text, [string]$Wav)
$v = New-Object -ComObject SAPI.SpVoice
$fs = New-Object -ComObject SAPI.SpFileStream
$fs.Format.Type = 22   # 16kHz 16bit mono
$fs.Open($Wav, 3)      # SSFMCreateForWrite
$v.AudioOutputStream = $fs
$v.Rate = 0
$v.Volume = 100
$v.Speak($Text) | Out-Null
$fs.Close()
Write-Output ("wav: " + (Get-Item $Wav).Length + " bytes")
