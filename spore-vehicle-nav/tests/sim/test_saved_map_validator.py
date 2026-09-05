#!/usr/bin/env python3

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "validate_saved_map.py"
SPEC = importlib.util.spec_from_file_location("validate_saved_map", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SavedMapValidatorTest(unittest.TestCase):
    def _write_map(self, directory: Path, width: int = 170, height: int = 130):
        yaml_path = directory / "sim_farmland.yaml"
        pgm_path = directory / "sim_farmland.pgm"
        pixels = []
        for y in range(height):
            for x in range(width):
                if x in (10, width - 11) or y in (10, height - 11):
                    pixels.append("0")
                elif 15 < x < width - 15 and 15 < y < height - 15:
                    pixels.append("254")
                else:
                    pixels.append("205")
        pgm_path.write_text(
            "P2\n# generated test map\n"
            f"{width} {height}\n255\n"
            + "\n".join(pixels)
            + "\n",
            encoding="ascii",
        )
        yaml_path.write_text(
            "image: sim_farmland.pgm\nresolution: 0.05\n"
            "origin: [-4.0, -3.0, 0.0]\n",
            encoding="ascii",
        )
        return yaml_path

    def test_structural_map_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            stats = MODULE.inspect_map(self._write_map(Path(temporary)))
            self.assertEqual(MODULE.validate_map(stats), [])
            self.assertEqual((stats.width, stats.height), (170, 130))

    def test_small_blank_map_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            yaml_path = self._write_map(Path(temporary), width=20, height=20)
            stats = MODULE.inspect_map(yaml_path)
            errors = MODULE.validate_map(stats)
            self.assertTrue(any("coverage" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
