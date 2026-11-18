@echo off
title ClipDistrict Studio
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed.
  echo  Install Python 3.11 or newer from https://www.python.org/downloads/
  echo  IMPORTANT: tick "Add python.exe to PATH" during install, then run start.bat again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  First run: setting things up. This takes a few minutes...
  %PY% -m venv .venv || (echo Could not create the virtual environment & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

where ffmpeg >nul 2>nul
if errorlevel 1 if not exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
  echo  Installing FFmpeg ^(video engine^)...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
)

if not exist ".venv\.installed" (
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt || (echo Install failed. Check your internet and run start.bat again. & pause & exit /b 1)
  echo done> ".venv\.installed"
) else (
  rem keep the downloader fresh, YouTube changes often
  python -m pip install -q -U "yt-dlp[default]"
)

python -m clipdistrict app
pause
