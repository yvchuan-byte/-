# config/constants.py
ROLE_LABELS = {
    "ADMIN": "系统管理员",
    "OPERATOR": "运维人员",
    "VIEWER": "只读用户",
}

SEVERITY_LABELS = {
    1: "紧急",
    2: "高",
    3: "中",
    4: "低",
}

OPERATOR_LABELS = {
    ">": "GT",
    ">=": "GE",
    "<": "LT",
    "<=": "LE",
    "区间": "BETWEEN",
}

OPERATOR_REVERSE = {v: k for k, v in OPERATOR_LABELS.items()}


# core/app_paths.py
import sys
from pathlib import Path


def app_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# core/security.py
import hashlib
import hmac
import secrets


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password, encoded):
    try:
        salt_hex, expected = encoded.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            120_000,
        ).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# core/time_utils.py
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(value=None):
    value = value or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value):
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def display_time(value):
    if not value:
        return "-"
    try:
        return parse_iso(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


# rules/base_rule.py
from abc import ABC, abstractmethod


class BaseRule(ABC):
    def __init__(self, threshold_value, threshold_upper=None):
        self.threshold_value = threshold_value
        self.threshold_upper = threshold_upper

    @abstractmethod
    def evaluate(self, value):
        raise NotImplementedError

    def describe(self):
        if self.threshold_upper is not None:
            return f"[{self.threshold_value}, {self.threshold_upper}]"
        return f"{self.threshold_value}"


# rules/comparison_rules.py
class GTRule(BaseRule):
    def evaluate(self, value):
        return value > self.threshold_value


class GERule(BaseRule):
    def evaluate(self, value):
        return value >= self.threshold_value


class LTRule(BaseRule):
    def evaluate(self, value):
        return value < self.threshold_value


class LERule(BaseRule):
    def evaluate(self, value):
        return value <= self.threshold_value


class BetweenRule(BaseRule):
    def evaluate(self, value):
        return self.threshold_value <= value <= self.threshold_upper


# rules/rule_factory.py
class RuleFactory:
    @staticmethod
    def create(operator_code, threshold_value, threshold_upper=None):
        if operator_code == "GT":
            return GTRule(threshold_value, threshold_upper)
        if operator_code == "GE":
            return GERule(threshold_value, threshold_upper)
        if operator_code == "LT":
            return LTRule(threshold_value, threshold_upper)
        if operator_code == "LE":
            return LERule(threshold_value, threshold_upper)
        if operator_code == "BETWEEN":
            return BetweenRule(threshold_value, threshold_upper)
        raise ValueError(f"Unsupported operator: {operator_code}")


# db/schema.py
class SchemaMixin:
    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sys_user (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role_code TEXT NOT NULL CHECK(role_code IN
                    ('ADMIN', 'OPERATOR', 'VIEWER')),
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device (
                device_code TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                device_type TEXT NOT NULL DEFAULT '',
                area_code TEXT NOT NULL,
                location_desc TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'OFFLINE',
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metric_definition (
                metric_code TEXT PRIMARY KEY,
                metric_name TEXT NOT NULL,
                unit TEXT NOT NULL,
                min_value REAL,
                max_value REAL,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS alert_rule (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                device_code TEXT,
                metric_code TEXT NOT NULL,
                operator_code TEXT NOT NULL,
                threshold_value REAL NOT NULL,
                threshold_upper REAL,
                consecutive_count INTEGER NOT NULL DEFAULT 1,
                severity INTEGER NOT NULL DEFAULT 2,
                cooldown_seconds INTEGER NOT NULL DEFAULT 300,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rule_state (
                rule_id INTEGER NOT NULL,
                device_code TEXT NOT NULL,
                consecutive_count INTEGER NOT NULL DEFAULT 0,
                last_alert_at TEXT,
                PRIMARY KEY(rule_id, device_code)
            );

            CREATE TABLE IF NOT EXISTS telemetry_event (
                event_id TEXT PRIMARY KEY,
                device_code TEXT NOT NULL,
                metric_code TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                event_time TEXT NOT NULL,
                ingest_time TEXT NOT NULL,
                quality_status INTEGER NOT NULL DEFAULT 0,
                raw_payload TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_telemetry_device_metric_time
                ON telemetry_event(device_code, metric_code, event_time DESC);

            CREATE TABLE IF NOT EXISTS metric_aggregate_1m (
                bucket_start TEXT NOT NULL,
                device_code TEXT NOT NULL,
                metric_code TEXT NOT NULL,
                avg_value REAL,
                min_value REAL,
                max_value REAL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                anomaly_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(bucket_start, device_code, metric_code)
            );

            CREATE TABLE IF NOT EXISTS alert_record (
                alert_id TEXT PRIMARY KEY,
                rule_id INTEGER,
                rule_name TEXT NOT NULL,
                device_code TEXT NOT NULL,
                metric_code TEXT NOT NULL,
                trigger_value REAL NOT NULL,
                severity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                triggered_at TEXT NOT NULL,
                acknowledged_by TEXT,
                acknowledged_at TEXT,
                resolved_at TEXT,
                message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alert_status_time
                ON alert_record(status, triggered_at DESC);

            CREATE TABLE IF NOT EXISTS dlq (
                dlq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_payload TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT NOT NULL,
                object_type TEXT,
                object_id TEXT,
                detail TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _seed_data(self):
        now = utc_iso()
        metrics = [
            ("power", "有功功率", "kW", 0, 2000),
            ("temperature", "温度", "℃", -20, 80),
            ("humidity", "湿度", "%", 0, 100),
            ("pm25", "PM2.5", "μg/m³", 0, 1000),
        ]
        devices = [
            ("POWER-A-01", "A栋西区电表", "电表", "A栋西区", "西区配电间"),
            ("POWER-A-02", "A栋东区电表", "电表", "A栋东区", "东区配电间"),
            ("ENV-A-01", "A栋环境传感器", "环境传感器", "A栋西区", "西区走廊"),
            ("AIR-B-01", "B栋空气质量传感器", "空气质量传感器", "B栋一层", "一层大厅"),
        ]

        with self.conn:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO metric_definition
                (metric_code, metric_name, unit, min_value, max_value, enabled)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                metrics,
            )
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO device
                (device_code, device_name, device_type, area_code,
                 location_desc, enabled, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, 'OFFLINE', ?, ?)
                """,
                [(*d, now, now) for d in devices],
            )

            if not self.conn.execute(
                "SELECT 1 FROM sys_user LIMIT 1"
            ).fetchone():
                defaults = [
                    ("admin", "admin123", "系统管理员", "ADMIN"),
                    ("operator", "operator123", "运维人员", "OPERATOR"),
                    ("viewer", "viewer123", "只读用户", "VIEWER"),
                ]
                for username, password, display_name, role in defaults:
                    self.conn.execute(
                        """
                        INSERT INTO sys_user
                        (username, password_hash, display_name, role_code,
                         enabled, created_at)
                        VALUES (?, ?, ?, ?, 1, ?)
                        """,
                        (username, hash_password(password), display_name, role, now),
                    )

            default_rules = [
                ("A栋西区功率连续超限", "POWER-A-01", "power", 100, 3, 1, 300),
                ("温度偏高", None, "temperature", 35, 2, 2, 60),
                ("湿度偏高", None, "humidity", 80, 2, 3, 60),
                ("PM2.5偏高", None, "pm25", 75, 2, 2, 60),
            ]
            for (
                name,
                device_code,
                metric_code,
                threshold,
                consecutive_count,
                severity,
                cooldown,
            ) in default_rules:
                if not self.conn.execute(
                    """
                    SELECT 1 FROM alert_rule
                    WHERE metric_code=? AND device_code IS ?
                    LIMIT 1
                    """,
                    (metric_code, device_code),
                ).fetchone():
                    self.conn.execute(
                        """
                        INSERT INTO alert_rule
                        (rule_name, device_code, metric_code, operator_code,
                         threshold_value, threshold_upper, consecutive_count,
                         severity, cooldown_seconds, enabled, created_at, updated_at)
                        VALUES (?, ?, ?, 'GT', ?, NULL, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            name, device_code, metric_code, threshold, consecutive_count,
                            severity, cooldown, now, now,
                        ),
                    )


# services/user_service.py
from datetime import datetime, timedelta
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path



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


# services/device_service.py
from datetime import datetime, timedelta
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path



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


# services/telemetry_service.py
from datetime import datetime, timedelta
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path



class TelemetryServiceMixin:
    def _record_dlq(self, raw, reason):
        with self.conn:
            self.conn.execute(
                "INSERT INTO dlq(raw_payload, reason, created_at) VALUES (?, ?, ?)",
                (str(raw)[:20000], str(reason)[:500], utc_iso()),
            )

    def ingest_json(self, raw_text):
        try:
            payload = json.loads(raw_text)
        except Exception as exc:
            self._record_dlq(raw_text, f"JSON解析失败：{exc}")
            return {"status": "INVALID", "message": "JSON解析失败"}
        return self.process_event(payload, raw_text=raw_text)

    def _evaluate_rules(self, device_code, metric_code, value, event_time, unit):
        rules = self.conn.execute(
            """
            SELECT * FROM alert_rule
            WHERE enabled=1 AND metric_code=?
              AND (device_code IS NULL OR device_code=?)
            """,
            (metric_code, device_code),
        ).fetchall()
        alert_ids = []

        for rule in rules:
            matched = self._matches_rule(rule, value)
            state = self.conn.execute(
                """
                SELECT * FROM rule_state
                WHERE rule_id=? AND device_code=?
                """,
                (rule["rule_id"], device_code),
            ).fetchone()

            count = (state["consecutive_count"] if state else 0) + 1 if matched else 0
            last_alert_at = state["last_alert_at"] if state else None

            if state:
                self.conn.execute(
                    """
                    UPDATE rule_state SET consecutive_count=?
                    WHERE rule_id=? AND device_code=?
                    """,
                    (count, rule["rule_id"], device_code),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO rule_state
                    (rule_id, device_code, consecutive_count, last_alert_at)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (rule["rule_id"], device_code, count),
                )

            if not matched:
                recovered = self.conn.execute(
                    """
                    UPDATE alert_record
                    SET status='RESOLVED', resolved_at=?
                    WHERE rule_id=? AND device_code=?
                      AND status IN ('OPEN', 'ACKED')
                    """,
                    (event_time, rule["rule_id"], device_code),
                )
                if recovered.rowcount:
                    self._audit(
                        "system", "ALERT_RESOLVED", "Alert", device_code,
                        f"{rule['rule_name']} 指标已恢复",
                    )
                continue

            if count < rule["consecutive_count"]:
                continue

            active = self.conn.execute(
                """
                SELECT alert_id FROM alert_record
                WHERE rule_id=? AND device_code=? AND status IN ('OPEN', 'ACKED')
                LIMIT 1
                """,
                (rule["rule_id"], device_code),
            ).fetchone()
            if active:
                continue

            if last_alert_at and rule["cooldown_seconds"] > 0:
                try:
                    elapsed = (
                        parse_iso(event_time) - parse_iso(last_alert_at)
                    ).total_seconds()
                    if elapsed < rule["cooldown_seconds"]:
                        continue
                except Exception:
                    pass

            if rule["operator_code"] == "BETWEEN":
                condition = (
                    f"[{rule['threshold_value']:g}, "
                    f"{rule['threshold_upper']:g}]"
                )
            else:
                condition = (
                    f"{OPERATOR_REVERSE[rule['operator_code']]} "
                    f"{rule['threshold_value']:g}"
                )

            alert_id = str(uuid.uuid4())
            message = (
                f"{rule['rule_name']}：{metric_code}={value:g}{unit}，"
                f"条件 {condition}，连续满足 {count} 次"
            )
            self.conn.execute(
                """
                INSERT INTO alert_record
                (alert_id, rule_id, rule_name, device_code, metric_code,
                 trigger_value, severity, status, triggered_at, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (
                    alert_id, rule["rule_id"], rule["rule_name"], device_code,
                    metric_code, value, rule["severity"], event_time, message,
                ),
            )
            self.conn.execute(
                """
                UPDATE rule_state SET last_alert_at=?
                WHERE rule_id=? AND device_code=?
                """,
                (event_time, rule["rule_id"], device_code),
            )
            self._audit("system", "ALERT_CREATED", "Alert", alert_id, message)
            alert_ids.append(alert_id)

        return alert_ids

    def process_event(self, payload, raw_text=None):
        raw = raw_text
        if raw is None:
            try:
                raw = json.dumps(payload, ensure_ascii=False, allow_nan=True)
            except Exception:
                raw = str(payload)

        if not isinstance(payload, dict):
            self._record_dlq(raw, "消息必须是 JSON 对象")
            return {"status": "INVALID", "message": "消息必须是 JSON 对象"}

        event_id = str(payload.get("eventId", "")).strip()
        device_code = str(payload.get("deviceCode", "")).strip()
        metric_code = str(payload.get("metricCode", "")).strip()
        unit = str(payload.get("unit", "")).strip()
        raw_value = payload.get("value")
        raw_time = payload.get("eventTime")

        if not event_id or not device_code or not metric_code or not unit or not raw_time:
            self._record_dlq(raw, "缺少 eventId/deviceCode/metricCode/value/unit/eventTime 字段")
            return {"status": "INVALID", "message": "消息缺少必需字段"}
        if len(event_id) > 128 or len(device_code) > 64 or len(metric_code) > 48:
            self._record_dlq(raw, "字段长度超出限制")
            return {"status": "INVALID", "message": "字段长度超出限制"}
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            self._record_dlq(raw, "value 必须是数值")
            return {"status": "INVALID", "message": "value 必须是数值"}

        value = float(raw_value)
        if not math.isfinite(value):
            self._record_dlq(raw, "value 不能是 NaN 或无穷大")
            return {"status": "INVALID", "message": "value 不是有限数值"}

        try:
            event_dt = parse_iso(raw_time)
        except Exception:
            self._record_dlq(raw, "eventTime 不是有效的 ISO-8601 时间")
            return {"status": "INVALID", "message": "eventTime 格式错误"}

        event_time = utc_iso(event_dt)
        if (event_dt - utc_now()).total_seconds() > 300:
            self._record_dlq(raw, "eventTime 超前当前时间超过 5 分钟")
            return {"status": "INVALID", "message": "事件时间超前过多"}

        device = self.conn.execute(
            "SELECT * FROM device WHERE device_code=?", (device_code,)
        ).fetchone()
        if not device or not device["enabled"]:
            self._record_dlq(raw, "设备不存在或已停用")
            return {"status": "INVALID", "message": "设备不存在或已停用"}

        metric = self.conn.execute(
            "SELECT * FROM metric_definition WHERE metric_code=? AND enabled=1",
            (metric_code,),
        ).fetchone()
        if not metric:
            self._record_dlq(raw, "指标不存在或已停用")
            return {"status": "INVALID", "message": "指标不存在或已停用"}
        if metric["unit"] and unit != metric["unit"]:
            self._record_dlq(raw, f"单位不匹配：期望 {metric['unit']}，收到 {unit}")
            return {"status": "INVALID", "message": "指标单位不匹配"}
        if metric["min_value"] is not None and value < metric["min_value"]:
            self._record_dlq(raw, "数值低于指标允许范围")
            return {"status": "INVALID", "message": "数值低于允许范围"}
        if metric["max_value"] is not None and value > metric["max_value"]:
            self._record_dlq(raw, "数值高于指标允许范围")
            return {"status": "INVALID", "message": "数值高于允许范围"}

        if self.conn.execute(
            "SELECT 1 FROM telemetry_event WHERE event_id=?", (event_id,)
        ).fetchone():
            return {"status": "DUPLICATE", "message": "重复事件已忽略"}

        ingest_time = utc_iso()
        quality_status = 2 if (utc_now() - event_dt).total_seconds() > 60 else 0
        bucket_dt = event_dt.replace(second=0, microsecond=0)
        bucket_start = utc_iso(bucket_dt)
        bucket_end = utc_iso(bucket_dt + timedelta(minutes=1))
        alert_ids = []

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO telemetry_event
                (event_id, device_code, metric_code, metric_value, unit,
                 event_time, ingest_time, quality_status, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, device_code, metric_code, value, unit,
                    event_time, ingest_time, quality_status, str(raw)[:20000],
                ),
            )
            self.conn.execute(
                """
                UPDATE device SET last_seen_at=?, status='ONLINE', updated_at=?
                WHERE device_code=?
                """,
                (ingest_time, ingest_time, device_code),
            )

            aggregate = self.conn.execute(
                """
                SELECT AVG(metric_value) AS avg_value,
                       MIN(metric_value) AS min_value,
                       MAX(metric_value) AS max_value,
                       COUNT(*) AS sample_count,
                       SUM(CASE WHEN quality_status<>0 THEN 1 ELSE 0 END)
                           AS anomaly_count
                FROM telemetry_event
                WHERE device_code=? AND metric_code=?
                  AND event_time>=? AND event_time<?
                """,
                (device_code, metric_code, bucket_start, bucket_end),
            ).fetchone()

            self.conn.execute(
                """
                INSERT INTO metric_aggregate_1m
                (bucket_start, device_code, metric_code, avg_value, min_value,
                 max_value, sample_count, anomaly_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket_start, device_code, metric_code)
                DO UPDATE SET
                    avg_value=excluded.avg_value,
                    min_value=excluded.min_value,
                    max_value=excluded.max_value,
                    sample_count=excluded.sample_count,
                    anomaly_count=excluded.anomaly_count,
                    updated_at=excluded.updated_at
                """,
                (
                    bucket_start, device_code, metric_code,
                    aggregate["avg_value"], aggregate["min_value"],
                    aggregate["max_value"], aggregate["sample_count"],
                    aggregate["anomaly_count"] or 0, ingest_time,
                ),
            )

            alert_ids = self._evaluate_rules(
                device_code, metric_code, value, event_time, unit
            )

        return {
            "status": "OK",
            "message": "数据已接收并处理",
            "eventId": event_id,
            "alertIds": alert_ids,
        }

    @staticmethod
    def _matches_rule(rule, value):
        strategy = RuleFactory.create(
            rule["operator_code"], rule["threshold_value"], rule["threshold_upper"]
        )
        return strategy.evaluate(value)


# services/query_service.py
from datetime import datetime, timedelta
import json
import math
import re
import sqlite3
import uuid
from pathlib import Path



class QueryServiceMixin:
    def query_history(
        self, device_code="", metric_code="", start="", end="", limit=1000
    ):
        where = []
        params = []

        if device_code and device_code != "全部":
            where.append("t.device_code=?")
            params.append(device_code)
        if metric_code and metric_code != "全部":
            where.append("t.metric_code=?")
            params.append(metric_code)
        if start.strip():
            value = start.strip()
            if len(value) == 10:
                value += " 00:00:00"
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").astimezone()
            where.append("t.event_time>=?")
            params.append(utc_iso(dt))
        if end.strip():
            value = end.strip()
            if len(value) == 10:
                value += " 23:59:59"
            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").astimezone()
            where.append("t.event_time<=?")
            params.append(utc_iso(dt))

        sql = """
            SELECT t.*, d.device_name, d.area_code
            FROM telemetry_event t
            LEFT JOIN device d ON d.device_code=t.device_code
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.event_time DESC LIMIT ?"
        params.append(max(1, min(int(limit), 5000)))
        return [
            dict(row) for row in self.conn.execute(sql, params).fetchall()
        ]

    def latest_events(self, limit=50):
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT t.*, d.device_name, d.area_code
                FROM telemetry_event t
                LEFT JOIN device d ON d.device_code=t.device_code
                ORDER BY t.ingest_time DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

    def latest_aggregate(self, device_code, metric_code):
        row = self.conn.execute(
            """
            SELECT * FROM metric_aggregate_1m
            WHERE device_code=? AND metric_code=?
            ORDER BY bucket_start DESC LIMIT 1
            """,
            (device_code, metric_code),
        ).fetchone()
        return dict(row) if row else None

    def list_alerts(self, limit=300):
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT a.*, u.display_name AS acknowledged_name
                FROM alert_record a
                LEFT JOIN sys_user u ON u.username=a.acknowledged_by
                ORDER BY a.triggered_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

    def acknowledge_alert(self, alert_id, username):
        user = self.conn.execute(
            "SELECT role_code, enabled FROM sys_user WHERE username=?",
            (username,),
        ).fetchone()
        if not user or not user["enabled"] or user["role_code"] == "VIEWER":
            return False, "当前用户没有确认告警的权限"

        row = self.conn.execute(
            "SELECT status FROM alert_record WHERE alert_id=?", (alert_id,)
        ).fetchone()
        if not row:
            return False, "告警记录不存在"
        if row["status"] != "OPEN":
            return False, f"当前告警状态为 {row['status']}，不能重复确认"

        with self.conn:
            self.conn.execute(
                """
                UPDATE alert_record
                SET status='ACKED', acknowledged_by=?, acknowledged_at=?
                WHERE alert_id=? AND status='OPEN'
                """,
                (username, utc_iso(), alert_id),
            )
            self._audit(username, "ALERT_ACKNOWLEDGED", "Alert", alert_id, "确认告警")
        return True, "告警已确认"

    def list_dlq(self, limit=200):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM dlq ORDER BY dlq_id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]

    def list_audit(self, limit=200):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]

    def stats(self):
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_text = utc_iso(today_start)
        samples = self.conn.execute(
            "SELECT COUNT(*) AS n FROM telemetry_event WHERE ingest_time>=?",
            (today_start_text,),
        ).fetchone()["n"]
        alerts = self.conn.execute(
            "SELECT COUNT(*) AS n FROM alert_record WHERE status IN ('OPEN','ACKED')"
        ).fetchone()["n"]
        invalid = self.conn.execute("SELECT COUNT(*) AS n FROM dlq").fetchone()["n"]
        cutoff = utc_iso(utc_now() - timedelta(seconds=30))
        online = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM device
            WHERE enabled=1 AND last_seen_at>=?
            """,
            (cutoff,),
        ).fetchone()["n"]
        total = self.conn.execute(
            "SELECT COUNT(*) AS n FROM device WHERE enabled=1"
        ).fetchone()["n"]
        return {
            "today_samples": samples,
            "active_alerts": alerts,
            "invalid_messages": invalid,
            "online_devices": online,
            "total_devices": total,
        }

    def simulator_profiles(self):
        metrics = {m["metric_code"]: m for m in self.list_metrics()}
        profiles = []
        for device in self.list_devices():
            if not device["enabled"]:
                continue
            code = device["device_code"]
            kind = device["device_type"]
            if code.startswith("POWER") or "电表" in kind:
                choices = ["power"]
            elif code.startswith("AIR") or "空气" in kind:
                choices = ["temperature", "humidity", "pm25"]
            else:
                choices = ["temperature", "humidity"]
            choices = [m for m in choices if m in metrics and metrics[m]["enabled"]]
            profiles.append(
                {
                    "device_code": code,
                    "metrics": [
                        {
                            "metric_code": m,
                            "unit": metrics[m]["unit"],
                        }
                        for m in choices
                    ],
                }
            )
        return profiles

    def reset_telemetry(self, actor):
        with self.conn:
            self.conn.execute("DELETE FROM telemetry_event")
            self.conn.execute("DELETE FROM metric_aggregate_1m")
            self.conn.execute("DELETE FROM alert_record")
            self.conn.execute("DELETE FROM rule_state")
            self.conn.execute("DELETE FROM dlq")
            self.conn.execute(
                """
                UPDATE device SET status='OFFLINE', last_seen_at=NULL, updated_at=?
                """,
                (utc_iso(),),
            )
            self._audit(actor, "TELEMETRY_RESET", "System", "", "清空实验遥测数据")

    def close(self):
        self.conn.close()


# db/store.py
import sqlite3


DB_PATH = app_directory() / "energy_monitor.db"


class Store(SchemaMixin, UserServiceMixin, DeviceServiceMixin, TelemetryServiceMixin, QueryServiceMixin):
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        self._seed_data()


# services/simulator.py
import random
import threading
import uuid
from abc import ABC, abstractmethod



class MetricValueGenerator(ABC):
    @abstractmethod
    def generate(self, rng):
        raise NotImplementedError


class PowerValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(60, 96)
        if rng.random() < 0.08:
            value = rng.uniform(102, 130)
        return round(value, 2)


class TemperatureValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(21, 31)
        if rng.random() < 0.08:
            value = rng.uniform(36, 39)
        return round(value, 2)


class HumidityValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(35, 72)
        if rng.random() < 0.08:
            value = rng.uniform(82, 96)
        return round(value, 2)


class PM25ValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(6, 48)
        if rng.random() < 0.08:
            value = rng.uniform(80, 150)
        return round(value, 2)


class SimulatorService:
    """生成遥测数据；线程和队列由 UI 控制，业务事件由后端处理。"""

    def __init__(self, store):
        self.store = store
        self._generators = {
            "power": PowerValueGenerator(),
            "temperature": TemperatureValueGenerator(),
            "humidity": HumidityValueGenerator(),
            "pm25": PM25ValueGenerator(),
        }

    def profiles(self):
        return self.store.simulator_profiles()

    def generate_event(self, device_code, metric_code, rng=None):
        profiles = self.profiles()
        profile = next(
            (item for item in profiles if item["device_code"] == device_code),
            None,
        )
        if not profile:
            raise ValueError(f"设备未启用模拟数据：{device_code}")

        metric = next(
            (
                item for item in profile["metrics"]
                if item["metric_code"] == metric_code
            ),
            None,
        )
        if not metric:
            raise ValueError(f"设备 {device_code} 不支持指标 {metric_code}")

        return self._create_event(device_code, metric, rng or random.Random())

    def generate_cycle(self, profiles=None, rng=None):
        profiles = self.profiles() if profiles is None else profiles
        rng = rng or random.Random()
        return [
            self._create_event(profile["device_code"], metric, rng)
            for profile in profiles
            for metric in profile["metrics"]
        ]

    def _create_event(self, device_code, metric, rng):
        metric_code = metric["metric_code"]
        generator = self._generators.get(metric_code)
        if generator is None:
            raise ValueError(f"没有为指标 {metric_code} 配置模拟数据生成器")

        return {
            "eventId": str(uuid.uuid4()),
            "deviceCode": device_code,
            "metricCode": metric_code,
            "value": generator.generate(rng or random.Random()),
            "unit": metric["unit"],
            "eventTime": utc_iso(),
        }

    def produce(self, stop_event, event_queue, interval, error_queue, profiles):
        try:
            if not profiles:
                raise ValueError("没有启用的设备可供模拟")

            rng = random.Random()
            while not stop_event.is_set():
                for event in self.generate_cycle(profiles, rng):
                    if stop_event.is_set():
                        break
                    event_queue.put(event)
                stop_event.wait(interval)
        except Exception as exc:
            error_queue.put(str(exc))


# services/monitor_backend.py
class MonitorBackend:
    """供界面调用的后端门面；数据库连接不暴露给 UI。"""

    _API_METHODS = {
        "acknowledge_alert",
        "add_user",
        "audit",
        "authenticate",
        "ingest_json",
        "latest_aggregate",
        "latest_events",
        "list_alerts",
        "list_audit",
        "list_devices",
        "list_dlq",
        "list_metrics",
        "list_rules",
        "list_users",
        "process_event",
        "query_history",
        "reset_telemetry",
        "save_device",
        "save_rule",
        "set_device_enabled",
        "set_user_enabled",
        "stats",
        "toggle_rule",
    }

    def __init__(self, store=None):
        self._store = store or Store()
        self.simulator = SimulatorService(self._store)

    @property
    def database_path(self):
        return self._store.path

    def close(self):
        self._store.close()

    def __getattr__(self, name):
        if name not in self._API_METHODS:
            raise AttributeError(name)
        return getattr(self._store, name)
