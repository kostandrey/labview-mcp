' run_vi_get_value2.vbs - like run_vi_get_value.vbs but with timing + wait-for-completion poll.
' Usage: cscript //nologo run_vi_get_value2.vbs "<vi path>" "<control name>" [expected] [timeout_s]
' Diagnoses whether Run(True) blocks: prints timestamp at each phase and reads the
' control twice (immediately and after Running goes False).
Option Explicit
On Error Resume Next
Dim app, vi, result, result2, expected, t0, timeoutS, waited, isRunning
If WScript.Arguments.Count < 2 Then
    WScript.Echo "ERROR: usage: run_vi_get_value2.vbs <vi path> <control name> [expected] [timeout_s]"
    WScript.Quit 1
End If
expected = ""
If WScript.Arguments.Count >= 3 Then expected = WScript.Arguments(2)
timeoutS = 180
If WScript.Arguments.Count >= 4 Then timeoutS = CLng(WScript.Arguments(3))

Function TS() : TS = Timer : End Function

t0 = Timer
Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
    WScript.Echo "ERROR: cannot start LabVIEW COM: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] COM connected"
Set vi = app.GetVIReference(WScript.Arguments(0))
If Err.Number <> 0 Or vi Is Nothing Then
    WScript.Echo "ERROR: GetVIReference failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If

' Pre-run state of control
result = vi.GetControlValue(WScript.Arguments(1))
If Err.Number = 0 Then
    WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] pre-run value: " & result
Else
    Err.Clear
    WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] pre-run read failed (ignored)"
End If

vi.Run True
If Err.Number <> 0 Then
    WScript.Echo "ERROR: vi.Run failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] vi.Run(True) returned"

' Poll Running (ignore errors if property unsupported)
waited = 0
Do
    isRunning = vi.Running
    If Err.Number <> 0 Then
        Err.Clear
        WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] Running property not supported"
        Exit Do
    End If
    If Not isRunning Then Exit Do
    WScript.Sleep 500
    waited = waited + 500
Loop While waited < timeoutS * 1000
WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] wait loop done (polled " & waited & " ms)"

result = vi.GetControlValue(WScript.Arguments(1))
If Err.Number <> 0 Then
    WScript.Echo "ERROR: GetControlValue('" & WScript.Arguments(1) & "') failed: 0x" & Hex(Err.Number) & " - " & Err.Description
    WScript.Quit 1
End If
WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] value: " & result

WScript.Sleep 1000
result2 = vi.GetControlValue(WScript.Arguments(1))
If Err.Number = 0 Then WScript.Echo "[" & FormatNumber(Timer - t0, 3) & "s] value after 1s: " & result2

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
