from energy_monitor_app.rules.comparison_rules import (
    BetweenRule,
    GERule,
    GTRule,
    LERule,
    LTRule,
)


class RuleFactory:
    @staticmethod
    def create(operator_code, threshold_value, threshold_upper=None):
        if operator_code == "GT":
            return GTRule(threshold_value, threshold_upper)
        if operator_code == "GE":
            return GERule(threshold_value, threshold_upper)
        if operator_code == "LT":
            return LTRule(threshold_value, threshold_upper)
        if operator_code == "LE":
            return LERule(threshold_value, threshold_upper)
        if operator_code == "BETWEEN":
            return BetweenRule(threshold_value, threshold_upper)
        raise ValueError(f"Unsupported operator: {operator_code}")
