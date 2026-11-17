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
