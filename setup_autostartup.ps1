# Groww AI Trading Agent - Windows Task Scheduler Setup
# Run this ONCE as Administrator to register auto-start and auto-stop tasks
# Usage: Right-click PowerShell -> "Run as Administrator" -> Run this script

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GROWW AI TRADING AGENT - WINDOWS AUTO-STARTUP SETUP" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ---- Project path (auto-detect from script location) ----
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ProjectDir "start_agent.bat"
$StopScript  = Join-Path $ProjectDir "stop_agent.bat"

Write-Host "[INFO] Project directory: $ProjectDir" -ForegroundColor Yellow

# Verify scripts exist
if (-not (Test-Path $StartScript)) {
    Write-Host "[ERROR] start_agent.bat not found at: $StartScript" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $StopScript)) {
    Write-Host "[ERROR] stop_agent.bat not found at: $StopScript" -ForegroundColor Red
    exit 1
}

# ---- Check Administrator privileges ----
$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "[ERROR] This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "        Right-click PowerShell -> 'Run as administrator'" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Running as Administrator." -ForegroundColor Green
Write-Host ""

# ---- Task names ----
$StartTaskName = "GrowwAI_MarketOpen"
$StopTaskName  = "GrowwAI_MarketClose"

# ---- Remove existing tasks if any ----
Write-Host "[STEP 1] Removing old tasks (if any)..." -ForegroundColor Cyan

foreach ($TaskName in @($StartTaskName, $StopTaskName)) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Removed old task: $TaskName" -ForegroundColor Yellow
    }
}

# ---- Create START task (09:00 IST Mon-Fri) ----
Write-Host ""
Write-Host "[STEP 2] Creating startup task: $StartTaskName" -ForegroundColor Cyan
Write-Host "         Trigger: 09:00 IST, Monday to Friday" -ForegroundColor White

$StartAction = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$StartScript`"" `
    -WorkingDirectory $ProjectDir

# 09:00 IST = 03:30 UTC (IST = UTC+5:30)
# Task Scheduler uses LOCAL TIME — so we use 09:00 local
$StartTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "09:00AM"

$StartSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$StartPrincipal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType InteractiveToken `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $StartTaskName `
    -Action $StartAction `
    -Trigger $StartTrigger `
    -Settings $StartSettings `
    -Principal $StartPrincipal `
    -Description "Groww AI Trading Agent - Auto-start at market open (09:00 IST Mon-Fri)" `
    -Force | Out-Null

Write-Host "  [OK] Startup task created." -ForegroundColor Green

# ---- Create STOP task (15:35 IST Mon-Fri) ----
Write-Host ""
Write-Host "[STEP 3] Creating shutdown task: $StopTaskName" -ForegroundColor Cyan
Write-Host "         Trigger: 15:35 IST, Monday to Friday" -ForegroundColor White

$StopAction = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$StopScript`"" `
    -WorkingDirectory $ProjectDir

$StopTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "03:35PM"

$StopSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$StopPrincipal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType InteractiveToken `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $StopTaskName `
    -Action $StopAction `
    -Trigger $StopTrigger `
    -Settings $StopSettings `
    -Principal $StopPrincipal `
    -Description "Groww AI Trading Agent - Auto-stop at market close (15:35 IST Mon-Fri)" `
    -Force | Out-Null

Write-Host "  [OK] Shutdown task created." -ForegroundColor Green

# ---- Verify tasks ----
Write-Host ""
Write-Host "[STEP 4] Verifying registered tasks..." -ForegroundColor Cyan
Write-Host ""

$tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like "GrowwAI_*" }
foreach ($t in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName
    Write-Host ("  Task : " + $t.TaskName) -ForegroundColor White
    Write-Host ("  State: " + $t.State) -ForegroundColor Green
    Write-Host ("  Next : " + $info.NextRunTime) -ForegroundColor Yellow
    Write-Host ""
}

# ---- Summary ----
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AUTO-STARTUP SETUP COMPLETE!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  START Task : GrowwAI_MarketOpen  (09:00 IST Mon-Fri)" -ForegroundColor White
Write-Host "  STOP  Task : GrowwAI_MarketClose (15:35 IST Mon-Fri)" -ForegroundColor White
Write-Host ""
Write-Host "  What happens automatically every weekday:" -ForegroundColor Yellow
Write-Host "  09:00 -> start_agent.bat checks NSE holiday/weekend" -ForegroundColor White
Write-Host "  09:00 -> If market day: starts server on port 8000" -ForegroundColor White
Write-Host "  09:15 -> Market opens, agents begin scanning" -ForegroundColor White
Write-Host "  15:15 -> Position Monitor auto square-off begins" -ForegroundColor White
Write-Host "  15:35 -> stop_agent.bat gracefully shuts down" -ForegroundColor White
Write-Host ""
Write-Host "  IMPORTANT: .env must have SIMULATE_MARKET_HOURS=false" -ForegroundColor Red
Write-Host "             for real NSE hours operation." -ForegroundColor Red
Write-Host ""
Write-Host "  To remove tasks later, run:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName GrowwAI_MarketOpen -Confirm:`$false" -ForegroundColor Gray
Write-Host "  Unregister-ScheduledTask -TaskName GrowwAI_MarketClose -Confirm:`$false" -ForegroundColor Gray
Write-Host ""

Read-Host "Press Enter to close"
