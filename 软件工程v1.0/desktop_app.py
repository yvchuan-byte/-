import tkinter as tk
from tkinter import messagebox, ttk

from v1_store import V1Store


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
        self.store = V1Store(database_path)
        self.user = None
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
        ttk.Label(panel, text="园区能耗与环境监测平台").pack(anchor="w", pady=(4, 18))

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
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        devices_page = ttk.Frame(notebook, padding=10)
        metrics_page = ttk.Frame(notebook, padding=10)
        notebook.add(devices_page, text="设备档案")
        notebook.add(metrics_page, text="指标定义")
        self.build_devices(devices_page)
        self.build_metrics(metrics_page)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

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
        self.store.close()
        self.root.destroy()
