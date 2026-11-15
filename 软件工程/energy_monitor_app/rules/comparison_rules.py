from energy_monitor_app.rules.base_rule import BaseRule


class GTRule(BaseRule):
    def evaluate(self, value):
        return value > self.threshold_value


class GERule(BaseRule):
    def evaluate(self, value):
        return value >= self.threshold_value


class LTRule(BaseRule):
    def evaluate(self, value):
        return value < self.threshold_value


class LERule(BaseRule):
    def evaluate(self, value):
        return value <= self.threshold_value


class BetweenRule(BaseRule):
    def evaluate(self, value):
        return self.threshold_value <= value <= self.threshold_upper
