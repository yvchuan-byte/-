import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from telemetry_service import QueueProcessor, TelemetrySimulator, V2Store


ROLE_NAMES = {
    "ADMIN": "系统管理员",
    "OPERATOR": "运维人员",
    "VIEWER": "只读用户",
}


class DesktopApp:
    def __init__(self, root, database_path):
        self.root = root
        self.root.withdraw()
        self.root.title("智慧园区实时能耗与环境监测系统")
        self.root.geometry("1120x720")
        self.root.minsize(900, 600)
        self.store = V2Store(database_path)
        self.user = None
        self.event_queue = queue.Queue()
        self.processor = QueueProcessor(self.store, self.event_queue)
        self.simulator = TelemetrySimulator(self.store)
        self.sim_stop_event = None
        self.sim_thread = None
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_login()

    def show_login(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("用户登录")
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", self.close)

        panel = ttk.Frame(dialog, padding=28)
        panel.pack(fill="both", expand=True)
        ttk.Label(
            panel, text="智慧园区监测系统", font=("Microsoft YaHei UI", 18, "bold")
        ).pack(anchor="w")
        ttk.Label(panel, text="园区能耗与环境数据接入平台").pack(anchor="w", pady=(4, 18))

        form = ttk.Frame(panel)
        form.pack(fill="x")
        ttk.Label(form, text="用户名").grid(row=0, column=0, sticky="w", pady=5)
        username = ttk.Entry(form, width=34)
        username.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        username.insert(0, "admin")
        ttk.Label(form, text="密码").grid(row=2, column=0, sticky="w", pady=5)
        password = ttk.Entry(form, width=34, show="*")
        password.grid(row=3, column=0, sticky="ew")
        password.insert(0, "admin123")

        ttk.Label(
            panel,
            text="管理员：admin / admin123\n运维人员：operator / operator123\n只读用户：viewer / viewer123",
            justify="left",
        ).pack(anchor="w", pady=14)

        def submit(_event=None):
            user = self.store.authenticate(username.get(), password.get())
            if not user:
                messagebox.showerror("登录失败", "用户名或密码错误，或用户已停用。", parent=dialog)
                return
            self.user = user
            dialog.destroy()
            self.build_window()
            self.root.deiconify()

        ttk.Button(panel, text="登录", command=submit).pack(fill="x", pady=(2, 0))
        password.bind("<Return>", submit)
        dialog.bind("<Return>", submit)
        dialog.grab_set()
        username.focus_set()
        self.root.wait_window(dialog)

    def build_window(self):
        header = tk.Frame(self.root, bg="#15263d", height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="智慧园区实时能耗与环境监测",
            bg="#15263d",
            fg="white",
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(side="left", padx=18)
        role = ROLE_NAMES[self.user["role_code"]]
        tk.Label(
            header,
            text=f"{self.user['display_name']}（{role}）",
            bg="#15263d",
            fg="#dce7f4",
        ).pack(side="right", padx=16)
        ttk.Button(header, text="退出", command=self.close).pack(
            side="right", padx=4, pady=10
        )

        notebook = ttk.Notebook(self.root)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        devices_page = ttk.Frame(notebook, padding=10)
        metrics_page = ttk.Frame(notebook, padding=10)
        notebook.add(devices_page, text="设备档案")
        notebook.add(metrics_page, text="指标定义")
        self.build_devices(devices_page)
        self.build_metrics(metrics_page)
        self.build_ingest_page(notebook)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ingest_page(self, notebook):
        page = ttk.Frame(notebook, padding=10)
        notebook.add(page, text="数据接入")
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 8))
        ingest_state = (
            "normal" if self.user["role_code"] in ("ADMIN", "OPERATOR") else "disabled"
        )
        self.start_button = ttk.Button(
            toolbar, text="启动模拟器", command=self.start_simulator, state=ingest_state
        )
        self.start_button.pack(side="left", padx=(0, 5))
        self.stop_button = ttk.Button(
            toolbar,
            text="停止模拟器",
            command=self.stop_simulator,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=5)
        ttk.Label(toolbar, text="采集间隔（秒）").pack(side="left", padx=(14, 4))
        self.interval_var = tk.StringVar(value="2")
        interval_input = ttk.Spinbox(
            toolbar, from_=1, to=60, width=5, textvariable=self.interval_var
        )
        interval_input.pack(side="left")
        if ingest_state == "disabled":
            interval_input.configure(state="disabled")
        ttk.Button(
            toolbar,
            text="导入 JSON / JSONL",
            command=self.import_file,
            state=ingest_state,
        ).pack(side="left", padx=14)
        self.ingest_status = tk.StringVar(value="模拟器已停止")
        ttk.Label(page, textvariable=self.ingest_status).pack(anchor="w", pady=(0, 8))

        columns = ("received", "device", "metric", "value", "unit", "event_time")
        self.event_tree = ttk.Treeview(page, columns=columns, show="headings")
        headings = ("接收时间", "设备编号", "指标编码", "数值", "单位", "事件时间")
        widths = (180, 140, 130, 100, 100, 210)
        for column, heading, width in zip(columns, headings, widths):
            self.event_tree.heading(column, text=heading)
            self.event_tree.column(column, width=width, anchor="center")
        ybar = ttk.Scrollbar(page, orient="vertical", command=self.event_tree.yview)
        self.event_tree.configure(yscrollcommand=ybar.set)
        self.event_tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        self.refresh_events()
        self.root.after(100, self.pump_event_queue)

    def refresh_events(self):
        if not hasattr(self, "event_tree"):
            return
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)
        for event in self.store.list_recent_events():
            self.event_tree.insert(
                "",
                "end",
                values=(
                    event["received_at"],
                    event["device_code"],
                    event["metric_code"],
                    event["metric_value"],
                    event["unit"],
                    event["event_time"],
                ),
            )

    def start_simulator(self):
        if self.sim_thread and self.sim_thread.is_alive():
            return
        self.simulator = TelemetrySimulator(self.store)
        if not self.simulator.profiles:
            messagebox.showwarning(
                "无法启动", "没有启用的设备和指标可供模拟。", parent=self.root
            )
            return
        try:
            interval = float(self.interval_var.get())
            if not 1 <= interval <= 60:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "输入无效", "采集间隔须为 1 到 60 秒。", parent=self.root
            )
            return
        self.sim_stop_event = threading.Event()
        self.sim_thread = threading.Thread(
            target=self.simulator.produce,
            args=(self.sim_stop_event, self.event_queue, interval),
            daemon=True,
        )
        self.sim_thread.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.ingest_status.set("模拟器运行中，遥测事件已进入处理队列")

    def stop_simulator(self):
        if self.sim_stop_event:
            self.sim_stop_event.set()
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=1)
        self.sim_stop_event = None
        self.sim_thread = None
        if hasattr(self, "start_button"):
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.ingest_status.set("模拟器已停止")

    def pump_event_queue(self):
        if not self.root.winfo_exists():
            return
        results = self.processor.process_pending()
        if results:
            accepted = sum(result["status"] == "OK" for result in results)
            invalid = sum(result["status"] == "INVALID" for result in results)
            duplicates = sum(result["status"] == "DUPLICATE" for result in results)
            self.ingest_status.set(
                f"队列处理 {len(results)} 条：入库 {accepted}，无效 {invalid}，重复 {duplicates}；"
                f"异常记录 {self.store.count_ingest_errors()}"
            )
            self.refresh_events()
        self.root.after(100, self.pump_event_queue)

    def import_file(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择遥测 JSON / JSONL 文件",
            filetypes=(("遥测文件", "*.json *.jsonl *.ndjson"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            results = self.store.import_file(path)
        except (OSError, UnicodeError, sqlite3.Error) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)
            return
        accepted = sum(result["status"] == "OK" for result in results)
        invalid = sum(result["status"] == "INVALID" for result in results)
        duplicates = sum(result["status"] == "DUPLICATE" for result in results)
        self.ingest_status.set(
            f"文件导入完成 {len(results)} 条：入库 {accepted}，无效 {invalid}，重复 {duplicates}"
        )
        self.refresh_events()

    def build_devices(self, page):
        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 8))
        editable = self.user["role_code"] in ("ADMIN", "OPERATOR")
        state = "normal" if editable else "disabled"
        ttk.Button(toolbar, text="新增设备", command=self.add_device, state=state).pack(
            side="left", padx=(0, 5)
        )
        ttk.Button(toolbar, text="编辑设备", command=self.edit_device, state=state).pack(
            side="left", padx=5
        )
        ttk.Button(
            toolbar, text="启用/停用设备", command=self.toggle_device, state=state
        ).pack(side="left", padx=5)

        columns = ("code", "name", "type", "area", "location", "enabled")
        self.device_tree = ttk.Treeview(page, columns=columns, show="headings")
        headings = ("设备编号", "设备名称", "设备类型", "所属区域", "安装位置", "状态")
        widths = (140, 180, 130, 130, 220, 80)
        for column, heading, width in zip(columns, headings, widths):
            self.device_tree.heading(column, text=heading)
            self.device_tree.column(column, width=width, anchor="center")
        ybar = ttk.Scrollbar(page, orient="vertical", command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=ybar.set)
        self.device_tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        self.refresh_devices()

    def build_metrics(self, page):
        columns = ("code", "name", "unit", "minimum", "maximum", "enabled")
        tree = ttk.Treeview(page, columns=columns, show="headings")
        headings = ("指标编码", "指标名称", "单位", "最小值", "最大值", "状态")
        widths = (150, 180, 130, 120, 120, 80)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="center")
        for metric in self.store.list_metrics():
            tree.insert(
                "",
                "end",
                values=(
                    metric["metric_code"],
                    metric["metric_name"],
                    metric["unit"],
                    "不限" if metric["min_value"] is None else metric["min_value"],
                    "不限" if metric["max_value"] is None else metric["max_value"],
                    "启用" if metric["enabled"] else "停用",
                ),
            )
        tree.pack(fill="both", expand=True)

    def refresh_devices(self):
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        for device in self.store.list_devices():
            self.device_tree.insert(
                "",
                "end",
                iid=device["device_code"],
                values=(
                    device["device_code"],
                    device["device_name"],
                    device["device_type"],
                    device["area_code"],
                    device["location_desc"],
                    "启用" if device["enabled"] else "停用",
                ),
            )

    def selected_device(self):
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一台设备。", parent=self.root)
            return None
        return next(
            device
            for device in self.store.list_devices()
            if device["device_code"] == selected[0]
        )

    def edit_device(self):
        device = self.selected_device()
        if device:
            self.device_dialog(device)

    def add_device(self):
        self.device_dialog()

    def device_dialog(self, device=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑设备" if device else "新增设备")
        dialog.transient(self.root)
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=16)
        panel.pack(fill="both", expand=True)
        fields = (
            ("device_code", "设备编号"),
            ("device_name", "设备名称"),
            ("device_type", "设备类型"),
            ("area_code", "所属区域"),
            ("location_desc", "安装位置"),
        )
        entries = {}
        for row, (key, label) in enumerate(fields):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(panel, width=36)
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
            entry.insert(0, (device or {}).get(key, ""))
            if device and key == "device_code":
                entry.configure(state="readonly")
            entries[key] = entry

        def save():
            data = {key: entry.get() for key, entry in entries.items()}
            data["is_edit"] = bool(device)
            try:
                self.store.save_device(data)
            except (TypeError, ValueError) as exc:
                messagebox.showerror("保存失败", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.refresh_devices()

        buttons = ttk.Frame(panel)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=4)
        panel.columnconfigure(1, weight=1)

    def toggle_device(self):
        device = self.selected_device()
        if not device:
            return
        try:
            self.store.set_device_enabled(
                device["device_code"], not bool(device["enabled"])
            )
        except (TypeError, ValueError) as exc:
            messagebox.showerror("操作失败", str(exc), parent=self.root)
            return
        self.refresh_devices()

    def close(self):
        self.stop_simulator()
        self.store.close()
        self.root.destroy()
