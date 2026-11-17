import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from telemetry_service import QueueProcessor, TelemetrySimulator, V2Store


class V2IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = V2Store(Path(self.temp_dir.name) / "v2.db")

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

    def test_valid_event_persists_and_duplicate_is_ignored(self):
        event = self.event()
        self.assertEqual(self.store.ingest_event(event)["status"], "OK")
        self.assertEqual(self.store.ingest_event(event)["status"], "DUPLICATE")
        self.assertEqual(len(self.store.list_recent_events()), 1)

    def test_invalid_values_are_isolated_and_recorded(self):
        event = self.event(value=float("nan"))
        result = self.store.ingest_event(event)
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(self.store.count_ingest_errors(), 1)
        self.assertEqual(self.store.list_recent_events(), [])

    def test_jsonl_import_continues_after_bad_line(self):
        valid = self.event()
        path = Path(self.temp_dir.name) / "batch.jsonl"
        path.write_text(
            json.dumps(valid) + "\nnot-json\n" + json.dumps(self.event()) + "\n",
            encoding="utf-8",
        )
        results = self.store.import_file(path)
        self.assertEqual([item["status"] for item in results], ["OK", "INVALID", "OK"])
        self.assertEqual(len(self.store.list_recent_events()), 2)

    def test_queue_continues_after_invalid_event(self):
        processor = QueueProcessor(self.store)
        processor.event_queue.put({"not": "an event"})
        processor.event_queue.put(self.event())
        results = processor.process_pending()
        self.assertEqual([item["status"] for item in results], ["INVALID", "OK"])
        self.assertEqual(len(self.store.list_recent_events()), 1)

    def test_simulator_generates_events_accepted_by_ingestion(self):
        events = TelemetrySimulator(self.store).generate_cycle()
        self.assertTrue(events)
        results = [self.store.ingest_event(event) for event in events]
        self.assertTrue(all(result["status"] == "OK" for result in results))


if __name__ == "__main__":
    unittest.main()
