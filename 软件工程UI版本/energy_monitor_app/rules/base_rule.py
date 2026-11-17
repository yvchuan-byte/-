from abc import ABC, abstractmethod


class BaseRule(ABC):
    def __init__(self, threshold_value, threshold_upper=None):
        self.threshold_value = threshold_value
        self.threshold_upper = threshold_upper

    @abstractmethod
    def evaluate(self, value):
        raise NotImplementedError

    def describe(self):
        if self.threshold_upper is not None:
            return f"[{self.threshold_value}, {self.threshold_upper}]"
        return f"{self.threshold_value}"
