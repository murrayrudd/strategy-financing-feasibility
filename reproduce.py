"""Offline reproduction: quick figures/tables, verification, or full simulations."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['quick', 'verify', 'full'], nargs='?', default='quick')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    logdir = ROOT / 'build/logs'
    logdir.mkdir(parents=True, exist_ok=True)
    steps = []
    def run(script, *arguments):
        command = [sys.executable, str(ROOT / script), *map(str, arguments)]
        start = time.monotonic()
        print('Running', script, *arguments, flush=True)
        log = logdir / (str(len(steps) + 1).zfill(2) + '_' + Path(script).stem + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            print(log.read_text()[-12000:])
            raise SystemExit(f'Failed: {script}. Full log: {log.relative_to(ROOT)}')
        steps.append(dict(script=script, arguments=list(arguments), seconds=round(time.monotonic() - start, 2)))

    run('scripts/unpack_data.py')
    if args.mode == 'full':
        # Never silently reuse retained searches when a full rerun was requested.
        backup = ROOT / 'build/retained_search_jobs'
        jobs = ROOT / 'inverse/results/jobs'
        if backup.exists():
            raise SystemExit('A full rerun backup already exists. Use a fresh release copy to start another full run.')
        shutil.move(str(jobs), str(backup))
        run('research/parse_filings.py')
        run('research/build_panel.py')
        run('research/empirical_tests.py')
        run('research/diagnostics.py')
        run('validation/historical_validation.py')
        run('validation/endpoint_diagnostics.py')
        run('validation/scenario_study.py', '--force')
        run('validation/supplemental_study.py')
        run('validation/analyze_study.py')
        run('validation/analyze_supplement.py')
        run('validation/verify_study.py')
        run('validation/revision_controls.py')
        run('validation/preferred_reconciliation.py')
        run('validation/verify_revision.py')
        run('inverse/study.py', '--workers', args.workers)
    if args.mode in ('verify', 'full'):
        run('validation/historical_validation.py')
        run('inverse/verify.py', '--builder-only')
        run('inverse/verify_package.py')
    run('inverse/analyze.py')
    run('publication/prepare_data.py')
    run('publication/build_figures.py')
    run('publication/build_tables.py')
    run('scripts/check_results.py')
    report = dict(mode=args.mode, python=sys.version.split()[0], steps=steps,
                  full_simulation_rerun=args.mode == 'full', finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    (ROOT / 'build/reproduction_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Completed. Figures: publication/figures; tables: publication/tables; checks: build/')


if __name__ == '__main__':
    main()
