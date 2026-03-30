$here = Split-Path $MyInvocation.MyCommand.Definition -Parent
Set-Location $here
$port = 3001
Write-Host "Serving add-in on http://127.0.0.1:$port" -ForegroundColor Green
python -m http.server $port --bind 127.0.0.1
