' lv_getval_hex.vbs - getval driver: calls Gateway.vi verb=getval and prints
' the reply with the data string HEX-ENCODED (the raw reply contains binary
' bytes 0x00-0xFF which the console truncates at the first NUL; the COM
' BSTR itself is intact, so hex-encode it here).
'
' Usage:
'   cscript //nologo lv_getval_hex.vbs <Gateway.vi> <viPath>
' Output (for lv_flat.py):
'   TYPE=60,16464,...
'   DATA_HEX=01FFFF...
Option Explicit

Const VI_OPEN_NO_DIALOGS = &H20

Dim gwPath, viPath
If WScript.Arguments.Count < 2 Then
  WScript.Echo "usage: cscript //nologo lv_getval_hex.vbs <Gateway.vi> <viPath>"
  WScript.Quit 2
End If
gwPath = WScript.Arguments(0)
viPath = WScript.Arguments(1)

Dim app, i
Const APP_TRIES = 15
For i = 1 To APP_TRIES
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < APP_TRIES Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot create LabVIEW.Application: " & Err.Description
  WScript.Quit 1
End If

Dim gw
Const REF_TRIES = 5
For i = 1 To REF_TRIES
  Err.Clear
  Set gw = app.GetVIReference(gwPath, "", False, VI_OPEN_NO_DIALOGS)
  If Err.Number = 0 Then Exit For
  If i < REF_TRIES Then WScript.Sleep 1000
Next
If Err.Number <> 0 Then
  WScript.Echo "ERROR: cannot open " & gwPath & " - " & Err.Description
  WScript.Quit 1
End If

gw.SetControlValue "verb", "getval"
gw.SetControlValue "vi path", viPath
Err.Clear
gw.Run
If Err.Number <> 0 Then
  WScript.Echo "ERROR: Gateway Run failed: " & Err.Description
  WScript.Quit 1
End If

Dim result
result = gw.GetControlValue("result")
If Err.Number <> 0 Then
  WScript.Echo "ERROR: GetControlValue('result') failed: " & Err.Description
  WScript.Quit 1
End If

' Split the reply (v3.30+): "Data type array: <csv> ... Data string length: N
' Data string hex='<hex>'". Older gateways returned a raw binary
' "Data string='<binary>'" - still supported as a fallback.
Dim ti, di, hi, nl, lf, s, ch, typeCsv, dataStr, h, j
ti = InStr(result, "Data type array: ")
hi = InStr(result, "Data string hex='")
di = InStr(result, "Data string='")
If ti = 0 Or (hi = 0 And di = 0) Then
  WScript.Echo "ERROR: unexpected reply format: " & Replace(result, vbCrLf, " | ")
  WScript.Quit 1
End If
s = Mid(result, ti + 17)
nl = InStr(s, vbCr)
lf = InStr(s, vbLf)
If nl > 0 And (nl < lf Or lf = 0) Then s = Left(s, nl - 1)
If lf > 0 And (lf < nl Or nl = 0) Then s = Left(s, lf - 1)
For j = 1 To Len(s)
  ch = Mid(s, j, 1)
  If (ch >= "0" And ch <= "9") Or ch = "-" Or ch = "," Then typeCsv = typeCsv & ch
Next
If hi > 0 Then
  s = Mid(result, hi + 17)
  h = ""
  For j = 1 To Len(s)
    ch = LCase(Mid(s, j, 1))
    If (ch >= "0" And ch <= "9") Or (ch >= "a" And ch <= "f") Then h = h & ch Else Exit For
  Next
Else
  dataStr = Mid(result, di + 13)
  If Right(dataStr, 1) = "'" Then dataStr = Left(dataStr, Len(dataStr) - 1)
  h = ""
  For j = 1 To Len(dataStr)
    h = h & Right("0" & Hex(AscW(Mid(dataStr, j, 1)) And 255), 2)
  Next
End If
WScript.Echo "TYPE=" & typeCsv
WScript.Echo "DATA_HEX=" & h

On Error Resume Next
gw.CloseFrontPanel
gw.Revert
Set gw = Nothing
Set app = Nothing
WScript.Quit 0
