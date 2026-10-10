# Manuscript figures and numerical tables

From the repository root, run `python reproduce.py quick`. This recreates all four figures and Tables 2–4 and E1–E3 from the retained numerical model outputs.

`prepare_data.py` derives all four plotting datasets from `inverse/results/`. `build_figures.py` draws Figures 1–4 as PNG, SVG, and PDF. `build_tables.py` exports CSV tables and a readable Markdown table document. `captions.json` preserves the figure captions used with the manuscript.

The release checks compare regenerated plotting data with the original manuscript figure package. Figure 4 now has its own reproducible drawing code; it is no longer just a copied image. No new simulations are needed for the quick route.

Figures 1–3 use 450 dpi PNG output; Figure 4 uses 400 dpi. The grayscale design uses line patterns, marker shapes, and fills to distinguish outcomes. The vector files retain editable text. The datasets represent conditional cases, not estimated probabilities.
