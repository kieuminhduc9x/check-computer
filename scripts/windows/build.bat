@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."

where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo Chua co PyInstaller. Dang cai...
  python -m pip install -r requirements.txt pyinstaller
)

set MODE=%1
if "%MODE%"=="" set MODE=onefile

if /I "%MODE%"=="console" (
  echo === Build DEBUG (co cua so CMD) ===
  python -m PyInstaller --noconfirm --clean --onefile --console --name PCMonitor --specpath build --distpath dist --workpath build\pyi --hidden-import mss --hidden-import mss.windows --hidden-import PIL --hidden-import PIL.Image --hidden-import psutil --hidden-import dotenv --hidden-import requests --hidden-import urllib3 --collect-all mss main.py
  goto :done
)

if /I "%MODE%"=="onedir" (
  echo === Build ONEDIR (thu muc, khoi dong nhanh hon) ===
  python -m PyInstaller --noconfirm --clean --onedir --noconsole --name PCMonitor --specpath build --distpath dist --workpath build\pyi --hidden-import mss --hidden-import mss.windows --hidden-import PIL --hidden-import PIL.Image --hidden-import psutil --hidden-import dotenv --hidden-import requests --hidden-import urllib3 --collect-all mss main.py
  goto :done
)

echo === Build ONEFILE (1 file .exe, an cua so) ===
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name PCMonitor --specpath build --distpath dist --workpath build\pyi --hidden-import mss --hidden-import mss.windows --hidden-import PIL --hidden-import PIL.Image --hidden-import psutil --hidden-import dotenv --hidden-import requests --hidden-import urllib3 --collect-all mss main.py

:done
if errorlevel 1 (
  echo BUILD THAT BAI.
  exit /b 1
)
echo.
echo Xong. File nam o: dist\PCMonitor.exe  (hoac dist\PCMonitor\ neu onedir)
echo Copy .exe (va thu muc neu onedir) + file .env vao 1 folder tren may dich.
echo Huong dan day du: BUILD.md
exit /b 0
