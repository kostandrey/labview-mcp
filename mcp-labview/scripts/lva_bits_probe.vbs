' lva_bits_probe.vbs - set ArgSave under this cscript bitness, read it back
' via GetControlValue, print. Run under BOTH cscript bitnesses to compare.
Option Explicit
On Error Resume Next
Dim vi : Set vi = CreateObject("LabVIEW.Application").GetVIReference("C:\LabView skill\gateway\LVA\LVA Session.vi", "", False, &H20)
If Err.Number <> 0 Then
  WScript.Echo "attach/ref err 0x" & Hex(Err.Number) & " " & Err.Description
  WScript.Quit 1
End If
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_bits_target.vi", Empty, False)
WScript.Echo "set err=0x" & Hex(Err.Number) & " " & Err.Description
Err.Clear
Dim v : v = vi.GetControlValue("ArgOpen")
If Err.Number <> 0 Then
  WScript.Echo "get err=0x" & Hex(Err.Number) & " " & Err.Description
Else
  Dim i, s
  For i = 0 To UBound(v)
    If IsObject(v(i)) Then
      s = s & "obj;"
    ElseIf IsEmpty(v(i)) Then
      s = s & "empty;"
    ElseIf IsNull(v(i)) Then
      s = s & "null;"
    Else
      s = s & TypeName(v(i)) & ":" & CStr(v(i)) & ";"
    End If
  Next
  WScript.Echo "readback: " & s
End If
