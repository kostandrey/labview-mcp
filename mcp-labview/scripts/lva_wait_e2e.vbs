' lva_wait_e2e.vbs - run-test the Wait(ms)-modified server copy.
' Holds COM references for the whole test (keeper pattern), drives open+save,
' reports reply content and LabVIEW CPU before/after.
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim lg : Set lg = fso.CreateTextFile("C:\LabView skill\_service\tmp\lva_wait_e2e.log", True)
On Error Resume Next

Dim rpO : rpO = "C:\LabView skill\_service\tmp\lva_reply_open.txt"
Dim rpS : rpS = "C:\LabView skill\_service\tmp\lva_reply_save.txt"
Dim trig : trig = "C:\LabView skill\_service\tmp\lva_server_trig.txt"
If fso.FileExists(rpO) Then fso.DeleteFile rpO, True
If fso.FileExists(rpS) Then fso.DeleteFile rpS, True

Dim app : Set app = CreateObject("LabVIEW.Application")
lg.WriteLine Now & " attached " & app.Version
Dim vi : Set vi = app.GetVIReference("C:\LabView skill\_service\tmp\lva_server_wait2.vi", "", False, &H20)
Err.Clear
vi.Run True
lg.WriteLine Now & " Run: 0x" & Hex(Err.Number)

Dim sh : Set sh = CreateObject("WScript.Shell")
Set sh = Nothing
Dim cpu1 : cpu1 = Cpu()
lg.WriteLine Now & " cpu before=" & cpu1

' wait for first loop iteration (trig file written by WT4)
Dim j, got : got = False
For j = 1 To 120
  WScript.Sleep 500
  If fso.FileExists(trig) Then got = True : Exit For
Next
lg.WriteLine Now & " trig present=" & got & " after " & (j * 0.5) & "s cpu=" & Cpu()

' drive open
Err.Clear
vi.SetControlValue "ArgOpen", Array("C:\LabView skill\_service\tmp\lva_spike_target.vi", Empty, False)
vi.SetControlValue "Tool", ""
WScript.Sleep 200
vi.SetControlValue "Tool", "open_vi"
lg.WriteLine Now & " open drive err=0x" & Hex(Err.Number)
PollReply rpO, "OPEN"
lg.WriteLine Now & " cpu after open=" & Cpu()

' drive save
Err.Clear
vi.SetControlValue "ArgSave", Array(1, "C:\LabView skill\_service\tmp\lva_wait2_saved.vi", Empty, False)
vi.SetControlValue "Tool", ""
WScript.Sleep 200
vi.SetControlValue "Tool", "save_vi"
lg.WriteLine Now & " save drive err=0x" & Hex(Err.Number)
PollReply rpS, "SAVE"

WScript.Sleep 3000
lg.WriteLine Now & " cpu final=" & Cpu() & " saved_exists=" & fso.FileExists("C:\LabView skill\_service\tmp\lva_wait2_saved.vi")
lg.Close
WScript.Quit 0

Sub PollReply(p, tag)
  Dim k
  For k = 1 To 60
    WScript.Sleep 500
    If fso.FileExists(p) Then
      If fso.GetFile(p).Size > 0 Then
        Dim t : Set t = fso.OpenTextFile(p, 1)
        lg.WriteLine Now & " " & tag & " REPLY: " & t.ReadAll
        t.Close
        Exit Sub
      End If
    End If
  Next
  lg.WriteLine Now & " " & tag & " TIMEOUT trig=[" & ReadF(trig) & "]"
End Sub

Function ReadF(p)
  ReadF = ""
  If Not fso.FileExists(p) Then Exit Function
  Dim t : Set t = fso.OpenTextFile(p, 1)
  ReadF = t.ReadAll
  t.Close
End Function

Function Cpu()
  On Error Resume Next
  Dim wmi, p, c : c = -1
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  For Each p In wmi.ExecQuery("SELECT ProcessorTime FROM Win32_PerfFormattedData_PerfProc_Process WHERE Name='LabVIEW' OR Name LIKE 'LabVIEW%'")
    c = p.PercentProcessorTime
  Next
  If c < 0 Then
    ' fallback: cumulative CPU seconds
    c = -2
    For Each p In wmi.ExecQuery("SELECT IDProcess, PercentProcessorTime FROM Win32_PerfFormattedData_PerfProc_Process WHERE Name LIKE 'LabVIEW%'")
      c = p.PercentProcessorTime
    Next
  End If
  Cpu = c
End Function
