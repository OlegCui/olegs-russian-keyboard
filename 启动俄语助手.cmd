@echo off
chcp 65001 >nul
set "PY=D:\Tools\Python312\python.exe"
set "LOG=%~dp0p1\launcher.log"
echo [%date% %time%] launcher start >> "%LOG%"
if not exist "%PY%" goto NOPY
cd /d "%~dp0p1"
echo [%date% %time%] python=%PY% >> "%LOG%"
"%PY%" -u app.py
echo [%date% %time%] app exited rc=%ERRORLEVEL% >> "%LOG%"
echo.
echo ============================================
echo  App exited. rc=%ERRORLEVEL%
echo  Log: %LOG%
echo ============================================
pause
exit /b 0

:NOPY
echo [%date% %time%] python not found >> "%LOG%"
echo.
echo Python not found: %PY%
echo.
pause
exit /b 1
