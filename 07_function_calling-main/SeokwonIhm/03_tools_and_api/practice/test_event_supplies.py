import unittest

from pydantic import ValidationError

from event_supplies import SupplyResult, calculate_supplies


class EventSuppliesTests(unittest.TestCase):
    def test_default_reserve_and_box_rounding(self):
        result = calculate_supplies.invoke({"participants": 23})
        self.assertEqual(result.model_dump(), {
            "participants": 23, "reserve_percent": 10,
            "servings": 26, "water_bottles": 26, "snack_boxes": 3,
        })

    def test_explicit_zero_and_upper_boundary(self):
        result = calculate_supplies.invoke({"participants": 20, "reserve_percent": 0})
        self.assertEqual((result.servings, result.snack_boxes), (20, 2))
        result = calculate_supplies.invoke({"participants": 500, "reserve_percent": 30})
        self.assertEqual((result.servings, result.snack_boxes), (650, 65))

    def test_invalid_inputs_are_not_normal_results(self):
        for args in [{}, {"participants": 0}, {"participants": 501},
                     {"participants": "23"}, {"participants": True},
                     {"participants": 23, "reserve_percent": 31},
                     {"participants": 23, "extra": 1}]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                calculate_supplies.invoke(args)

    def test_wrong_calculated_output_is_rejected(self):
        for change in [{"servings": 25}, {"water_bottles": 25}, {"snack_boxes": 2}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                SupplyResult.model_validate({
                    "participants": 23, "reserve_percent": 10,
                    "servings": 26, "water_bottles": 26, "snack_boxes": 3,
                    **change,
                })


if __name__ == "__main__":
    unittest.main()
