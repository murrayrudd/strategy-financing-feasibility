# Results-to-code index

Paths below refer to files after `python scripts/unpack_data.py`.

| Manuscript item | Primary data | Code / check |
|---|---|---|
| Section 4.1; historical reconciliation | `validation/results/historical_replay.csv`, `historical_flow_inputs.csv`, `xbrl_input_evidence.json` | `validation/historical_validation.py` |
| Initial 2,646-case comparison; 335 permission stops | `validation/results/scenario_runs.csv`, `failure_diagnostics.csv` | `validation/scenario_study.py`, `revision_controls.py` |
| Settlement controls: 104 / 98 / 104 completions | `validation/results/revision_runs.csv`, `revision_summary.json` | `validation/settlement_calendar.py`, `revision_controls.py`, `verify_revision.py` |
| Figure 1; Table E1; five outcome counts | `inverse/results/scenario_evaluations.csv` | `publication/prepare_data.py`, `build_figures.py`, `build_tables.py` |
| Figure 2; 441 matched paths / 379 joint completions | `publication/data/figure_2_matched_paths.csv` | `publication/prepare_data.py`, `build_figures.py` |
| Management-rule comparisons | `validation/results/adaptive_pairs.csv`, `principal_buffer_pairs.csv` | `validation/analyze_study.py` |
| Table 2; required valuation | `inverse/results/valuation_requirements_summary.csv` | `inverse/analyze.py`, `publication/build_tables.py` |
| Figure 3; Table 3; Bitcoin conditions | `inverse/results/required_conditions.csv` | `publication/prepare_data.py`, `build_figures.py`, `build_tables.py` |
| Table E2; zero-financing cases | `inverse/results/required_conditions.csv`, `scenario_evaluations.csv` | `inverse/study.py` (capacity axis), `publication/build_tables.py` |
| General-use sale authority | `inverse/results/required_conditions.csv` (sale_authority axis) | `inverse/study.py`, `inverse/replay.py` |
| Figure 4; Table 4; STRC effects | `inverse/results/strc_outcomes.csv`, `strc_matched_comparisons.csv` | `inverse/analyze.py`, publication scripts |
| Historical valuation attribution | `validation/results/endpoint_timing_comparison.json`, `research/results/diagnostic_summary.json` | `validation/endpoint_diagnostics.py`, `research/diagnostics.py` |
| Table E3; conditional errors | `research/results/backtest_metrics.csv`, `conditional_backtests.csv` | `research/empirical_tests.py`, `publication/build_tables.py` |
| Search grids; tolerances; outcome definitions | `inverse/design.json` | `inverse/study.py`, `inverse/verify.py` |
| All evaluated configurations and hash witnesses | `inverse/inputs/`, `inverse/results/jobs/`, `scenario_evaluations.csv` | `inverse/replay.py`, `inverse/verify_package.py` |
| Opening resources and instrument terms | `research/legacy_engine/calibration/`, `examples/strategy_dated_demo.json` | `validation/preferred_reconciliation.py`; source ledgers |

Tables 1 and A1–C1 describe securities, opening inputs, and experimental design. They are not estimated-result tables. The relevant frozen inputs and terms are retained, but this repository does not reproduce manuscript prose or Word formatting.
