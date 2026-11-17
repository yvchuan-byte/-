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
