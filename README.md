# 智慧园区能耗与环境监测系统

本目录汇总了系统从 v1.0 到 v4.0 的多个迭代版本，以及独立的桌面 Web UI 版本。各版本目录相互独立，数据库、依赖和启动入口均位于各自目录中。

## 版本一览

| 目录 | 文件数 | 主要内容 |
|---|---:|---|
| [`软件工程v1.0/`](./软件工程v1.0/) | 19 | Sprint 1：需求与基础框架，包含 Tkinter 桌面界面、用户/设备/指标基础存储和遥测格式定义。 |
| [`软件工程v2.0/`](./软件工程v2.0/) | 16 | Sprint 2：在基础框架上增加遥测模拟、文件导入、校验、去重和持久化。 |
| [`软件工程v3.0/`](./软件工程v3.0/) | 19 | Sprint 3：增加实时处理、分钟聚合、在线状态和阈值告警。 |
| [`软件工程v4.0/软件工程v4.0/`](./软件工程v4.0/软件工程v4.0/) | 12 | v4.0 单体实现，包含完整桌面系统、业务服务、测试和 Windows 打包脚本。 |
| [`软件工程v4.0f/`](./软件工程v4.0f/) | 132 | v4.0 模块化版本，包含应用源码、测试、可执行程序及 PyInstaller 构建目录。 |
| [`软件工程v4.0ff/`](./软件工程v4.0ff/) | 103 | v4.0 模块化运行版本，包含源码、测试和可执行程序。 |
| [`软件工程UI版本/`](./软件工程UI版本/) | 82 | 基于 Python 业务服务和 SQLite 的 Layui 网页界面，通过桌面窗口运行。 |
| [`软件工程v4.0(1).zip`](./软件工程v4.0(1).zip) | — | v4.0 压缩归档文件。 |

上表文件数是本 README 编写时各版本目录中的文件数，包含缓存和构建产物，但不包含本 README。版本之间有重复文件，它们是各自独立的快照，不应将目录合并使用。

## 各版本文件说明

### v1.0：需求与基础框架

- `main.py`：启动入口；`desktop_app.py`：Tkinter 桌面界面。
- `v1_store.py`：基础数据存储；`energy_monitor.db`：SQLite 数据库。
- `index.html`：交互式网页原型；`telemetry_event.schema.json`：遥测事件格式定义。
- `requirements.txt`：Python 依赖；`启动系统.bat`：Windows 启动脚本。
- `需求规格说明书.md`、`系统原型说明.md`、`数据库设计.md`：需求和设计文档。
- `tests/test_v1_store.py`：基础存储测试。
- `README.txt`：本版本的启动、功能范围和测试说明。

### v2.0：数据接入

- `main.py`、`desktop_app.py`：启动入口和桌面界面。
- `telemetry_service.py`：遥测导入、校验、去重、队列及模拟器逻辑；`v1_store.py`：基础数据存储。
- `energy_monitor.db`：SQLite 数据库；`telemetry_event.schema.json`：遥测格式定义。
- `requirements.txt`、`启动系统.bat`：依赖和启动脚本。
- `需求规格说明书.md`、`系统原型说明.md`、`数据库设计.md`：设计文档。
- `tests/test_v2_ingest.py`：数据接入测试；`README.txt`：本版本说明。

### v3.0：实时处理与告警

- `main.py`、`desktop_app.py`：启动入口和桌面界面。
- `processing_service.py`：实时处理、分钟聚合、在线状态及告警；`telemetry_service.py`：数据接入和模拟；`v1_store.py`：基础存储。
- `energy_monitor.db`、`telemetry_event.schema.json`：SQLite 数据库和遥测格式定义。
- `requirements.txt`、`启动系统.bat`：依赖和启动脚本。
- `需求规格说明书.md`、`系统原型说明.md`、`数据库设计.md`：设计文档。
- `tests/test_v3_processing.py`：处理和告警测试；`README.txt`：本版本说明。

### v4.0：单体版本

文件位于额外嵌套的 [`软件工程v4.0/`](./软件工程v4.0/软件工程v4.0/) 子目录中：

- `main.py`：启动入口；`desktop_app.py`：桌面界面和登录窗口。
- `monitor_service.py`：主要业务服务；`park_energy_monitor.py`：兼容旧版导入的入口。
- `energy_monitor.db`：SQLite 数据库；`requirements.txt`：依赖。
- `启动系统.bat`：运行脚本；`build_exe.bat`：PyInstaller 打包脚本。
- `tests/test_v4.py`：核心功能测试；`README.txt`：启动、测试和功能说明。

### v4.0f：模块化版本与构建目录

- 根目录文件：`main.py`、`park_energy_monitor.py`、`build_exe.bat`、`ParkEnergyMonitor.spec`、`ParkEnergyMonitor_Fixed.spec`、`ParkEnergyMonitor_Fixed.exe`、`energy_monitor.db`。
- `energy_monitor_app/__init__.py`：应用包初始化。
- `energy_monitor_app/app/`：`main.py`（应用入口）、`monitor_app.py`（应用协调）。
- `energy_monitor_app/config/constants.py`：常量配置。
- `energy_monitor_app/core/`：`app_paths.py`（路径）、`security.py`（安全相关）、`time_utils.py`（时间处理）。
- `energy_monitor_app/db/`：`schema.py`（数据库结构）、`store.py`（存储操作）。
- `energy_monitor_app/rules/`：`base_rule.py`、`comparison_rules.py`、`rule_factory.py`（告警规则）。
- `energy_monitor_app/services/`：`device_service.py`、`monitor_backend.py`、`query_service.py`、`simulator.py`、`telemetry_service.py`、`user_service.py`（设备、监控、查询、模拟、遥测和用户服务）。
- `energy_monitor_app/ui/`：`alert_view.py`、`dashboard_view.py`、`device_view.py`、`dialogs.py`、`history_view.py`、`quality_view.py`、`simulator_view.py`、`user_view.py`、`widgets.py`（各功能界面和通用控件）。
- `tests/`：`_support.py`、`test_alerts.py`、`test_rules.py`、`test_simulator.py`、`test_telemetry.py`。
- `build/`：PyInstaller 生成的 `ParkEnergyMonitor` 和 `ParkEnergyMonitor_Fixed` 构建目录，含 `.toc` 清单、`.pyz`/`.pkg` 包、可执行文件、警告/交叉引用报告及 `localpycs` 运行库文件。

### v4.0ff：模块化运行版本

模块划分与 v4.0f 相同，包含 `energy_monitor_app/` 下的应用、配置、核心、数据库、规则、服务和 UI 模块，以及 `tests/` 下的 `_support.py`、`test_alerts.py`、`test_rules.py`、`test_simulator.py`、`test_telemetry.py`。本目录另外包含：

- `main.py`、`park_energy_monitor.py`：启动及兼容入口。
- `build_exe.bat`：打包脚本；`ParkEnergyMonitor_Fixed.exe`：Windows 可执行程序。
- `energy_monitor.db`：SQLite 数据库；`requirements.txt`：依赖。
- `启动系统.bat`：Windows 启动脚本；`README.txt`：本版本说明。

### 桌面 Web UI 版本

- `main.py`、`web_server.py`：启动入口和本地 Web 服务。
- `index.html`：Layui 前端页面；`energy_monitor.db`：SQLite 数据库。
- `requirements.txt`、`启动系统.bat`、`README.txt`：依赖、启动方式和版本说明。
- `energy_monitor_app/` 包含：
  - `app/`：`main.py`、`monitor_app.py`。
  - `config/`：`constants.py`。
  - `core/`：`app_paths.py`、`security.py`、`time_utils.py`。
  - `db/`：`schema.py`、`store.py`。
  - `rules/`：`base_rule.py`、`comparison_rules.py`、`rule_factory.py`。
  - `services/`：`device_service.py`、`monitor_backend.py`、`query_service.py`、`simulator.py`、`telemetry_service.py`、`user_service.py`。
  - `ui/`：`alert_view.py`、`dashboard_view.py`、`device_view.py`、`dialogs.py`、`history_view.py`、`quality_view.py`、`simulator_view.py`、`user_view.py`、`widgets.py`。
- `tests/test_web_server_simulator.py`：Web 服务和模拟器测试。

## 运行与测试

每个版本请在对应目录中独立运行。通常可双击该目录中的 `启动系统.bat`；Python 方式及测试命令请以对应 `README.txt` 为准。各版本的数据库文件也是独立的，运行时请确保所在目录可写。

常见测试命令：

```powershell
python -m unittest discover -s tests -v
```

## 生成文件与注意事项

- `__pycache__/` 下的 `.pyc` 是 Python 自动生成的缓存，不是源码。各版本保留了不同 Python 版本生成的缓存文件。
- v4.0f 的 `build/` 是打包中间产物；`*.spec` 是 PyInstaller 配置；`.exe` 是 Windows 可执行程序。
- 各版本中的 `energy_monitor.db` 是 SQLite 数据文件，内容可能因运行而变化；不要将一个版本的数据库随意替换到另一个版本。
- v4.0f 与 v4.0ff 均含同一模块化应用的副本，但目录中的文件并不完全相同；使用前请核对各自的 `README.txt`。
# -
作业
