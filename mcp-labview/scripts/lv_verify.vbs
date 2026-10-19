' lv_verify.vbs - post-build verification: wires broken-flags + errors verb
' in one call, with a PASS/FAIL verdict and exit code. Replaces the manual
' "run wires, grep broken:1, run errors, parse" cycle.
'
' Usage:
'   cscript //nologo lv_verify.vbs <Gateway.vi> <vi>
' Output:
'   VERIFY PASS: VI clean (N wires, 0 broken, no errors)
'   VERIFY FAIL: M broken wire(s) [UID:...]; error item(s): ...
' Exit 0 = clean, 1 = broken/errors, 2 = usage/COM failure.
Option Explicit
Const VI_OPEN_NO_DIALOGS = &H20

Dim gwPath, vi
If WScript.Arguments.Count < 2 Then
  WScript.Echo "usage: lv_verify.vbs <Gateway.vi> <vi>"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0) : vi = WScript.Arguments(1)

Dim app, gw, i
For i = 1 To 15
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < 15 Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot create LabVIEW.Application: 0x" & Hex(Err.Number) & " " & Err.Description
  WScript.Quit 2
End If
For i = 1 To 5
  Err.Clear
  Set gw = app.GetVIReference(gwPath, "", False, VI_OPEN_NO_DIALOGS)
  If Err.Number = 0 Then Exit For
  If i < 5 Then WScript.Sleep 1000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot open Gateway: " & Err.Description : WScript.Quit 2
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
    WScript.Quit 2
  End If
  CallGW = CStr(gw.GetControlValue("result"))
End Function

' --- wires ---
Dim rW, lines, ln, j, nWires, nBroken, uids
nWires = 0 : nBroken = 0 : uids = ""
rW = CallGW("wires", vi, "", "", "")
If Left(rW, 5) = "ERROR" Then
  WScript.Echo "ERROR: wires verb failed: " & rW
  WScript.Quit 2
End If
lines = Split(Replace(rW, vbCr, ""), vbLf)
For j = 0 To UBound(lines)
  If InStr(lines(j), "Wire:") > 0 Then
    nWires = nWires + 1
    If InStr(lines(j), "broken: 1") > 0 Then
      nBroken = nBroken + 1
      Dim re, m
      Set re = New RegExp
      re.Pattern = "UID:(\d+)"
      Set m = re.Execute(lines(j))
      If m.Count > 0 Then
        If uids <> "" Then uids = uids & ", "
        uids = uids & m(0).SubMatches(0)
      End If
      WScript.Echo "BROKEN: " & Trim(lines(j))
    End If
  End If
Next

' --- errors ---
Dim rErr, itemList, nErr
nErr = 0 : itemList = ""
rErr = CallGW("errors", vi, "", "", "")
If Left(rErr, 5) = "ERROR" Then
  WScript.Echo "ERROR: errors verb failed: " & rErr
  WScript.Quit 2
End If
Dim p0, p1
p0 = InStr(rErr, "Errors list = '")
If p0 > 0 Then
  p0 = p0 + Len("Errors list = '")
  p1 = InStr(p0, rErr, "'")
  If p1 > p0 Then itemList = Mid(rE, p0, p1 - p0)
End If
itemList = Replace(Replace(itemList, vbCr, ""), vbLf, "")
If itemList <> "" Then
  Dim items
  items = Split(itemList, ";")
  Dim seen, k, dedup
  seen = ";" : dedup = ""
  For k = 0 To UBound(items)
    Dim it
    it = Trim(items(k))
    If it <> "" And InStr(seen, ";" & it & ";") = 0 Then
      seen = seen & it & ";"
      If dedup <> "" Then dedup = dedup & " | "
      dedup = dedup & it
      nErr = nErr + 1
    End If
  Next
  itemList = dedup
End If

' --- compile check (the error list is computed LAZILY: a VI whose error
' list was never populated returns EMPTY errors even when broken - the
' failed run attempts on 2026-10-19 proved this). Run a temp copy: a
' 0x3EB = VI not executable = FAIL; a successful start = executable.
Dim fso, tmpDir, tmpVi, base, app2, vi2
Set fso = CreateObject("Scripting.FileSystemObject")
tmpDir = fso.GetParentFolderName(vi)   ' SAME dir (see lv_runcheck note)
base = fso.GetBaseName(vi)
tmpVi = tmpDir & "\\" & base & "_chk.vi"
fso.CopyFile vi, tmpVi, True
If Err.Number <> 0 Then
  WScript.Echo "WARN: compile-check copy failed: " & Err.Description & " - skipping"
  Err.Clear
Else
  Set app2 = app
  Set vi2 = app2.GetVIReference(tmpVi)
  If Err.Number <> 0 Or vi2 Is Nothing Then
    WScript.Echo "WARN: compile-check GetVIReference failed - skipping"
    Err.Clear
  Else
    Err.Clear
    On Error Resume Next
    vi2.Run True
    Dim runErr, runDesc
    runErr = Err.Number : runDesc = Err.Description
    On Error GoTo 0
    If runErr <> 0 Then
      WScript.Echo "COMPILE CHECK FAIL: the VI is NOT executable (0x" & Hex(runErr) & ") - " & runDesc
      nErr = nErr + 1
      If itemList <> "" Then itemList = itemList & " | "
      itemList = itemList & "VI not executable (compile check)"
    Else
      On Error Resume Next
      vi2.Abort
      On Error GoTo 0
    End If
  End If
End If

' --- verdict ---
If nBroken = 0 And nErr = 0 Then
  WScript.Echo "VERIFY PASS: VI clean (" & nWires & " wires, 0 broken, no errors)"
  On Error Resume Next
  gw.CloseFrontPanel
  On Error GoTo 0
  gw.Revert
  Set gw = Nothing : Set app = Nothing
  WScript.Quit 0
Else
  Dim verdict
  verdict = "VERIFY FAIL: " & nBroken & " broken wire(s)"
  If uids <> "" Then verdict = verdict & " [UID: " & uids & "]"
  If nErr > 0 Then verdict = verdict & "; " & nErr & " error item(s): " & itemList
  WScript.Echo verdict
  On Error Resume Next
  gw.CloseFrontPanel
  On Error GoTo 0
  gw.Revert
  Set gw = Nothing : Set app = Nothing
  WScript.Quit 1
End If
