' Probe: can the IDE Error List / broken-VI reason be read via VI Server COM?
' Read-only probe against sr1.vi (currently broken: Add contains unwired terminal).
Option Explicit
Dim lv, vi, s, bd
On Error Resume Next
Set lv = CreateObject("LabVIEW.Application")
If Err.Number <> 0 Then
  WScript.Echo "FAIL COM activate: 0x" & Hex(Err.Number) & " " & Err.Description : WScript.Quit 1
End If
WScript.Echo "COM OK"
Err.Clear

Set vi = lv.GetVIReference("C:\LabView skill\gen\sr1_probe_tmp.vi")
If Err.Number <> 0 Then
  WScript.Echo "FAIL GetVIReference: 0x" & Hex(Err.Number) & " " & Err.Description : WScript.Quit 1
End If
vi.Loaded = True

' 1. Baseline property (should work)
Err.Clear : s = vi.Name
WScript.Echo "vi.Name = " & s & "   err=0x" & Hex(Err.Number)
If Err.Number <> 0 Then Err.Clear

' 2. Does a VI-level 'Is Broken' property exist?
Err.Clear : s = vi.IsBroken
WScript.Echo "vi.IsBroken -> 0x" & Hex(Err.Number) & " (" & Err.Description & ") val=" & s
If Err.Number <> 0 Then Err.Clear

' 3. Any error-list-ish property?
Err.Clear : s = vi.ErrorList
WScript.Echo "vi.ErrorList -> 0x" & Hex(Err.Number) & " (" & Err.Description & ")"
If Err.Number <> 0 Then Err.Clear
Err.Clear : s = vi.Errors
WScript.Echo "vi.Errors -> 0x" & Hex(Err.Number) & " (" & Err.Description & ")"
If Err.Number <> 0 Then Err.Clear

' 4. Can we even reach the block diagram from raw COM?
Err.Clear
Set bd = vi.BlockDiagram
WScript.Echo "vi.BlockDiagram -> 0x" & Hex(Err.Number) & " (" & Err.Description & ")"
If Err.Number <> 0 Then Err.Clear
If Not bd Is Nothing Then
  Err.Clear : s = bd.GObjects.Count
  WScript.Echo "  bd.GObjects.Count -> 0x" & Hex(Err.Number) & " (" & Err.Description & ") val=" & s
  If Err.Number <> 0 Then Err.Clear
End If

' 5. Sanity: Run on a broken VI tells THAT it is broken, not WHY (known: 0x3EB)
WScript.Echo "Probe done."
