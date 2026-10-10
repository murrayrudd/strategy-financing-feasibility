"""Maintainer utility: hash explicitly staged/tracked release files."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')[:-1]
assert names, 'Stage the public release files before generating its manifest.'
rows = []
for name in sorted(names):
    if name == 'provenance/release_files.json':
        continue
    path = ROOT / name
    raw = path.read_bytes()
    rows.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
result = dict(version='1.0.0', hash_algorithm='SHA-256', manifest_self_excluded=True, files=rows)
(ROOT / 'provenance/release_files.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'total_bytes': sum(r['bytes'] for r in rows),
                  'maximum_file_bytes': max(r['bytes'] for r in rows)}))
