import queue
import time
import unittest

import web_server
from energy_monitor_app.services.simulator import SimulatorService


class SimulatorBackend:
    def __init__(self):
        self.simulator = SimulatorService(self)
        self.processed_events = []

    def simulator_profiles(self):
        return [
            {
                "device_code": "POWER-A-01",
                "metrics": [{"metric_code": "power", "unit": "kW"}],
            }
        ]

    def process_event(self, event):
        self.processed_events.append(event)


class WebServerSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.originals = (
            web_server.backend,
            web_server.simulator_event_queue,
            web_server.simulator_error_queue,
            web_server.simulator_stop_event,
            web_server.simulator_thread,
            dict(web_server.simulator),
        )
        self.backend = SimulatorBackend()
        web_server.backend = self.backend
        web_server.simulator_event_queue = queue.Queue()
        web_server.simulator_error_queue = queue.Queue()
        web_server.simulator_stop_event = None
        web_server.simulator_thread = None
        web_server.simulator.update(
            running=False, interval=5, last_cycle=0.0, error=""
        )

    def tearDown(self):
        web_server._stop_simulator()
        (
            web_server.backend,
            web_server.simulator_event_queue,
            web_server.simulator_error_queue,
            web_server.simulator_stop_event,
            web_server.simulator_thread,
            previous_state,
        ) = self.originals
        web_server.simulator.clear()
        web_server.simulator.update(previous_state)

    def test_simulator_generates_on_interval_without_dashboard_polling(self):
        web_server._start_simulator(1)
        deadline = time.monotonic() + 3
        while web_server.simulator_event_queue.qsize() < 2:
            if time.monotonic() >= deadline:
                self.fail("simulator did not generate events at the configured interval")
            time.sleep(0.02)

        web_server.RequestHandler._pump_simulator(None)
        self.assertGreaterEqual(len(self.backend.processed_events), 2)

        previous_stop_event = web_server.simulator_stop_event
        web_server._start_simulator(2)
        self.assertTrue(previous_stop_event.is_set())
        self.assertEqual(web_server.simulator["interval"], 2)
        self.assertTrue(web_server.simulator["running"])


if __name__ == "__main__":
    unittest.main()
