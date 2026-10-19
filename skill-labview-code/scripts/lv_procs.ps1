$procs = Get-Process LabVIEW -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    $path = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").ExecutablePath
    Write-Output ("pid=" + $p.Id + " path=" + $path)
}
