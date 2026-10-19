' lv_tunnels_regular.vbs - set ALL border tunnels of a loop to Regular
' (IndexMode 0). Automates RULE 2: after the LAST border-crossing wire,
' count tunnels (tunnel:0;-2) and set each Regular (tunnel:i;0).
'
' Usage:
'   cscript //nologo lv_tunnels_regular.vbs <Gateway.vi> <vi> <ForLoopLabel>
' Example:
'   lv_tunnels_regular.vbs Gateway.vi "C:\...\X.vi" Loop1
' Exit 0 = every tunnel Regular; 1 = failure (details printed).
Option Explicit
Const VI_OPEN_NO_DIALOGS = &H20

Dim gwPath, vi, loopLabel
If WScript.Arguments.Count < 3 Then
  WScript.Echo "usage: lv_tunnels_regular.vbs <Gateway.vi> <vi> <ForLoopLabel>"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0) : vi = WScript.Arguments(1)
loopLabel = WScript.Arguments(2)

Dim app, gw, i
For i = 1 To 15
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < 15 Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot create LabVIEW.Application: 0x" & Hex(Err.Number) & " " & Err.Description
  WScript.Quit 1
End If
For i = 1 To 5
  Err.Clear
  Set gw = app.GetVIReference(gwPath, "", False, VI_OPEN_NO_DIALOGS)
  If Err.Number = 0 Then Exit For
  If i < 5 Then WScript.Sleep 1000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot open Gateway: " & Err.Description : WScript.Quit 1
End If

Function CallGW(verb, vPath, a1, a2, a3)
  Dim r
  Err.Clear
  gw.SetControlValue "verb", verb
  gw.SetControlValue "vi path", vPath
  gw.SetControlValue "arg1", a1
  gw.SetControlValue "arg2", a2
  gw.SetControlValue "arg3", a3
  Err.Clear
  gw.Run
  If Err.Number <> 0 Then
    WScript.Echo "ERROR: Gateway Run failed: " & Err.Description
    WScript.Quit 1
  End If
  CallGW = CStr(gw.GetControlValue("result"))
End Function

Function Failed(r) : Failed = (Left(r, 5) = "ERROR") : End Function

Dim loopRes, r, okAll
okAll = True
loopRes = vi & "%ForLoop|" & loopLabel

r = CallGW("loop", loopRes, "tunnel:0", "-2", "")
WScript.Echo "[count] " & Replace(r, vbCr, "")
If Failed(r) Then WScript.Quit 1

Dim re, m, nT, j
Set re = New RegExp
re.Pattern = "Tunnels:\s*(\d+)" : re.IgnoreCase = True
Set m = re.Execute(r)
If m.Count = 0 Then
  WScript.Echo "ERROR: could not parse tunnel count from: " & r
  WScript.Quit 1
End If
nT = CLng(m(0).SubMatches(0))
WScript.Echo "[tunnels] " & nT & " tunnel(s) on '" & loopLabel & "'"

For j = 0 To nT - 1
  r = CallGW("loop", loopRes, "tunnel:" & j, "0", "")
  WScript.Echo "[tunnel " & j & "] " & Replace(r, vbCr, "")
  If Failed(r) Then okAll = False
Next

If okAll Then
  WScript.Echo "TUNNELS OK: all " & nT & " tunnel(s) set Regular. Verify with lv_verify.vbs."
Else
  WScript.Echo "TUNNELS FAILED - see lines above."
End If

On Error Resume Next
gw.CloseFrontPanel
On Error GoTo 0
gw.Revert
Set gw = Nothing : Set app = Nothing
If okAll Then WScript.Quit 0 Else WScript.Quit 1
