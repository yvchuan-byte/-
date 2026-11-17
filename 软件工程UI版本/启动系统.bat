@echo off
chcp 65001 >nul
cd /d "%~dp0"
python main.py
if errorlevel 1 (
  echo.
  echo 系统启动失败。请确认已安装 Python 3 和桌面界面依赖。
  echo 可运行 python -m pip install -r requirements.txt 安装依赖。
  pause
)
