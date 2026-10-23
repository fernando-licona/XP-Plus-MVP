# Public MVP validation

Validated 2026-10-22 from the isolated public folder; source snapshot is identified in SOURCE_MANIFEST.json. These checks assess the computational export, not physical reproduction or the full FlowLab product.

## Executed checks

- Fresh Python 3.12.14 environment; base installation ran **44 tests passed, 1 optional GP module skipped** before installing optional packages.
- Final complete suite, including real GP reconstruction and the four public-package isolation checks: **56 passed in 14.20 s**, exit 0. No mocked numerical engine or fallback was used.
- Real paper gate reported blocking gaps; expected gate exit code 1. After explicit resolutions, the actual tracer engine generated a Standard with no physical record and verdict `insufficient_data`. Schema export passed.
- Optional GP stack used Torch **2.14.1+cpu**, BoTorch **0.18.1**, GPyTorch **1.15.2**, scikit-learn **1.9.0**. Public training data was downloaded and hash-checked in the ignored local cache. No training CSV was committed.
- Frontend production build passed on Node **22.15.0**. The chart/diagram bundle produces a non-blocking size warning; no broken private imports remain.
- Actual headless Edge browser, real local API/UI, at **1440 and 1280 px**: choose RTD example, inspect blocking gaps, inspect cited reactor provenance, execute the real twin, inspect `insufficient_data`, download/parse the Standard, and verify no horizontal document overflow or browser errors. No HTTP requests were mocked.
- Screenshots were visually inspected. Export-only inspector casing was corrected to preserve `µL`; the final browser check asserts the exact unit. An initial test chose an unreported reservoir; it was corrected to select the cited reactor. Windows shell encoding of the test symbol was corrected using an explicit Unicode escape. Final checks passed at both widths.

## Run checks locally

```powershell
.venv\Scripts\python.exe -m pytest -q
cd web
npm.cmd ci
npm.cmd run build
cd ..
.venv\Scripts\python.exe -m pip install -e ".[browser]"
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe tests/browser_smoke.py
```

On Windows with Edge already installed, `tests/browser_smoke.py --browser-channel msedge` avoids downloading a separate browser. The script uses its own temporary local API/UI ports (8875/5118), starts no FlowLab backend or Lab edge, and stops its child processes. Logs, screenshots and downloaded test receipts remain ignored under `.cache/browser/`.

## Publication boundary

A fresh Git history contains only the allowlisted computational export and its README/tests. It contains no private submodule or repository history, full FlowLab application, Lab edge/hardware driver, key/certificate, database, raw publisher PDF/XLSX, downloaded training data, equipment-instance calibration file, desktop GUI, CFD tools or equipment artwork. Runtime registries are intentionally empty; presets carry explicit values and assumptions. Numerical kernels remain source-identifiable in the manifest; only export facades, UI bindings/scope and unit formatting differ.

The original source repositories were read only for this task; their pre-existing state is preserved, including the staged FlowLab gitlink in the Hackathon checkout. This export does not update their branches, contents, remotes, visibility or history.

Technical execution: **PASS** for the bounded checks above. Actual browser journey: **PASS** at both widths for this computational scope. Independent product-change review: **NOT APPLICABLE** to upstream projects; no upstream production implementation was changed. Physical scientific reproduction: **NOT ASSESSED / incomplete**. Automatic LLM extraction, PoLARIS segmentation/PLQY and arbitrary paper support remain excluded.
