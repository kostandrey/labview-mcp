' lva_relink.vbs - re-save the cleaned session VI with a correct LVA_State link.
' Preload LVA_State.vi by absolute path, open the session VI (its relative
' link binds to the correct in-memory copy), then Save - the stored link is
' rewritten as-resolved.
Option Explicit
On Error Resume Next
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_relink.log", True)

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

' 1. preload the CORRECT LVA_State by absolute path
Dim vst : Set vst = app.GetVIReference(base & "\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
lg.WriteLine Now & " state ref: 0x" & Hex(Err.Number)

' 2. open the session VI - link binds to the correct in-memory copy
Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
lg.WriteLine Now & " session ref: 0x" & Hex(Err.Number)
Err.Clear
vi.Run True
lg.WriteLine Now & " session Run: 0x" & Hex(Err.Number)

' 3. save the session VI -> rewrites the subVI links as-resolved
Err.Clear
vi.SaveInstrument base & "\gateway\LVA\LVA Session.vi", False, False
lg.WriteLine Now & " session SaveInstrument: 0x" & Hex(Err.Number) & " " & Err.Description
lg.Close
