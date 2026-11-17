@echo off
setlocal
cd /d "%~dp0"

py -3.11 -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed for Python 3.11.
    echo Install it with: py -3.11 -m pip install pyinstaller
    exit /b 1
)

py -3.11 -m PyInstaller --noconfirm --clean --windowed --onefile ^
    --name ParkEnergyMonitor_Fixed ^
    --distpath "%CD%" ^
    --paths "%CD%" ^
    main.py
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo %CD%\ParkEnergyMonitor_Fixed.exe
echo The writable energy_monitor.db will be created beside the EXE.
endlocal
