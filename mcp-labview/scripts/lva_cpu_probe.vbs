' lva_cpu_probe.vbs - sample LabVIEW CPU% over ~10s. Requires LabVIEW alive
' with the server running (start keeper first).
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim wmi : Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Dim i, p, s
For i = 1 To 10
  s = "?"
  For Each p In wmi.ExecQuery("SELECT PercentProcessorTime FROM Win32_PerfFormattedData_PerfProc_Process WHERE Name LIKE 'LabVIEW%'")
    s = p.PercentProcessorTime
  Next
  WScript.Echo "cpu=" & s & "%"
  WScript.Sleep 1000
Next
