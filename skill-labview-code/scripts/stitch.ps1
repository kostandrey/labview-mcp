param([string]$Dir, [string]$Filter = "\d+\.png$", [int]$Cols = 4, [int]$Rows = 2, [string]$OutPrefix = "sheet", [string]$NamePattern = "")
Add-Type -AssemblyName System.Drawing
$regex = $NamePattern
if ($regex -eq "") { $regex = $Filter }
$files = Get-ChildItem -Path $Dir -Filter "*.png" | Where-Object { $_.BaseName -match $regex } |
    Sort-Object { if ($_.BaseName -match '(\d+)$') { [int]$Matches[1] } else { 0 } }
Write-Output ("found " + $files.Count + " files")
if ($files.Count -eq 0) { exit 1 }

$cellW = 0; $cellH = 0
foreach ($f in $files) {
    $i = [System.Drawing.Image]::FromFile($f.FullName)
    if ($i.Width -gt $cellW) { $cellW = $i.Width }
    if ($i.Height -gt $cellH) { $cellH = $i.Height }
    $i.Dispose()
}
Write-Output ("cell " + $cellW + "x" + $cellH)

$capH = 18
$perSheet = $Cols * $Rows
$sheetCount = [Math]::Ceiling($files.Count / $perSheet)
for ($s = 0; $s -lt $sheetCount; $s++) {
    $start = $s * $perSheet
    $end = [Math]::Min(($s+1)*$perSheet - 1, $files.Count-1)
    $sheetFiles = @($files[$start..$end])
    $W = [int]($Cols * $cellW)
    $H = [int]($Rows * ($cellH + $capH))
    $bmp = New-Object System.Drawing.Bitmap -ArgumentList $W, $H
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $font = New-Object System.Drawing.Font "Consolas", 9
    $brush = [System.Drawing.Brushes]::Black
    $pen = [System.Drawing.Pens]::Gray
    for ($k = 0; $k -lt $sheetFiles.Count; $k++) {
        $cx = [int](($k % $Cols) * $cellW)
        $cy = [int]([Math]::Floor($k / $Cols) * ($cellH + $capH))
        $g.DrawString($sheetFiles[$k].Name, $font, $brush, $cx + 2, $cy + 1)
        $img = [System.Drawing.Image]::FromFile($sheetFiles[$k].FullName)
        $g.DrawImage($img, $cx, $cy + $capH, $cellW, $cellH)
        $g.DrawRectangle($pen, $cx, $cy + $capH, $cellW - 1, $cellH - 1)
        $img.Dispose()
    }
    $out = Join-Path $Dir ($OutPrefix + $s + ".png")
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Output ("saved " + $out)
}
