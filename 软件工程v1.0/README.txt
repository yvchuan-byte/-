智慧园区能耗与环境监测系统 v1.0
Sprint 1：需求与基础框架（Tkinter 原生桌面 UI）

启动：
1. 双击“启动系统.bat”，程序会在独立桌面窗口中打开。
2. 使用 Python 3 运行；界面采用 Python 标准库 Tkinter，不依赖第三方 UI 库。

演示账号：
管理员：admin / admin123
运维人员：operator / operator123
只读用户：viewer / viewer123

本版包含：登录与角色、设备档案、指标目录、SQLite 基础表、遥测 JSON Schema。
本版不包含：数据接入/模拟、实时处理、告警、历史查询和系统验收等后续 Sprint 功能。

SQLite 数据库：energy_monitor.db（首次启动自动创建于本目录）。
桌面界面：desktop_app.py（Tkinter，沿用“软件工程”主程序的原生桌面交互方式）。
交互式网页原型：index.html（原生 HTML/CSS/JavaScript，不使用外部 UI 库）。
原型说明：系统原型说明.md
需求说明：需求规格说明书.md
数据库说明：数据库设计.md
遥测格式：telemetry_event.schema.json
测试：python -m unittest discover -s tests -v

