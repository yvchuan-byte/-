import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from processing_service import V3Store
from telemetry_service import QueueProcessor


class V3ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = V3Store(Path(self.temp_dir.name) / "v3.db")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def event(self, **updates):
        payload = {
            "eventId": str(uuid.uuid4()),
            "deviceCode": "POWER-A-01",
            "metricCode": "power",
            "value": 82.4,
            "unit": "kW",
            "eventTime": datetime.now(timezone.utc).isoformat(),
        }
        payload.update(updates)
        return payload

    def test_minute_aggregate_and_online_device_update(self):
        event_time = datetime.now(timezone.utc).replace(second=10, microsecond=0)
        for value in (80, 100):
            event = self.event(
                value=value,
                eventTime=event_time.isoformat(),
            )
            self.assertEqual(self.store.ingest_event(event)["status"], "OK")

        aggregate = self.store.list_recent_aggregates()[0]
        self.assertEqual(aggregate["sample_count"], 2)
        self.assertEqual(aggregate["avg_value"], 90)
        self.assertEqual(aggregate["min_value"], 80)
        self.assertEqual(aggregate["max_value"], 100)
        device = next(
            item for item in self.store.list_devices()
            if item["device_code"] == "POWER-A-01"
        )
        self.assertEqual(device["status"], "ONLINE")

    def test_duplicate_does_not_change_aggregate(self):
        event = self.event()
        self.assertEqual(self.store.ingest_event(event)["status"], "OK")
        self.assertEqual(self.store.ingest_event(event)["status"], "DUPLICATE")
        aggregate = self.store.list_recent_aggregates()[0]
        self.assertEqual(aggregate["sample_count"], 1)

    def test_alert_triggers_after_consecutive_threshold_matches_and_resolves(self):
        event_time = datetime.now(timezone.utc)
        result = None
        for index in range(3):
            result = self.store.ingest_event(
                self.event(
                    value=130,
                    eventTime=(event_time + timedelta(seconds=index)).isoformat(),
                )
            )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(len(result["alertIds"]), 1)
        self.assertEqual(self.store.list_alerts()[0]["status"], "OPEN")

        recovery = self.store.ingest_event(
            self.event(
                value=80,
                eventTime=(event_time + timedelta(seconds=4)).isoformat(),
            )
        )
        self.assertEqual(recovery["status"], "OK")
        self.assertEqual(self.store.list_alerts()[0]["status"], "RESOLVED")

    def test_alert_acknowledgement_checks_role_and_state(self):
        event_time = datetime.now(timezone.utc)
        for index in range(3):
            result = self.store.ingest_event(
                self.event(
                    value=130,
                    eventTime=(event_time + timedelta(seconds=index)).isoformat(),
                )
            )
        alert_id = result["alertIds"][0]
        ok, _ = self.store.acknowledge_alert(alert_id, "viewer")
        self.assertFalse(ok)
        ok, _ = self.store.acknowledge_alert(alert_id, "operator")
        self.assertTrue(ok)
        self.assertEqual(self.store.list_alerts()[0]["status"], "ACKED")

    def test_late_event_is_counted_as_anomaly(self):
        event = self.event(
            eventTime=(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        )
        self.assertEqual(self.store.ingest_event(event)["status"], "OK")
        aggregate = self.store.list_recent_aggregates()[0]
        self.assertEqual(aggregate["anomaly_count"], 1)

    def test_error_cases_are_detected_and_isolated(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()
        cases = (
            (None, "消息必须是 JSON 对象"),
            ({}, "消息缺少必需字段"),
            (self.event(extraField="not allowed"), "消息包含未定义字段"),
            (self.event(eventId="not-a-uuid"), "eventId 必须是 UUID"),
            (self.event(deviceCode="UNKNOWN-01"), "设备不存在或已停用"),
            (self.event(metricCode="unknown"), "指标不存在或已停用"),
            (self.event(unit="W"), "指标单位不匹配"),
            (self.event(value=True), "value 必须是数值"),
            (self.event(value=float("inf")), "value 必须是有限数值"),
            (self.event(value=3000), "数值高于指标允许范围"),
            (self.event(eventTime="2026-99-99T00:00:00Z"), "eventTime 必须是带时区的 ISO 8601 时间"),
            (self.event(eventTime="2026-11-16T08:00:00"), "eventTime 必须是带时区的 ISO 8601 时间"),
            (self.event(eventTime=future), "事件时间超前当前时间超过 5 分钟"),
        )
        for payload, expected_message in cases:
            with self.subTest(message=expected_message):
                result = self.store.ingest_event(payload)
                self.assertEqual(result["status"], "INVALID")
                self.assertIn(expected_message, result["message"])
        self.assertEqual(len(self.store.list_ingest_errors()), len(cases))
        self.assertEqual(self.store.list_recent_events(), [])

    def test_malformed_json_is_detected(self):
        result = self.store.ingest_json('{"eventId":')
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("JSON 解析失败", result["message"])
        self.assertEqual(len(self.store.list_ingest_errors()), 1)

    def test_queue_continues_after_bad_input_and_valid_event(self):
        processor = QueueProcessor(self.store)
        processor.event_queue.put({"not": "an event"})
        processor.event_queue.put(self.event())
        results = processor.process_pending()
        self.assertEqual(
            [result["status"] for result in results], ["INVALID", "OK"]
        )
        self.assertEqual(len(self.store.list_recent_events()), 1)
        self.assertEqual(
            self.store.list_ingest_errors()[0]["reason"], "消息包含未定义字段"
        )

if __name__ == "__main__":
    unittest.main()
