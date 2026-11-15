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
