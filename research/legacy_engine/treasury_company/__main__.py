import argparse
import json
from pathlib import Path
from .io import run_configuration


def main():
    parser = argparse.ArgumentParser(description='Run a supplied-path treasury-company configuration.')
    parser.add_argument('configuration', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.configuration.read_text(encoding='utf-8'))
    result = run_configuration(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result.to_dict(), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(f'{result.configuration_id}: complete={result.complete}, '
          f'events={len(result.snapshots)}/{result.expected_event_count}')


if __name__ == '__main__':
    main()
