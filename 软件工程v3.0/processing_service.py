import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from telemetry_service import V2Store
from v1_store import _now


class V3Store(V2Store):
    def __init__(self, path):
        super().__init__(path)
        self._create_processing_schema()
        self._seed_alert_rules()

    def _create_processing_schema(self):
        device_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(device)").fetchall()
        }
        event_columns = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(telemetry_event)"
            ).fetchall()
        }
        with self.conn:
            if "status" not in device_columns:
                self.conn.execute(
                    "ALTER TABLE device ADD COLUMN status TEXT NOT NULL DEFAULT 'OFFLINE'"
                )
            if "last_seen_at" not in device_columns:
                self.conn.execute(
                    "ALTER TABLE device ADD COLUMN last_seen_at TEXT"
                )
            if "quality_status" not in event_columns:
                self.conn.execute(
                    """
                    ALTER TABLE telemetry_event
                    ADD COLUMN quality_status INTEGER NOT NULL DEFAULT 0
                    """
                )
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metric_aggregate_1m (
                    bucket_start TEXT NOT NULL,
                    device_code TEXT NOT NULL,
                    metric_code TEXT NOT NULL,
                    avg_value REAL NOT NULL,
                    min_value REAL NOT NULL,
                    max_value REAL NOT NULL,
                    sample_count INTEGER NOT NULL,
                    anomaly_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(bucket_start, device_code, metric_code)
                );

                CREATE TABLE IF NOT EXISTS alert_rule (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    device_code TEXT,
                    metric_code TEXT NOT NULL,
                    operator_code TEXT NOT NULL
                        CHECK(operator_code IN ('GT', 'GE', 'LT', 'LE', 'BETWEEN')),
                    threshold_value REAL NOT NULL,
                    threshold_upper REAL,
                    consecutive_count INTEGER NOT NULL DEFAULT 1
                        CHECK(consecutive_count >= 1),
                    severity INTEGER NOT NULL DEFAULT 2
                        CHECK(severity BETWEEN 1 AND 4),
                    cooldown_seconds INTEGER NOT NULL DEFAULT 300
                        CHECK(cooldown_seconds >= 0),
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

                CREATE TABLE IF NOT EXISTS alert_record (
                    alert_id TEXT PRIMARY KEY,
                    rule_id INTEGER NOT NULL,
                    rule_name TEXT NOT NULL,
                    device_code TEXT NOT NULL,
                    metric_code TEXT NOT NULL,
                    trigger_value REAL NOT NULL,
                    severity INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK(status IN ('OPEN', 'ACKED', 'RESOLVED')),
                    triggered_at TEXT NOT NULL,
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    resolved_at TEXT,
                    message TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_aggregate_latest
                    ON metric_aggregate_1m(bucket_start DESC);
                CREATE INDEX IF NOT EXISTS idx_alert_status_time
                    ON alert_record(status, triggered_at DESC);
                """
            )

    def _seed_alert_rules(self):
        now = _now()
        defaults = (
            ("A栋西区功率连续超限", "POWER-A-01", "power", "GT", 100, None, 3, 1, 300),
            ("温度偏高", None, "temperature", "GT", 35, None, 2, 2, 60),
            ("湿度偏高", None, "humidity", "GT", 80, None, 2, 3, 60),
            ("PM2.5偏高", None, "pm25", "GT", 75, None, 2, 2, 60),
        )
        with self.conn:
            for rule in defaults:
                name, device, metric, operator, threshold, upper, count, severity, cooldown = rule
                exists = self.conn.execute(
                    """
                    SELECT 1 FROM alert_rule
                    WHERE rule_name=? AND device_code IS ? AND metric_code=?
                    LIMIT 1
                    """,
                    (name, device, metric),
                ).fetchone()
                if exists:
                    continue
                self.conn.execute(
                    """
                    INSERT INTO alert_rule
                    (rule_name, device_code, metric_code, operator_code,
                     threshold_value, threshold_upper, consecutive_count,
                     severity, cooldown_seconds, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        name, device, metric, operator, threshold, upper,
                        count, severity, cooldown, now, now,
                    ),
                )

    @staticmethod
    def _parse_event_time(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("事件时间必须包含时区")
        return parsed.astimezone(timezone.utc)

    def ingest_event(self, payload, raw_text=None):
        if isinstance(payload, dict) and isinstance(payload.get("eventTime"), str):
            try:
                event_time = self._parse_event_time(payload["eventTime"])
            except (ValueError, OverflowError):
                event_time = None
            if event_time and event_time > datetime.now(timezone.utc) + timedelta(minutes=5):
                if raw_text is None:
                    raw_text = self._raw_payload(payload)
                return self._reject(raw_text, "事件时间超前当前时间超过 5 分钟")

        result = super().ingest_event(payload, raw_text)
        if result["status"] != "OK":
            return result

        event_time = self._parse_event_time(payload["eventTime"])
        event_time_text = event_time.isoformat().replace("+00:00", "Z")
        received_at = _now()
        quality_status = (
            2
            if (datetime.now(timezone.utc) - event_time).total_seconds() > 60
            else 0
        )
        with self.conn:
            self.conn.execute(
                """
                UPDATE telemetry_event
                SET quality_status=?
                WHERE event_id=?
                """,
                (quality_status, result["eventId"]),
            )
            self.conn.execute(
                """
                UPDATE device
                SET status='ONLINE', last_seen_at=?, updated_at=?
                WHERE device_code=?
                """,
                (received_at, received_at, payload["deviceCode"]),
            )
            self._update_aggregate(
                payload["deviceCode"],
                payload["metricCode"],
                event_time,
                received_at,
            )
            result["alertIds"] = self._evaluate_alerts(
                payload["deviceCode"],
                payload["metricCode"],
                float(payload["value"]),
                event_time_text,
                payload["unit"],
            )
        return result

    @staticmethod
    def _raw_payload(payload):
        import json

        return json.dumps(payload, ensure_ascii=False, allow_nan=True, default=str)

    def _update_aggregate(self, device_code, metric_code, event_time, updated_at):
        bucket_start = event_time.replace(second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(minutes=1)
        start_text = bucket_start.isoformat().replace("+00:00", "Z")
        end_text = bucket_end.isoformat().replace("+00:00", "Z")
        row = self.conn.execute(
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
            (device_code, metric_code, start_text, end_text),
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
                start_text, device_code, metric_code, row["avg_value"],
                row["min_value"], row["max_value"], row["sample_count"],
                row["anomaly_count"] or 0, updated_at,
            ),
        )

    def _evaluate_alerts(self, device_code, metric_code, value, event_time, unit):
        rules = self.conn.execute(
            """
            SELECT * FROM alert_rule
            WHERE enabled=1 AND metric_code=?
              AND (device_code IS NULL OR device_code=?)
            """,
            (metric_code, device_code),
        ).fetchall()
        alert_ids = []
        parsed_event_time = self._parse_event_time(event_time)
        for rule in rules:
            matched = self._matches_rule(rule, value)
            state = self.conn.execute(
                """
                SELECT consecutive_count, last_alert_at
                FROM rule_state WHERE rule_id=? AND device_code=?
                """,
                (rule["rule_id"], device_code),
            ).fetchone()
            count = (
                (state["consecutive_count"] + 1 if matched else 0)
                if state
                else (1 if matched else 0)
            )
            last_alert_at = state["last_alert_at"] if state else None
            self.conn.execute(
                """
                INSERT INTO rule_state
                (rule_id, device_code, consecutive_count, last_alert_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(rule_id, device_code)
                DO UPDATE SET consecutive_count=excluded.consecutive_count
                """,
                (rule["rule_id"], device_code, count, last_alert_at),
            )

            if not matched:
                self.conn.execute(
                    """
                    UPDATE alert_record
                    SET status='RESOLVED', resolved_at=?
                    WHERE rule_id=? AND device_code=?
                      AND status IN ('OPEN', 'ACKED')
                    """,
                    (event_time, rule["rule_id"], device_code),
                )
                continue
            if count < rule["consecutive_count"]:
                continue
            active = self.conn.execute(
                """
                SELECT 1 FROM alert_record
                WHERE rule_id=? AND device_code=? AND status IN ('OPEN', 'ACKED')
                LIMIT 1
                """,
                (rule["rule_id"], device_code),
            ).fetchone()
            if active:
                continue
            if last_alert_at and rule["cooldown_seconds"]:
                try:
                    elapsed = (
                        parsed_event_time - self._parse_event_time(last_alert_at)
                    ).total_seconds()
                except (ValueError, OverflowError):
                    elapsed = rule["cooldown_seconds"]
                if elapsed < rule["cooldown_seconds"]:
                    continue

            alert_id = str(uuid.uuid4())
            if rule["operator_code"] == "BETWEEN":
                condition = (
                    f"[{rule['threshold_value']:g}, {rule['threshold_upper']:g}]"
                )
            else:
                operator = {
                    "GT": ">",
                    "GE": ">=",
                    "LT": "<",
                    "LE": "<=",
                }[rule["operator_code"]]
                condition = f"{operator} {rule['threshold_value']:g}"
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
            alert_ids.append(alert_id)
        return alert_ids

    @staticmethod
    def _matches_rule(rule, value):
        operator = rule["operator_code"]
        if operator == "GT":
            return value > rule["threshold_value"]
        if operator == "GE":
            return value >= rule["threshold_value"]
        if operator == "LT":
            return value < rule["threshold_value"]
        if operator == "LE":
            return value <= rule["threshold_value"]
        return rule["threshold_value"] <= value <= rule["threshold_upper"]

    def refresh_device_statuses(self, online_seconds=30):
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=online_seconds)
        ).isoformat().replace("+00:00", "Z")
        with self.conn:
            self.conn.execute(
                """
                UPDATE device
                SET status=CASE
                    WHEN enabled=1 AND last_seen_at>=? THEN 'ONLINE'
                    ELSE 'OFFLINE'
                END
                """,
                (cutoff,),
            )

    def list_devices(self):
        self.refresh_device_statuses()
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM device ORDER BY area_code, device_code"
            ).fetchall()
        ]

    def list_recent_aggregates(self, limit=100):
        rows = self.conn.execute(
            """
            SELECT * FROM metric_aggregate_1m
            ORDER BY bucket_start DESC, updated_at DESC LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_alerts(self, limit=200):
        rows = self.conn.execute(
            """
            SELECT * FROM alert_record
            ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'ACKED' THEN 1 ELSE 2 END,
                     triggered_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [dict(row) for row in rows]

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
            return False, "只有未确认告警可以确认"
        with self.conn:
            self.conn.execute(
                """
                UPDATE alert_record
                SET status='ACKED', acknowledged_by=?, acknowledged_at=?
                WHERE alert_id=? AND status='OPEN'
                """,
                (username, _now(), alert_id),
            )
        return True, "告警已确认"

    def list_ingest_errors(self, limit=200):
        rows = self.conn.execute(
            "SELECT * FROM ingest_error ORDER BY error_id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self):
        self.refresh_device_statuses()
        samples = self.conn.execute(
            "SELECT COUNT(*) FROM telemetry_event"
        ).fetchone()[0]
        online = self.conn.execute(
            "SELECT COUNT(*) FROM device WHERE enabled=1 AND status='ONLINE'"
        ).fetchone()[0]
        total = self.conn.execute(
            "SELECT COUNT(*) FROM device WHERE enabled=1"
        ).fetchone()[0]
        alerts = self.conn.execute(
            "SELECT COUNT(*) FROM alert_record WHERE status IN ('OPEN', 'ACKED')"
        ).fetchone()[0]
        errors = self.count_ingest_errors()
        return {
            "total_samples": samples,
            "online_devices": online,
            "total_devices": total,
            "active_alerts": alerts,
            "error_cases": errors,
        }
