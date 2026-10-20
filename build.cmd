@echo off
REM Build Oleg's Russian Keyboard into a single windowless exe (tray only).
REM Run by double-clicking from the project root.

setlocal
set PY=D:\Tools\Python312\python.exe
set ROOT=%~dp0
set NAME=OlegsRussianKeyboard

"%PY%" -m PyInstaller ^
  --noconfirm --clean --onefile --windowed ^
  --name %NAME% ^
  --add-data "%ROOT%p0\rules.json;." ^
  --add-data "%ROOT%data\ru-words.txt;." ^
  --add-data "%ROOT%data\ru-bigram.tsv;." ^
  --collect-all pymorphy3 ^
  --collect-all pymorphy3_dicts_ru ^
  --hidden-import tray ^
  --hidden-import pystray ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import PIL.ImageFont ^
  --hidden-import wordbook ^
  --hidden-import lookup ^
  --hidden-import learn ^
  --hidden-import dict_index ^
  --hidden-import paths ^
  --distpath "%ROOT%dist" ^
  --workpath "%ROOT%build" ^
  --specpath "%ROOT%build" ^
  "%ROOT%p1\app.py"

echo.
echo Done: %ROOT%dist\%NAME%.exe
pause
