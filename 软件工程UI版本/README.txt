智慧园区实时能耗与环境监测系统 - Layui UI 版本

启动方式：
1. 在本目录双击“启动系统.bat”，即可在独立桌面窗口中运行。
2. 如果提示缺少桌面界面依赖，在本目录运行 python -m pip install -r requirements.txt。
3. 关闭桌面窗口即可退出系统，不会打开外部浏览器。

实验账号：
管理员：admin / admin123
运维人员：operator / operator123
只读用户：viewer / viewer123

本版本保留原系统的 Python 业务服务和 SQLite 数据库，在 PyQtWebEngine 桌面窗口中显示 Layui 界面。
窗口内部通过本地回环地址连接业务服务，不会对局域网开放。
Layui 样式和组件从 unpkg CDN 加载，首次启动需要网络连接。

运行总览页的“采集间隔”支持 1–60 秒整数：
1. 启动前设置间隔，再点击“启动模拟器”。
2. 运行中修改间隔后，点击“应用间隔”立即生效，无需停止模拟器。
