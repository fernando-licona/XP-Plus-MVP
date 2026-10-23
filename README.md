# XP Plus — Public MVP

A small, self-contained computational demo for checking whether a published experiment is specified well enough to reproduce.

**Paper metadata → provenance and gaps → digital twin / rebuilt model → comparison → Reproducibility Standard.**

This repository contains XP Plus's reproduction screens and pipeline, a headless snapshot of the Danamic numerical code they use, and small annotated examples. It runs without a FlowLab checkout, private repositories, API keys, or lab hardware. The original FlowLab, Danamic and Hackathon repositories remain separate.

## Quick start

Requirements: **Python 3.12+** and **Node.js 22+**. Commands below use Windows PowerShell; on macOS/Linux replace `.venv\Scripts\python.exe` with `.venv/bin/python` and `npm.cmd` with `npm`.

```powershell
git clone https://github.com/fernando-licona/XP-Plus-MVP.git
cd XP-Plus-MVP
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m xp_plus api
```

In a second terminal opened at the repository root:

```powershell
cd web
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:5100/reproduce**. Both servers bind to loopback. This is a local demonstration, not a hosted multi-user lab service.

1. Select **RTD tracer, tau = 9 min**.
2. **Check the paper as written** to see missing parameters.
3. Inspect **Rig** and **Gaps**, including citations and provenance.
4. Leave the explicit resolutions selected and choose **Run XP Plus**.
5. Inspect **Results** and download the JSON from **Standard**.

The real-paper receipt remains `insufficient_data` because no physical reproduction has been performed. The toy example has explicitly **synthetic observations**; its `reproduced` verdict demonstrates comparison logic only.

## Optional Gaussian-process demo

The basic installation runs tracer/gap/receipt demos without Torch. For the paper's GP, install the CPU model stack first:

```powershell
.venv\Scripts\python.exe -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -e ".[gp]"
```

Restart the API, select **CdSe DFE + paper's GP**, and run it with `botorch_legacy`. Training data is downloaded on first use from the authors' pinned public repository, verified by SHA256, and retained under ignored `.cache/xp_plus/`. It is not included in this repository. Model defaults and explicit assumptions remain visible.

## Command-line demo

```powershell
# Expected exit code 1: the paper has blocking gaps.
.venv\Scripts\python.exe -m xp_plus gate examples/dfe_rtd/tau_9min/extraction.json

# Applies the reviewed, provenance-tagged resolutions and runs the real transport engine.
.venv\Scripts\python.exe -m xp_plus run examples/dfe_rtd/tau_9min/extraction.json --resolutions examples/dfe_rtd/tau_9min/resolutions.json --out standard.json

.venv\Scripts\python.exe -m xp_plus schema --out standard.schema.json
.venv\Scripts\python.exe -m pytest -q
```

## What is included

- `xp_plus/`: existing schema, completeness/model gates, revisions/resolutions, comparison, receipt export, local API and GP reconstruction.
- `fluidsim_twin/`, `m6flow/`: only the headless transport and black-box runtime required by the examples. Numerical kernels are preserved; the public facade exposes analytical and black-box execution.
- `web/`: reproduction-only UI, rig/provenance inspection and Standard download. Icon fallbacks replace equipment artwork.
- `examples/`: synthetic tracer and annotated Delgado-Licona RTD/GP experiments; PoLARIS verification scripts use separately obtained source files.
- `tests/`: inherited scientific regression tests and public-package/browser checks.
- `SOURCE_MANIFEST.json`, `NOTICE.md`: exact source provenance, hashes and export changes.
- `docs/`: extraction checklist, findings and bounded validation evidence.

## Results and limits

The DFE examples expose detector-line timing and model-configuration questions. For Junbin/PoLARIS, the 80-row source workbook gives **R² = 0.7086**; reconstruction gives **0.7146** with legacy defaults and **0.7401** with current defaults. These are computational checks, not physical reproductions. See [findings](docs/RESULTS.md) and [validation](docs/VALIDATION.md).

This MVP uses reviewed, pre-annotated examples. Automatic LLM paper extraction is not implemented in the standalone package. Raw PDFs, spreadsheets, training CSVs, hardware drivers/control, device bindings, local databases, credentials, the full FlowLab app, desktop/CFD tools and calibrated equipment-instance registries are excluded. The public rig view is a read-only paper diagram, not a FlowLab Platform editor.

Physical validation, complete PoLARIS segmented-flow/PLQY science, and dynamic absolute-flow model inputs remain later work. Missing information must be reviewed and resolved with provenance; it must not be filled silently to make a gate pass.

## Source papers

- Delgado-Licona et al. (2025), [Flow-driven data intensification to accelerate autonomous inorganic materials discovery](https://doi.org/10.1038/s44286-025-00249-z).
- Li et al. (2026), [Autonomous microfluidic experimentation for exploring reaction inference and synthesizing double perovskite nanoplatelets](https://doi.org/10.1038/s41467-026-72765-2); [PoLARIS code/training data deposit](https://zenodo.org/records/19665377).

Source attribution and the supplied snapshot's license status are recorded in [NOTICE.md](NOTICE.md). No raw publisher material is redistributed.
