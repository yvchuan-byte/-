import random
import queue
import threading

from energy_monitor_app.services.simulator import SimulatorService
from energy_monitor_app.services.monitor_backend import MonitorBackend
from _support import StoreTestCase


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
