' lva_call.vbs - call a tool lane on the running LVA Session server (gateway\LVA\LVA Session.vi).
' Usage:
'   lva_call.vbs open_vi <vi_path>
'   lva_call.vbs save_vi <vi_id> <save_path>
' Prints the reply XML to stdout. Exit 0 = reply received, 1 = timeout/error.
' Protocol: request via COM SetControlValue, reply via file (GetControlValue is
' stale during a run - file reply is the only reliable channel).
' Server persistence: a keeper process (lva_keeper.vbs) holds the COM reference
' so the COM-launched LabVIEW never quits between calls. This script ensures
' the keeper is running first.
Option Explicit
Const VI_OPEN_NO_DIALOGS = &H20
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim sh : Set sh = CreateObject("WScript.Shell")
Dim base : base = "C:\LabView skill"
Dim viPath : viPath = base & "\gateway\LVA\LVA Session.vi"
Dim readyF : readyF = base & "\_service\tmp\lva_keeper_ready.txt"
Dim keeper : keeper = base & "\mcp-labview\scripts\lva_keeper.vbs"

Dim tool : tool = WScript.Arguments(0)
Dim replyPath, argCtl
If tool = "open_vi" Then
  replyPath = base & "\_service\tmp\lva_reply_open.txt"
  argCtl = "ArgOpen"
ElseIf tool = "save_vi" Then
  replyPath = base & "\_service\tmp\lva_reply_save.txt"
  argCtl = "ArgSave"
Else
  WScript.Echo "ERROR: unknown tool " & tool
  WScript.Quit 1
End If

EnsureServer

Dim app, vi, i
For i = 1 To 15
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < 15 Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: no LabVIEW.Application: 0x" & Hex(Err.Number)
  WScript.Quit 1
End If
Set vi = app.GetVIReference(viPath, "", False, VI_OPEN_NO_DIALOGS)

' COM calls below raise trappable errors on expected conditions
' (Run True on a running VI raises 0x1964 = already running) - check Err.Number
On Error Resume Next

' ensure the server hierarchy is running (Run is async; 0x1964 = already running)
Err.Clear
vi.Run True
If Err.Number <> 0 And Err.Number <> &H1964 Then WScript.Sleep 2000

' set the lane arguments (cluster control accepts a variant array)
Err.Clear
If tool = "open_vi" Then
  vi.SetControlValue "ArgOpen", Array(WScript.Arguments(1), Empty, False)
Else
  vi.SetControlValue "ArgSave", Array(CLng(WScript.Arguments(1)), WScript.Arguments(2), Empty, False)
End If
If Err.Number <> 0 Then
  WScript.Echo "ERROR: SetControlValue " & argCtl & ": 0x" & Hex(Err.Number) & " " & Err.Description
  WScript.Quit 1
End If

' reset the edge trigger, then set the tool (Chg needs a change)
Err.Clear
vi.SetControlValue "Tool", ""
WScript.Sleep 100
If fso.FileExists(replyPath) Then fso.DeleteFile replyPath, True
Err.Clear
vi.SetControlValue "Tool", tool
If Err.Number <> 0 Then
  WScript.Echo "ERROR: SetControlValue Tool: 0x" & Hex(Err.Number)
  WScript.Quit 1
End If

' poll the reply file
Dim ok : ok = False
For i = 1 To 80
  WScript.Sleep 250
  If fso.FileExists(replyPath) Then
    If fso.GetFile(replyPath).Size > 0 Then
      Dim tr : Set tr = fso.OpenTextFile(replyPath, 1)
      WScript.Echo tr.ReadAll
      tr.Close
      ok = True
      Exit For
    End If
  End If
Next
If Not ok Then
  WScript.Echo "ERROR: no reply within 20s"
  WScript.Quit 1
End If

Sub EnsureServer
  ' precise check: is a keeper cscript process alive? (CreateObject would SPAWN
  ' LabVIEW, so it is not a valid liveness probe)
  Dim wmi, procs
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE CommandLine LIKE '%lva_keeper.vbs%' AND Name='cscript.exe'")
  If procs.Count = 0 Then
    If fso.FileExists(readyF) Then fso.DeleteFile readyF, True
    sh.Run "cscript //nologo """ & keeper & """", 0, False
    Dim i
    For i = 1 To 90
      WScript.Sleep 1000
      If fso.FileExists(readyF) Then Exit For
    Next
    If Not fso.FileExists(readyF) Then
      WScript.Echo "ERROR: keeper did not become ready in 90s"
      WScript.Quit 1
    End If
  End If
End Sub
