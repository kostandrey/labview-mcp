Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*server.py*' } |
  ForEach-Object { "PID=$($_.ProcessId) started=$($_.CreationDate) cmd=$($_.CommandLine)" }
if (-not $?) { }
