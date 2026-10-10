"""Check published file hashes, data membership, and exclusion of private artifacts."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'provenance/release_files.json').read_text())
for row in manifest['files']:
    p = ROOT / row['path']
    assert p.is_file(), row['path']
    assert len(p.read_bytes()) == row['bytes'], row['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256'], row['path']
    assert row['bytes'] < 20 * 1024 * 1024, row['path']
    assert not p.suffix.lower() in {'.docx', '.doc', '.pptx'}, row['path']
data = json.loads((ROOT / 'data/manifest.json').read_text())
members = 0
for bundle in data['bundles']:
    with zipfile.ZipFile(ROOT / bundle['path']) as z:
        for info in z.infolist():
            name = info.filename.lower()
            assert not any(v in name for v in ['manuscript/', 'paper_content', 'paper_source', 'paper_revision', 'revise_manuscript']), name
            assert not name.endswith(('.docx', '.doc', '.pptx', '.py')), name
            members += 1
print(json.dumps({'published_files_verified': len(manifest['files']), 'data_bundle_members_checked': members,
                  'maximum_file_bytes': max(r['bytes'] for r in manifest['files']),
                  'private_document_paths_absent': True}))
