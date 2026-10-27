' lva_dep_probe.vbs - probe each subVI of the session server with Run True
' from THIS LabVIEW instance; reports which are broken. 64-bit cscript!
Option Explicit
On Error Resume Next
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_dep_probe1.log", True)

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

Dim base : base = "C:\LabView skill"
Dim vis : vis = Array(WScript.Arguments(0))

Dim p
For Each p In vis
  Err.Clear
  Set vi = app.GetVIReference(p, "", False, &H20)
  If Err.Number <> 0 Then
    lg.WriteLine Now & " REF FAIL 0x" & Hex(Err.Number) & " " & p
  Else
    Err.Clear
    vi.Run True
    If Err.Number = 0 Then
      lg.WriteLine Now & " RUN OK  " & p
    Else
      lg.WriteLine Now & " RUN 0x" & Hex(Err.Number) & " " & p
    End If
  End If
Next
lg.Close
