智慧园区能耗与环境监测系统 v3.0
Sprint 3：实时处理与告警

启动：
1. 双击“启动系统.bat”，或运行 python main.py。
2. 使用 Python 3（需包含 Tkinter）；无需第三方 UI 库或网络连接。

演示账号：
管理员：admin / admin123
运维人员：operator / operator123
只读用户：viewer / viewer123

本迭代包含：
- 继承数据接入、事件校验、JSON/JSONL 导入和 eventId 去重。
- 实时更新设备在线状态，迟到事件标记质量状态。
- 按设备、指标和事件分钟计算均值、最小值、最大值、样本数及异常数。
- 内置阈值规则，支持连续次数、冷却时间、告警确认和指标恢复后自动解除。
- 错误用例检测：无效消息进入隔离记录，在界面查看错误原因和原始数据。
- 自动化测试覆盖正常处理、聚合、告警、恢复、重复事件及非法输入。

文件说明：
- desktop_app.py：Tkinter 桌面界面。
- processing_service.py：实时事件处理、分钟聚合、在线状态和告警。
- telemetry_service.py：模拟器、队列及 v2 数据接入/校验逻辑。
- v1_store.py：用户、设备、指标和遥测基础存储。
- tests/test_v3_processing.py：错误用例和核心处理测试。
- 数据库设计.md、需求规格说明书.md、系统原型说明.md：设计和验收说明。

测试：python -m unittest discover -s tests -v
SQLite 数据库 energy_monitor.db 在首次运行时创建于本目录。
