"""Expand the five frozen, hash-checked data bundles without network access."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def unpack(force=False):
    manifest = json.loads((ROOT / 'data/manifest.json').read_text())
    written = checked = 0
    for bundle in manifest['bundles']:
        archive = ROOT / bundle['path']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != bundle['sha256']:
            raise ValueError(f'Bundle checksum mismatch: {archive.name}')
        expected = {m['path']: m for m in bundle['members']}
        with zipfile.ZipFile(archive) as z:
            if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
                raise ValueError(f'Bundle members differ: {archive.name}')
            for info in z.infolist():
                rel = PurePosixPath(info.filename)
                dest = ROOT.joinpath(*rel.parts)
                if rel.is_absolute() or '..' in rel.parts or not dest.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError(f'Unsafe archive path: {info.filename}')
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f'Symlink in archive: {info.filename}')
                raw = z.read(info)
                member = expected[info.filename]
                if len(raw) != member['bytes'] or hashlib.sha256(raw).hexdigest() != member['sha256']:
                    raise ValueError(f'Member checksum mismatch: {info.filename}')
                checked += 1
                if dest.exists():
                    if hashlib.sha256(dest.read_bytes()).hexdigest() == member['sha256']:
                        continue
                    if not force:
                        raise ValueError(f'Changed extracted file: {info.filename}. Use a fresh copy, or --force to restore frozen data.')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                written += 1
    print(json.dumps({'bundle_members_checked': checked, 'files_extracted': written}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Restore frozen data over changed extracted files.')
    unpack(parser.parse_args().force)
