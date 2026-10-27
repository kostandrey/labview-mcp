' lva_keeper.vbs - persistent keeper for the LVA Session server.
' Holds a LabVIEW.Application + VI reference forever so the COM-launched
' LabVIEW instance never quits (last-reference-released would kill it).
' Starts the server hierarchy if not running. Writes a ready marker.
' Stop: create the stop file _service\tmp\lva_keeper_stop.txt (checked each s).
Option Explicit
Dim fso : Set fso = CreateObject("Scripting.FileSystemObject")
Dim sh : Set sh = CreateObject("WScript.Shell")
Dim base : base = "C:\LabView skill"
Dim log : Set log = fso.OpenTextFile(base & "\_service\tmp\lva_keeper.log", 8, True)
Dim ready : ready = base & "\_service\tmp\lva_keeper_ready.txt"
Dim stopF : stopF = base & "\_service\tmp\lva_keeper_stop.txt"
If fso.FileExists(stopF) Then fso.DeleteFile stopF, True
If fso.FileExists(ready) Then fso.DeleteFile ready, True
log.WriteLine Now & " keeper start"

Dim app, vi, i
For i = 1 To 60
  Err.Clear
  Set app = CreateObject("LabVIEW.Application")
  If Err.Number = 0 Then Exit For
  If i < 60 Then WScript.Sleep 2000
Next
If Err.Number <> 0 Then
  log.WriteLine Now & " FATAL no LabVIEW.Application: 0x" & Hex(Err.Number)
  log.Close
  WScript.Quit 1
End If
log.WriteLine Now & " attached " & app.Version

' NOTE: no LVA_State preload needed - the session VI's subVI links are
' correct (scripting-server\Scripting Server\ copies, verified 16:03).
' A top-level Run True on LVA_State hung once in a half-initialized
' instance, so it is deliberately not used here.
Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
log.WriteLine Now & " ref ok"

Err.Clear
vi.Run True   ' starts the server hierarchy (async); error 0x1964 = already running
log.WriteLine Now & " Run: 0x" & Hex(Err.Number) & " " & Err.Description

fso.CreateTextFile(ready).Close
log.WriteLine Now & " ready - holding references"

Dim wmi3, p4, alive
Do
  WScript.Sleep 1000
  If fso.FileExists(stopF) Then Exit Do
  ' self-heal: if the LabVIEW process died (crash / user quit), re-attach
  ' and restart the server - otherwise the next driver call would spawn
  ' a doomed instance the keeper does not hold.
  alive = False
  Err.Clear
  Set wmi3 = GetObject("winmgmts:\\.\root\cimv2")
  For Each p4 In wmi3.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name='LabVIEW.exe'")
    alive = True
  Next
  If Not alive Then
    log.WriteLine Now & " LabVIEW gone - re-attaching"
    Err.Clear
    Set app = CreateObject("LabVIEW.Application")
    If Err.Number = 0 Then
      Set vst = app.GetVIReference(base & "\scripting-server\Scripting Server\LVA_State.vi", "", False, &H20)
      Set vi = app.GetVIReference(base & "\gateway\LVA\LVA Session.vi", "", False, &H20)
      vi.Run True
      log.WriteLine Now & " re-attached, server Run: 0x" & Hex(Err.Number)
    Else
      log.WriteLine Now & " re-attach failed 0x" & Hex(Err.Number)
    End If
  End If
Loop
log.WriteLine Now & " stop file seen - exiting (references released)"
log.Close
