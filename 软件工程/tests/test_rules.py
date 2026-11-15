import unittest

from energy_monitor_app.rules.rule_factory import RuleFactory


class AlertRuleStrategyTests(unittest.TestCase):
    def test_comparison_strategies(self):
        cases = (
            ("GT", 10, None, 11, True),
            ("GE", 10, None, 10, True),
            ("LT", 10, None, 9, True),
            ("LE", 10, None, 10, True),
            ("BETWEEN", 10, 20, 15, True),
            ("BETWEEN", 10, 20, 21, False),
        )

        for operator, lower, upper, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                rule = RuleFactory.create(operator, lower, upper)
                self.assertEqual(rule.evaluate(value), expected)

    def test_unknown_operator_is_rejected(self):
        with self.assertRaises(ValueError):
            RuleFactory.create("UNKNOWN", 1)


if __name__ == "__main__":
    unittest.main()
