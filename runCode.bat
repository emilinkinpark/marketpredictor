@echo off
echo Setting up environment...

REM Ensure pip is up to date
python -m pip install --upgrade pip

REM Install required packages
python -m pip install requests pandas matplotlib openpyxl
python -m pip install httpx python-telegram-bot==20.7
python -m pip install tk

REM Launch the script
echo Running marketpredictor.py...
python marketpredictor.py

pause >nul
exit

