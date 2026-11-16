@echo off
setlocal
cd /d "%~dp0"
title Build Verilumen - ATE Release Installer
echo ============================================================
echo   VERILUMEN - ATE RELEASE BUILDER
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_release.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)
echo.
echo [DONE] Build finished! Check desktop\dist for installer and update files.
pause
