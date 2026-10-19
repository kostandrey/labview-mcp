' lv_runcheck.vbs - copy-first runtime check: copy the VI to a temp run
' copy, run THAT, poll GetControlValue until stable, report PASS/FAIL.
' Enforces the copy-first verification rule (the user's control values
' stay undisturbed) in one command.
'
' Usage:
'   cscript //nologo lv_runcheck.vbs "<vi path>" "<control name>" [expected]
' Example:
'   lv_runcheck.vbs "C:\LabView skill\gen\X.vi" "Out1" 4950
' Output includes "RUNCOPY: <temp path>" (the copy is kept for reuse).
' Exit 0 = pass (or no expected given), 1 = fail/COM error.
Option Explicit
On Error Resume Next

Dim srcVi, ctrl, expected
If WScript.Arguments.Count < 2 Then
    WScript.Echo "ERROR: usage: lv_runcheck.vbs <vi path> <control name> [expected]"
    WScript.Quit 1
End If
srcVi = WScript.Arguments(0)
ctrl = WScript.Arguments(1)
expected = ""
If WScript.Arguments.Count >= 3 Then expected = WScript.Arguments(2)

' --- copy to temp (keep .vi extension; reuse one temp name per source) ---
Dim fso, tmpDir, tmpVi, base
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(srcVi) Then
    WScript.Echo "ERROR: VI not found: " & srcVi
    WScript.Quit 1
End If
tmpDir = fso.GetSpecialFolder(2) & "\lv_mcp"
If Not fso.FolderExists(tmpDir) Then fso.CreateFolder tmpDir
base = fso.GetBaseName(srcVi)
tmpVi = tmpDir & "\" & base & "_run.vi"
fso.CopyFile srcVi, tmpVi, True
If Err.Number <> 0 Then
    WScript.Echo "ERROR: copy failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
WScript.Echo "RUNCOPY: " & tmpVi

' --- run the copy and poll until stable ---
Dim app, vi, result, last, polls, stable, elapsed
Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
    WScript.Echo "ERROR: cannot start LabVIEW COM: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
Set vi = app.GetVIReference(tmpVi)
If Err.Number <> 0 Or vi Is Nothing Then
    WScript.Echo "ERROR: GetVIReference failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
vi.Run True
If Err.Number <> 0 Then
    WScript.Echo "ERROR: vi.Run failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If

elapsed = 0
stable = False
result = ""
Do
    WScript.Sleep 500
    elapsed = elapsed + 500
    last = result
    result = vi.GetControlValue(ctrl)
    If Err.Number <> 0 Then
        WScript.Echo "ERROR: GetControlValue('" & ctrl & "') failed: 0x" & Hex(Err.Number) & " - " & Err.Description
        WScript.Quit 1
    End If
    If elapsed >= 1500 And CStr(result) = CStr(last) Then stable = True
Loop While Not stable And elapsed < 120000
WScript.Echo ctrl & " = " & result & "  (after " & elapsed & " ms)"
If expected <> "" Then
    If CStr(result) = CStr(expected) Then
        WScript.Echo "PASS (expected " & expected & ")"
        WScript.Quit 0
    Else
        WScript.Echo "FAIL (expected " & expected & ")"
        WScript.Quit 1
    End If
End If
WScript.Quit 0
