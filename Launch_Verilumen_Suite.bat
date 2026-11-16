@echo off
title VERILUMEN ATE Intelligence Suite Launcher
echo ============================================================
echo   Starting VERILUMEN ATE Intelligence Suite (.exe)
echo ============================================================
cd /d "%~dp0"
if exist "%~dp0Launch_Verilumen_Suite.exe" (
    start "" "%~dp0Launch_Verilumen_Suite.exe"
) else (
    python run_suite.py
)
