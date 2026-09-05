import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "compare_farmland_maps.py"
SPEC = importlib.util.spec_from_file_location("compare_farmland_maps", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FarmlandMapCompareTest(unittest.TestCase):
    def _write_map(self, directory: Path, name: str, rows) -> Path:
        width, height = 160, 120
        resolution = 0.05
        origin_x, origin_y = -4.0, -3.0
        pixels = ["254"] * (width * height)
        for world_y in rows:
            grid_y = round((world_y - origin_y) / resolution)
            image_row = height - 1 - grid_y
            for grid_x in range(round(1.6 / resolution), round(6.4 / resolution)):
                pixels[image_row * width + grid_x] = "0"

        pgm_path = directory / f"{name}.pgm"
        pgm_path.write_text(
            f"P2\n{width} {height}\n255\n" + "\n".join(pixels) + "\n",
            encoding="ascii",
        )
        yaml_path = directory / f"{name}.yaml"
        yaml_path.write_text(
            f"image: {name}.pgm\n"
            "resolution: 0.05\n"
            "origin: [-4.0, -3.0, 0.0]\n",
            encoding="ascii",
        )
        return yaml_path

    def test_repeated_maps_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = self._write_map(directory, "first", (-1.42, 0.0, 1.42))
            second = self._write_map(directory, "second", (-1.42, 0.0, 1.42))
            _, _, errors = MODULE.compare_maps(
                first,
                second,
                ROOT / "src/spore_patrol_sim/config/farmland_layout.json",
            )
            self.assertEqual(errors, [])

    def test_row_shift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = self._write_map(directory, "first", (-1.42, 0.0, 1.42))
            second = self._write_map(directory, "second", (-1.42, 0.0, 1.60))
            _, _, errors = MODULE.compare_maps(
                first,
                second,
                ROOT / "src/spore_patrol_sim/config/farmland_layout.json",
            )
            self.assertTrue(any("center shift" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
