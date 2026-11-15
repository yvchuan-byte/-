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
