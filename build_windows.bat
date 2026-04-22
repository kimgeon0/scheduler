@echo off
py -3 -m venv .venv
call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install PySide6 pyinstaller

pyinstaller --noconfirm scheduler_app.spec

echo 완료: dist\SchedulerApp
pause