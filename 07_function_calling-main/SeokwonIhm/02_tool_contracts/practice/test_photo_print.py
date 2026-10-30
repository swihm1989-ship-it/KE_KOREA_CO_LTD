"""실행: python -m unittest discover -s 02_tool_contracts/practice -v"""

import unittest

from pydantic import ValidationError

from photo_print import PhotoPrintArgs, calculate_photo_print, validate_result


class PhotoPrintContractTests(unittest.TestCase):
    def test_quotes_use_the_price_table(self):
        for args, expected in [
            ({"size": "5x7", "quantity": 6}, 4200),
            ({"size": "4x6", "quantity": 3}, 1200),
            ({"size": "4x6", "quantity": 1}, 400),
            ({"size": "5x7", "quantity": 20}, 14000),
        ]:
            with self.subTest(args=args):
                checked = PhotoPrintArgs.model_validate(args)
                result = validate_result(calculate_photo_print.invoke(args), checked)
                self.assertEqual(result.total_fee_won, expected)
                self.assertEqual((result.size, result.quantity),
                                 (args["size"], args["quantity"]))

    def test_bad_arguments_are_rejected_before_calculation(self):
        for change in [
            {"quantity": "6"}, {"quantity": True}, {"quantity": None},
            {"quantity": 0}, {"quantity": 21}, {"size": "8x10"},
            {"unexpected": 1},
        ]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                calculate_photo_print.invoke({"size": "5x7", "quantity": 6, **change})
        with self.assertRaises(ValidationError):
            PhotoPrintArgs.model_validate({"size": "5x7"})

    def test_wrong_integer_fee_and_mismatched_result_are_rejected(self):
        args = PhotoPrintArgs(size="5x7", quantity=6)
        correct = {"size": "5x7", "quantity": 6,
                   "unit_price_won": 700, "total_fee_won": 4200}
        for change in [
            {"total_fee_won": 4100}, {"unit_price_won": 400},
            {"size": "4x6"}, {"quantity": 5},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_result({**correct, **change}, args)

    def test_result_contract_rejects_coercion_and_extra_keys(self):
        args = PhotoPrintArgs(size="5x7", quantity=6)
        correct = {"size": "5x7", "quantity": 6,
                   "unit_price_won": 700, "total_fee_won": 4200}
        for change in [{"total_fee_won": "4200"}, {"extra": 1}]:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                validate_result({**correct, **change}, args)


if __name__ == "__main__":
    unittest.main()
