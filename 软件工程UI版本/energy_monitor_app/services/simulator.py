import random
import threading
import uuid
from abc import ABC, abstractmethod

from energy_monitor_app.core.time_utils import utc_iso


class MetricValueGenerator(ABC):
    @abstractmethod
    def generate(self, rng):
        raise NotImplementedError


class PowerValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(60, 96)
        if rng.random() < 0.08:
            value = rng.uniform(102, 130)
        return round(value, 2)


class TemperatureValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(21, 31)
        if rng.random() < 0.08:
            value = rng.uniform(36, 39)
        return round(value, 2)


class HumidityValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(35, 72)
        if rng.random() < 0.08:
            value = rng.uniform(82, 96)
        return round(value, 2)


class PM25ValueGenerator(MetricValueGenerator):
    def generate(self, rng):
        value = rng.uniform(6, 48)
        if rng.random() < 0.08:
            value = rng.uniform(80, 150)
        return round(value, 2)


class SimulatorService:
    """生成遥测数据；线程和队列由 UI 控制，业务事件由后端处理。"""

    def __init__(self, store):
        self.store = store
        self._generators = {
            "power": PowerValueGenerator(),
            "temperature": TemperatureValueGenerator(),
            "humidity": HumidityValueGenerator(),
            "pm25": PM25ValueGenerator(),
        }

    def profiles(self):
        return self.store.simulator_profiles()

    def generate_event(self, device_code, metric_code, rng=None):
        profiles = self.profiles()
        profile = next(
            (item for item in profiles if item["device_code"] == device_code),
            None,
        )
        if not profile:
            raise ValueError(f"设备未启用模拟数据：{device_code}")

        metric = next(
            (
                item for item in profile["metrics"]
                if item["metric_code"] == metric_code
            ),
            None,
        )
        if not metric:
            raise ValueError(f"设备 {device_code} 不支持指标 {metric_code}")

        return self._create_event(device_code, metric, rng or random.Random())

    def generate_cycle(self, profiles=None, rng=None):
        profiles = self.profiles() if profiles is None else profiles
        rng = rng or random.Random()
        return [
            self._create_event(profile["device_code"], metric, rng)
            for profile in profiles
            for metric in profile["metrics"]
        ]

    def _create_event(self, device_code, metric, rng):
        metric_code = metric["metric_code"]
        generator = self._generators.get(metric_code)
        if generator is None:
            raise ValueError(f"没有为指标 {metric_code} 配置模拟数据生成器")

        return {
            "eventId": str(uuid.uuid4()),
            "deviceCode": device_code,
            "metricCode": metric_code,
            "value": generator.generate(rng or random.Random()),
            "unit": metric["unit"],
            "eventTime": utc_iso(),
        }

    def produce(self, stop_event, event_queue, interval, error_queue, profiles):
        try:
            if not profiles:
                raise ValueError("没有启用的设备可供模拟")

            rng = random.Random()
            while not stop_event.is_set():
                for event in self.generate_cycle(profiles, rng):
                    if stop_event.is_set():
                        break
                    event_queue.put(event)
                stop_event.wait(interval)
        except Exception as exc:
            error_queue.put(str(exc))
