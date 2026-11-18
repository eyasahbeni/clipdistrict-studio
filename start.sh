#!/usr/bin/env bash
# ClipDistrict Studio launcher for macOS / Linux
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Install Python 3.11+ first"; exit 1; }
[ -x .venv/bin/python ] || "$PY" -m venv .venv
source .venv/bin/activate
if [ ! -f .venv/.installed ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch .venv/.installed
else
  python -m pip install -q -U "yt-dlp[default]"
fi
python -m clipdistrict app
