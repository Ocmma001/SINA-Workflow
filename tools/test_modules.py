"""Stage boundaries must stay usable without a desktop or network API."""
import unittest
from modules.pins import locate_pin, attach_pins
from modules.image_io import read_image


class ModuleTests(unittest.TestCase):
    def test_pins_keep_unresolved_and_coordinates(self):
        class Grid:
            shape = (3, 10)
            def __getitem__(self, pos):
                return 4 if pos == (1, 9) else 0
        circuit = [{'id': 'R_1', 'connection_points': [[0, 1], [9, 1]]}]
        pins = attach_pins(circuit, Grid(), radius=2)['R_1']
        self.assertIsNone(pins[0]['connection_candidate'])
        self.assertEqual(pins[1]['connection_candidate']['region'], 4)
        self.assertEqual(pins[0]['image_point'], [0, 1])
        self.assertEqual(circuit[0]['connection_points'], [[0, 1], [9, 1]])

    def test_invalid_image_is_explicit_error(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '不是图片.png'
            path.write_bytes(b'not an image')
            with self.assertRaises(ValueError):
                read_image(path)

    def test_legacy_pin_import_delegates(self):
        from training_contract import locate_pin as legacy
        self.assertIs(legacy, locate_pin)


if __name__ == '__main__':
    unittest.main()
