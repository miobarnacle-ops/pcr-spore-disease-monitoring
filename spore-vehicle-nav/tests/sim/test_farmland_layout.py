#!/usr/bin/env python3

import copy
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "validate_farmland_layout.py"
SPEC = importlib.util.spec_from_file_location("validate_farmland_layout", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FarmlandLayoutTest(unittest.TestCase):
    def setUp(self):
        self.layout = MODULE.load_layout(
            ROOT / "src" / "spore_patrol_sim" / "config" / "farmland_layout.json"
        )
        self.world = ROOT / "src" / "spore_patrol_sim" / "worlds" / "farmland_8x6.world"

    def test_canonical_layout_passes(self):
        errors, metrics = MODULE.validate_layout(self.layout)
        self.assertEqual(errors, [])
        self.assertAlmostEqual(metrics["min_clear_corridor_m"], 1.20, places=6)
        self.assertAlmostEqual(metrics["headland_m"], 1.60, places=6)

    def test_world_matches_layout(self):
        self.assertEqual(MODULE.validate_world(self.layout, self.world), [])

    def test_insufficient_corridor_is_rejected(self):
        invalid = copy.deepcopy(self.layout)
        invalid["rows"]["required_clear_corridor_m"] = 1.25
        errors, _ = MODULE.validate_layout(invalid)
        self.assertTrue(any("clear corridor" in error for error in errors))

    def test_short_headland_is_rejected(self):
        invalid = copy.deepcopy(self.layout)
        invalid["rows"]["length_m"] = 5.20
        errors, _ = MODULE.validate_layout(invalid)
        self.assertTrue(any("headland" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
