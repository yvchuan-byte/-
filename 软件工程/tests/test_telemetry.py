from datetime import timedelta

from energy_monitor_app.core.time_utils import utc_now
from _support import StoreTestCase


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
