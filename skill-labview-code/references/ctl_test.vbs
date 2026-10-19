' ctl_test.vbs - test SetControlValue/GetControlValue round-trip on array controls
' Usage: cscript //nologo ctl_test.vbs "<vi path>" "<control name>"
Option Explicit
On Error Resume Next
Dim app, vi, v, s, i
Set app = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then WScript.Echo "ERR app: " & Err.Description : WScript.Quit 1
Set vi = app.GetVIReference(WScript.Arguments(0))
If Err.Number <> 0 Then WScript.Echo "ERR open: " & Err.Description : WScript.Quit 1

Err.Clear
vi.SetControlValue WScript.Arguments(1), Array(5.0, 3.0, 8.0, 1.0, 9.0, 2.0)
If Err.Number <> 0 Then
  WScript.Echo "SET FAILED: 0x" & Hex(Err.Number) & " - " & Err.Description
Else
  WScript.Echo "SET ok"
End If

Err.Clear
v = vi.GetControlValue(WScript.Arguments(1))
If Err.Number <> 0 Then
  WScript.Echo "GET FAILED: 0x" & Hex(Err.Number) & " - " & Err.Description
Else
  If IsArray(v) Then
    s = ""
    For i = LBound(v) To UBound(v)
      s = s & CStr(v(i)) & " "
    Next
    WScript.Echo "GET array: " & s
  Else
    WScript.Echo "GET scalar: " & CStr(v)
  End If
End If
vi.Revert
WScript.Quit 0
