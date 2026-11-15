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
