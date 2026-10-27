' lva_order2.vbs - preload LVA_State first, then the session; then re-probe both.
Option Explicit
On Error Resume Next
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_order2.log", True)

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

' 1. preload LVA_State by absolute path
Err.Clear
Set vi = app.GetVIReference(base & "\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
lg.WriteLine Now & " state ref: 0x" & Hex(Err.Number)
Err.Clear
vi.Run True
lg.WriteLine Now & " state Run (pre): 0x" & Hex(Err.Number)

' 2. open the session VI
Err.Clear
Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
lg.WriteLine Now & " session ref: 0x" & Hex(Err.Number)
Err.Clear
vi.Run True
lg.WriteLine Now & " session Run: 0x" & Hex(Err.Number)

' 3. re-probe both
Err.Clear
Set vi = app.GetVIReference(base & "\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
Err.Clear
vi.Run True
lg.WriteLine Now & " state Run (post): 0x" & Hex(Err.Number)
Err.Clear
Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
Err.Clear
vi.Run True
lg.WriteLine Now & " session Run (post): 0x" & Hex(Err.Number)
lg.Close
