from datetime import timedelta

from energy_monitor_app.core.time_utils import utc_now
from _support import StoreTestCase


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
