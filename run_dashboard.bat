@echo off
REM Double-click to start the dashboard.
REM The window opens centered, the dashboard opens in your browser, and Esc stops everything.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_dashboard.ps1"
