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
