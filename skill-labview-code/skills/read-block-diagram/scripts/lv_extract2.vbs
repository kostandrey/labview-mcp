' Parametrized LabVIEW code extraction via ActiveX (VI Server)
' Usage: cscript //nologo lv_extract2.vbs <sourceViPath> <workDir>
' Copies the VI, then exports strings + HTML report with PNGs. Original untouched.
Option Explicit
Const optsNoDialogs = &H20

Dim srcVi, work
If WScript.Arguments.Count < 2 Then
  WScript.Echo "usage: lv_extract2.vbs <vi path> <work dir>"
  WScript.Quit 1
End If
srcVi = WScript.Arguments(0)
work = WScript.Arguments(1)

Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(srcVi) Then
  WScript.Echo "SOURCE NOT FOUND: " & srcVi
  WScript.Quit 1
End If
If Not fso.FolderExists(work) Then fso.CreateFolder work

Dim base, dst
base = fso.GetBaseName(srcVi)
dst = work & "\" & base & " (copy).vi"
If fso.FileExists(dst) Then fso.DeleteFile dst
fso.CopyFile srcVi, dst

Dim app, tries
Set app = CreateObject("LabVIEW.Application")
tries = 0
Do While app.Version = "" And tries < 45
  WScript.Sleep 2000
  tries = tries + 1
Loop
WScript.Echo "App.Version : " & app.Version

Dim vi
Set vi = app.GetVIReference(dst, "", False, optsNoDialogs)
WScript.Echo "VI.Name    : " & vi.Name
On Error Resume Next
WScript.Echo "VI.Revision: " & vi.RevisionNumber
Err.Clear
On Error GoTo 0

Dim stringsFile, logFile
stringsFile = work & "\" & base & "_strings.txt"
logFile = work & "\" & base & "_strings.log"
vi.ExportVIStrings stringsFile, False, logFile, False, True
WScript.Echo "VI strings exported: " & stringsFile & " (" & fso.GetFile(stringsFile).Size & " bytes)"

Dim imgDir
imgDir = work & "\images_" & base
If Not fso.FolderExists(imgDir) Then fso.CreateFolder imgDir
vi.PrintVIToHTML work & "\" & base & "_report.html", False, 4, 0, 24, imgDir
WScript.Echo "HTML report: " & work & "\" & base & "_report.html"
WScript.Echo "images: " & fso.GetFolder(imgDir).Files.Count & " file(s)"

On Error Resume Next
vi.CloseFrontPanel
app.Quit
On Error GoTo 0
WScript.Echo "done"
