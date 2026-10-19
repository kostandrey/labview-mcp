' test_getterminal.vbs - call GetTerminal.vi directly (bypasses Gateway.vi)
' Usage: cscript //nologo test_getterminal.vbs <TerminalType> <Label> <TerminalIndex>
Option Explicit

Const VI_OPEN_NO_DIALOGS = &H20

Dim tt, lbl, tidx
tt = "c" : lbl = "A" : tidx = 0
If WScript.Arguments.Count > 0 Then tt = WScript.Arguments(0)
If WScript.Arguments.Count > 1 Then lbl = WScript.Arguments(1)
If WScript.Arguments.Count > 2 Then tidx = CLng(WScript.Arguments(2))

Dim app
Set app = CreateObject("LabVIEW.Application")

Dim gt, demo
Set gt = app.GetVIReference("C:\LabView skill\gateway\GetTerminal.vi", "", False, VI_OPEN_NO_DIALOGS)
Set demo = app.GetVIReference("C:\LabView skill\gen\demo.vi", "", False, VI_OPEN_NO_DIALOGS)

On Error Resume Next
Err.Clear
gt.SetControlValue "TerminalType", tt
If Err.Number <> 0 Then WScript.Echo "ERR set TerminalType: " & Err.Description : WScript.Quit 1
Err.Clear
gt.SetControlValue "Label", lbl
If Err.Number <> 0 Then WScript.Echo "ERR set Label: " & Err.Description : WScript.Quit 1
Err.Clear
gt.SetControlValue "TerminalIndex", tidx
If Err.Number <> 0 Then WScript.Echo "ERR set TerminalIndex: " & Err.Description : WScript.Quit 1
Err.Clear
gt.SetControlValue "vi reference", demo
If Err.Number <> 0 Then WScript.Echo "ERR set vi reference: " & Err.Description : WScript.Quit 1

Err.Clear
gt.Run
If Err.Number <> 0 Then WScript.Echo "RUN ERR: " & Err.Description : WScript.Quit 1

Dim eo
eo = gt.GetControlValue("error out")
If Err.Number <> 0 Then WScript.Echo "ERR get error out: " & Err.Description : WScript.Quit 1

' cluster comes back as variant array: status (bool), code (i32), source (string)
Dim s
On Error GoTo 0
s = "error out: status=" & CStr(eo(0)) & " code=" & CStr(eo(1)) & " source=" & eo(2)
WScript.Echo s

Dim trm
Err.Clear
trm = gt.GetControlValue("Terminal out")
If Err.Number = 0 Then
  If IsNull(trm) Then
    WScript.Echo "Terminal out: NULL"
  Else
    WScript.Echo "Terminal out: " & CStr(trm)
  End If
Else
  WScript.Echo "Terminal out: (unreadable: " & Err.Description & ")"
End If

gt.CloseFrontPanel
gt.Revert
demo.CloseFrontPanel
Set gt = Nothing : Set demo = Nothing : Set app = Nothing
WScript.Quit 0
