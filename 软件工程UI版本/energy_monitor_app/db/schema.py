from energy_monitor_app.core.security import hash_password
from energy_monitor_app.core.time_utils import utc_iso


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
