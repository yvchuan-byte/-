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
from energy_monitor_app.ui.dashboard_view import DashboardViewMixin
from energy_monitor_app.ui.device_view import DeviceViewMixin
from energy_monitor_app.ui.history_view import HistoryViewMixin
from energy_monitor_app.ui.alert_view import AlertViewMixin
from energy_monitor_app.ui.quality_view import QualityViewMixin
from energy_monitor_app.ui.user_view import UserViewMixin
from energy_monitor_app.ui.simulator_view import SimulatorViewMixin
from energy_monitor_app.services.monitor_backend import MonitorBackend


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
