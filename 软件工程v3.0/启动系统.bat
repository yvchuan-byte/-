@echo off
chcp 65001 >nul
cd /d "%~dp0"
python main.py
if errorlevel 1 (
  echo.
  echo 启动失败。请确认已安装支持 Tkinter 的 Python 3。
  pause
)
