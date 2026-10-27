' lva_save_diag.vbs - open/save sequence diagnostics with indicator reads.
Option Explicit
On Error Resume Next
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_save_diag_np2.log", True)

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

Set vi = app.GetVIReference("C:\LabView skill\gateway\LVA\LVA Session.vi", "", False, &H20)
Err.Clear
vi.Run True
lg.WriteLine Now & " Run: 0x" & Hex(Err.Number)

Dim rpO : rpO = "C:\LabView skill\_service\tmp\lva_reply_open.txt"
Dim rpS : rpS = "C:\LabView skill\_service\tmp\lva_reply_save.txt"
If fso.FileExists(rpO) Then fso.DeleteFile rpO, True
If fso.FileExists(rpS) Then fso.DeleteFile rpS, True

' --- open
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike_target.vi", Empty, False)
lg.WriteLine Now & " ArgOpen: 0x" & Hex(Err.Number)
vi.SetControlValue "Tool", ""
WScript.Sleep 200
vi.SetControlValue "Tool", "open_vi"
Dim vid : vid = WaitReply(rpO, "OPEN")
lg.WriteLine Now & " after open: ErrOpen=[" & ReadInd("ErrOpen") & "]"

' --- save attempt 1
Err.Clear
vi.SetControlValue "ArgSave", Array(CLng(vid), "C:\LabView skill\_service\tmp\lva_sd_saved1.vi", Empty, False)
lg.WriteLine Now & " ArgSave: 0x" & Hex(Err.Number)
vi.SetControlValue "Tool", ""
WScript.Sleep 300
vi.SetControlValue "Tool", "save_vi"
Dim r1 : r1 = WaitReply(rpS, "SAVE1")
lg.WriteLine Now & " after save1: ErrSave=[" & ReadInd("ErrSave") & "]"

' --- save attempt 2 (same id, new path)
If fso.FileExists(rpS) Then fso.DeleteFile rpS, True
Err.Clear
vi.SetControlValue "ArgSave", Array(CLng(vid), "C:\LabView skill\_service\tmp\lva_sd_saved2.vi", Empty, False)
vi.SetControlValue "Tool", ""
WScript.Sleep 300
vi.SetControlValue "Tool", "save_vi"
Dim r2 : r2 = WaitReply(rpS, "SAVE2")
lg.WriteLine Now & " after save2: ErrSave=[" & ReadInd("ErrSave") & "]"

' --- open a second file -> does the DC still work?
If fso.FileExists(rpO) Then fso.DeleteFile rpO, True
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_diag2_target.vi", Empty, False)
vi.SetControlValue "Tool", ""
WScript.Sleep 300
vi.SetControlValue "Tool", "open_vi"
Dim vid2 : vid2 = WaitReply(rpO, "OPEN2")
lg.WriteLine Now & " second open vi_id=" & vid2
lg.Close

Function WaitReply(p, tag)
  Dim k
  For k = 1 To 60
    WScript.Sleep 500
    If fso.FileExists(p) Then
      If fso.GetFile(p).Size > 0 Then Exit For
    End If
  Next
  If Not fso.FileExists(p) Then
    lg.WriteLine Now & " " & tag & " TIMEOUT"
    WaitReply = ""
    Exit Function
  End If
  Dim t : Set t = fso.OpenTextFile(p, 1)
  Dim s : s = t.ReadAll : t.Close
  lg.WriteLine Now & " " & tag & " reply: " & Replace(s, vbCrLf, " ")
  Dim re : Set re = New RegExp
  re.Pattern = "<Name>vi_id</Name>\s*<Val>(\d+)</Val>"
  If re.Test(s) Then
    WaitReply = re.Execute(s)(0).SubMatches(0)
  Else
    re.Pattern = "<Name>VI Path</Name>\s*<Val>([^<]*)</Val>"
    If re.Test(s) Then
      lg.WriteLine Now & " " & tag & " path=[" & re.Execute(s)(0).SubMatches(0) & "]"
      WaitReply = "PATH"
    Else
      WaitReply = ""
    End If
  End If
End Function

Function ReadInd(name)
  Dim v : v = vi.GetControlValue(name)
  If Err.Number <> 0 Then
    ReadInd = "GETERR 0x" & Hex(Err.Number) : Err.Clear
  Else
    If IsArray(v) Then
      ReadInd = "array(" & UBound(v) + 1 & ")"
    Else
      ReadInd = CStr(v)
    End If
  End If
End Function
