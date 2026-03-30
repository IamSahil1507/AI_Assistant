$root = "C:\AI_Assistant\office-addin"
$bas = Join-Path $root "openclaw.bas"
$out = Join-Path $root "openclaw.xlam"

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$wb = $excel.Workbooks.Add()
$vbproj = $wb.VBProject
$vbcomp = $vbproj.VBComponents.Import($bas)

$xlAddIn = 55
$wb.SaveAs($out, $xlAddIn)
$wb.Close($true)
$excel.Quit()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
Write-Host "Created $out"
