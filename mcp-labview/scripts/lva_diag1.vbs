' lva_diag1.vbs - reproduce: open -> save via lva_call.vbs driver, log to file.
Option Explicit
Dim sh : Set sh = CreateObject("WScript.Shell")
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_diag1.log", True)

Dim out, rc
' 1. open (target must EXIST - open_vi opens a file from disk)
Dim tgt : tgt = "C:\LabView skill\_service\tmp\lva_spike_target.vi"
If Not fso.FileExists(tgt) Then
  fso.CopyFile "C:\LabView skill\_service\tmp\lva_server_target_saved.vi", tgt
End If
out = RunCap("cscript //nologo ""C:\LabView skill\mcp-labview\scripts\lva_call.vbs"" open_vi """ & tgt & """")
lg.WriteLine Now & " OPEN rc=" & rc & " out=" & out

' extract vi_id from the reply XML (naive)
Dim vid : vid = ""
Dim m1, m2
m1 = InStr(out, "<Name>vi_id</Name>")
If m1 > 0 Then
  m1 = InStr(m1, out, "<Val>")
  m2 = InStr(m1, out, "</Val>")
  If m1 > 0 And m2 > m1 Then vid = Mid(out, m1 + 5, m2 - m1 - 5)
End If
lg.WriteLine Now & " parsed vi_id=[" & vid & "]"

' 2. save
out = RunCap("cscript //nologo ""C:\LabView skill\mcp-labview\scripts\lva_call.vbs"" save_vi " & vid & " ""C:\LabView skill\_service\tmp\lva_diag1_saved.vi""")
lg.WriteLine Now & " SAVE rc=" & rc & " out=" & out

' 3. did the file appear?
WScript.Sleep 1000
lg.WriteLine Now & " saved file exists=" & fso.FileExists("C:\LabView skill\_service\tmp\lva_diag1_saved.vi")
lg.Close

Function RunCap(cmd)
  Dim oExec : Set oExec = sh.Exec(cmd)
  Do While oExec.Status = 0
    WScript.Sleep 200
  Loop
  rc = oExec.ExitCode
  RunCap = oExec.StdOut.ReadAll & " STDERR:" & oExec.StdErr.ReadAll
End Function
