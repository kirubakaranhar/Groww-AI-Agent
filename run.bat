@echo off
title Groww Autonomous AI Trading Agent
color 0A
echo ============================================================
echo   GROWW AUTONOMOUS AI TRADING AGENT - VERSION 1.0
echo ============================================================
echo.
echo [1/2] Changing directory to project folder...
cd /d "%~dp0"

echo [2/2] Starting Python FastAPI & Agent Server...
echo.
echo Control Center URL: http://127.0.0.1:8000
echo.
echo Press Ctrl+C anytime to stop the server safely.
echo ============================================================
echo.

.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%.
    pause
)
