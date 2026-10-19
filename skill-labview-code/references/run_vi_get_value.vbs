' run_vi_get_value.vbs - run a generated VI via COM and read one control.
' Usage:
'   cscript //nologo run_vi_get_value.vbs "<vi path>" "<control name>" [expected]
' Examples:
'   cscript //nologo run_vi_get_value.vbs "C:\LabView skill\gen\sumtest9.vi" "Result"
'   cscript //nologo run_vi_get_value.vbs "C:\LabView skill\gen\sumtest9.vi" "Result" 4950
' Exit code 0 on pass / no expected, 1 on fail or COM error.
' Notes (verified 2026-10-15):
'   - VirtualInstrument ActiveX has NO FP property; use GetControlValue/SetControlValue.
'   - vi.Run(True) is ASYNCHRONOUS - it returns immediately, before the VI finishes!
'     Reading the control right after Run returns a MID-RUN value (bit us 1h on pimc3:
'     read 0.0337 at iteration ~10.7k of 1e6; final was 3.140772 = PASS).
'   - vi.Running property is NOT supported on VirtualInstrument (Err 4502-ish).
'     So we poll GetControlValue until it is stable for 2 consecutive polls.
'   - PowerShell GetVIReference returns null (marshalling) - VBScript/cscript only.
'   - A VI open in the user's IDE is fine to run (live, visible) - but the
'     standard is to verify on a COPY so the user's control values stay
'     undisturbed (copy-first rule).
Option Explicit
On Error Resume Next
Dim app, vi, result, last, expected, polls, stable, elapsed
If WScript.Arguments.Count < 2 Then
    WScript.Echo "ERROR: usage: run_vi_get_value.vbs <vi path> <control name> [expected]"
    WScript.Quit 1
End If
expected = ""
If WScript.Arguments.Count >= 3 Then expected = WScript.Arguments(2)

Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
    WScript.Echo "ERROR: cannot start LabVIEW COM: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
Set vi = app.GetVIReference(WScript.Arguments(0))
If Err.Number <> 0 Or vi Is Nothing Then
    WScript.Echo "ERROR: GetVIReference failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
vi.Run True
If Err.Number <> 0 Then
    WScript.Echo "ERROR: vi.Run failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If

' Wait for completion: value must be identical on 2 consecutive polls 500 ms apart,
' and at least 1.5 s must have elapsed. Timeout 120 s.
elapsed = 0
stable = False
result = ""
Do
    WScript.Sleep 500
    elapsed = elapsed + 500
    last = result
    result = vi.GetControlValue(WScript.Arguments(1))
    If Err.Number <> 0 Then
        WScript.Echo "ERROR: GetControlValue('" & WScript.Arguments(1) & "') failed: 0x" & Hex(Err.Number) & " - " & Err.Description
        WScript.Quit 1
    End If
    If elapsed >= 1500 And CStr(result) = CStr(last) Then stable = True
Loop While Not stable And elapsed < 120000
WScript.Echo WScript.Arguments(1) & " = " & result & "  (after " & elapsed & " ms)"
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
