@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% "%~dp0bandcamp_gui.py"
if errorlevel 1 (
    echo.
    echo The application exited with an error. See the message above.
    pause
)
endlocal
