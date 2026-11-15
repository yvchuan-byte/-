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

