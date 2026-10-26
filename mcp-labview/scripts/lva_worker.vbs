' lva_worker.vbs - drive a single Scripting Server Do*.vi worker via COM.
' Usage:
'   cscript //nologo lva_worker.vbs <abs worker.vi> [Ctrl=type:value ...] [--read Ctrl ...] [--sleep ms]
'   type prefixes: s:=string  i:=integer  b:=true/false  e:=Empty (0x70 notifier)
'   (no prefix = string)
' Examples:
'   cscript //nologo lva_worker.vbs "C:\...\Do Get Open VIs.vi" --read "Get open VIs Argument" --read "Data Cluster 2"
'   cscript //nologo lva_worker.vbs "C:\...\Do Open Vi.vi" "open_vi Argument=s:C:\temp\foo.vi|e:|b:false" --read "open_vi Argument"
'     (array elements are '|'-separated; the cluster must match the worker's FP control)
' Notes:
'   - Run with 32-bit cscript (SysWOW64) for the background 32-bit LV2020,
'     64-bit (System32) for a 64-bit instance.
'   - Session-dependent workers (anything taking vi_id/object_id) return
'     empty results outside the server context - use an in-LabVIEW runner
'     VI for chains (see skill-labview-code/references/scripting-server-2020.md).
Option Explicit
On Error Resume Next

Dim args, viPath, sets, reads, sleepMs, i
Set args = WScript.Arguments
If args.Count < 1 Then
  WScript.Echo "usage: lva_worker.vbs <abs worker.vi> [Ctrl=type:value ...] [--read Ctrl ...] [--sleep ms]"
  WScript.Quit 2
End If
viPath = args(0)
Set sets = CreateObject("Scripting.Dictionary")
Set reads = CreateObject("Scripting.Dictionary")
sleepMs = 3000
i = 1
Do While i < args.Count
  Dim a : a = args(i)
  Dim nxt : nxt = ""
  If i + 1 < args.Count Then nxt = args(i + 1)
  If Left(a, 7) = "--sleep" Then
    If InStr(a, "=") > 0 Then sleepMs = CLng(Split(a, "=")(1)) Else sleepMs = CLng(nxt) : i = i + 1
  ElseIf a = "--read" Then
    If InStr(a, "=") > 0 Then reads(Split(a, "=", 2)(1)) = True Else reads(nxt) = True : i = i + 1
  ElseIf Left(a, 6) = "--read" And InStr(a, "=") > 0 Then
    reads(Split(a, "=", 2)(1)) = True
  ElseIf InStr(a, "=") > 0 Then
    sets(Split(a, "=", 2)(0)) = Split(a, "=", 2)(1)
  End If
  i = i + 1
Loop

Dim app : Set app = CreateObject("LabVIEW.Application")
Do While app.Version = "" : WScript.Sleep 1000 : Loop
WScript.Echo "attached: " & app.Version
Dim vi : Set vi = app.GetVIReference(viPath, "", False, &H20)
If Err.Number <> 0 Then
  WScript.Echo "OPEN FAIL 0x" & Hex(Err.Number) & ": " & Err.Description : WScript.Quit 1
End If

Dim k
For Each k In sets.Keys
  Err.Clear
  vi.SetControlValue k, ParseVal(sets(k))
  If Err.Number <> 0 Then
    WScript.Echo "SET FAIL " & k & " 0x" & Hex(Err.Number) & ": " & Err.Description
  Else
    WScript.Echo "set " & k
  End If
Next

Err.Clear
vi.Run True
If Err.Number <> 0 Then
  WScript.Echo "RUN FAIL 0x" & Hex(Err.Number) & ": " & Err.Description : WScript.Quit 1
End If
WScript.Echo "run ok, waiting " & sleepMs & " ms"
WScript.Sleep sleepMs

For Each k In reads.Keys
  Err.Clear
  Dim v : v = vi.GetControlValue(k)
  If Err.Number <> 0 Then
    WScript.Echo k & " : READ FAIL 0x" & Hex(Err.Number)
  Else
    WScript.Echo k & " = " & Fmt(v)
  End If
Next
WScript.Echo "DONE"

Function ParseVal(s)
  Dim arr, j
  If InStr(s, "|") > 0 Then
    arr = Split(s, "|")
    For j = 0 To UBound(arr)
      arr(j) = ParseVal(arr(j))
    Next
    ParseVal = arr
  ElseIf Left(s, 2) = "s:" Then
    ParseVal = Mid(s, 3)
  ElseIf Left(s, 2) = "i:" Then
    ParseVal = CLng(Mid(s, 3))
  ElseIf Left(s, 2) = "b:" Then
    ParseVal = (LCase(Mid(s, 3)) = "true")
  ElseIf s = "e:" Then
    ParseVal = Empty
  Else
    ParseVal = s
  End If
End Function

Function Fmt(v)
  Dim s, j
  If IsArray(v) Then
    s = "["
    For j = 0 To UBound(v)
      If j > 0 Then s = s & "; "
      s = s & Fmt(v(j))
    Next
    Fmt = s & "]"
  ElseIf IsNull(v) Then
    Fmt = "(null)"
  ElseIf IsEmpty(v) Then
    Fmt = "(empty)"
  Else
    Fmt = CStr(v)
    If Len(Fmt) > 300 Then Fmt = Left(Fmt, 300) & "...(" & Len(Fmt) & " chars)"
  End If
End Function
