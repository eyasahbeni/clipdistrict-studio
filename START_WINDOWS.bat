@echo off
setlocal
cd /d "%~dp0"
echo.
echo --------------------------------------
echo     ClipDistrict Studio - GTA 6
 echo --------------------------------------
echo.
where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
      echo Python 3.11+ not found. Install from https://www.python.org/downloads/
      pause
      exit /b 1
    )
    set "PY=python"
)
%PY% -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if errorlevel 1 (
  echo Please install Python 3.11 or newer.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo.
  echo WARNING: FFmpeg not detected. You can browse the app, but rendering needs FFmpeg.
  echo Install FFmpeg from an official trusted source and add it to PATH.
  echo.
)
echo Starting local server at http://127.0.0.1:8765
%PY% -m clipdistrict.web
if errorlevel 1 (
  echo.
  echo Server stopped due to an error. See messages above.
  pause
)
