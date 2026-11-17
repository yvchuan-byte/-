import json
import math
import queue
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from v1_store import V1Store, _now


class V2Store(V1Store):
    def _create_ingest_schema(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_error (
                    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_payload TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def __init__(self, path):
        super().__init__(path)
        self._create_ingest_schema()

    def _reject(self, raw, reason):
        with self.conn:
            self.conn.execute(
                "INSERT INTO ingest_error(raw_payload, reason, created_at) VALUES (?, ?, ?)",
                (str(raw)[:20000], str(reason)[:500], _now()),
            )
        return {"status": "INVALID", "message": reason}

    def ingest_event(self, payload, raw_text=None):
        if raw_text is None:
            try:
                raw_text = json.dumps(payload, ensure_ascii=False, allow_nan=True)
            except (TypeError, ValueError):
                raw_text = str(payload)

        if not isinstance(payload, dict):
            return self._reject(raw_text, "消息必须是 JSON 对象")
        allowed = {"eventId", "deviceCode", "metricCode", "value", "unit", "eventTime"}
        required = allowed
        if set(payload) - allowed:
            return self._reject(raw_text, "消息包含未定义字段")
        if required - set(payload):
            return self._reject(raw_text, "消息缺少必需字段")

        event_id = payload["eventId"]
        device_code = payload["deviceCode"]
        metric_code = payload["metricCode"]
        unit = payload["unit"]
        value = payload["value"]
        event_time = payload["eventTime"]
        if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 128:
            return self._reject(raw_text, "eventId 必须是有效字符串")
        try:
            uuid.UUID(event_id)
        except (ValueError, AttributeError, TypeError):
            return self._reject(raw_text, "eventId 必须是 UUID")
        if not isinstance(device_code, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{2,64}", device_code
        ):
            return self._reject(raw_text, "deviceCode 格式无效")
        if not isinstance(metric_code, str) or not 1 <= len(metric_code) <= 48:
            return self._reject(raw_text, "metricCode 格式无效")
        if not isinstance(unit, str) or not unit.strip():
            return self._reject(raw_text, "unit 不能为空")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return self._reject(raw_text, "value 必须是数值")
        value = float(value)
        if not math.isfinite(value):
            return self._reject(raw_text, "value 必须是有限数值")
        if not isinstance(event_time, str):
            return self._reject(raw_text, "eventTime 必须是 ISO 8601 时间")
        try:
            parsed_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                raise ValueError("时间必须包含时区")
            parsed_time = parsed_time.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            return self._reject(raw_text, "eventTime 必须是带时区的 ISO 8601 时间")
        canonical_time = parsed_time.isoformat().replace("+00:00", "Z")

        device = self.conn.execute(
            "SELECT enabled FROM device WHERE device_code=?", (device_code,)
        ).fetchone()
        if not device or not device["enabled"]:
            return self._reject(raw_text, "设备不存在或已停用")
        metric = self.conn.execute(
            "SELECT unit, min_value, max_value, enabled FROM metric_definition WHERE metric_code=?",
            (metric_code,),
        ).fetchone()
        if not metric or not metric["enabled"]:
            return self._reject(raw_text, "指标不存在或已停用")
        if unit != metric["unit"]:
            return self._reject(raw_text, "指标单位不匹配")
        if metric["min_value"] is not None and value < metric["min_value"]:
            return self._reject(raw_text, "数值低于指标允许范围")
        if metric["max_value"] is not None and value > metric["max_value"]:
            return self._reject(raw_text, "数值高于指标允许范围")

        if self.conn.execute(
            "SELECT 1 FROM telemetry_event WHERE event_id=?", (event_id,)
        ).fetchone():
            return {"status": "DUPLICATE", "message": "重复事件已忽略"}

        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO telemetry_event
                    (event_id, device_code, metric_code, metric_value, unit,
                     event_time, received_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, device_code, metric_code, value, unit,
                        canonical_time, _now(), str(raw_text)[:20000],
                    ),
                )
        except sqlite3.IntegrityError as exc:
            return self._reject(raw_text, f"数据写入失败：{exc}")
        return {"status": "OK", "message": "数据已入库", "eventId": event_id}

    def ingest_json(self, raw_text):
        try:
            payload = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
            return self._reject(raw_text, f"JSON 解析失败：{exc}")
        return self.ingest_event(payload, raw_text=raw_text)

    def import_file(self, path):
        if str(path).lower().endswith((".jsonl", ".ndjson")):
            results = []
            with open(path, "r", encoding="utf-8-sig") as source:
                for line_number, line in enumerate(source, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError as exc:
                        results.append(
                            self._reject(
                                line, f"第 {line_number} 行 JSON 解析失败：{exc}"
                            )
                        )
                        continue
                    results.append(self.ingest_event(payload, raw_text=line))
            return results

        with open(path, "r", encoding="utf-8-sig") as source:
            content = source.read()
        if not content.strip():
            return []
        try:
            document = json.loads(content)
        except json.JSONDecodeError:
            results = []
            for line_number, line in enumerate(content.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    results.append(
                        self._reject(line, f"第 {line_number} 行 JSON 解析失败：{exc}")
                    )
                    continue
                results.append(self.ingest_event(payload, raw_text=line))
            return results

        if isinstance(document, list):
            return [
                self.ingest_event(item, raw_text=json.dumps(item, ensure_ascii=False))
                for item in document
            ]
        return [self.ingest_event(document, raw_text=content)]

    def list_recent_events(self, limit=100):
        rows = self.conn.execute(
            """
            SELECT event_id, device_code, metric_code, metric_value, unit,
                   event_time, received_at
            FROM telemetry_event
            ORDER BY received_at DESC LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_ingest_errors(self):
        return self.conn.execute("SELECT COUNT(*) FROM ingest_error").fetchone()[0]


class QueueProcessor:
    def __init__(self, store, event_queue=None):
        self.store = store
        self.event_queue = event_queue or queue.Queue()

    def process_pending(self, limit=100):
        results = []
        for _ in range(limit):
            try:
                payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                results.append(self.store.ingest_event(payload))
            except Exception as exc:
                raw = json.dumps(payload, ensure_ascii=False, default=str)
                results.append(self.store._reject(raw, f"处理异常：{exc}"))
            finally:
                self.event_queue.task_done()
        return results


class TelemetrySimulator:
    def __init__(self, store):
        self.store = store
        self.profiles = []
        metric_map = {
            metric["metric_code"]: metric
            for metric in store.list_metrics()
            if metric["enabled"]
        }
        for device in store.list_devices():
            if not device["enabled"]:
                continue
            code, kind = device["device_code"], device["device_type"]
            if code.startswith("POWER") or "电表" in kind:
                codes = ("power",)
            elif code.startswith("AIR") or "空气" in kind:
                codes = ("temperature", "humidity", "pm25")
            else:
                codes = ("temperature", "humidity")
            for metric_code in codes:
                metric = metric_map.get(metric_code)
                if metric:
                    self.profiles.append((code, metric_code, metric["unit"]))

    def generate_cycle(self):
        events = []
        for code, metric_code, unit in self.profiles:
            events.append(
                {
                    "eventId": str(uuid.uuid4()),
                    "deviceCode": code,
                    "metricCode": metric_code,
                    "value": self._value(metric_code),
                    "unit": unit,
                    "eventTime": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                }
            )
        return events

    @staticmethod
    def _value(metric_code):
        import random

        ranges = {
            "power": (60, 96),
            "temperature": (21, 31),
            "humidity": (35, 72),
            "pm25": (6, 48),
        }
        outlier_ranges = {
            "power": (102, 130),
            "temperature": (36, 39),
            "humidity": (82, 96),
            "pm25": (80, 150),
        }
        if random.random() < 0.08:
            low, high = outlier_ranges[metric_code]
            return round(random.uniform(low, high), 2)
        low, high = ranges[metric_code]
        return round(random.uniform(low, high), 2)

    def produce(self, stop_event, event_queue, interval):
        while not stop_event.is_set():
            for event in self.generate_cycle():
                if stop_event.is_set():
                    break
                event_queue.put(event)
            stop_event.wait(interval)
