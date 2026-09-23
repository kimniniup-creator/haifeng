# Kept as the compatible foreground launch entry point.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
& .\start.ps1 -NoBrowser
