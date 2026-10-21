' lv_loop_scaffold.vbs - ONE-COMMAND loop skeleton builder (gateway composite).
' Implements the proven order of operations (recipe v3.18) for the mechanical
' part: place ForLoop -> place N constant -> setval -> wire N (c|0|n|0) ->
' optional addSR -> set all tunnels Regular.
'
' Usage:
'   cscript //nologo lv_loop_scaffold.vbs <Gateway.vi> <vi> <loopLabel> "<x,y[,W,H]>" <NconstLabel> <Nvalue> [SRlabel [SRy [Nxy]]]
' Example:
'   cscript //nologo lv_loop_scaffold.vbs "C:\LabView skill\gateway\Gateway.vi" "C:\LabView skill\gen\X.vi" Loop2 "800,100,300,200" N2 100 SR2 260
'
' After this: place nodes INSIDE via resolver "vi%ForLoop|<loopLabel>",
' wire internals (out=n|0, y=n|1, x=n|2), do border crossings LAST, then
' run lv_tunnels_regular.vbs again, lv_verify.vbs, lv_runcheck.vbs.
' Exit 0 = scaffold complete; 1 = failure (details printed).
Option Explicit
Const VI_OPEN_NO_DIALOGS = &H20

Dim gwPath, vi, loopLabel, bounds, nLabel, nValue, srLabel, srY, nXY
If WScript.Arguments.Count < 6 Then
  WScript.Echo "usage: lv_loop_scaffold.vbs <Gateway.vi> <vi> <loopLabel> <x,y[,W,H]> <NconstLabel> <Nvalue> [SRlabel [SRy [Nxy]]]"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0) : vi = WScript.Arguments(1)
loopLabel = WScript.Arguments(2) : bounds = WScript.Arguments(3)
nLabel = WScript.Arguments(4) : nValue = WScript.Arguments(5)
srLabel = "" : srY = "" : nXY = "30,30"
If WScript.Arguments.Count > 6 Then srLabel = WScript.Arguments(6)
If WScript.Arguments.Count > 7 Then srY = WScript.Arguments(7)
If WScript.Arguments.Count > 8 Then nXY = WScript.Arguments(8)

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
  r = CStr(gw.GetControlValue("result"))
  CallGW = r
End Function

Function Failed(r) : Failed = (Left(r, 5) = "ERROR") : End Function

Dim r, ok
' 1. place the ForLoop (any:2002)
r = CallGW("place", vi, "any:2002", bounds, loopLabel)
WScript.Echo "[loop] " & r
If Failed(r) Then WScript.Quit 1

' 2. place the N constant (top level)
r = CallGW("place", vi, "numconst", nXY, nLabel)
WScript.Echo "[Nconst] " & r
If Failed(r) Then WScript.Quit 1

' 3. setval N (dec - integers only)
r = CallGW("setval", vi & "%NumericConstant|" & nLabel, nValue, "dec", "")
WScript.Echo "[Nsetval] " & r
If Failed(r) Then WScript.Quit 1

' 4. wire N -> loop count
r = CallGW("wire", vi, nLabel & "|" & loopLabel, "c|0|n|0", "")
WScript.Echo "[Nwire] " & r
If Failed(r) Then WScript.Quit 1

' 5. optional shift register
If srLabel <> "" Then
  Dim loopPath
  loopPath = vi & "%ForLoop|" & loopLabel
  If srY = "" Then srY = "0"
  r = CallGW("loop", loopPath, "addSR", srY, srLabel)
  WScript.Echo "[SR] " & r
  If Failed(r) Then WScript.Quit 1
  WScript.Echo "WARNING: the SR is UNINITIALIZED - wire its left terminal (slo0|0) to an init constant, or it KEEPS ITS STATE BETWEEN RUNS in the same instance and later runs read stale values. Also: an unwired RIGHT SR terminal BREAKS the VI - wire sri0 (inside) immediately, or delete the whole SR via its UID above (deleting the RightShiftRegister removes the SR)."
End If

' 6. set every border tunnel Regular (the N wire just created one)
Dim loopRes
loopRes = vi & "%ForLoop|" & loopLabel
r = CallGW("loop", loopRes, "tunnel:0", "-2", "")
WScript.Echo "[tcount] " & r
If Failed(r) Then WScript.Quit 1
Dim re, m, nT
Set re = New RegExp
re.Pattern = "Tunnels:\s*(\d+)" : re.IgnoreCase = True
Set m = re.Execute(r)
If m.Count = 0 Then
  WScript.Echo "WARN: could not parse tunnel count from: " & r
Else
  nT = CLng(m(0).SubMatches(0))
  For i = 0 To nT - 1
    r = CallGW("loop", loopRes, "tunnel:" & i, "0", "")
    WScript.Echo "[tunnel " & i & "] " & r
    If Failed(r) Then WScript.Quit 1
  Next
End If

WScript.Echo "SCAFFOLD OK: loop '" & loopLabel & "' with N=" & nValue & _
  " ready. Place nodes inside via resolver '" & vi & "%ForLoop|" & loopLabel & _
  "'; border crossings LAST, then lv_tunnels_regular.vbs."

On Error Resume Next
gw.CloseFrontPanel
On Error GoTo 0
gw.Revert
Set gw = Nothing : Set app = Nothing
WScript.Quit 0
