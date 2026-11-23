@echo off
title Groww AI Trading Agent - Auto Start
color 0A

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe"
set "LOG_DIR=%PROJECT_DIR%logs\startup"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set "DATE_STR=%%c%%b%%a"
set "LOGFILE=%LOG_DIR%\startup_%DATE_STR%.log"

echo [%date% %time%] ===== Groww AI Agent Auto-Startup ===== >> "%LOGFILE%"

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] SKIP: Agent already running on port 8000. >> "%LOGFILE%"
    echo Agent already running on port 8000. Exiting.
    exit /b 0
)

echo [%date% %time%] Checking market calendar... >> "%LOGFILE%"
cd /d "%PROJECT_DIR%"

"%PYTHON%" -c "import sys; sys.path.insert(0,'.');from backend.core.scheduler import MarketScheduler;state=MarketScheduler.get_session_state();phase=state.get('phase','');reason=state.get('reason','');print('SKIP:'+reason) if phase in ('WEEKEND','HOLIDAY') else print('OK:'+reason);sys.exit(1 if phase in ('WEEKEND','HOLIDAY') else 0)" 2>>"%LOGFILE%"

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] SKIP: NSE market closed today. >> "%LOGFILE%"
    echo NSE market closed today. Skipping startup.
    exit /b 0
)

echo [%date% %time%] Market day confirmed. Starting agent server... >> "%LOGFILE%"

start "Groww AI Agent Server" /min cmd /c ""%PYTHON%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 >> "%LOG_DIR%\server_%DATE_STR%.log" 2>&1"

timeout /t 5 /nobreak >nul

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] SUCCESS: Agent started on http://127.0.0.1:8000 >> "%LOGFILE%"
    echo Groww AI Agent started on http://127.0.0.1:8000
) else (
    echo [%date% %time%] ERROR: Server did not start within 5 seconds. >> "%LOGFILE%"
    echo ERROR: Server did not start. Check logs.
)

endlocal
exit /b 0