' lva_smoke.vbs - full-restart smoke test, logs to file (no pipe loss).
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_smoke.log", True)
On Error Resume Next

Dim rpO : rpO = "C:\LabView skill\_service\tmp\lva_reply_open.txt"
Dim rpS : rpS = "C:\LabView skill\_service\tmp\lva_reply_save.txt"
If fso.FileExists(rpO) Then fso.DeleteFile rpO, True
If fso.FileExists(rpS) Then fso.DeleteFile rpS, True
If fso.FileExists("C:\LabView skill\_service\tmp\lva_smoke_saved.vi") Then fso.DeleteFile "C:\LabView skill\_service\tmp\lva_smoke_saved.vi", True

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

' preload LVA_State first (see lva_order2.vbs - session-first poisons both)
Err.Clear
Set vi = app.GetVIReference("C:\LabView skill\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
vi.Run True
lg.WriteLine Now & " state preload: 0x" & Hex(Err.Number)

Set vi = app.GetVIReference("C:\LabView skill\gateway\LVA\LVA Session.vi", "", False, &H20)
Err.Clear
vi.Run True
lg.WriteLine Now & " Run: 0x" & Hex(Err.Number) & " " & Err.Description

' drive open lane
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike_target.vi", Empty, False)
lg.WriteLine Now & " ArgOpen: 0x" & Hex(Err.Number)
vi.SetControlValue "Tool", ""
WScript.Sleep 200
vi.SetControlValue "Tool", "open_vi"
lg.WriteLine Now & " Tool: 0x" & Hex(Err.Number)

Dim vid : vid = ""
Dim k
For k = 1 To 60
  WScript.Sleep 500
  If fso.FileExists(rpO) Then
    If fso.GetFile(rpO).Size > 0 Then Exit For
  End If
Next
If fso.FileExists(rpO) Then
  Dim t : Set t = fso.OpenTextFile(rpO, 1)
  Dim s : s = t.ReadAll : t.Close
  Dim re : Set re = New RegExp
  re.Pattern = "<Name>vi_id</Name>\s*<Val>(\d+)</Val>"
  If re.Test(s) Then vid = re.Execute(s)(0).SubMatches(0)
  lg.WriteLine Now & " OPEN reply vi_id=" & vid & " status_ok=" & (InStr(s, "<Name>status</Name>") > 0)
  Dim rstatus : rstatus = ""
  re.Pattern = "<Name>status</Name>\s*<Val>(\d)</Val>"
  If re.Test(s) Then rstatus = re.Execute(s)(0).SubMatches(0)
  lg.WriteLine Now & " OPEN error.status=" & rstatus
Else
  lg.WriteLine Now & " OPEN TIMEOUT"
End If

' drive save lane
Err.Clear
vi.SetControlValue "ArgSave", Array(CLng(vid), "C:\LabView skill\_service\tmp\lva_smoke_saved.vi", Empty, False)
lg.WriteLine Now & " ArgSave: 0x" & Hex(Err.Number)
vi.SetControlValue "Tool", ""
WScript.Sleep 200
vi.SetControlValue "Tool", "save_vi"
lg.WriteLine Now & " Tool: 0x" & Hex(Err.Number)

Dim saved : saved = False
For k = 1 To 60
  WScript.Sleep 500
  If fso.FileExists(rpS) Then
    If fso.GetFile(rpS).Size > 0 Then Exit For
  End If
Next
If fso.FileExists(rpS) Then
  Set t = fso.OpenTextFile(rpS, 1)
  Dim sp : sp = t.ReadAll : t.Close
  lg.WriteLine Now & " SAVE reply: " & Replace(sp, vbCrLf, " ")
  WScript.Sleep 500
  saved = fso.FileExists("C:\LabView skill\_service\tmp\lva_smoke_saved.vi")
  lg.WriteLine Now & " saved file exists=" & saved
Else
  lg.WriteLine Now & " SAVE TIMEOUT"
End If

If vid <> "" And rstatus = "0" And saved Then
  lg.WriteLine Now & " SMOKE PASS"
Else
  lg.WriteLine Now & " SMOKE FAIL"
End If
lg.Close
