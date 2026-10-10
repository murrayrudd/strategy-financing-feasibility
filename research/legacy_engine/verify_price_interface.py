"""Reproduce the preserved 750-record archive through the new price adapter."""
from pathlib import Path
import hashlib
import json
import lzma

from price_interface.adapter import run_price_scenario, replay
from price_interface.providers import from_engine_path

ROOT = Path(__file__).resolve().parent
ECONOMIC_FIELDS = ('complete','expected_event_count','initial_snapshot','snapshots',
    'ledger','failure','unprocessed_path','assessment','reconciliation',
    'generated_payments','financing_decisions')


def check_preservation():
    manifest=json.loads((ROOT/'MANIFEST_v0.6.0.json').read_text())
    files={p:h for p,h in manifest['files'].items()
           if p.startswith(('treasury_company/','calibration/'))}
    for path, expected in files.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise AssertionError('Original engine/calibration changed: '+path)
    report=dict(files_checked=len(files), all_original_hashes_match=True, sha256=files)
    (ROOT/'interface_results').mkdir(exist_ok=True)
    (ROOT/'interface_results'/'preservation_checks.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    preserved=check_preservation()
    count=failed=0
    with lzma.open(ROOT/'revision'/'paths.jsonl.xz','rt',encoding='utf-8') as stream:
        for line in stream:
            old=json.loads(line)
            prices=from_engine_path(old,old['configuration_id'])
            new=run_price_scenario(old,prices,daily_valuation=False)
            for key in ECONOMIC_FIELDS:
                if new['corporate_result'][key] != old[key]:
                    raise AssertionError((old['configuration_id'],key))
            replay(new)
            count+=1;failed+=not old['complete']
    print('Archive economic equivalence and full interface replay:',count,'records;',failed,'failed continuations')
    dest=ROOT/'interface_results';dest.mkdir(exist_ok=True)
    report=dict(archive_records_checked=count,failed_continuations_checked=failed,
        exact_economic_fields=list(ECONOMIC_FIELDS),all_economic_fields_identical=True,
        all_interface_records_replayed=True,
        preserved_engine_and_calibration_files=preserved['files_checked'],
        note='Identifiers, input hashes, and added price provenance change intentionally. No fitted or historical price dataset is implied.')
    (dest/'benchmark_verification.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
