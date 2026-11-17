智慧园区能耗与环境监测系统 v2.0
Sprint 2：数据接入

启动：
1. 双击“启动系统.bat”，或运行 python main.py。
2. 使用 Python 3（需包含 Tkinter）；无需第三方 UI 库或网络连接。

演示账号：
管理员：admin / admin123
运维人员：operator / operator123
只读用户：viewer / viewer123

本迭代在 Sprint 1 的登录、设备档案和指标目录基础上新增：
- 本地遥测模拟器，可设置采集间隔并持续向队列发送事件。
- JSON 对象、JSON 数组及 JSONL/NDJSON 文件导入。
- 遥测字段、设备/指标、单位、取值范围和事件时间校验。
- eventId 重复事件去重；单条无效记录隔离并继续处理后续记录。
- SQLite 遥测持久化、异常记录和最近接收数据查看。

本迭代尚不包含实时聚合、阈值告警、历史查询和 CSV 导出；这些属于后续 Sprint。

文件说明：
- desktop_app.py：Tkinter 桌面 UI。
- telemetry_service.py：遥测校验、文件导入、队列处理和模拟器。
- v1_store.py：Sprint 1 用户、设备、指标和基础数据表。
- telemetry_event.schema.json：遥测事件格式。
- 数据库设计.md、需求规格说明书.md、系统原型说明.md：设计和验收说明。
- tests：自动化测试。运行 python -m unittest discover -s tests -v。

SQLite 数据库 energy_monitor.db 在首次运行时创建于本目录。
