' lva_server_e2e3.vbs - trigger-trace drive: wait for trig file (first-iteration stall!),
' then set Tool, poll replies generously, dump trig state.
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim ts : Set ts = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_e2e3.log", True)
ts.WriteLine Now & " e2e3 start"
On Error Resume Next

Dim rp : rp = Array("C:\LabView skill\_service\tmp\lva_reply_open.txt", _
                    "C:\LabView skill\_service\tmp\lva_reply_save.txt", _
                    "C:\LabView skill\_service\tmp\lva_server_tick.txt", _
                    "C:\LabView skill\_service\tmp\lva_server_trig.txt")
Dim i
For i = 0 To 3
  If fso.FileExists(rp(i)) Then fso.DeleteFile rp(i), True
Next

Dim sh : Set sh = CreateObject("WScript.Shell")
sh.Run "cscript //nologo ""C:\LabView skill\mcp-labview\scripts\lva_server_bg.vbs""", 0, False
ts.WriteLine Now & " bg launched"

Dim app : Set app = CreateObject("LabVIEW.Application")
Dim vi : Set vi = app.GetVIReference("C:\LabView skill\_service\tmp\lva_server.vi", "", False, &H20)
Err.Clear
vi.Run True
ts.WriteLine Now & " Run: 0x" & Hex(Err.Number)

' wait for trig file - loop body executes (may stall ~40s on first-exec compile)
Dim j, got : got = False
For j = 1 To 180
  WScript.Sleep 500
  If fso.FileExists(rp(3)) Then got = True : Exit For
Next
If Not got Then
  ts.WriteLine Now & " NO TRIG FILE after 90s - loop body never executed"
  ts.Close
  WScript.Quit
End If
ts.WriteLine Now & " trig file present at t+" & (j * 0.5) & "s"

' drive open lane
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike_target.vi", Empty, False)
ts.WriteLine Now & " ArgOpen set: 0x" & Hex(Err.Number)
Err.Clear
vi.SetControlValue "Tool", "open_vi"
ts.WriteLine Now & " Tool=open_vi: 0x" & Hex(Err.Number)
PollReply ts, fso, rp(0), "OPEN", 15000

' drive save lane
Err.Clear
vi.SetControlValue "ArgSave", Array(1, "C:\LabView skill\_service\tmp\lva_server_target_saved.vi", Empty, False)
ts.WriteLine Now & " ArgSave set: 0x" & Hex(Err.Number)
Err.Clear
vi.SetControlValue "Tool", "save_vi"
ts.WriteLine Now & " Tool=save_vi: 0x" & Hex(Err.Number)
PollReply ts, fso, rp(1), "SAVE", 15000

WScript.Sleep 2000
ts.WriteLine Now & " final trig=[" & ReadFile(fso, rp(3)) & "] tick_size=" & FileSize(fso, rp(2))
ts.Close

Sub PollReply(ts, fso, p, tag, ms)
  Dim j
  For j = 1 To (ms \ 500)
    WScript.Sleep 500
    If fso.FileExists(p) Then
      ts.WriteLine Now & " " & tag & " REPLY t+" & (j * 0.5) & "s size=" & fso.GetFile(p).Size
      If fso.GetFile(p).Size > 0 Then ts.WriteLine tag & " CONTENT: " & ReadFile(fso, p)
      Exit Sub
    End If
  Next
  ts.WriteLine Now & " " & tag & " TIMEOUT"
  ts.WriteLine Now & " trig now=[" & ReadFile(fso, "C:\LabView skill\_service\tmp\lva_server_trig.txt") & "]"
End Sub

Function ReadFile(fso, p)
  On Error Resume Next
  ReadFile = ""
  If Not fso.FileExists(p) Then Exit Function
  Dim tr : Set tr = fso.OpenTextFile(p, 1)
  ReadFile = tr.ReadAll
  tr.Close
End Function

Function FileSize(fso, p)
  FileSize = -1
  If fso.FileExists(p) Then FileSize = fso.GetFile(p).Size
End Function
