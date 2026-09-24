# Bring the two watchers back after a restart or a power cut.
#
# They are what lets the robot survive a USB dropout unattended: robot_guard
# revives the daemon and re-enables the motors, then restarts the conversation
# app so it re-attaches to it.
#
# Every path comes from $PSScriptRoot and this file stays pure ASCII on
# purpose. Windows PowerShell reads a .ps1 as ANSI, so a hard-coded path with
# non-ASCII characters in it arrives mangled and every redirect fails with
# DirectoryNotFoundException - which is exactly how this file came to exist.
$root = $PSScriptRoot
$py   = Join-Path $root '.venv\Scripts\python.exe'
$run  = Join-Path $root '.runtime'

# Tight timings on purpose: a robot left dead for four minutes during a demo
# is a dead demo. The backoff still exists, it is just short.
$jobs = @(
  @{ name = 'robot_guard'
     script = Join-Path $root 'tools\robot_guard.py'
     extra = @('--cooldown', '20', '--max-backoff', '60') },
  @{ name = 'watchdog'
     script = Join-Path $root 'tools\conversation_watchdog.py'
     extra = @() }
)

foreach ($j in $jobs) {
  $name    = $j.name
  $pidFile = Join-Path $run "$name.pid"

  # Never leave two guards fighting over the same daemon. The pid file only
  # covers the last one this script started, so sweep by command line too -
  # a stray guard from an earlier hand-typed launch is exactly what made one
  # instance back off for four minutes while another kept restarting.
  #
  # Counting processes to check this is a trap: the venv's python.exe is a
  # launcher stub that spawns the real interpreter as a child, so ONE guard
  # always shows up as TWO python.exe rows with the same command line and the
  # same creation time. Killing "the duplicate" kills the pair. Judge by
  # whether robot_guard.log is still advancing, not by the process count.
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match [regex]::Escape($j.script) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

  $argv = @('-u', $j.script) + $j.extra
  $p = Start-Process -FilePath $py -ArgumentList $argv `
       -WorkingDirectory $root -WindowStyle Hidden -PassThru `
       -RedirectStandardOutput (Join-Path $run "$name.out.log") `
       -RedirectStandardError  (Join-Path $run "$name.err.log")
  $p.Id | Out-File -Encoding ascii $pidFile
  Write-Output "$name pid $($p.Id) args: $($argv -join ' ')"
}
