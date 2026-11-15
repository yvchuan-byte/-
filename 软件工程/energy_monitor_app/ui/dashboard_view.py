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

from energy_monitor_app.config.constants import OPERATOR_REVERSE, ROLE_LABELS, SEVERITY_LABELS
from energy_monitor_app.core.time_utils import display_time, utc_iso, utc_now
from energy_monitor_app.ui.dialogs import DeviceDialog, LoginDialog, RuleDialog, UserDialog
from energy_monitor_app.ui.widgets import make_tree


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
