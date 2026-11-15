Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GROWW AUTONOMOUS AI TRADING AGENT - VERSION 1.0" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Set-Location -Path $PSScriptRoot
Write-Host "Dashboard URL: http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "Press Ctrl + C to stop the agent server safely." -ForegroundColor Gray
Write-Host ""

& ".\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
