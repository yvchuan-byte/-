from monitor_service import (
    OPERATOR_LABELS, OPERATOR_REVERSE, ROLE_LABELS, SEVERITY_LABELS,
    MonitorBackend, display_time, utc_iso, utc_now,
)

# ui/widgets.py
import tkinter as tk
from tkinter import ttk


def make_tree(parent, columns, headings, widths=None, height=10):
    box = ttk.Frame(parent)
    box.pack(fill="both", expand=True)
    tree = ttk.Treeview(box, columns=columns, show="headings", height=height)
    widths = widths or {}
    for col, heading in zip(columns, headings):
        tree.heading(col, text=heading)
        tree.column(col, width=widths.get(col, 120), anchor="center")
    ybar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    ybar.grid(row=0, column=1, sticky="ns")
    xbar.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)
    return tree


# ui/dialogs.py
import tkinter as tk
from tkinter import messagebox, ttk



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


# ui/dashboard_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class DashboardViewMixin:
    def build_dashboard_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="实时大屏")

        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(0, 8))

        self.start_button = ttk.Button(
            controls, text="启动模拟器", command=self.start_simulator
        )
        self.start_button.pack(side="left", padx=3)
        self.stop_button = ttk.Button(
            controls, text="停止模拟器", command=self.stop_simulator
        )
        self.stop_button.pack(side="left", padx=3)
        ttk.Label(controls, text="采集间隔（秒）").pack(side="left", padx=(15, 4))
        self.interval_var = tk.StringVar(value="5")
        ttk.Spinbox(
            controls, from_=1, to=60, width=5, textvariable=self.interval_var
        ).pack(side="left")
        self.demo_button = ttk.Button(
            controls, text="注入四点告警样例", command=self.run_demo
        )
        self.demo_button.pack(side="left", padx=12)
        self.sample_button = ttk.Button(
            controls,
            text="当前指标采样",
            command=self.inject_selected_sample,
        )
        self.sample_button.pack(side="left", padx=3)

        if self.is_admin:
            ttk.Button(
                controls, text="清空实验数据", command=self.clear_telemetry
            ).pack(side="left", padx=3)

        self.sim_status_label = ttk.Label(controls, text="模拟器：已停止")
        self.sim_status_label.pack(side="right", padx=6)
        self.sim_coverage_var = tk.StringVar(value="模拟器将采集所有启用设备支持的指标")
        ttk.Label(page, textvariable=self.sim_coverage_var, foreground="#365c83").pack(
            anchor="w", pady=(0, 3)
        )

        if not self.can_operate:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self.demo_button.configure(state="disabled")
            self.sample_button.configure(state="disabled")

        cards = ttk.Frame(page)
        cards.pack(fill="x", pady=4)
        self.kpi_vars = {
            "today": tk.StringVar(value="0"),
            "online": tk.StringVar(value="0/0"),
            "alerts": tk.StringVar(value="0"),
            "dlq": tk.StringVar(value="0"),
        }
        card_data = [
            ("今日接收数据", self.kpi_vars["today"]),
            ("在线设备", self.kpi_vars["online"]),
            ("活动告警", self.kpi_vars["alerts"]),
            ("异常数据", self.kpi_vars["dlq"]),
        ]
        for i, (title, variable) in enumerate(card_data):
            box = ttk.LabelFrame(cards, text=title, padding=10)
            box.grid(row=0, column=i, sticky="nsew", padx=5)
            ttk.Label(box, textvariable=variable, font=("Arial", 18, "bold")).pack()
            cards.columnconfigure(i, weight=1)

        selector = ttk.Frame(page)
        selector.pack(fill="x", pady=(6, 3))
        ttk.Label(selector, text="设备").pack(side="left")
        self.chart_device_var = tk.StringVar(value="POWER-A-01")
        self.chart_device_combo = ttk.Combobox(
            selector, textvariable=self.chart_device_var, state="readonly", width=20
        )
        self.chart_device_combo.pack(side="left", padx=5)
        self.chart_device_combo.bind(
            "<<ComboboxSelected>>", self.on_chart_device_selected
        )

        ttk.Label(selector, text="指标").pack(side="left", padx=(12, 0))
        self.chart_metric_var = tk.StringVar(value="power")
        self.chart_metric_combo = ttk.Combobox(
            selector, textvariable=self.chart_metric_var, state="readonly", width=16
        )
        self.chart_metric_combo.pack(side="left", padx=5)
        self.chart_metric_combo.bind(
            "<<ComboboxSelected>>", self.on_chart_metric_selected
        )
        ttk.Label(
            selector,
            text="先选设备；指标列表仅显示该设备支持的数据",
            foreground="#64748b",
        ).pack(side="left", padx=8)

        self.aggregate_var = tk.StringVar(value="最近一分钟统计：暂无数据")
        ttk.Label(
            selector, textvariable=self.aggregate_var, foreground="#365c83"
        ).pack(side="left", padx=18)

        self.chart = tk.Canvas(
            page, height=270, bg="#101827", highlightthickness=0
        )
        self.chart.pack(fill="x", expand=False, pady=5)

        ttk.Label(page, text="最新遥测数据").pack(anchor="w", pady=(6, 2))
        live_frame = ttk.Frame(page)
        live_frame.pack(fill="both", expand=True)
        self.live_tree = make_tree(
            live_frame,
            ("time", "device", "name", "metric", "value", "unit", "quality"),
            ("采集时间", "设备编号", "设备名称", "指标", "数值", "单位", "质量"),
            widths={
                "time": 160, "device": 130, "name": 160,
                "metric": 100, "value": 90, "unit": 75, "quality": 80,
            },
            height=8,
        )

    def refresh_dashboard(self):
        stats = self.backend.stats()
        self.kpi_vars["today"].set(str(stats["today_samples"]))
        self.kpi_vars["online"].set(
            f"{stats['online_devices']}/{stats['total_devices']}"
        )
        self.kpi_vars["alerts"].set(str(stats["active_alerts"]))
        self.kpi_vars["dlq"].set(str(stats["invalid_messages"]))

        profiles = self.backend.simulator.profiles()
        self.device_metric_map = {
            profile["device_code"]: [
                metric["metric_code"] for metric in profile["metrics"]
            ]
            for profile in profiles
        }
        device_codes = list(self.device_metric_map)
        if device_codes:
            self.chart_device_combo["values"] = device_codes
            if self.chart_device_var.get() not in device_codes:
                self.chart_device_var.set(
                    "POWER-A-01" if "POWER-A-01" in device_codes else device_codes[0]
                )

        metric_codes = [
            metric["metric_code"]
            for metric in self.backend.list_metrics()
            if metric["enabled"]
        ]
        self.chart_metric_combo["values"] = metric_codes
        if metric_codes and self.chart_metric_var.get() not in metric_codes:
            self.chart_metric_var.set(metric_codes[0])
        metric_count = sum(len(items) for items in self.device_metric_map.values())
        self.sim_coverage_var.set(
            f"模拟覆盖：{len(device_codes)} 台启用设备、{metric_count} 个设备指标组合；"
            "启动后每个采集周期均会上报"
        )

        device_code = self.chart_device_var.get()
        metric_code = self.chart_metric_var.get()
        aggregate = self.backend.latest_aggregate(device_code, metric_code)
        if aggregate:
            self.aggregate_var.set(
                "最近一分钟统计："
                f"均值 {aggregate['avg_value']:.2f}，"
                f"最小 {aggregate['min_value']:.2f}，"
                f"最大 {aggregate['max_value']:.2f}，"
                f"样本数 {aggregate['sample_count']}"
            )
        else:
            self.aggregate_var.set("最近一分钟统计：暂无数据")

        rows = self.backend.latest_events(40)
        for iid in self.live_tree.get_children():
            self.live_tree.delete(iid)
        for row in rows:
            quality = "迟到数据" if row["quality_status"] else "正常"
            self.live_tree.insert(
                "", "end",
                values=(
                    display_time(row["event_time"]),
                    row["device_code"],
                    row.get("device_name") or "",
                    row["metric_code"],
                    f"{row['metric_value']:g}",
                    row["unit"],
                    quality,
                ),
            )
        self.draw_chart()

    def update_chart_metrics(self):
        metrics = [
            metric["metric_code"]
            for metric in self.backend.list_metrics()
            if metric["enabled"]
        ]
        self.chart_metric_combo["values"] = metrics
        if metrics and self.chart_metric_var.get() not in metrics:
            self.chart_metric_var.set(metrics[0])

    def on_chart_device_selected(self, _event=None):
        self.draw_chart()

    def on_chart_metric_selected(self, _event=None):
        metric_code = self.chart_metric_var.get()
        if metric_code not in self.device_metric_map.get(
            self.chart_device_var.get(), []
        ):
            device_code = next(
                (
                    code for code, metrics in self.device_metric_map.items()
                    if metric_code in metrics
                ),
                None,
            )
            if device_code is not None:
                self.chart_device_var.set(device_code)
        self.draw_chart()

    def draw_chart(self):
        if not hasattr(self, "chart"):
            return

        canvas = self.chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 220)

        left, right, top, bottom = 60, width - 24, 22, height - 36
        canvas.create_text(
            12, 10, anchor="nw", fill="#cbd5e1",
            text=f"{self.chart_device_var.get()} / {self.chart_metric_var.get()}",
            font=("Microsoft YaHei UI", 10, "bold"),
        )

        rows = self.backend.query_history(
            device_code=self.chart_device_var.get(),
            metric_code=self.chart_metric_var.get(),
            limit=30,
        )
        rows = sorted(rows, key=lambda r: r["event_time"])

        if not rows:
            canvas.create_text(
                width // 2, height // 2,
                text="暂无数据，请启动模拟器或注入演示样例",
                fill="#cbd5e1",
                font=("Microsoft YaHei UI", 12),
            )
            return

        values = [float(r["metric_value"]) for r in rows]
        thresholds = [
            float(r["threshold_value"])
            for r in self.backend.list_rules()
            if r["enabled"]
            and r["metric_code"] == self.chart_metric_var.get()
            and r["operator_code"] in ("GT", "GE")
            and r["device_code"] in (None, self.chart_device_var.get())
        ]
        all_values = values + thresholds
        low, high = min(all_values), max(all_values)
        if high == low:
            low -= 1
            high += 1
        padding = (high - low) * 0.12
        low -= padding
        high += padding

        for i in range(5):
            y = top + (bottom - top) * i / 4
            val = high - (high - low) * i / 4
            canvas.create_line(left, y, right, y, fill="#263449")
            canvas.create_text(
                left - 8, y, anchor="e",
                text=f"{val:.1f}", fill="#94a3b8", font=("Arial", 8),
            )

        if thresholds:
            threshold = thresholds[0]
            y = bottom - (threshold - low) / (high - low) * (bottom - top)
            canvas.create_line(
                left, y, right, y, fill="#f97316", dash=(6, 4), width=2
            )
            canvas.create_text(
                right - 2, y - 8, anchor="e",
                text=f"阈值 {threshold:g}", fill="#fb923c",
            )

        points = []
        count = len(values)
        for i, value in enumerate(values):
            x = left if count == 1 else left + (right - left) * i / (count - 1)
            y = bottom - (value - low) / (high - low) * (bottom - top)
            points.extend((x, y))

        if len(points) >= 4:
            canvas.create_line(*points, fill="#38bdf8", width=2, smooth=True)
        for i, value in enumerate(values):
            x = left if count == 1 else left + (right - left) * i / (count - 1)
            y = bottom - (value - low) / (high - low) * (bottom - top)
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#7dd3fc", outline="")
        for index in (0, count // 2, count - 1):
            if 0 <= index < count:
                x = left if count == 1 else left + (right - left) * index / (count - 1)
                label = display_time(rows[index]["event_time"])[11:19]
                canvas.create_text(
                    x, bottom + 14, text=label,
                    fill="#94a3b8", font=("Arial", 8),
                )


# ui/device_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class DeviceViewMixin:
    def build_device_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="设备与指标")

        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 6))
        state = "normal" if self.can_operate else "disabled"
        ttk.Button(toolbar, text="新增设备", command=self.add_device, state=state).pack(
            side="left", padx=3
        )
        ttk.Button(toolbar, text="编辑设备", command=self.edit_device, state=state).pack(
            side="left", padx=3
        )
        ttk.Button(
            toolbar, text="启用/停用设备",
            command=self.toggle_device, state=state,
        ).pack(side="left", padx=3)

        split = ttk.Panedwindow(page, orient="vertical")
        split.pack(fill="both", expand=True)

        device_box = ttk.LabelFrame(split, text="设备信息", padding=5)
        metric_box = ttk.LabelFrame(split, text="指标定义", padding=5)
        split.add(device_box, weight=3)
        split.add(metric_box, weight=2)

        self.device_tree = make_tree(
            device_box,
            ("code", "name", "type", "area", "location", "status", "last_seen"),
            ("设备编号", "设备名称", "设备类型", "所属区域", "安装位置", "状态", "最后上报"),
            widths={
                "code": 130, "name": 170, "type": 120, "area": 110,
                "location": 170, "status": 80, "last_seen": 160,
            },
        )
        self.metric_tree = make_tree(
            metric_box,
            ("code", "name", "unit", "range", "enabled"),
            ("指标编码", "指标名称", "单位", "允许范围", "启用"),
            widths={"code": 140, "name": 140, "unit": 100, "range": 200, "enabled": 80},
        )

    def refresh_devices(self):
        devices = self.backend.list_devices()
        for iid in self.device_tree.get_children():
            self.device_tree.delete(iid)
        for d in devices:
            self.device_tree.insert(
                "", "end", iid=d["device_code"],
                values=(
                    d["device_code"], d["device_name"], d["device_type"],
                    d["area_code"], d["location_desc"], d["status_label"],
                    display_time(d["last_seen_at"]),
                ),
            )

        for iid in self.metric_tree.get_children():
            self.metric_tree.delete(iid)
        for m in self.backend.list_metrics():
            minimum = "-∞" if m["min_value"] is None else f"{m['min_value']:g}"
            maximum = "+∞" if m["max_value"] is None else f"{m['max_value']:g}"
            self.metric_tree.insert(
                "", "end",
                values=(
                    m["metric_code"], m["metric_name"], m["unit"],
                    f"{minimum} ～ {maximum}",
                    "是" if m["enabled"] else "否",
                ),
            )

        codes = ["全部"] + [d["device_code"] for d in devices]
        if hasattr(self, "history_device_combo"):
            self.history_device_combo["values"] = codes
        metrics = ["全部"] + [m["metric_code"] for m in self.backend.list_metrics()]
        if hasattr(self, "history_metric_combo"):
            self.history_metric_combo["values"] = metrics

    def add_device(self):
        DeviceDialog(
            self.root, self.backend, self.user["username"],
            on_saved=self.refresh_all,
        )

    def edit_device(self):
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择设备。", parent=self.root)
            return
        code = selected[0]
        device = next(
            (d for d in self.backend.list_devices() if d["device_code"] == code), None
        )
        if device:
            DeviceDialog(
                self.root, self.backend, self.user["username"],
                device=device, on_saved=self.refresh_all,
            )

    def toggle_device(self):
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择设备。", parent=self.root)
            return
        code = selected[0]
        device = next(
            (d for d in self.backend.list_devices() if d["device_code"] == code), None
        )
        if not device:
            return
        enabled = not bool(device["enabled"])
        try:
            self.backend.set_device_enabled(code, enabled, self.user["username"])
        except Exception as exc:
            messagebox.showerror("操作失败", str(exc), parent=self.root)
        self.refresh_all()


# ui/history_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class HistoryViewMixin:
    def build_history_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="历史查询")

        filters = ttk.Frame(page)
        filters.pack(fill="x", pady=(0, 8))

        ttk.Label(filters, text="设备").grid(row=0, column=0, padx=3, pady=4)
        self.history_device_var = tk.StringVar(value="全部")
        self.history_device_combo = ttk.Combobox(
            filters, textvariable=self.history_device_var, state="readonly", width=18
        )
        self.history_device_combo.grid(row=0, column=1, padx=3, pady=4)

        ttk.Label(filters, text="指标").grid(row=0, column=2, padx=3, pady=4)
        self.history_metric_var = tk.StringVar(value="全部")
        self.history_metric_combo = ttk.Combobox(
            filters, textvariable=self.history_metric_var, state="readonly", width=14
        )
        self.history_metric_combo.grid(row=0, column=3, padx=3, pady=4)

        now = datetime.now()
        self.history_start_var = tk.StringVar(
            value=now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        )
        self.history_end_var = tk.StringVar(value=now.strftime("%Y-%m-%d %H:%M:%S"))

        ttk.Label(filters, text="开始时间").grid(row=0, column=4, padx=3, pady=4)
        ttk.Entry(filters, textvariable=self.history_start_var, width=20).grid(
            row=0, column=5, padx=3, pady=4
        )
        ttk.Label(filters, text="结束时间").grid(row=0, column=6, padx=3, pady=4)
        ttk.Entry(filters, textvariable=self.history_end_var, width=20).grid(
            row=0, column=7, padx=3, pady=4
        )

        ttk.Button(filters, text="查询", command=self.search_history).grid(
            row=0, column=8, padx=5
        )
        ttk.Button(filters, text="导出 CSV", command=self.export_history).grid(
            row=0, column=9, padx=5
        )

        table = ttk.Frame(page)
        table.pack(fill="both", expand=True)
        self.history_tree = make_tree(
            table,
            ("time", "device", "name", "metric", "value", "unit", "quality"),
            ("采集时间", "设备编号", "设备名称", "指标", "数值", "单位", "质量状态"),
            widths={
                "time": 170, "device": 130, "name": 160, "metric": 100,
                "value": 100, "unit": 80, "quality": 100,
            },
        )

    def search_history(self):
        try:
            self.history_rows = self.backend.query_history(
                device_code=self.history_device_var.get(),
                metric_code=self.history_metric_var.get(),
                start=self.history_start_var.get(),
                end=self.history_end_var.get(),
                limit=5000,
            )
        except Exception as exc:
            messagebox.showerror(
                "查询失败",
                f"时间格式请使用 YYYY-MM-DD HH:MM:SS。\n{exc}",
                parent=self.root,
            )
            return

        for iid in self.history_tree.get_children():
            self.history_tree.delete(iid)
        for row in self.history_rows:
            quality = "迟到数据" if row["quality_status"] else "正常"
            self.history_tree.insert(
                "", "end",
                values=(
                    display_time(row["event_time"]), row["device_code"],
                    row.get("device_name") or "", row["metric_code"],
                    f"{row['metric_value']:g}", row["unit"], quality,
                ),
            )
        self.status_var.set(f"历史查询完成，共 {len(self.history_rows)} 条")

    def export_history(self):
        if not self.history_rows:
            self.search_history()
        if not self.history_rows:
            messagebox.showinfo("导出", "当前没有可导出的查询结果。", parent=self.root)
            return

        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出历史数据",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile="telemetry_history.csv",
        )
        if not filename:
            return

        with open(filename, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(
                ["事件编号", "设备编号", "设备名称", "区域", "指标",
                 "数值", "单位", "采集时间", "接收时间", "质量状态"]
            )
            for row in self.history_rows:
                writer.writerow(
                    [
                        row["event_id"], row["device_code"],
                        row.get("device_name", ""), row.get("area_code", ""),
                        row["metric_code"], row["metric_value"], row["unit"],
                        row["event_time"], row["ingest_time"],
                        row["quality_status"],
                    ]
                )
        messagebox.showinfo("导出完成", f"已导出到：\n{filename}", parent=self.root)


# ui/alert_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class AlertViewMixin:
    def build_alert_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="告警与规则")

        split = ttk.Panedwindow(page, orient="vertical")
        split.pack(fill="both", expand=True)

        alarm_box = ttk.LabelFrame(split, text="告警记录", padding=6)
        rule_box = ttk.LabelFrame(split, text="告警规则", padding=6)
        split.add(alarm_box, weight=3)
        split.add(rule_box, weight=2)

        alarm_toolbar = ttk.Frame(alarm_box)
        alarm_toolbar.pack(fill="x", pady=(0, 5))
        ack_state = "normal" if self.can_operate else "disabled"
        ttk.Button(
            alarm_toolbar, text="确认选中告警",
            command=self.acknowledge_selected, state=ack_state,
        ).pack(side="left", padx=3)
        ttk.Button(
            alarm_toolbar, text="刷新", command=self.refresh_alerts
        ).pack(side="left", padx=3)

        self.alert_tree = make_tree(
            alarm_box,
            ("rule", "device", "metric", "value", "severity", "status", "triggered", "ack"),
            ("规则名称", "设备", "指标", "触发值", "级别", "状态", "触发时间", "确认人"),
            widths={
                "rule": 190, "device": 125, "metric": 90, "value": 90,
                "severity": 75, "status": 85, "triggered": 160, "ack": 100,
            },
        )

        rule_toolbar = ttk.Frame(rule_box)
        rule_toolbar.pack(fill="x", pady=(0, 5))
        rule_state = "normal" if self.can_operate else "disabled"
        ttk.Button(
            rule_toolbar, text="新增规则", command=self.add_rule, state=rule_state
        ).pack(side="left", padx=3)
        ttk.Button(
            rule_toolbar, text="编辑规则", command=self.edit_rule, state=rule_state
        ).pack(side="left", padx=3)
        ttk.Button(
            rule_toolbar, text="启用/停用规则",
            command=self.toggle_rule, state=rule_state,
        ).pack(side="left", padx=3)

        self.rule_tree = make_tree(
            rule_box,
            ("id", "name", "device", "metric", "operator", "threshold",
             "count", "severity", "enabled"),
            ("编号", "规则名称", "适用设备", "指标", "条件", "阈值",
             "连续次数", "级别", "启用"),
            widths={
                "id": 55, "name": 190, "device": 125, "metric": 90,
                "operator": 70, "threshold": 110, "count": 80,
                "severity": 70, "enabled": 65,
            },
        )

    def refresh_alerts(self):
        if not hasattr(self, "alert_tree"):
            return

        for iid in self.alert_tree.get_children():
            self.alert_tree.delete(iid)
        for a in self.backend.list_alerts():
            ack_name = a.get("acknowledged_name") or a.get("acknowledged_by") or "-"
            self.alert_tree.insert(
                "", "end", iid=a["alert_id"],
                values=(
                    a["rule_name"], a["device_code"], a["metric_code"],
                    f"{a['trigger_value']:g}",
                    SEVERITY_LABELS.get(a["severity"], str(a["severity"])),
                    a["status"], display_time(a["triggered_at"]), ack_name,
                ),
            )

        for iid in self.rule_tree.get_children():
            self.rule_tree.delete(iid)
        for r in self.backend.list_rules():
            operator = OPERATOR_REVERSE.get(r["operator_code"], r["operator_code"])
            if r["operator_code"] == "BETWEEN":
                threshold = f"{r['threshold_value']:g} ～ {r['threshold_upper']:g}"
            else:
                threshold = f"{operator} {r['threshold_value']:g}"
            self.rule_tree.insert(
                "", "end", iid=str(r["rule_id"]),
                values=(
                    r["rule_id"], r["rule_name"], r["device_code"] or "全部",
                    r["metric_code"], operator, threshold, r["consecutive_count"],
                    SEVERITY_LABELS.get(r["severity"], r["severity"]),
                    "是" if r["enabled"] else "否",
                ),
            )

    def add_rule(self):
        RuleDialog(
            self.root, self.backend, self.user["username"], on_saved=self.refresh_all
        )

    def edit_rule(self):
        selected = self.rule_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择规则。", parent=self.root)
            return
        rule_id = int(selected[0])
        rule = next(
            (r for r in self.backend.list_rules() if r["rule_id"] == rule_id), None
        )
        if rule:
            RuleDialog(
                self.root, self.backend, self.user["username"],
                rule=rule, on_saved=self.refresh_all,
            )

    def toggle_rule(self):
        selected = self.rule_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择规则。", parent=self.root)
            return
        try:
            self.backend.toggle_rule(int(selected[0]), self.user["username"])
        except Exception as exc:
            messagebox.showerror("操作失败", str(exc), parent=self.root)
        self.refresh_all()

    def acknowledge_selected(self):
        selected = self.alert_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择告警。", parent=self.root)
            return
        ok, message = self.backend.acknowledge_alert(
            selected[0], self.user["username"]
        )
        if ok:
            messagebox.showinfo("告警处理", message, parent=self.root)
        else:
            messagebox.showwarning("告警处理", message, parent=self.root)
        self.refresh_all()


# ui/quality_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class QualityViewMixin:
    def build_quality_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="数据质量与日志")

        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 5))
        self.quality_status_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.quality_status_var).pack(side="left")
        state = "normal" if self.can_operate else "disabled"
        ttk.Button(
            toolbar, text="导入 JSONL 遥测文件",
            command=self.import_jsonl, state=state,
        ).pack(side="right", padx=4)
        ttk.Button(
            toolbar, text="刷新", command=self.refresh_quality
        ).pack(side="right", padx=4)

        split = ttk.Panedwindow(page, orient="vertical")
        split.pack(fill="both", expand=True)
        dlq_box = ttk.LabelFrame(split, text="异常数据隔离队列（DLQ）", padding=5)
        audit_box = ttk.LabelFrame(split, text="操作审计日志", padding=5)
        split.add(dlq_box, weight=1)
        split.add(audit_box, weight=1)

        self.dlq_tree = make_tree(
            dlq_box,
            ("id", "time", "reason", "raw"),
            ("编号", "时间", "错误原因", "原始消息"),
            widths={"id": 60, "time": 160, "reason": 300, "raw": 600},
        )
        self.audit_tree = make_tree(
            audit_box,
            ("id", "time", "user", "action", "object", "detail"),
            ("编号", "时间", "用户", "操作", "对象", "详情"),
            widths={
                "id": 60, "time": 160, "user": 100,
                "action": 160, "object": 120, "detail": 500,
            },
        )

    def refresh_quality(self):
        if not hasattr(self, "dlq_tree"):
            return
        qsize = self.event_queue.qsize()
        self.quality_status_var.set(
            f"本地处理队列待处理：{qsize} 条；数据库：{self.backend.database_path}"
        )

        for iid in self.dlq_tree.get_children():
            self.dlq_tree.delete(iid)
        for row in self.backend.list_dlq():
            self.dlq_tree.insert(
                "", "end", iid=str(row["dlq_id"]),
                values=(
                    row["dlq_id"], display_time(row["created_at"]),
                    row["reason"], row["raw_payload"] or "",
                ),
            )

        for iid in self.audit_tree.get_children():
            self.audit_tree.delete(iid)
        for row in self.backend.list_audit():
            self.audit_tree.insert(
                "", "end", iid=str(row["audit_id"]),
                values=(
                    row["audit_id"], display_time(row["created_at"]),
                    row["username"] or "", row["action"],
                    f"{row['object_type']} {row['object_id']}",
                    row["detail"] or "",
                ),
            )

    def import_jsonl(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="选择 JSONL 文件",
            filetypes=[("JSONL/文本文件", "*.jsonl *.txt"), ("所有文件", "*.*")],
        )
        if not filename:
            return

        ok = invalid = duplicate = 0
        try:
            with open(filename, "r", encoding="utf-8-sig") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    result = self.backend.ingest_json(line)
                    if result["status"] == "OK":
                        ok += 1
                    elif result["status"] == "DUPLICATE":
                        duplicate += 1
                    else:
                        invalid += 1
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)
            return

        self.refresh_all()
        messagebox.showinfo(
            "导入完成",
            f"成功：{ok} 条\n重复：{duplicate} 条\n异常：{invalid} 条",
            parent=self.root,
        )

    def clear_telemetry(self):
        if not messagebox.askyesno(
            "确认清空",
            "将清空遥测数据、分钟聚合、告警和异常数据，不会删除设备、规则、用户和审计日志。继续吗？",
            parent=self.root,
        ):
            return
        self.backend.reset_telemetry(self.user["username"])
        self.refresh_all()


# ui/user_view.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class UserViewMixin:
    def build_user_tab(self):
        page = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(page, text="用户管理")

        toolbar = ttk.Frame(page)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="新增用户", command=self.add_user).pack(
            side="left", padx=3
        )
        ttk.Button(toolbar, text="启用/停用用户", command=self.toggle_user).pack(
            side="left", padx=3
        )

        self.user_tree = make_tree(
            page,
            ("username", "display", "role", "enabled", "created"),
            ("用户名", "显示名称", "角色", "启用", "创建时间"),
            widths={
                "username": 160, "display": 180, "role": 120,
                "enabled": 80, "created": 180,
            },
        )

    def refresh_users(self):
        if not hasattr(self, "user_tree"):
            return
        for iid in self.user_tree.get_children():
            self.user_tree.delete(iid)
        for user in self.backend.list_users():
            self.user_tree.insert(
                "", "end", iid=user["username"],
                values=(
                    user["username"], user["display_name"],
                    ROLE_LABELS.get(user["role_code"], user["role_code"]),
                    "是" if user["enabled"] else "否",
                    display_time(user["created_at"]),
                ),
            )

    def add_user(self):
        UserDialog(
            self.root, self.backend, self.user["username"],
            on_saved=self.refresh_users,
        )

    def toggle_user(self):
        selected = self.user_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择用户。", parent=self.root)
            return
        username = selected[0]
        if username == self.user["username"]:
            messagebox.showwarning("提示", "不能停用当前登录用户。", parent=self.root)
            return
        user = next(
            (u for u in self.backend.list_users() if u["username"] == username), None
        )
        if not user:
            return
        enabled = not bool(user["enabled"])
        try:
            self.backend.set_user_enabled(
                username, enabled, self.user["username"]
            )
        except Exception as exc:
            messagebox.showerror("操作失败", str(exc), parent=self.root)
        self.refresh_users()


# ui/simulator_view.py
import csv
import json
import math
import os
import queue
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class SimulatorViewMixin:
    def run_demo(self):
        if self.sim_thread and self.sim_thread.is_alive():
            self.stop_simulator()

        base = utc_now().replace(microsecond=0) - timedelta(seconds=15)
        values = [96, 108, 115, 121]
        results = []
        for i, value in enumerate(values):
            event_time = utc_iso(base + timedelta(seconds=i * 5))
            payload = {
                "eventId": str(uuid.uuid4()),
                "deviceCode": "POWER-A-01",
                "metricCode": "power",
                "value": value,
                "unit": "kW",
                "eventTime": event_time,
            }
            results.append(self.backend.process_event(payload))

        self.backend.audit(
            self.user["username"], "DEMO_DATA_INJECTED", "Telemetry",
            "POWER-A-01", "注入 96、108、115、121 kW 四点样例",
        )
        self.refresh_all()

        alert_count = sum(
            len(result.get("alertIds", []))
            for result in results
            if result["status"] == "OK"
        )
        messagebox.showinfo(
            "演示数据已注入",
            "已向 POWER-A-01 注入 96、108、115、121 kW 四条数据。\n"
            f"本次新触发告警数：{alert_count}\n\n"
            "默认规则为功率 >100 kW 连续 3 次。\n"
            "若要确保分钟样本数恰好为 4，可先点击“清空实验数据”。",
            parent=self.root,
        )

    def inject_selected_sample(self):
        device_code = self.chart_device_var.get()
        metric_code = self.chart_metric_var.get()
        try:
            self.event_queue.put(
                self.backend.simulator.generate_event(device_code, metric_code)
            )
        except ValueError as exc:
            messagebox.showerror("采样失败", str(exc), parent=self.root)
            return
        self.status_var.set(f"已生成采样：{device_code} / {metric_code}")

    def start_simulator(self):
        if not self.can_operate:
            return
        if self.sim_thread and self.sim_thread.is_alive():
            return

        try:
            interval = max(1.0, min(60.0, float(self.interval_var.get())))
        except ValueError:
            messagebox.showerror("参数错误", "采集间隔必须是数字。", parent=self.root)
            return

        profiles = self.backend.simulator.profiles()
        if not profiles:
            messagebox.showwarning("模拟器", "没有启用的设备。", parent=self.root)
            return

        stop_event = threading.Event()
        self.sim_stop_event = stop_event

        self.sim_thread = threading.Thread(
            target=self.backend.simulator.produce,
            args=(
                stop_event,
                self.event_queue,
                interval,
                self.sim_error_queue,
                profiles,
            ),
            daemon=True,
        )
        self.sim_thread.start()
        self.sim_status_label.configure(text=f"模拟器：运行中（每 {interval:g} 秒）")
        self.status_var.set("模拟器已启动")
        self.backend.audit(
            self.user["username"], "SIMULATOR_STARTED", "Simulator", "",
            f"interval={interval}",
        )

    def stop_simulator(self, audit=True):
        if self.sim_stop_event:
            self.sim_stop_event.set()
        if self.sim_thread and self.sim_thread.is_alive():
            self.sim_thread.join(timeout=0.5)
        was_running = self.sim_thread is not None
        self.sim_thread = None
        self.sim_stop_event = None

        if hasattr(self, "sim_status_label"):
            self.sim_status_label.configure(text="模拟器：已停止")
        if audit and was_running and self.user:
            self.backend.audit(
                self.user["username"], "SIMULATOR_STOPPED", "Simulator", "", ""
            )

    def pump_queue(self):
        if not self.user:
            return
        try:
            error = self.sim_error_queue.get_nowait()
        except queue.Empty:
            error = None
        if error:
            self.stop_simulator(audit=False)
            self.sim_status_label.configure(text="模拟器：发生错误")
            self.status_var.set(f"模拟器错误：{error}")

        processed = 0
        while processed < 500:
            try:
                payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                result = self.backend.process_event(payload)
                if result["status"] == "INVALID":
                    self.status_var.set(f"接入异常：{result['message']}")
            except Exception as exc:
                self.status_var.set(f"数据处理失败：{exc}")
            processed += 1

        self.root.after(250, self.pump_queue)


# app/monitor_app.py
import csv
import json
import math
import os
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class MonitorApp(DashboardViewMixin, DeviceViewMixin, HistoryViewMixin, AlertViewMixin, QualityViewMixin, UserViewMixin, SimulatorViewMixin):
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("智慧园区实时能耗与环境监测系统")
        self.root.geometry("1360x860")
        self.root.minsize(1080, 700)

        self.backend = MonitorBackend()
        self.user = None
        self.event_queue = queue.Queue()
        self.sim_error_queue = queue.Queue()
        self.sim_stop_event = None
        self.sim_thread = None
        self.history_rows = []
        self.status_var = tk.StringVar(value="本地系统已启动")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        LoginDialog(self)

    def run(self):
        self.root.mainloop()

    def login_succeeded(self, user):
        self.user = user
        self.root.deiconify()
        self.build_ui()

    @property
    def can_operate(self):
        return self.user["role_code"] in ("ADMIN", "OPERATOR")

    @property
    def is_admin(self):
        return self.user["role_code"] == "ADMIN"

    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

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

        role = ROLE_LABELS.get(self.user["role_code"], self.user["role_code"])
        tk.Label(
            header,
            text=f"{self.user['display_name']}（{role}）",
            bg="#15263d",
            fg="#dce7f4",
            font=("Microsoft YaHei UI", 10),
        ).pack(side="right", padx=10)
        ttk.Button(header, text="退出", command=self.logout).pack(
            side="right", padx=12, pady=10
        )

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.build_dashboard_tab()
        self.build_device_tab()
        self.build_history_tab()
        self.build_alert_tab()
        self.build_quality_tab()
        if self.is_admin:
            self.build_user_tab()

        self.refresh_all()
        self.root.after(250, self.pump_queue)
        self.root.after(1200, self.periodic_refresh)

    def _set_tree_rows(self, tree, rows, columns, iid_key=None):
        for iid in tree.get_children():
            tree.delete(iid)
        for row in rows:
            values = [row.get(key, "") for key in columns]
            iid = str(row.get(iid_key)) if iid_key else None
            try:
                tree.insert("", "end", iid=iid, values=values)
            except tk.TclError:
                tree.insert("", "end", values=values)

    def refresh_all(self):
        if not self.user:
            return
        self.refresh_dashboard()
        self.refresh_devices()
        self.refresh_alerts()
        self.refresh_quality()
        if self.is_admin:
            self.refresh_users()

    def periodic_refresh(self):
        if not self.user:
            return
        try:
            self.refresh_all()
        except Exception as exc:
            self.status_var.set(f"界面刷新失败：{exc}")
        self.root.after(1500, self.periodic_refresh)

    def logout(self):
        if messagebox.askyesno("退出", "确定退出系统吗？", parent=self.root):
            self.stop_simulator()
            self.backend.close()
            self.root.destroy()

    def on_close(self):
        try:
            self.stop_simulator(audit=False)
            self.backend.close()
        finally:
            self.root.destroy()


def main():
    MonitorApp().run()


if __name__ == "__main__":
    main()
