# BUAA LaTeX Spike Template

This directory contains the BUAA LaTeX feasibility templates used by
`scripts/render_latex.py`.

Default backend:

- `bhosc/`: BHOSC-backed project runtime. This is the fidelity path for
  `--degree bachelor` and `--degree master`.

Fallback backend:

- `main.tex.template` plus `figure/`: lightweight standalone renderer retained
  for debug comparison with `--backend lightweight`.

Reference material:

- `BHOSC/BUAAthesis`, especially `sample-bachelor.tex`, `buaathesis.cls`, and
  the cover image assets under `figure/`.
- `yzd-v/BUAA_thesis_overleaf` and the Overleaf clean template are treated as
  Overleaf-oriented variants of the same BUAA LaTeX family.
- `CheckBoxStudio/BUAAThesis` is reference-only because it targets graduate
  theses.

The copied BHOSC class, bibliography support files, and figure assets come from
the BHOSC template checkout used for the spike. Keep license attribution with
the upstream project if these files are retained beyond feasibility work.
