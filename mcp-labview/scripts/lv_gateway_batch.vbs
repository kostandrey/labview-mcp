' lv_gateway_batch.vbs - run a SCRIPT of gateway commands in ONE LabVIEW session.
' Build sheet: skill-labview-code/references/gateway-recipe.md
'
' Usage:
'   cscript //nologo lv_gateway_batch.vbs <Gateway.vi path> <scriptfile>
'
' Script file format - one command per line, fields separated by ';':
'   verb;vi_path;arg1;arg2;arg3    gateway verb (empty fields = empty arg;
'                                  trailing fields may be omitted)
'   !verb;...                      '!' prefix = failure tolerated, keep going
'   # ...                          comment line
'   delete;<path>                  delete a file (retry workflow; use a FRESH
'                                  vi name per attempt instead when possible -
'                                  the LabVIEW instance keeps deleted VIs in
'                                  memory under their old name)
'   copy;<src>;<dst>               copy a file (fresh-name wires/analyze checks)
'   echo;<text>                    print text
'   sleep;<ms>                     pause
'
' Output: "LINE <n> [<verb>]: <gateway result>" per command.
' Stops at the first failing gateway command (result starts with ERROR) unless
' the line is prefixed '!'. Exit 0 = all ok, 1 = stopped on error.
Option Explicit

Const VI_OPEN_NO_DIALOGS = &H20   ' GetVIReference option: load with no prompts

Dim gwPath, scriptFile
If WScript.Arguments.Count < 2 Then
  P "usage: cscript //nologo lv_gateway_batch.vbs <Gateway.vi> <scriptfile>"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0)
scriptFile = WScript.Arguments(1)

Dim fso, oLog
Set fso = CreateObject("Scripting.FileSystemObject")
Set oLog = fso.CreateTextFile(scriptFile & ".log", True)

Sub P(s)
  WScript.Echo s
  On Error Resume Next
  oLog.WriteLine s
End Sub

Sub CallGateway(lineNo, verb, viPath, arg1, arg2, arg3, ByRef ok)
  ' Push all 5 controls (empty = cleared, prevents leakage from the
  ' previous line), run the Gateway, read the result indicator.
  ok = False
  Err.Clear
  gw.SetControlValue "verb", verb
  If Err.Number <> 0 Then
    P "LINE " & lineNo & " [" & verb & "]: ERROR - SetControlValue('verb') failed: " & Err.Description
  Else
    Err.Clear
    gw.SetControlValue "vi path", viPath
    Err.Clear
    gw.SetControlValue "arg1", arg1
    Err.Clear
    gw.SetControlValue "arg2", arg2
    Err.Clear
    gw.SetControlValue "arg3", arg3
    Err.Clear
    gw.Run
    If Err.Number <> 0 Then
      P "LINE " & lineNo & " [" & verb & "]: ERROR - Gateway Run failed: " & Err.Description
    Else
      result = gw.GetControlValue("result")
      If Err.Number <> 0 Then
        P "LINE " & lineNo & " [" & verb & "]: ERROR - GetControlValue('result') failed: " & Err.Description
      ElseIf IsEmpty(result) Or IsNull(result) Then
        P "LINE " & lineNo & " [" & verb & "]: ERROR - empty result"
      Else
        result = CStr(result)
        P "LINE " & lineNo & " [" & verb & "]: " & result
        If Left(result, 5) = "ERROR" Or Left(result, 5) = "error" Then
          ok = False
        Else
          ok = True
        End If
      End If
    End If
  End If
End Sub
If Not fso.FileExists(scriptFile) Then
  P "ERROR: script file not found: " & scriptFile
  WScript.Quit 2
End If

On Error Resume Next

' Attach to (or spawn) the LabVIEW automation instance ONCE for the whole batch.
Dim app
Err.Clear
Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
  P "ERROR 0x" & Hex(Err.Number) & " - cannot create LabVIEW.Application: " & Err.Description
  WScript.Quit 1
End If

Dim gw
Err.Clear
Set gw = app.GetVIReference(gwPath, "", False, VI_OPEN_NO_DIALOGS)
If Err.Number <> 0 Then
  P "ERROR: cannot open " & gwPath & " - " & Err.Description
  WScript.Quit 1
End If

Dim ts, lineNo, line, parts, verb, viPath, arg1, arg2, arg3
Dim tolerate, ok, allOk, result
Set ts = fso.OpenTextFile(scriptFile, 1)   ' 1 = ForReading
lineNo = 0
allOk = True

Do While Not ts.AtEndOfStream
  line = Trim(ts.ReadLine)
  lineNo = lineNo + 1
  If line = "" Or Left(line, 1) = "#" Then
    ' skip comments and blank lines
  Else
    tolerate = False
    If Left(line, 1) = "!" Then
      tolerate = True
      line = Mid(line, 2)
    End If
    parts = Split(line, ";")
    verb = "" : viPath = "" : arg1 = "" : arg2 = "" : arg3 = ""
    If UBound(parts) >= 0 Then verb  = Trim(parts(0))
    If UBound(parts) >= 1 Then viPath = Trim(parts(1))
    If UBound(parts) >= 2 Then arg1  = Trim(parts(2))
    If UBound(parts) >= 3 Then arg2  = Trim(parts(3))
    If UBound(parts) >= 4 Then arg3  = Trim(parts(4))

    ' Guard (2026-10-21): an FP object placed without W,H gets an unreadable
    ' front-panel item. Warn - do not fail (the place may still be wanted).
    If LCase(verb) = "place" Then
      Dim reFP, reXY, fpSet
      fpSet = LCase(arg1)
      Set reFP = New RegExp
      reFP.Pattern = "^(numind|numctl|strind|strctl|boolind|boolctl|any:2[01][0-9]{3})$"
      Set reXY = New RegExp
      reXY.Pattern = "^[0-9]+\s*,\s*[0-9]+$"
      If reFP.Test(fpSet) And reXY.Test(arg2) Then
        P "LINE " & lineNo & " [place]: WARNING - FP object '" & arg1 & _
          "' placed with 'x,y' only; the front-panel item will be UNREADABLE." & _
          " Use arg2 'x,y,W,H' (numeric ctl/ind standard 80,32; graph 400,300)."
      End If
    End If

    ok = False
    Select Case LCase(verb)
      Case "delete"
        ' Distinguish: 'delete;<path>' (2 fields) = script meta-command
        ' delete a FILE from disk (retry workflow). 'delete;<vi>;<class>;<id>'
        ' (3+ fields) = the GATEWAY's delete verb (remove a GObject/wire).
        ' Before Gateway v3.12 had no delete verb, so the meta-command won
        ' unconditionally and silently ATE any delete-verb line (deleting
        ' the .vi itself). Now only the 2-field form is the meta-command.
        If UBound(parts) = 1 Then
          Err.Clear
          If viPath = "" Then
            P "LINE " & lineNo & " [delete]: ERROR - no path given"
          ElseIf fso.FileExists(viPath) Then
            fso.DeleteFile viPath, True
            If Err.Number <> 0 Then
              P "LINE " & lineNo & " [delete]: ERROR - " & Err.Description
            Else
              P "LINE " & lineNo & " [delete]: ok " & viPath
              ok = True
            End If
          Else
            P "LINE " & lineNo & " [delete]: ok (not present) " & viPath
            ok = True
          End If
        Else
          Call CallGateway(lineNo, verb, viPath, arg1, arg2, arg3, ok)
        End If
      Case "copy"
        Err.Clear
        If viPath = "" Or arg1 = "" Then
          P "LINE " & lineNo & " [copy]: ERROR - need copy;<src>;<dst>"
        Else
          If fso.FileExists(arg1) Then fso.DeleteFile arg1, True : Err.Clear
          fso.CopyFile viPath, arg1, True
          If Err.Number <> 0 Then
            P "LINE " & lineNo & " [copy]: ERROR - " & Err.Description
          Else
            P "LINE " & lineNo & " [copy]: ok " & viPath & " -> " & arg1
            ok = True
          End If
        End If
      Case "echo"
        P "LINE " & lineNo & " [echo]: " & viPath
        ok = True
      Case "sleep"
        Err.Clear
        If IsNumeric(viPath) Then WScript.Sleep CLng(viPath)
        P "LINE " & lineNo & " [sleep]: ok " & viPath & " ms"
        ok = True
      Case Else
        ' ---- gateway verb: push all 5 controls (empty = cleared, prevents
        ' ---- leakage from the previous line), run, read result.
        Call CallGateway(lineNo, verb, viPath, arg1, arg2, arg3, ok)
        ' Guard (2026-10-21): an SR created here is UNINITIALIZED until its
        ' left terminal (slo<i>) is wired - an uninitialized SR keeps its
        ' value from previous runs while the VI stays in the instance,
        ' silently polluting later runtime tests.
        If ok And LCase(verb) = "loop" And InStr(LCase(arg1), "addsr") = 1 Then
          P "LINE " & lineNo & " [addSR]: WARNING - the shift register is UNINITIALIZED. Wire its left terminal (slo<i>|0) to an init constant, or it KEEPS ITS STATE BETWEEN RUNS in the same instance and later runs read stale values. Also: an unwired RIGHT terminal breaks the VI."
        End If
    End Select

    If Not ok Then
      allOk = False
      If Not tolerate Then
        P "STOPPED at line " & lineNo & " (prefix the line with ! to tolerate failure)"
        Exit Do
      End If
    End If
  End If
Loop
ts.Close

' Tidy up: discard the control changes made via SetControlValue so the
' in-memory Gateway never becomes dirty (prevents 'Save changes?' prompts).
gw.CloseFrontPanel
gw.Revert
Set gw = Nothing
Set app = Nothing

If allOk Then WScript.Quit 0 Else WScript.Quit 1
