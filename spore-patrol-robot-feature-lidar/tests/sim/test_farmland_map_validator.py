import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "validate_farmland_map.py"
SPEC = importlib.util.spec_from_file_location("validate_farmland_map", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FarmlandMapValidatorTest(unittest.TestCase):
    def _write_map(self, directory: Path, rows=(-1.42, 0.0, 1.42)) -> Path:
        width, height = 160, 120
        resolution = 0.05
        origin_x, origin_y = -4.0, -3.0
        pixels = ["254"] * (width * height)

        for world_y in rows:
            grid_y = round((world_y - origin_y) / resolution)
            image_row = height - 1 - grid_y
            for grid_x in range(round(1.6 / resolution), round(6.4 / resolution)):
                pixels[image_row * width + grid_x] = "0"

        pgm_path = directory / "farmland.pgm"
        pgm_path.write_text(
            f"P2\n{width} {height}\n255\n" + "\n".join(pixels) + "\n",
            encoding="ascii",
        )
        yaml_path = directory / "farmland.yaml"
        yaml_path.write_text(
            "image: farmland.pgm\n"
            "resolution: 0.05\n"
            "origin: [-4.0, -3.0, 0.0]\n",
            encoding="ascii",
        )
        return yaml_path

    def test_aligned_rows_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            yaml_path = self._write_map(Path(temporary))
            checks, errors = MODULE.check_rows(
                yaml_path,
                ROOT / "src/spore_patrol_sim/config/farmland_layout.json",
            )
            self.assertEqual(errors, [])
            self.assertEqual(len(checks), 3)
            self.assertTrue(all(check.coverage > 0.95 for check in checks))

    def test_missing_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            yaml_path = self._write_map(Path(temporary), rows=(-1.42, 0.0))
            _, errors = MODULE.check_rows(
                yaml_path,
                ROOT / "src/spore_patrol_sim/config/farmland_layout.json",
            )
            self.assertTrue(any("y=1.42" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
