@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

echo Installing dependencies...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%~dp0requirements.txt"
echo.
echo Done. You can now start the app with run.bat
pause
endlocal
