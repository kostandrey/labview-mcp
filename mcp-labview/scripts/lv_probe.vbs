' Probe a VI inside an LLB: export strings + connector-pane/diagram images (read-only, no save)
Option Explicit
Const optsNoDialogs = &H20
Dim viPath, work
viPath = WScript.Arguments(0)
work = WScript.Arguments(1)
Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(work) Then fso.CreateFolder work

Dim app, tries
Set app = CreateObject("LabVIEW.Application")
tries = 0
Do While app.Version = "" And tries < 45
  WScript.Sleep 2000
  tries = tries + 1
Loop
WScript.Echo "App.Version : " & app.Version

Dim vi
Set vi = app.GetVIReference(viPath, "", False, optsNoDialogs)
WScript.Echo "VI.Name : " & vi.Name

Dim base
base = fso.GetBaseName(viPath)
Dim stringsFile
stringsFile = work & "\" & base & "_strings.txt"
vi.ExportVIStrings stringsFile, False, work & "\" & base & "_strings.log", False, True
WScript.Echo "strings: " & fso.GetFile(stringsFile).Size & " bytes"

Dim imgDir
imgDir = work & "\images_" & base
If Not fso.FolderExists(imgDir) Then fso.CreateFolder imgDir
vi.PrintVIToHTML work & "\" & base & "_report.html", False, 4, 0, 24, imgDir
WScript.Echo "images: " & fso.GetFolder(imgDir).Files.Count & " file(s)"

On Error Resume Next
vi.CloseFrontPanel
app.Quit
On Error GoTo 0
WScript.Echo "done"
