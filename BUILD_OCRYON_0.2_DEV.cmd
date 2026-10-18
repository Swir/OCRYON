@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo OCRYON 0.2.0 - BUILD NA WINDOWS 11 (PYTHON 3.12 x64)
echo ==========================================================
where py >nul 2>&1
if %errorlevel% == 0 (
  py -3.12 tools\build_on_windows_preview.py
) else (
  python tools\build_on_windows_preview.py
)
if errorlevel 1 (
  echo.
  echo KOMPILACJA LUB TESTY NIE PRZESZLY. ZOBACZ KOMUNIKAT POWYZEJ.
) else (
  echo.
  echo GOTOWE: OCRYON-0.2.0-Windows-x64-PORTABLE.zip
  echo ROZPAKUJ CALY PLIK I URUCHOM OCRYON.exe.
)
pause
