' Probe: list VIs in memory of the running LabVIEW instance (COM)
On Error Resume Next
Set lv = GetObject(, "LabVIEW.Application")
If Err.Number <> 0 Then
  WScript.Echo "NO INSTANCE: " & Err.Description
  WScript.Quit 1
End If
WScript.Echo "App: " & lv.Name & " ver " & lv.Version
Set vms = lv.AllVIsInMemory
WScript.Echo "VIs in memory: " & vms.Count
For Each vi In vms
  WScript.Echo "  [" & vi.Name & "]  gtwy=" & vi.Path
Next
