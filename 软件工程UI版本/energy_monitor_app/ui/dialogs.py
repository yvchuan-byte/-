import tkinter as tk
from tkinter import messagebox, ttk

from energy_monitor_app.config.constants import OPERATOR_LABELS, OPERATOR_REVERSE, ROLE_LABELS, SEVERITY_LABELS
from energy_monitor_app.core.time_utils import display_time


class LoginDialog:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("智慧园区监测系统 - 登录")
        self.win.geometry("420x330")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", app.root.destroy)
        self.win.grab_set()

        frame = ttk.Frame(self.win, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="智慧园区实时监测系统",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(pady=(4, 20))

        self.username = tk.StringVar(value="admin")
        self.password = tk.StringVar(value="admin123")

        ttk.Label(frame, text="用户名").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.username).pack(fill="x", pady=(4, 12))
        ttk.Label(frame, text="密码").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.password, show="*").pack(
            fill="x", pady=(4, 16)
        )
        ttk.Button(frame, text="登录", command=self.login).pack(fill="x", pady=4)

        ttk.Label(
            frame,
            text="实验账号：admin / admin123\n"
                 "运维账号：operator / operator123\n"
                 "只读账号：viewer / viewer123",
            justify="left",
            foreground="#666666",
        ).pack(anchor="w", pady=(12, 0))

        self.win.bind("<Return>", lambda _event: self.login())

    def login(self):
        user = self.app.backend.authenticate(
            self.username.get(), self.password.get()
        )
        if not user:
            messagebox.showerror("登录失败", "用户名或密码错误，或用户已停用。", parent=self.win)
            return
        self.win.destroy()
        self.app.login_succeeded(user)


class DeviceDialog:
    def __init__(self, parent, backend, actor, device=None, on_saved=None):
        self.backend = backend
        self.actor = actor
        self.device = device
        self.on_saved = on_saved

        self.win = tk.Toplevel(parent)
        self.win.title("编辑设备" if device else "新增设备")
        self.win.geometry("420x360")
        self.win.transient(parent)
        self.win.grab_set()

        data = device or {}
        self.vars = {
            "device_code": tk.StringVar(value=data.get("device_code", "")),
            "device_name": tk.StringVar(value=data.get("device_name", "")),
            "device_type": tk.StringVar(value=data.get("device_type", "")),
            "area_code": tk.StringVar(value=data.get("area_code", "")),
            "location_desc": tk.StringVar(value=data.get("location_desc", "")),
        }
        labels = [
            ("device_code", "设备编号"),
            ("device_name", "设备名称"),
            ("device_type", "设备类型"),
            ("area_code", "所属区域"),
            ("location_desc", "安装位置"),
        ]

        form = ttk.Frame(self.win, padding=18)
        form.pack(fill="both", expand=True)
        for row, (key, label) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=7)
            entry = ttk.Entry(form, textvariable=self.vars[key])
            entry.grid(row=row, column=1, sticky="ew", pady=7)
            if key == "device_code" and device:
                entry.configure(state="readonly")
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form)
        buttons.grid(row=len(labels), column=0, columnspan=2, sticky="e", pady=18)
        ttk.Button(buttons, text="取消", command=self.win.destroy).pack(
            side="right", padx=4
        )
        ttk.Button(buttons, text="保存", command=self.save).pack(side="right", padx=4)

    def save(self):
        data = {key: var.get() for key, var in self.vars.items()}
        try:
            self.backend.save_device(data, self.actor)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.win)
            return
        if self.on_saved:
            self.on_saved()
        self.win.destroy()


class RuleDialog:
    def __init__(self, parent, backend, actor, rule=None, on_saved=None):
        self.backend = backend
        self.actor = actor
        self.rule = rule
        self.on_saved = on_saved

        self.win = tk.Toplevel(parent)
        self.win.title("编辑告警规则" if rule else "新增告警规则")
        self.win.geometry("480x470")
        self.win.transient(parent)
        self.win.grab_set()

        device_codes = ["全部"] + [d["device_code"] for d in backend.list_devices()]
        metric_codes = [m["metric_code"] for m in backend.list_metrics()]
        r = rule or {}

        self.name_var = tk.StringVar(value=r.get("rule_name", ""))
        self.device_var = tk.StringVar(value=r.get("device_code") or "全部")
        self.metric_var = tk.StringVar(value=r.get("metric_code") or "power")
        op = OPERATOR_REVERSE.get(r.get("operator_code", "GT"), ">")
        self.operator_var = tk.StringVar(value=op)
        self.threshold_var = tk.StringVar(
            value=str(r.get("threshold_value", 100))
        )
        self.upper_var = tk.StringVar(
            value="" if r.get("threshold_upper") is None
            else str(r.get("threshold_upper"))
        )
        self.count_var = tk.StringVar(value=str(r.get("consecutive_count", 3)))
        self.severity_var = tk.StringVar(value=str(r.get("severity", 1)))
        self.cooldown_var = tk.StringVar(value=str(r.get("cooldown_seconds", 300)))

        form = ttk.Frame(self.win, padding=18)
        form.pack(fill="both", expand=True)

        def add_row(index, label, widget):
            ttk.Label(form, text=label).grid(
                row=index, column=0, sticky="w", padx=(0, 12), pady=7
            )
            widget.grid(row=index, column=1, sticky="ew", pady=7)

        add_row(0, "规则名称", ttk.Entry(form, textvariable=self.name_var))
        add_row(
            1, "适用设备",
            ttk.Combobox(
                form, textvariable=self.device_var, values=device_codes,
                state="readonly",
            ),
        )
        add_row(
            2, "指标编码",
            ttk.Combobox(
                form, textvariable=self.metric_var, values=metric_codes,
                state="readonly",
            ),
        )
        add_row(
            3, "比较方式",
            ttk.Combobox(
                form, textvariable=self.operator_var,
                values=list(OPERATOR_LABELS.keys()), state="readonly",
            ),
        )
        add_row(4, "阈值/区间下限", ttk.Entry(form, textvariable=self.threshold_var))
        add_row(5, "区间上限", ttk.Entry(form, textvariable=self.upper_var))
        add_row(6, "连续触发次数", ttk.Entry(form, textvariable=self.count_var))
        add_row(
            7, "告警级别 (1最高)",
            ttk.Combobox(
                form, textvariable=self.severity_var,
                values=["1", "2", "3", "4"], state="readonly",
            ),
        )
        add_row(8, "冷却秒数", ttk.Entry(form, textvariable=self.cooldown_var))

        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(form)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e", pady=18)
        ttk.Button(buttons, text="取消", command=self.win.destroy).pack(
            side="right", padx=4
        )
        ttk.Button(buttons, text="保存", command=self.save).pack(side="right", padx=4)

    def save(self):
        try:
            operator = OPERATOR_LABELS[self.operator_var.get()]
            data = {
                "rule_name": self.name_var.get(),
                "device_code": (
                    None if self.device_var.get() == "全部" else self.device_var.get()
                ),
                "metric_code": self.metric_var.get(),
                "operator_code": operator,
                "threshold_value": float(self.threshold_var.get()),
                "threshold_upper": self.upper_var.get(),
                "consecutive_count": int(self.count_var.get()),
                "severity": int(self.severity_var.get()),
                "cooldown_seconds": int(self.cooldown_var.get()),
            }
            self.backend.save_rule(
                self.rule.get("rule_id") if self.rule else None,
                data,
                self.actor,
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.win)
            return

        if self.on_saved:
            self.on_saved()
        self.win.destroy()


class UserDialog:
    def __init__(self, parent, backend, actor, on_saved=None):
        self.backend = backend
        self.actor = actor
        self.on_saved = on_saved

        self.win = tk.Toplevel(parent)
        self.win.title("新增用户")
        self.win.geometry("400x330")
        self.win.transient(parent)
        self.win.grab_set()

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.display_name = tk.StringVar()
        self.role = tk.StringVar(value="OPERATOR")

        form = ttk.Frame(self.win, padding=18)
        form.pack(fill="both", expand=True)
        rows = [
            ("用户名", ttk.Entry(form, textvariable=self.username)),
            ("初始密码", ttk.Entry(form, textvariable=self.password, show="*")),
            ("显示名称", ttk.Entry(form, textvariable=self.display_name)),
            (
                "角色",
                ttk.Combobox(
                    form, textvariable=self.role,
                    values=list(ROLE_LABELS.keys()), state="readonly",
                ),
            ),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=8)
            widget.grid(row=i, column=1, sticky="ew", pady=8)
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=15)
        ttk.Button(buttons, text="取消", command=self.win.destroy).pack(
            side="right", padx=4
        )
        ttk.Button(buttons, text="保存", command=self.save).pack(side="right", padx=4)

    def save(self):
        try:
            self.backend.add_user(
                self.username.get(),
                self.password.get(),
                self.display_name.get(),
                self.role.get(),
                self.actor,
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.win)
            return
        if self.on_saved:
            self.on_saved()
        self.win.destroy()
