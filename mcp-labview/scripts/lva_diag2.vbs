' lva_diag2.vbs - prove DC persistence: open a second VI -> expect vi_id=2.
Option Explicit
Dim sh : Set sh = CreateObject("WScript.Shell")
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_diag2.log", True)

' make a distinct second target
Dim t2 : t2 = "C:\LabView skill\_service\tmp\lva_diag2_target.vi"
If Not fso.FileExists(t2) Then fso.CopyFile "C:\LabView skill\_service\tmp\lva_spike_target.vi", t2

Dim out, rc, vid, m1, m2
out = RunCap("cscript //nologo ""C:\LabView skill\mcp-labview\scripts\lva_call.vbs"" open_vi """ & t2 & """")
lg.WriteLine Now & " OPEN2 rc=" & rc & " out=" & out
vid = ParseId(out)
lg.WriteLine Now & " second vi_id=[" & vid & "] (expect 2 if DC persisted)"
lg.Close

Function ParseId(s)
  Dim a, b
  a = InStr(s, "<Name>vi_id</Name>")
  If a = 0 Then Exit Function
  a = InStr(a, s, "<Val>")
  b = InStr(a, s, "</Val>")
  If a > 0 And b > a Then ParseId = Mid(s, a + 5, b - a - 5)
End Function

Function RunCap(cmd)
  Dim oExec : Set oExec = sh.Exec(cmd)
  Do While oExec.Status = 0
    WScript.Sleep 200
  Loop
  rc = oExec.ExitCode
  RunCap = oExec.StdOut.ReadAll & " STDERR:" & oExec.StdErr.ReadAll
End Function
