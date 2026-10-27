' lva_order_probe.vbs - does opening the session VI first poison LVA_State?
Option Explicit
On Error Resume Next
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_order_probe.log", True)

Dim app, vi, i
For i = 1 To 30
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < 30 Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  lg.WriteLine Now & " FATAL no LabVIEW.Application 0x" & Hex(Err.Number)
  lg.Close : WScript.Quit 1
End If
lg.WriteLine Now & " attached"

Dim wmi2, p3
Set wmi2 = GetObject("winmgmts:\\.\root\cimv2")
For Each p3 In wmi2.ExecQuery("SELECT CreationDate FROM Win32_Process WHERE Name='LabVIEW.exe'")
  lg.WriteLine Now & " LV process started " & p3.CreationDate
Next

Dim base : base = "C:\LabView skill"

' 1. open the SESSION VI first (driver's order)
Err.Clear
Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
lg.WriteLine Now & " session ref: 0x" & Hex(Err.Number)
Err.Clear
vi.Run True
lg.WriteLine Now & " session Run: 0x" & Hex(Err.Number)

' 2. now probe LVA_State alone
Err.Clear
Set vi = app.GetVIReference(base & "\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
lg.WriteLine Now & " state ref: 0x" & Hex(Err.Number)
Err.Clear
vi.Run True
lg.WriteLine Now & " state Run: 0x" & Hex(Err.Number)
lg.Close
