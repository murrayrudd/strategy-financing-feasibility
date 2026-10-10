# Strategy financing feasibility

Code, frozen data, numerical results, and figure reproduction for Murray A. Rudd's working paper, **Financing feasibility and shareholder outcomes in a Bitcoin treasury company: historical validation and conditional stress testing of Strategy** (9 October 2026 manuscript).

The model maps the conditions needed to meet scheduled payments, preserve reserves, preserve common-share value, earn a specified common return, or preserve Bitcoin per basic share. These objectives can diverge. Each tested condition reruns the corporate financing and transaction sequence.

**Release 1.0.0** retains 46,481 evaluations across 2,687 jobs. The corporate opening is 30 June 2026, with disclosures through 3 August 2026. The 457-day horizon ends on 30 September 2027. Model engine: 0.6.0. No manuscript, private review, or correspondence is included.

## Working paper and SSRN link

**Author:** Murray A. Rudd  
**Paper:** *Financing feasibility and shareholder outcomes in a Bitcoin treasury company: historical validation and conditional stress testing of Strategy* (2026 working paper; 9 October 2026 manuscript).

**SSRN status:** Submission planned for 10 October 2026; the public paper link is pending SSRN approval. This package does not claim that the paper is already available on SSRN.

**SSRN link:** `SSRN_URL_PLACEHOLDER` — replace this marker with the public SSRN abstract-page URL when available. No paper DOI is required or used.

Provisional paper citation:

> Rudd, Murray A. (2026). *Financing feasibility and shareholder outcomes in a Bitcoin treasury company: historical validation and conditional stress testing of Strategy*. Working paper. SSRN link pending approval.

Cite the paper for its analysis and this replication package for its code or numerical results. `CITATION.cff` currently describes the replication package. Once SSRN provides the public URL, update this section and the paper-link comment in `CITATION.cff`; see `docs/PUBLISHING.md` for the exact steps. The manuscript itself is not included in this repository.

## Start here

Use Python 3.12. The release was checked with Python 3.12.14 and the package versions in `requirements-lock.txt`.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python reproduce.py quick
```

The installation requires access to a Python package index. All analysis after installation runs offline from the supplied data. No API key or live market-data request is needed.

| Route | Command | What it does |
|---|---|---|
| Quick rebuild | `python reproduce.py quick` | Checks and extracts frozen bundles; rebuilds aggregate outputs, four figures, and six numerical tables; checks the results against retained references. |
| Verification | `python reproduce.py verify` | Also reruns historical reconciliation, 270 builder comparisons, and 243 exact recipe replays; checks every retained search summary and bracket. |
| Full analysis | `python reproduce.py full --workers 4` | Rebuilds the historical panels, initial comparisons, controls, and all financing-feasibility searches. Requires substantially more time and disk space. Run in a fresh copy. |

Results are written to `publication/figures/`, `publication/tables/`, and `build/`. The quick route does not rerun all simulations. Verification recomputes selected simulations and checks retained summaries; it does not independently rerun all 13,740,202 arithmetic checks. The full route recomputes those checks at every model evaluation.

## Reproduce a particular result

After running the quick route, find a `job_id` and `coordinate` in `inverse/results/scenario_evaluations.csv`, then run:

```bash
python inverse/replay.py c71d05c82b238a0f34c0 --out build/example_witness.json.gz
```

This recreates a full configuration, ledger, financial snapshots, daily marks, and endpoint obligations. Both configuration and result hashes must match the retained record. Add `--coordinate NUMBER` to select another evaluated point for that job. Without it, the script selects the lowest feasible nominal-value point, then the funded point if necessary, or the first tested point if neither succeeds.

## Repository map

| Location | Contents |
|---|---|
| `inverse/` | Financing-feasibility search, explicit design, analysis, replay, and verification. The directory name preserves existing identifiers; the method is described as financing feasibility mapping. |
| `validation/` | Historical reconciliation, corporate scenario builder, settlement calendar, and targeted control studies. |
| `research/legacy_engine/` | Corporate accounting and financing engine, calibration provenance, and inherited modules required by the current study. These modules are this project's implementation, not the separate Monster Model review. |
| `research/` | Historical panel construction and supplementary valuation diagnostics. |
| `data/` | Five frozen ZIP bundles, compact builder references, plotting-data references, and member-level SHA-256 manifest. |
| `publication/` | Four figure scripts/outputs, plotting data, captions, and numerical tables. |
| `docs/` | Reproduction details, data dictionary, source/rights notes, and a results-to-code map. |
| `provenance/` | Source-package hashes, release checks, environment, and packaging changes. |

The source and result bundles expand into their original relative paths. Every member is checked before extraction. Existing changed files are not overwritten silently. To restore frozen files deliberately, run `python scripts/unpack_data.py --force`; use a fresh copy for a new full run.

The large initial-comparison and control ledgers are regenerated by the full route. Their summary rows and record hashes are retained. Complete search ledgers can be recreated individually from the frozen source configuration and recipe; selected worked-case ledgers are also retained. There are no external data-download links required for replication.

## Reading the results

Scenario counts describe the specified cases; they are not probabilities. Future Bitcoin prices, market valuation, financing capacity, rates, and asset-use permissions are scenario conditions. The terminal valuation multiplier is relative to the model's residual equity reference, not a fixed mNAV ratio. Shareholder returns are conditional model outputs, not forecasts.

Payment completion refers to the declared schedule and permissions within the model horizon. It does not establish indefinite solvency. The reserve, payment, common-return, and Bitcoin-per-share targets have separate definitions in `inverse/design.json`.

See [the results index](docs/RESULTS_INDEX.md) for the connection between manuscript findings, datasets, and scripts. [Reproduction notes](docs/REPRODUCING.md) explain retained versus recomputed evidence and the full-run workflow.

## Citation and reuse

Use `CITATION.cff` to cite the replication package and the provisional citation above to cite the paper. The paper will be posted on SSRN once approved; its public URL is pending. No paper DOI is required. Add the actual repository URL to `CITATION.cff` after the GitHub repository exists.

See [LICENSE.md](LICENSE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No blanket open-source license has been selected for this release. Coin Metrics data retain their CC BY-NC 4.0 attribution and terms. Source-provider data and filings are not relicensed by this package.
