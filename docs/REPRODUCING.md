# Reproducing the study

Use a fresh extracted release or clone, Python 3.12, and the pinned environment. Run commands from the repository root. The scripts derive paths from their own file locations; no development workspace is required.

## Frozen data and checks

`data/manifest.json` identifies each bundle, every member path, byte count, and SHA-256 digest. The five bundles contain source material, search inputs, and retained numerical outputs. `scripts/unpack_data.py` checks both the bundle and individual members and rejects unsafe paths or changed existing files. ZIPs reduce file-count overhead while preserving original file bytes.

`data/builder_references.json.gz` retains the complete input configurations, financial snapshots, and assessments for 270 cases from five original baseline archives. It also identifies the original archive hashes. This replaces those large full archives only for the builder comparison; it does not replace the simulation logic.

`data/publication_reference.zip` holds the four plotting datasets used for the current manuscript. Figure data regenerated from the model must match these references within floating-point serialization precision.

## Quick reproduction

```bash
python reproduce.py quick
```

This reconstructs `scenario_evaluations.csv`, `required_conditions.csv`, `feasible_bands.csv`, STRC comparisons, and summary statistics from all retained job/probe records. It then extracts plotting data, redraws Figures 1–4 in PNG/SVG/PDF, and exports Tables 2–4 and E1–E3 as CSV/Markdown.

The final checks compare regenerated model tables with the frozen tables and compare plotting datasets with the manuscript figure package. They also check key manuscript counts, observed reversals, zero-capacity outcomes, and STRC paired effects. The script records its actual steps in `build/reproduction_report.json`.

## Verification without every simulation

```bash
python reproduce.py verify
```

In addition to the quick route, this:

1. Rebuilds the five-interval historical reconciliation from frozen filing evidence.
2. Rebuilds 270 corporate configurations and compares their financial snapshots and assessments exactly with retained references.
3. Checks all 2,687 job summaries, all 46,481 evaluation summaries, source-configuration hashes, target nesting, recorded transitions, and sale-authorization bounds.
4. Replays 243 selected evaluated results across 117 strata and requires exact configuration and result hashes.
5. Runs the original four synthetic search fixtures and verifies that the independent arithmetic audit rejects a deliberate one-dollar purchase error.

The reported 13,740,202 arithmetic checks are summed from retained evaluation records on this route. They were performed during the original simulations. An exact replay recomputes them for that replayed case; verification does not claim every original check has just been rerun.

## Full analysis

```bash
python reproduce.py full --workers 4
```

Start from a fresh copy. The runner preserves retained search-job files in `build/retained_search_jobs/` and regenerates every search instead of accepting those files as completed work. It rebuilds the historical panels, initial 2,646 configurations, 198 supplementary controls, and 1,748 revision controls, then regenerates the financing-feasibility searches and STRC comparisons. Large full ledgers are written under `validation/results/` and `inverse/results/jobs/`; they are excluded from Git tracking.

The full search reruns the frozen source configurations and job recipes. Baseline regeneration is checked separately through the 270 exact financial comparisons. The original archive carries migration provenance labels that differ from the current builder; regenerating those labels with `inverse/study.py --prepare` creates different configuration and job hashes despite the matched financial outcomes. The supported full route therefore preserves frozen search inputs and their original identifiers. It does not replace these inputs with newly labeled versions.

The full run can use several gigabytes of disk space and substantially more processing time than verification. `--workers` sets search parallelism. For an interrupted full search, resume with `python inverse/study.py --workers 4`, then run `python inverse/verify_package.py`, `python inverse/analyze.py`, and the publication scripts. Baseline windows can be resumed with `python validation/scenario_study.py` without `--force`. Use `--start` and `--stop` for zero-based subsets of the 49 windows.

## Individual modules

The retained `research/legacy_engine/` files include dependencies from earlier engine development. The root runner is the supported entry point. Older module-level demonstration commands can refer to archives that are outside this release; they are not necessary for the manuscript's replication routes. The public release does not redistribute the separate private Monster Model replication project.

## What numerical equality means

Configuration and model-result hashes use the original JSON serialization and are exact under the tested environment. CSV comparisons allow small differences from floating-point text conversion. The diagnostic maximum arithmetic residual has a separate absolute tolerance of one millionth of its reported unit because audit summation order can change that residual without changing the configuration or result hash. Economic outputs and hashes do not receive this relaxed diagnostic tolerance. Plot data and labels are checked independently of image-file bytes. Different rendering-library versions or fonts can change image bytes without changing plotted results. PNG and vector outputs use DejaVu Serif; SVG/PDF creation timestamps are suppressed in the new publication script.

The release report distinguishes tests actually run for packaging from original retained verification and from an unexecuted full rerun. It does not claim that numerical consistency validates future demand, valuation assumptions, or indefinite company survival.
