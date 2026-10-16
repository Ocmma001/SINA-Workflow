import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from import_assets import restore


class AssetTests(unittest.TestCase):
    def fixture(self, directory, payload=b'weights', actual=b'weights'):
        root = Path(directory) / 'repo'
        (root / 'assets').mkdir(parents=True)
        (root / 'assets/manifest.json').write_text(json.dumps({'files': {
            'weights/model.pt': hashlib.sha256(payload).hexdigest()}}), encoding='utf-8')
        archive = Path(directory) / 'assets.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('weights/model.pt', actual)
        return root, archive

    def test_import_is_verified_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root, archive = self.fixture(directory)
            self.assertEqual(restore(archive, root), 1)
            self.assertEqual(restore(archive, root), 1)
            self.assertEqual((root / 'weights/model.pt').read_bytes(), b'weights')

    def test_corrupt_archive_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root, archive = self.fixture(directory, actual=b'wrong')
            with self.assertRaises(ValueError):
                restore(archive, root)
            self.assertFalse((root / 'weights/model.pt').exists())

    def test_does_not_overwrite_teammate_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            root, archive = self.fixture(directory)
            target = root / 'weights/model.pt'
            target.parent.mkdir()
            target.write_bytes(b'teammate experiment')
            with self.assertRaises(ValueError):
                restore(archive, root)
            self.assertEqual(target.read_bytes(), b'teammate experiment')
