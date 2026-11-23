@echo off
title Groww AI Trading Agent - Stop
color 0C

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
set "LOG_DIR=%PROJECT_DIR%logs\startup"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set "DATE_STR=%%c%%b%%a"
set "LOGFILE=%LOG_DIR%\startup_%DATE_STR%.log"

echo [%date% %time%] ===== Groww AI Agent Graceful Shutdown ===== >> "%LOGFILE%"

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do set "SERVER_PID=%%p"

if not defined SERVER_PID (
    echo [%date% %time%] INFO: No process on port 8000. Already stopped. >> "%LOGFILE%"
    echo No agent running. Nothing to stop.
    exit /b 0
)

echo [%date% %time%] Found PID: %SERVER_PID%. Stopping... >> "%LOGFILE%"

set "PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"
cd /d "%PROJECT_DIR%"
"%PYTHON%" -c "import urllib.request;r=urllib.request.Request('http://127.0.0.1:8000/api/agent/stop',method='POST');r.add_header('Content-Type','application/json');urllib.request.urlopen(r,data=b'{}',timeout=5)" >nul 2>&1

timeout /t 10 /nobreak >nul

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    taskkill /PID %SERVER_PID% /F >nul 2>&1
    echo [%date% %time%] Force killed PID %SERVER_PID%. >> "%LOGFILE%"
    echo Agent force-stopped.
) else (
    echo [%date% %time%] Agent stopped gracefully. >> "%LOGFILE%"
    echo Agent stopped gracefully.
)

endlocal
exit /b 0