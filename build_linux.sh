#!/usr/bin/env bash
set -e

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install PySide6 pyinstaller

pyinstaller --noconfirm scheduler_app.spec

echo "완료: dist/SchedulerApp"