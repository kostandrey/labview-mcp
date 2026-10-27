' lva_session_probe.vbs - two runner runs in ONE process (no release between)
Option Explicit
Dim app : Set app = CreateObject("LabVIEW.Application")
Do While app.Version = "" : WScript.Sleep 1000 : Loop
WScript.Echo "attached: " & app.Version
Dim vi : Set vi = app.GetVIReference("C:\LabView skill\_service\tmp\lva_spike.vi", "", False, &H20)

vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike_target.vi", Empty, False)
vi.Run True
WScript.Sleep 12000
WScript.Echo "run1 ViId = " & vi.GetControlValue("ViId")

vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike.vi", Empty, False)
vi.Run True
WScript.Sleep 12000
WScript.Echo "run2 ViId = " & vi.GetControlValue("ViId")
WScript.Echo "DONE"
