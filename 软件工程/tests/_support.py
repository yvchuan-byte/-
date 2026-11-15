import tempfile
import unittest
from pathlib import Path

from energy_monitor_app.core.time_utils import utc_iso
from energy_monitor_app.db.store import Store


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
