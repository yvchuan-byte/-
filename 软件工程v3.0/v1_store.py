import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROLE_LABELS = {
    "ADMIN": "系统管理员",
    "OPERATOR": "运维人员",
    "VIEWER": "只读用户",
}

DEMO_USERS = (
    ("admin", "admin123", "系统管理员", "ADMIN"),
    ("operator", "operator123", "运维人员", "OPERATOR"),
    ("viewer", "viewer123", "只读用户", "VIEWER"),
)

DEMO_DEVICES = (
    ("POWER-A-01", "A栋西区电表", "电表", "A栋西区", "西区配电间"),
    ("POWER-A-02", "A栋东区电表", "电表", "A栋东区", "东区配电间"),
    ("ENV-A-01", "A栋环境传感器", "环境传感器", "A栋西区", "西区走廊"),
    ("AIR-B-01", "B栋空气质量传感器", "空气质量传感器", "B栋一层", "一层大厅"),
)

DEMO_METRICS = (
    ("power", "有功功率", "kW", 0, 2000),
    ("temperature", "温度", "℃", -20, 80),
    ("humidity", "湿度", "%", 0, 100),
    ("pm25", "PM2.5", "μg/m³", 0, 1000),
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return "%s$%s" % (salt.hex(), digest.hex())


def _verify_password(password, encoded):
    try:
        salt_hex, digest_hex = encoded.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 200_000
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


class V1Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        self._seed_data()

    def _create_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sys_user (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role_code TEXT NOT NULL
                    CHECK (role_code IN ('ADMIN', 'OPERATOR', 'VIEWER')),
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

            CREATE TABLE IF NOT EXISTS telemetry_event (
                event_id TEXT PRIMARY KEY,
                device_code TEXT NOT NULL REFERENCES device(device_code),
                metric_code TEXT NOT NULL REFERENCES metric_definition(metric_code),
                metric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                event_time TEXT NOT NULL,
                received_at TEXT NOT NULL,
                raw_payload TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _seed_data(self):
        now = _now()
        with self.conn:
            if not self.conn.execute("SELECT 1 FROM sys_user LIMIT 1").fetchone():
                self.conn.executemany(
                    """
                    INSERT INTO sys_user
                    (username, password_hash, display_name, role_code, enabled, created_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    """,
                    [
                        (username, _hash_password(password), display, role, now)
                        for username, password, display, role in DEMO_USERS
                    ],
                )
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO device
                (device_code, device_name, device_type, area_code, location_desc,
                 enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                [(*device, now, now) for device in DEMO_DEVICES],
            )
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO metric_definition
                (metric_code, metric_name, unit, min_value, max_value, enabled)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                DEMO_METRICS,
            )

    def authenticate(self, username, password):
        row = self.conn.execute(
            """
            SELECT username, password_hash, display_name, role_code, enabled
            FROM sys_user WHERE username=?
            """,
            ((username or "").strip(),),
        ).fetchone()
        if not row or not row["enabled"] or not _verify_password(
            password or "", row["password_hash"]
        ):
            return None
        return {
            "username": row["username"],
            "display_name": row["display_name"],
            "role_code": row["role_code"],
            "role_name": ROLE_LABELS[row["role_code"]],
        }

    def list_devices(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM device ORDER BY area_code, device_code"
            ).fetchall()
        ]

    def list_metrics(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM metric_definition ORDER BY metric_code"
            ).fetchall()
        ]

    def save_device(self, data):
        code = str(data.get("device_code", "")).strip()
        name = str(data.get("device_name", "")).strip()
        device_type = str(data.get("device_type", "")).strip()
        area = str(data.get("area_code", "")).strip()
        location = str(data.get("location_desc", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", code):
            raise ValueError("设备编号须为 2–64 位英文、数字、下划线或连字符")
        if not name or not area:
            raise ValueError("设备名称和所属区域不能为空")

        now = _now()
        with self.conn:
            existing = self.conn.execute(
                "SELECT 1 FROM device WHERE device_code=?", (code,)
            ).fetchone()
            is_edit = bool(data.get("is_edit"))
            if existing and not is_edit:
                raise ValueError("设备编号已存在")
            if not existing and is_edit:
                raise ValueError("待编辑设备不存在")
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
            else:
                self.conn.execute(
                    """
                    INSERT INTO device
                    (device_code, device_name, device_type, area_code, location_desc,
                     enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (code, name, device_type, area, location, now, now),
                )

    def set_device_enabled(self, device_code, enabled):
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE device SET enabled=?, updated_at=? WHERE device_code=?",
                (int(bool(enabled)), _now(), device_code),
            )
            if cursor.rowcount != 1:
                raise ValueError("设备不存在")

    def close(self):
        self.conn.close()
