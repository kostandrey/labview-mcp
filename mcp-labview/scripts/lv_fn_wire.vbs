' lv_fn_wire.vbs - auto-wire a Feedback Node (map detected per instance).
' Replaces the manual probe-and-decide FN cycle (recipe v3.7/v3.20):
' getNode on the FN -> the isSource:1 terminal is the OUTPUT; source=[0]
' -> Map B (out/init/in), source=[1] -> Map A (in/out/init); init/input
' follow from the rotation. Then wires all three connections and checks
' the isSource pattern of every wire response.
'
' Usage:
'   cscript //nologo lv_fn_wire.vbs <Gateway.vi> <vi> <FNlabel> "inLabel|inKind|inIdx" "outLabel|outKind|outIdx" "initLabel|initKind|initIdx"
' Example (accumulator: FN input <- Add output, output -> indicator, init <- const):
'   lv_fn_wire.vbs Gateway.vi "C:\...\X.vi" FN1 "ACC|n|0" "PI0|c|0" "ZeroConst|c|0"
' Note: a border-crossing wire (init from top level) auto-creates a tunnel -
' run lv_tunnels_regular.vbs afterwards.
' Exit 0 = all three wires created and legal (src isSource:1, dst 0);
' 1 = failure or illegal pattern (details printed).
Option Explicit
Const VI_OPEN_NO_DIALOGS = &H20

Dim gwPath, vi, fnLabel, inSpec, outSpec, initSpec
If WScript.Arguments.Count < 6 Then
  WScript.Echo "usage: lv_fn_wire.vbs <Gateway.vi> <vi> <FNlabel> ""inLabel|inKind|inIdx"" ""outLabel|outKind|outIdx"" ""initLabel|initKind|initIdx"""
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0) : vi = WScript.Arguments(1)
fnLabel = WScript.Arguments(2)
inSpec = Split(WScript.Arguments(3), "|")
outSpec = Split(WScript.Arguments(4), "|")
initSpec = Split(WScript.Arguments(5), "|")
If UBound(inSpec) <> 2 Or UBound(outSpec) <> 2 Or UBound(initSpec) <> 2 Then
  WScript.Echo "ERROR: specs must be label|kind|idx (e.g. ACC|n|0)"
  WScript.Quit 2
End If

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

' --- 1. determine the map ---
Dim getNodePath, r, srcIdx, mCount
getNodePath = vi & "%Node|" & fnLabel
r = CallGW("getNode", getNodePath, "terms", "", "")
WScript.Echo "[getNode] " & Replace(r, vbCr, "")
If Failed(r) Then WScript.Quit 1

Dim re, m, lines, ln, j
Set re = New RegExp
srcIdx = -1
lines = Split(Replace(r, vbCr, ""), vbLf)
For j = 0 To UBound(lines)
  If InStr(lines(j), "isSource: 1") > 0 And InStr(lines(j), "Term[") > 0 Then
    re.Pattern = "Term\[(\d+)\]"
    Set m = re.Execute(lines(j))
    If m.Count > 0 Then srcIdx = CLng(m(0).SubMatches(0))
  End If
Next
If srcIdx < 0 Then
  WScript.Echo "ERROR: no source terminal found in getNode output - is '" & fnLabel & "' a Feedback Node?"
  WScript.Quit 1
End If

Dim inT, outT, initT, mapName
If srcIdx = 0 Then
  mapName = "B" : outT = 0 : initT = 1 : inT = 2
ElseIf srcIdx = 1 Then
  mapName = "A" : inT = 0 : outT = 1 : initT = 2
Else
  WScript.Echo "ERROR: source terminal at Terms[" & srcIdx & "] - no verified rotation; run-test required (init=100/input=7, expect 7)."
  WScript.Quit 1
End If
WScript.Echo "[map] FN '" & fnLabel & "' = Map " & mapName & _
  " (in=n|" & inT & ", out=n|" & outT & ", init=n|" & initT & ")"

' --- 2. wire the three connections (checking the isSource pattern) ---
Dim resp(2), names(2), okAll
okAll = True
names(0) = "input" : names(1) = "output" : names(2) = "init"

r = CallGW("wire", vi, inSpec(0) & "|" & fnLabel, _
           inSpec(1) & "|" & inSpec(2) & "|n|" & inT, "")
resp(0) = Replace(r, vbCr, "")
WScript.Echo "[wire input] " & resp(0)

r = CallGW("wire", vi, fnLabel & "|" & outSpec(0), _
           "n|" & outT & "|" & outSpec(1) & "|" & outSpec(2), "")
resp(1) = Replace(r, vbCr, "")
WScript.Echo "[wire output] " & resp(1)

r = CallGW("wire", vi, initSpec(0) & "|" & fnLabel, _
           initSpec(1) & "|" & initSpec(2) & "|n|" & initT, "")
resp(2) = Replace(r, vbCr, "")
WScript.Echo "[wire init] " & resp(2)

' --- 3. legality check from the wire responses (src isSource:1, dst 0) ---
Dim re2, m2, flags(2), f
Set re2 = New RegExp
re2.Pattern = "isSource:\s*(\d)" : re2.Global = True
For j = 0 To 2
  flags(j) = True
  If Left(resp(j), 5) = "ERROR" Then
    flags(j) = False
  Else
    Set m2 = re2.Execute(resp(j))
    If m2.Count < 2 Then
      WScript.Echo "WARN: no isSource pair in the " & names(j) & " wire response (older gateway?) - check with lv_verify."
    Else
      If m2(0).SubMatches(0) <> "1" Or m2(1).SubMatches(0) <> "0" Then
        WScript.Echo "ILLEGAL: " & names(j) & " wire connected source->source or sink->sink - delete it (UID from wires) and rewire."
        flags(j) = False
      End If
    End If
  End If
  If Not flags(j) Then okAll = False
Next

If okAll Then
  WScript.Echo "FN WIRE OK: Map " & mapName & " - input<-'" & inSpec(0) & _
    "', output->'" & outSpec(0) & "', init<-'" & initSpec(0) & _
    "'. Run lv_tunnels_regular.vbs if any wire crossed the loop border."
Else
  WScript.Echo "FN WIRE FAILED - see [wire ...] lines above."
End If

On Error Resume Next
gw.CloseFrontPanel
On Error GoTo 0
gw.Revert
Set gw = Nothing : Set app = Nothing
If okAll Then WScript.Quit 0 Else WScript.Quit 1
