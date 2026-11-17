import tempfile
import unittest
from pathlib import Path

from monitor_service import utc_iso
from monitor_service import Store


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def make_event(self, event_id, device, metric, value, unit, event_time):
        return {
            "eventId": event_id,
            "deviceCode": device,
            "metricCode": metric,
            "value": value,
            "unit": unit,
            "eventTime": utc_iso(event_time),
        }

# test_alerts.py
from datetime import timedelta

from monitor_service import utc_now



class AlertTests(StoreTestCase):
    def test_three_consecutive_over_threshold_triggers_alert(self):
        base = utc_now().replace(second=0, microsecond=0)
        values = (96, 108, 115, 121)

        for index, value in enumerate(values):
            event = self.make_event(
                f"power-sample-{index}",
                "POWER-A-01",
                "power",
                value,
                "kW",
                base + timedelta(seconds=index * 5),
            )
            result = self.store.process_event(event)
            self.assertEqual(result["status"], "OK")

        alerts = self.store.list_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["status"], "OPEN")
        aggregate = self.store.latest_aggregate("POWER-A-01", "power")
        self.assertAlmostEqual(aggregate["avg_value"], 110)
        self.assertEqual(aggregate["min_value"], 96)
        self.assertEqual(aggregate["max_value"], 121)
        self.assertEqual(aggregate["sample_count"], 4)

    def test_alert_acknowledgement(self):
        base = utc_now().replace(second=0, microsecond=0)
        for index, value in enumerate((101, 102, 103)):
            event = self.make_event(
                f"ack-sample-{index}",
                "POWER-A-01",
                "power",
                value,
                "kW",
                base + timedelta(seconds=index * 5),
            )
            self.store.process_event(event)

        alert = self.store.list_alerts()[0]
        ok, _message = self.store.acknowledge_alert(alert["alert_id"], "operator")

        self.assertTrue(ok)
        self.assertEqual(self.store.list_alerts()[0]["status"], "ACKED")


# test_rules.py
import unittest

from monitor_service import RuleFactory


class AlertRuleStrategyTests(unittest.TestCase):
    def test_comparison_strategies(self):
        cases = (
            ("GT", 10, None, 11, True),
            ("GE", 10, None, 10, True),
            ("LT", 10, None, 9, True),
            ("LE", 10, None, 10, True),
            ("BETWEEN", 10, 20, 15, True),
            ("BETWEEN", 10, 20, 21, False),
        )

        for operator, lower, upper, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                rule = RuleFactory.create(operator, lower, upper)
                self.assertEqual(rule.evaluate(value), expected)

    def test_unknown_operator_is_rejected(self):
        with self.assertRaises(ValueError):
            RuleFactory.create("UNKNOWN", 1)


# test_simulator.py
import random
import queue
import threading

from monitor_service import SimulatorService
from monitor_service import MonitorBackend



class SimulatorTests(StoreTestCase):
    def test_cycle_generates_each_supported_metric(self):
        simulator = SimulatorService(self.store)
        profiles = simulator.profiles()
        events = simulator.generate_cycle(profiles, random.Random(7))

        self.assertEqual(
            {event["metricCode"] for event in events},
            {"power", "temperature", "humidity", "pm25"},
        )
        self.assertEqual(len(events), sum(len(p["metrics"]) for p in profiles))

        for event in events:
            result = self.store.process_event(event)
            self.assertEqual(result["status"], "OK")

    def test_single_sample_requires_device_metric_pair(self):
        simulator = SimulatorService(self.store)

        event = simulator.generate_event("AIR-B-01", "pm25", random.Random(1))

        self.assertEqual(event["deviceCode"], "AIR-B-01")
        self.assertEqual(event["metricCode"], "pm25")
        self.assertEqual(event["unit"], "μg/m³")
        with self.assertRaises(ValueError):
            simulator.generate_event("POWER-A-01", "pm25")

    def test_ui_backend_does_not_expose_database_connection(self):
        backend = MonitorBackend(self.store)

        self.assertTrue(backend.stats()["total_devices"] > 0)
        self.assertFalse(hasattr(backend, "conn"))

    def test_background_producer_uses_preloaded_profiles(self):
        simulator = SimulatorService(self.store)
        profiles = simulator.profiles()
        stop_event = threading.Event()
        event_queue = queue.Queue()
        error_queue = queue.Queue()
        worker = threading.Thread(
            target=simulator.produce,
            args=(stop_event, event_queue, 60, error_queue, profiles),
            daemon=True,
        )

        worker.start()
        events = [event_queue.get(timeout=2) for _ in range(7)]
        stop_event.set()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertTrue(error_queue.empty())
        self.assertEqual(
            {event["metricCode"] for event in events},
            {"power", "temperature", "humidity", "pm25"},
        )


# test_telemetry.py
from datetime import timedelta

from monitor_service import utc_now



class TelemetryProcessingTests(StoreTestCase):
    def test_duplicate_is_ignored(self):
        event = self.make_event(
            "test-duplicate-1",
            "POWER-A-01",
            "power",
            80,
            "kW",
            utc_now(),
        )

        first = self.store.process_event(event)
        second = self.store.process_event(event)

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "DUPLICATE")
        aggregate = self.store.latest_aggregate("POWER-A-01", "power")
        self.assertEqual(aggregate["sample_count"], 1)

    def test_one_minute_aggregation(self):
        base = utc_now().replace(second=0, microsecond=0)
        for index, value in enumerate((10, 20)):
            event = self.make_event(
                f"agg-{index}",
                "ENV-A-01",
                "temperature",
                value,
                "℃",
                base + timedelta(seconds=index * 5),
            )
            self.assertEqual(self.store.process_event(event)["status"], "OK")

        aggregate = self.store.latest_aggregate("ENV-A-01", "temperature")
        self.assertAlmostEqual(aggregate["avg_value"], 15)
        self.assertEqual(aggregate["min_value"], 10)
        self.assertEqual(aggregate["max_value"], 20)
        self.assertEqual(aggregate["sample_count"], 2)

    def test_invalid_device_goes_to_dlq(self):
        event = self.make_event(
            "unknown-device-1",
            "UNKNOWN-01",
            "power",
            80,
            "kW",
            utc_now(),
        )

        result = self.store.process_event(event)

        self.assertEqual(result["status"], "INVALID")
        self.assertGreaterEqual(len(self.store.list_dlq()), 1)
