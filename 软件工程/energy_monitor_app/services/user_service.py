from datetime import datetime, timedelta
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path

from energy_monitor_app.config.constants import OPERATOR_REVERSE, ROLE_LABELS
from energy_monitor_app.core.security import hash_password, verify_password
from energy_monitor_app.core.time_utils import parse_iso, utc_iso, utc_now
from energy_monitor_app.rules.rule_factory import RuleFactory


class UserServiceMixin:
    def _audit(self, username, action, object_type="", object_id="", detail=""):
        self.conn.execute(
            """
            INSERT INTO audit_log
            (username, action, object_type, object_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, action, object_type, str(object_id), str(detail), utc_iso()),
        )

    def audit(self, username, action, object_type="", object_id="", detail=""):
        with self.conn:
            self._audit(username, action, object_type, object_id, detail)

    def authenticate(self, username, password):
        username = (username or "").strip()
        row = self.conn.execute(
            "SELECT * FROM sys_user WHERE username = ?", (username,)
        ).fetchone()
        if row and row["enabled"] and verify_password(password, row["password_hash"]):
            with self.conn:
                self._audit(username, "LOGIN", "User", username, "登录成功")
            return {
                "username": row["username"],
                "display_name": row["display_name"],
                "role_code": row["role_code"],
            }

        with self.conn:
            self._audit(username or "unknown", "LOGIN_FAILED", "User", username, "登录失败")
        return None

    def list_users(self):
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT username, display_name, role_code, enabled, created_at
                FROM sys_user ORDER BY username
                """
            ).fetchall()
        ]

    def add_user(self, username, password, display_name, role_code, actor):
        username = username.strip()
        display_name = display_name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
            raise ValueError("用户名须为 3–64 位英文、数字、点、下划线或连字符")
        if len(password) < 8:
            raise ValueError("密码至少 8 位")
        if not display_name:
            raise ValueError("显示名称不能为空")
        if role_code not in ROLE_LABELS:
            raise ValueError("角色不合法")

        with self.conn:
            if self.conn.execute(
                "SELECT 1 FROM sys_user WHERE username = ?", (username,)
            ).fetchone():
                raise ValueError("用户名已存在")
            self.conn.execute(
                """
                INSERT INTO sys_user
                (username, password_hash, display_name, role_code, enabled, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (username, hash_password(password), display_name, role_code, utc_iso()),
            )
            self._audit(actor, "USER_CREATED", "User", username, f"角色={role_code}")

    def set_user_enabled(self, username, enabled, actor):
        row = self.conn.execute(
            "SELECT role_code, enabled FROM sys_user WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            raise ValueError("用户不存在")
        if not enabled and row["role_code"] == "ADMIN":
            admins = self.conn.execute(
                "SELECT COUNT(*) AS n FROM sys_user "
                "WHERE role_code='ADMIN' AND enabled=1"
            ).fetchone()["n"]
            if admins <= 1 and row["enabled"]:
                raise ValueError("不能停用最后一个启用的管理员")

        with self.conn:
            self.conn.execute(
                "UPDATE sys_user SET enabled = ? WHERE username = ?",
                (int(bool(enabled)), username),
            )
            self._audit(actor, "USER_ENABLED_CHANGED", "User", username, str(enabled))
