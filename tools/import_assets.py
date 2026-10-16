"""Restore only hash-verified files from the separately shared resource ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def restore(archive, root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root / 'assets/manifest.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(manifest['files']):
            raise ValueError('Asset archive entries do not match manifest')
        # Validate everything before modifying existing data.
        for name, expected in manifest['files'].items():
            destination = (root / name).resolve()
            if not destination.is_relative_to(root) or destination == root:
                raise ValueError('Invalid asset destination')
            if hashlib.sha256(z.read(name)).hexdigest() != expected:
                raise ValueError(f'Asset hash mismatch: {name}')
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
                raise ValueError(f'Refusing to overwrite a different file: {name}')
        for name in manifest['files']:
            destination = root / name
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(z.read(name))
    return len(manifest['files'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    print(f'Restored/verified {restore(p.parse_args().archive)} assets')
