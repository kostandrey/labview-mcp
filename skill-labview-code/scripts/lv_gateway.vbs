' lv_gateway.vbs - generic COM driver for the Gateway.vi helper
' Build sheet: references/gateway-recipe.md in this skill.
'
' Usage:
'   cscript //nologo lv_gateway.vbs <Gateway.vi path> <verb> [viPath] [arg1]
'
' Verbs (Gateway v1): ping | analyze <viPath> | listmem
' Prints the Gateway's "result" indicator to stdout. Exit code 0 = OK.
Option Explicit

Const VI_OPEN_NO_DIALOGS = &H20   ' GetVIReference option: load with no prompts

Dim gwPath, verb, viPath, arg1
If WScript.Arguments.Count < 2 Then
  WScript.Echo "usage: cscript //nologo lv_gateway.vbs <Gateway.vi> <verb> [viPath] [arg1]"
  WScript.Echo "verbs: ping | analyze <viPath> | listmem"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0)
verb   = WScript.Arguments(1)
viPath = ""
arg1   = ""
If WScript.Arguments.Count > 2 Then viPath = WScript.Arguments(2)
If WScript.Arguments.Count > 3 Then arg1   = WScript.Arguments(3)

On Error Resume Next

' Attach to (or spawn) the LabVIEW automation instance. CreateObject is
' multi-use: the first call spawns a 64-bit LabVIEW, later calls attach.
Dim app
Err.Clear
Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
  WScript.Echo "ERROR 0x" & Hex(Err.Number) & " - cannot create LabVIEW.Application: " & Err.Description
  WScript.Echo "Most common cause: a modal dialog (e.g. 'Save changes?') in an orphan"
  WScript.Echo "LabVIEW instance blocks COM activation. List processes with lv_procs.ps1,"
  WScript.Echo "kill the 64-bit orphan (taskkill /PID <pid> /F) and retry."
  WScript.Quit 1
End If

' Open the Gateway VI itself (no dialogs; front panel stays closed).
Dim gw
Err.Clear
Set gw = app.GetVIReference(gwPath, "", False, VI_OPEN_NO_DIALOGS)
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot open " & gwPath & " - " & Err.Description
  WScript.Quit 1
End If

' Push inputs (controls are addressed by exact label).
Err.Clear
gw.SetControlValue "verb", verb
If Err.Number <> 0 Then
  WScript.Echo "ERROR: SetControlValue('verb') failed - does Gateway.vi have a string control labeled 'verb'? (" & Err.Description & ")"
  WScript.Quit 1
End If
If viPath <> "" Then
  Err.Clear
  gw.SetControlValue "vi path", viPath
  If Err.Number <> 0 Then
    WScript.Echo "ERROR: SetControlValue('vi path') failed - missing/misnamed control? (" & Err.Description & ")"
    WScript.Quit 1
  End If
End If
If arg1 <> "" Then
  Err.Clear
  gw.SetControlValue "arg1", arg1
  If Err.Number <> 0 Then
    WScript.Echo "ERROR: SetControlValue('arg1') failed (" & Err.Description & ")"
    WScript.Quit 1
  End If
End If

' Run synchronously. A modal dialog inside the Gateway would hang here -
' that is why the build sheet bans dialog VIs (use Clear Errors instead).
Err.Clear
gw.Run
If Err.Number <> 0 Then
  WScript.Echo "ERROR: Gateway Run failed (broken VI, or a modal dialog is up?): " & Err.Description
  WScript.Quit 1
End If

' Read the output.
Dim result
Err.Clear
result = gw.GetControlValue("result")
If Err.Number <> 0 Then
  WScript.Echo "ERROR: GetControlValue('result') failed - missing string indicator 'result'? (" & Err.Description & ")"
  WScript.Quit 1
End If
WScript.Echo result

' Tidy up: close the window and discard the value changes made via
' SetControlValue so the in-memory Gateway never becomes dirty (prevents
' future 'Save changes?' prompts in the spawned instance).
gw.CloseFrontPanel
gw.Revert
Set gw = Nothing
Set app = Nothing
WScript.Quit 0
