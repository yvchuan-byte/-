智慧园区能耗与环境监测系统 v4.0

启动：
1. 双击“启动系统.bat”，或运行 python main.py。
2. 需要支持 Tkinter 的 Python 3；运行系统和测试不需要第三方 Python 包。
3. 运行测试：python -m unittest discover -s tests -v

实验账号：
管理员：admin / admin123
运维人员：operator / operator123
只读用户：viewer / viewer123

文件说明：
- main.py：系统启动入口。
- desktop_app.py：桌面界面和登录窗口。
- monitor_service.py：数据库、业务服务、规则和模拟器。
- park_energy_monitor.py：旧版导入兼容入口。
- tests/test_v4.py：规则、遥测、模拟器和告警测试。
- energy_monitor.db：SQLite 数据库；运行时会在应用目录中创建或更新。
- build_exe.bat：使用 PyInstaller 构建 Windows 单文件程序（需 Python 3.11 和 PyInstaller）。

系统包含设备与用户管理、遥测模拟与查询、告警规则、数据质量记录等功能。
数据库会在首次启动时初始化；请保留可写的应用目录。
