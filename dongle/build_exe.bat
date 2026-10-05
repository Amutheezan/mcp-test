@echo off
rem Builds dist\Dongle.exe (single file, no console). Needs: pip install pyinstaller PySide6
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name Dongle ^
  --add-data "sprites\f_0.png;sprites" --add-data "sprites\f_1.png;sprites" ^
  --add-data "sprites\f_2.png;sprites" --add-data "sprites\f_3.png;sprites" ^
  --add-data "sprites\f_4.png;sprites" --add-data "sprites\f_5.png;sprites" ^
  --add-data "sprites\f_6.png;sprites" --add-data "sprites\f_7.png;sprites" ^
  --add-data "sprites\f_8.png;sprites" ^
  dongle.py
