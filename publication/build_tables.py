"""Rebuild the six numerical Results/Appendix E tables as CSV and Markdown."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'publication/tables'
OUT.mkdir(exist_ok=True)
X = pd.read_csv(ROOT / 'inverse/results/scenario_evaluations.csv')
F = pd.read_csv(ROOT / 'inverse/results/required_conditions.csv')
V = pd.read_csv(ROOT / 'inverse/results/valuation_requirements_summary.csv')
tables = []


def save(name, title, headers, rows):
    frame = pd.DataFrame(rows, columns=headers)
    frame.to_csv(OUT / (name + '.csv'), index=False)
    text = [f'## {title}', '', '| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for row in rows:
        text.append('| ' + ' | '.join(str(v).replace('\n', ' ') for v in row) + ' |')
    tables.append('\n'.join(text))


rows = []
for perm, label in [('restricted', 'Restricted'), ('reserve_flexible', 'Flexible')]:
    for regime, access in [('open', 'Open'), ('capacity', 'Capacity constrained'), ('drawdown_closure', 'Drawdown closure')]:
        r = V[(V.target == 'nominal_value') & (V.permission == perm) & (V.regime == regime)].iloc[0]
        rows.append([label, access, f'{int(r.feasible_within_domain)}/{int(r.cases)}', f'{r["median"]:.3f}', f'{r.minimum:.3f}–{r.maximum:.3f}'])
save('table_2', 'Table 2. Valuation required to preserve nominal common value', ['Reserve use', 'Financing access', 'Solutions', 'Median factor', 'Factor range'], rows)

targets = ['funded', 'nominal_value', 'annual_5pct', 'bitcoin_per_share']
q = pd.read_csv(ROOT / 'publication/data/figure_3_bitcoin_requirements.csv')
rows = []
for window, label in [('2021-11-01', 'Nov 2021'), ('2022-05-01', 'May 2022'), ('2023-01-01', 'Jan 2023')]:
    for shape, shapename in [('historical', 'Historical'), ('smooth_matched', 'Smooth')]:
        group = q[(q.window == window) & (q['shape'] == shape)].set_index('target')
        values = [group.loc[t, 'required_terminal_bitcoin_usd'] for t in targets]
        rows.append([label + ' ' + shapename] + ['None found' if pd.isna(v) else f'{v / 1000:.1f}' for v in values])
save('table_3', 'Table 3. Required terminal Bitcoin prices ($ thousands)', ['Path source and shape', 'Payments and reserves', 'Nominal common value', '5% annual common return', 'Bitcoin-per-share'], rows)

s = X[X.kind == 'strc']
g = s[(s.window == '2022-05-01') & (s['shape'] == 'historical') & (s.premium == 'persistence') & (s.policy == 'reference') & (s.regime == 'drawdown_closure') & (s.future_strc_rate == .12)].sort_values('strc_scale')
assert len(g) == 3
metrics = [('STRC gross proceeds ($bn)', 'strc_gross_usd', 1e9, 3), ('Common gross proceeds ($bn)', 'common_gross_usd', 1e9, 3), ('Common-share growth (%)', 'common_share_growth', .01, 2), ('Bitcoin sold', 'bitcoin_sold', 1, 0), ('Closing Bitcoin holdings', 'final_bitcoin', 1, 0), ('Bitcoin-per-share change (%)', 'bitcoin_per_share_change', .01, 2), ('Common return (%)', 'common_return', .01, 2), ('Annual STRC distributions ($bn)', 'annualized_strc_distribution_usd', 1e9, 3)]
save('table_4', 'Table 4. STRC financing in the May 2022 historical path', ['Outcome', 'No new STRC', 'Half program', 'Full program'], [[label] + [f'{v/div:,.{digits}f}' for v in g[col]] for label, col, div, digits in metrics])

v = X[(X.axis == 'valuation') & (X.policy == 'reference') & X.coordinate.isin([.5, 1., 2.])]
rows = []
for perm, label in [('restricted', 'Restricted'), ('reserve_flexible', 'Flexible')]:
    for x in [.5, 1., 2.]:
        group = v[(v.permission == perm) & (v.coordinate == x)]
        assert len(group) == 294
        rows.append([label, f'{x:g}'] + [int(group[c].sum()) for c in ['payments', 'funded', 'nominal_value', 'annual_5pct', 'bitcoin_per_share']])
save('table_E1', 'Table E1. Outcomes at three valuation multiplier settings', ['Reserve use', 'Closing factor', 'Payments', 'Payments and reserves', 'Nominal value', '5% annual return', 'Bitcoin-per-share'], rows)

rows = []
for target, label in [('payments', 'Payments'), ('funded', 'Payments and reserves'), ('nominal_value', 'Nominal common value'), ('annual_5pct', '5% annual common return'), ('bitcoin_per_share', 'Bitcoin per share')]:
    values = []
    for perm in ['restricted', 'reserve_flexible']:
        group = F[(F.axis == 'capacity') & (F.permission == perm) & (F.target == target)]
        assert len(group) == 108
        values.extend([int(group.lowest_feasible_tested.count()), int((group.lowest_feasible_tested == 0).sum()), f'{group.lowest_feasible_tested.median():.3f}'])
    rows.append([label] + values)
save('table_E2', 'Table E2. Financing capacity required across 108 cases per reserve policy', ['Target', 'Restricted solutions', 'At zero (restricted)', 'Median factor (restricted)', 'Flexible solutions', 'At zero (flexible)', 'Median factor (flexible)'], rows)

bt = pd.read_csv(ROOT / 'research/results/backtest_metrics.csv')
rows = []
for horizon in [4, 13, 26, 52]:
    group = bt[(bt.period == '2024_2025') & (bt.route == 'asof') & (bt.basis == 'continuation') & (bt.horizon_weeks == horizon)].set_index('model')
    rows.append([horizon, int(group.loc['hold', 'n'])] + [f'{group.loc[m, "mae_log"]:.3f}' for m in ['hold', 'mean_reversion', 'macro_response']] + [f'{group.loc["mean_reversion", "coverage90"]:.0%}'])
save('table_E3', 'Table E3. Later conditional valuation errors', ['Horizon weeks', 'Origins', 'Fixed multiplier', 'Mean reversion', 'Four factors', 'Reversion interval coverage'], rows)
(OUT / 'numerical_tables.md').write_text('# Reproduced numerical tables\n\n' + '\n\n'.join(tables) + '\n')
print('Rebuilt six numerical tables: 2, 3, 4, E1, E2, E3.')
