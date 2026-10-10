# Financing feasibility mapping

This directory retains the original name `inverse` so that model paths and job identifiers remain stable. `design.json` specifies the axes, outcomes, grids, permissions, settlement timing, and tolerances.

Every tested coordinate reruns the complete corporate path. The search scans the declared grid and refines all observed changes in outcome; it does not assume global monotonicity. `replay.py` reconstructs any retained evaluated point from its frozen source and recipe and checks exact hashes.

Use the root `reproduce.py` entry point for installation, verification, figure/table reproduction, and full analysis. See `../docs/REPRODUCING.md` and `../docs/DATA_DICTIONARY.md` for commands and interpretation.
