@echo off
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"

echo [1/3] Installing runtime and build dependencies...
%PY% -m pip install --upgrade pip
if errorlevel 1 goto :error
%PY% -m pip install -r "%~dp0requirements.txt" -r "%~dp0requirements-build.txt"
if errorlevel 1 goto :error

echo [2/3] Building the portable single-file executable...
%PY% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name BandcampCollectionDownloader ^
  --icon "%~dp0assets\app.ico" ^
  --version-file "%~dp0version_info.txt" ^
  --hidden-import PIL._tkinter_finder ^
  --collect-all curl_cffi ^
  --collect-all browser_cookie3 ^
  --collect-data certifi ^
  --workpath "%~dp0build" ^
  --distpath "%~dp0dist" ^
  --specpath "%~dp0build" ^
  "%~dp0bandcamp_gui.py"
if errorlevel 1 goto :error

echo [3/3] Done.
for %%F in ("%~dp0dist\BandcampCollectionDownloader.exe") do echo %%~fF  (%%~zF bytes)
echo.
echo The portable executable is in the dist folder. No Python installation is required.
pause
exit /b 0

:error
echo.
echo Build failed. Read the messages above.
pause
exit /b 1
