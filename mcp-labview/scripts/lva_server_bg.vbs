' lva_server_bg.vbs - start lva_server.vi and STAY alive; log to file
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim ts : Set ts = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_server_bg.log", True)
ts.WriteLine Now & " bg start"
Dim app : Set app = CreateObject("LabVIEW.Application")
ts.WriteLine Now & " attached " & app.Version
Dim vi : Set vi = app.GetVIReference("C:\LabView skill\_service\tmp\lva_server.vi", "", False, &H20)
ts.WriteLine Now & " ref ok"
On Error Resume Next
Err.Clear
vi.Run True   ' blocks while the server loop runs - exactly what we want here
ts.WriteLine Now & " Run returned: 0x" & Hex(Err.Number) & " " & Err.Description
ts.Close
