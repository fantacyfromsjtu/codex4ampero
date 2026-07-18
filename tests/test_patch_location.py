import unittest

from ampero_control.errors import PlanValidationError
from ampero_control.patch_location import (
    parse_patch_label,
    patch_location_from_index,
)


class PatchLocationTests(unittest.TestCase):
    def test_a50_1_maps_to_linear_index_150(self):
        location = parse_patch_label("A50-1")
        self.assertEqual(location.index, 150)
        self.assertEqual(location.label, "A50-1")

    def test_linear_index_maps_to_bank_and_patch(self):
        location = patch_location_from_index(152)
        self.assertEqual(location.bank, 50)
        self.assertEqual(location.patch, 3)
        self.assertEqual(location.label, "A50-3")

    def test_invalid_patch_label_is_rejected(self):
        with self.assertRaises(PlanValidationError):
            parse_patch_label("A50")


if __name__ == "__main__":
    unittest.main()
