@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0bandcamp_gui.py"
    exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0bandcamp_gui.py"
    exit /b 0
)

echo pythonw was not found. Starting with a console window...
python "%~dp0bandcamp_gui.py"
if errorlevel 1 pause
endlocal
