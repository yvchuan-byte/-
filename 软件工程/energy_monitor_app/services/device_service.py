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


class DeviceServiceMixin:
    def list_devices(self):
        rows = self.conn.execute(
            "SELECT * FROM device ORDER BY area_code, device_code"
        ).fetchall()
        now = utc_now()
        result = []
        for row in rows:
            item = dict(row)
            if not item["enabled"]:
                item["status_label"] = "已停用"
            elif item["last_seen_at"]:
                try:
                    online = (now - parse_iso(item["last_seen_at"])).total_seconds() <= 30
                except Exception:
                    online = False
                item["status_label"] = "在线" if online else "离线"
            else:
                item["status_label"] = "离线"
            result.append(item)
        return result

    def save_device(self, data, actor):
        code = data["device_code"].strip()
        name = data["device_name"].strip()
        area = data["area_code"].strip()
        device_type = data.get("device_type", "").strip()
        location = data.get("location_desc", "").strip()

        if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", code):
            raise ValueError("设备编号只能使用英文、数字、下划线或连字符")
        if not name or not area:
            raise ValueError("设备名称和区域不能为空")

        existing = self.conn.execute(
            "SELECT 1 FROM device WHERE device_code = ?", (code,)
        ).fetchone()
        now = utc_iso()

        with self.conn:
            if existing:
                self.conn.execute(
                    """
                    UPDATE device
                    SET device_name=?, device_type=?, area_code=?, location_desc=?,
                        updated_at=?
                    WHERE device_code=?
                    """,
                    (name, device_type, area, location, now, code),
                )
                action = "DEVICE_UPDATED"
            else:
                self.conn.execute(
                    """
                    INSERT INTO device
                    (device_code, device_name, device_type, area_code, location_desc,
                     enabled, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, 'OFFLINE', ?, ?)
                    """,
                    (code, name, device_type, area, location, now, now),
                )
                action = "DEVICE_CREATED"
            self._audit(actor, action, "Device", code, name)

    def set_device_enabled(self, device_code, enabled, actor):
        with self.conn:
            self.conn.execute(
                "UPDATE device SET enabled=?, updated_at=? WHERE device_code=?",
                (int(bool(enabled)), utc_iso(), device_code),
            )
            self._audit(
                actor, "DEVICE_ENABLED_CHANGED", "Device", device_code, str(enabled)
            )

    def list_metrics(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM metric_definition ORDER BY metric_code"
            ).fetchall()
        ]

    def list_rules(self):
        rows = self.conn.execute(
            """
            SELECT r.*, m.metric_name, m.unit
            FROM alert_rule r
            LEFT JOIN metric_definition m ON m.metric_code=r.metric_code
            ORDER BY r.rule_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def save_rule(self, rule_id, data, actor):
        name = data["rule_name"].strip()
        device_code = data.get("device_code") or None
        metric_code = data["metric_code"]
        operator_code = data["operator_code"]

        if not name:
            raise ValueError("规则名称不能为空")
        if operator_code not in ("GT", "GE", "LT", "LE", "BETWEEN"):
            raise ValueError("比较方式不合法")
        if not self.conn.execute(
            "SELECT 1 FROM metric_definition WHERE metric_code=? AND enabled=1",
            (metric_code,),
        ).fetchone():
            raise ValueError("指标不存在或已停用")
        if device_code and not self.conn.execute(
            "SELECT 1 FROM device WHERE device_code=?", (device_code,)
        ).fetchone():
            raise ValueError("设备不存在")

        threshold = float(data["threshold_value"])
        upper = data.get("threshold_upper")
        upper = float(upper) if upper not in (None, "") else None
        consecutive = int(data["consecutive_count"])
        severity = int(data["severity"])
        cooldown = int(data["cooldown_seconds"])

        if not math.isfinite(threshold):
            raise ValueError("阈值必须是有限数值")
        if operator_code == "BETWEEN":
            if upper is None or not math.isfinite(upper) or upper <= threshold:
                raise ValueError("区间规则上限必须大于下限")
        if not 1 <= consecutive <= 100:
            raise ValueError("连续次数范围为 1–100")
        if severity not in (1, 2, 3, 4):
            raise ValueError("告警级别范围为 1–4")
        if not 0 <= cooldown <= 86400:
            raise ValueError("冷却时间范围为 0–86400 秒")

        now = utc_iso()
        with self.conn:
            if rule_id:
                self.conn.execute(
                    """
                    UPDATE alert_rule
                    SET rule_name=?, device_code=?, metric_code=?, operator_code=?,
                        threshold_value=?, threshold_upper=?, consecutive_count=?,
                        severity=?, cooldown_seconds=?, updated_at=?
                    WHERE rule_id=?
                    """,
                    (
                        name, device_code, metric_code, operator_code, threshold,
                        upper, consecutive, severity, cooldown, now, rule_id,
                    ),
                )
                action = "RULE_UPDATED"
            else:
                cursor = self.conn.execute(
                    """
                    INSERT INTO alert_rule
                    (rule_name, device_code, metric_code, operator_code,
                     threshold_value, threshold_upper, consecutive_count,
                     severity, cooldown_seconds, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        name, device_code, metric_code, operator_code, threshold,
                        upper, consecutive, severity, cooldown, now, now,
                    ),
                )
                rule_id = cursor.lastrowid
                action = "RULE_CREATED"
            self._audit(actor, action, "AlertRule", rule_id, name)
        return rule_id

    def toggle_rule(self, rule_id, actor):
        row = self.conn.execute(
            "SELECT enabled, rule_name FROM alert_rule WHERE rule_id=?", (rule_id,)
        ).fetchone()
        if not row:
            raise ValueError("规则不存在")
        enabled = 0 if row["enabled"] else 1
        with self.conn:
            self.conn.execute(
                "UPDATE alert_rule SET enabled=?, updated_at=? WHERE rule_id=?",
                (enabled, utc_iso(), rule_id),
            )
            self._audit(
                actor, "RULE_ENABLED_CHANGED", "AlertRule", rule_id, str(enabled)
            )
        return enabled
