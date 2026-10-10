"""Check manuscript-linked counts and compare regenerated plotting datasets."""
from pathlib import Path
import io
import json
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
x = pd.read_csv(ROOT / 'inverse/results/scenario_evaluations.csv')
f = pd.read_csv(ROOT / 'inverse/results/required_conditions.csv')
assert len(x) == 46481
assert x.job_id.nunique() == 2687
assert f.job_id.nunique() == 1391 and len(f) == 5950
assert int(f.observed_reversal.sum()) == 460
assert len(x[x.kind == 'strc']) == 1296
assert x.loc[x.kind == 'strc', 'funded'].all()
z = x[(x.axis == 'capacity') & (x.coordinate == 0) & (x.permission == 'reserve_flexible')]
assert len(z) == 108 and z.funded.all() and not z.bitcoin_per_share.any()
assert (z.common_gross_usd == 0).all() and (z.strc_gross_usd == 0).all()
assert np.allclose(z.gross_bitcoin_sales_usd, 2695518000, rtol=1e-6)
assert z.nominal_value.sum() == z.annual_5pct.sum() == 48
pairs = pd.read_csv(ROOT / 'inverse/results/strc_matched_comparisons.csv')
s = pairs[(pairs.strc_scale == 1) & (pairs.future_strc_rate == .12)]
assert len(s) == 108 and s.jointly_funded.all()
assert (s.bitcoin_per_share_difference > 1e-10).sum() == 107
assert (s.common_return_difference > 1e-10).sum() == 102
assert round(s.bitcoin_per_share_difference.median() * 100, 2) == 5.41
assert round(s.common_return_difference.median() * 100, 2) == 3.99
b = pd.read_csv(ROOT / 'validation/results/scenario_runs.csv')
assert len(b) == 2646 and b.funded.sum() == 2311
for name in ['figure_1_outcome_counts.csv', 'figure_2_matched_paths.csv', 'figure_3_bitcoin_requirements.csv', 'figure_4_strc_matched_comparisons.csv']:
    with zipfile.ZipFile(ROOT / 'data/publication_reference.zip') as z:
        old = pd.read_csv(io.BytesIO(z.read('data/' + name)))
    new = pd.read_csv(ROOT / 'publication/data' / name)
    pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-12, atol=1e-10)
for name in ['scenario_evaluations.csv', 'required_conditions.csv', 'feasible_bands.csv', 'strc_matched_comparisons.csv']:
    found = False
    for archive in sorted((ROOT / 'data').glob('retained_results_*.zip')):
        with zipfile.ZipFile(archive) as z:
            member = 'inverse/results/' + name
            if member not in z.namelist():
                continue
            old = pd.read_csv(io.BytesIO(z.read(member)))
            new = pd.read_csv(ROOT / 'inverse/results' / name)
            audit_cols = [c for c in old if c.endswith('maximum_arithmetic_error')]
            for c in audit_cols:
                assert np.allclose(old[c], new[c], rtol=0, atol=1e-6, equal_nan=True), c
            pd.testing.assert_frame_equal(old.drop(columns=audit_cols), new.drop(columns=audit_cols), check_exact=False, rtol=1e-12, atol=1e-10)
            found = True
            break
    assert found, name
report = dict(evaluations=46481, jobs=2687, target_searches=5950, reversals=460,
              manuscript_counts_match=True, figure_datasets_match=4, rebuilt_result_tables_match=4,
              full_search_rerun_performed=False,
              note='This check compares retained/rebuilt outputs. The reproduction driver records separately whether every simulation was rerun.')
(ROOT / 'build').mkdir(exist_ok=True)
(ROOT / 'build/result_checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
