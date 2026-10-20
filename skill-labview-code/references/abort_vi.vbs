' abort_vi.vbs - abort a running VI via COM
Set app = CreateObject("LabVIEW.Application")
Set vi = app.GetVIReference(WScript.Arguments(0))
vi.Abort
WScript.Echo "ABORTED: " & WScript.Arguments(0)
