---
name: paper-extraction
description: Checklist for extracting a flow-chemistry / self-driving-lab paper into a reproducibility Extraction (xp_plus.extraction.Extraction JSON). Covers the platform, hardware, chemistry, protocol, measurement and claims, plus the data and metadata papers often leave out. Use it when annotating a paper by hand, building an examples/<paper>/ extraction, reviewing an LLM extraction, or listing a paper's reproducibility gaps.
---

# Paper extraction checklist

Turn a paper (main text, Methods, SI, figure captions, tables, data/code statements) into an
`Extraction` (`features` + `gaps`, see `xp_plus/schema/`), with **every value tagged with where
it came from** and **every missing value recorded as a gap**. The goal is not a summary. It is
a complete, rerunnable account of what the paper says, what it implies, and what it leaves out.

Worked examples (Delgado-Licona et al., Nat. Chem. Eng. 2025): `examples/dfe_rtd/` (SI §1
RTD) and `examples/dfe_gp/` (the CdSe DFE and its GP digital twin, a full model card).

## Ground rules

1. **Never invent a value as `paper_stated`.** Stated values carry a short quote and its
   location in `source`, e.g. `"Methods: 'a 1,113-µl CFI reactor'"`.
2. **`inferred` values show their working** in `note`, e.g. `"total flow = V_R / tau = 1113 / 9"`.
   Infer only from the paper itself or physical identities (V = π(ID/2)²·L, Q = V/τ, recipe →
   concentration). Anything else is `assumed` and goes in `resolutions.json`, not the extraction.
3. **Missing means missing.** Leave the field empty (`provenance: "missing"`) and add a `Gap`
   (`detected_by: "extraction"`) when it matters to reproduction. Don't fill it with a "typical" value.
4. **Record contradictions; don't resolve them.** If the text, a caption and the SI disagree,
   extract the value you use, cite where it came from, and add a gap quoting both versions.
5. **One `Extraction` per experiment.** Use `experiment` to label it (e.g. "SI §1 RTD,
   tau = 9 min"). Separate operating points or claim sets get separate extractions.
6. **Units are set by field names** (`_mm`, `_uL`, `_uL_min`, `_C`, `_bar`, `_nm`, `_M`, `_s`).
   Convert at extraction time and say so in `note` (0.03 in → 0.762 mm).
7. **Distinguish nominal from measured.** Set points (nominal residence time, set flow rate,
   set temperature) are not observations. Claims say which they are.

Legend for the checklist: **[B]** the twin cannot run without it (the gate blocks);
**[M]** reproducibility metadata (recorded as a non-blocking gap if missing).
Paths are `Resolution.target` / `Gap.target` paths.

## Reading order

1. Abstract and conclusions: list every quantitative claim (→ section 11).
2. Methods: chemicals, preparation, hardware, software.
3. SI: platform details, characterization experiments (RTD, calibration), tables of conditions.
4. Figure captions and table footnotes. These often hold values not stated anywhere else.
5. Data / code availability statements (→ section 12).
6. Cited prior work only when the paper says "as described in ref. X". Note it as a gap, since
   the value isn't in *this* paper, and do not silently import it.

## 1. Paper and experiment identity

- [ ] Title, DOI, authors, year → `paper`
- [ ] Which experiment this extraction covers, and where it is described → `experiment`
- [ ] Is it a physical experiment, a computational/ML claim, or both? (Computational claims
      need section 12.)

## 2. Platform topology (structural gate)

- [ ] Every component in the flow path, from each feed to each outlet, in order → `rig.components`
- [ ] Every connection between them → `rig.connections` (`direct: true` only when there is
      truly no tubing, e.g. a syringe on its pump)
- [ ] **[B]** At least one pump and one detector; every pump has a path to a detector or collection
- [ ] **[B]** The detector each measurement uses is in the rig (`measurements[].instrument`)
- [ ] Components the paper describes for the *main* experiment but that this experiment
      bypasses (e.g. the RTD run enters at a T-mixer and skips the preheater). Exclude them,
      and say why in the experiment note.
- [ ] Junctions: tees, crosses, splitters, selector valves and their positions
- [ ] Anything downstream of the detector that affects it (back-pressure regulator, collection)

## 3. Fluid delivery (pumps)

- [ ] Pump type: syringe, HPLC/piston, peristaltic, pressure-driven
- [ ] [M] Manufacturer and model → `manufacturer`, `model` (per pump; check that the experiment
      used the same pumps as the main platform)
- [ ] **[B]** Flow rate for every stream at every stage → `flow_rate_uL_min`, or `set_flow_rate`
      protocol steps. If only τ and V are given, infer Q = V/τ and the split from the stated ratio.
- [ ] Flow schedule: steps, ramps (equation and parameters), ratios, constant total flow?
- [ ] [M] Syringe volume, material and make; how many syringe refills during a run
- [ ] [M] Pump calibration, flow accuracy, pulsation; check valves; maximum pressure
- [ ] [M] Startup dynamics: dead time, time to reach set flow

## 4. Feeds and reservoirs

- [ ] What each feed contains → `rig.components.<res>.contents.<species>`
- [ ] **[B]** Concentration of every measured species in its feed. If the response is
      normalized, note that the value doesn't matter but is still unreported.
- [ ] [M] Solvent, and the stream it dilutes
- [ ] [M] Atmosphere (glovebox, N₂ purge), degassing, headspace, stirring
- [ ] [M] Storage conditions and solution age at use; precursor aging over a campaign

## 5. Tubing and connections (most often missing)

For **each** connection, not just the reactor:

- [ ] [M] Inner diameter → `rig.connections.<a>-><b>.inner_diameter_mm`
- [ ] [M] Length → `.length_mm` (or volume, then infer ID or length)
- [ ] [M] Material (PFA, PTFE, FEP, stainless steel, PEEK) → `.material`
- [ ] [M] Outer diameter and part number (helps identify the ID)
- [ ] [M] Fittings, unions, ferrules; internal volumes of junctions
- [ ] [M] **Dead volumes**: pump → mixer, mixer → reactor, reactor → detector. These shift
      every time-based result.
- [ ] Insulation, heating or cooling of lines

## 6. Mixers

- [ ] Type: T-mixer, cross, static mixer, braided or micromixer, chip
- [ ] [M] Manufacturer, model, part number
- [ ] **[B]** Internal volume, or ID + length → `volume_uL`
- [ ] [M] Geometry that drives mixing (channel size, number of elements, braid length)

## 7. Reactor

- [ ] Type and geometry: coil, coiled flow inverter, chip, packed bed, CSTR; curvature
      diameter, pitch, turns, bends
- [ ] **[B]** Volume, or ID + length → `volume_uL`, `inner_diameter_mm`, `length_mm`
- [ ] **[B]** Temperature → `temperature_C`
- [ ] [M] Material (tube and block) → `material`
- [ ] [M] Heating method, heater model and power, controller model; where temperature is
      measured (block, fluid, wall); stability (±°C)
- [ ] [M] Preheaters, pre-cooling and quench sections: volume, temperature, which streams
- [ ] [M] Characterized RTD, i.e. the Bo/Pe or dispersion model and how it was fitted

## 8. Pressure

- [ ] [M] Back-pressure regulator: present? model, set pressure
- [ ] [M] Operating pressure; pressure sensors; whether solvents stay liquid at the temperature used

## 9. Measurement and detection

- [ ] Instrument chain: flow cell, spectrometer, light source(s), detector, fibers
      → detector component `name` / `manufacturer` / `model`
- [ ] [M] Flow cell: type, **optical path length** → `path_length_mm`, cell volume, material, windows
- [ ] [M] **Position: distance or volume from the reactor outlet.** It sets the transport delay.
- [ ] Wavelength(s) or range → `measurements[].wavelength_nm`; excitation wavelength for PL
- [ ] [M] Integration time, acquisition interval, number of spectra averaged
- [ ] [M] Blank, reference and dark spectra; calibration against a benchtop instrument
- [ ] [M] Data processing: baseline, normalization, peak fitting, feature extraction (λ, FWHM,
      P/V), smoothing → `measurements[].processing`
- [ ] **Time origin** for any time-based result (step at the pumps? arrival at the reactor? at
      the detector?) and whether dead volume was subtracted → `measurements[].t0_step` + a gap
      if unstated
- [ ] Software and versions (acquisition and processing)

## 10. Protocol and timing

- [ ] Ordered steps: priming, flushing, set flows, set temperatures, waits, steps or ramps,
      sampling, washing between conditions → `protocol`
- [ ] **[B]** Duration of every wait → `protocol.<step>.duration_s`
- [ ] [M] Steady-state criterion (e.g. "3 reactor volumes", "3.5 τ") and stabilization criteria
      (e.g. "±1 °C")
- [ ] [M] Recording duration after a change; how many measurements count as steady state
- [ ] [M] Ramp definitions: equation, initial and final values, slope, duration
- [ ] [M] Washing or solvent flush between conditions (flow rate, volume)
- [ ] [M] How the residence time is defined: nominal V/Q at pump conditions, or corrected
      for thermal expansion or dead volume?

## 11. Chemistry

- [ ] Every reagent: name, role, CAS if given, **supplier**, **purity**, lot → `chemistry.reagents`
- [ ] Preparation recipe (masses, volumes, temperatures, times, atmosphere). Infer
      concentrations from it and show the arithmetic.
- [ ] [M] Water content and drying; stabilizers; filtration
- [ ] Kinetics or mechanism parameters, if the twin needs a reactive model

## 12. Environment and lab context

- [ ] [M] Ambient temperature, humidity, pressure → `environment`
- [ ] [M] Glovebox or inert conditions; light exposure; day-to-day / batch-to-batch variation reported?

## 13. Claims (figures of merit)

For **every** quantitative claim → `claims[]`:

- [ ] `metric` (normalized name: `residence_time`, `mean_residence_time`,
      `bodenstein_number`, `yield`, `conversion`, `emission_wavelength`, `fwhm`, ...)
- [ ] `value`, `unit`, `qualifier` (`=`, `~`, `>`, `<`)
- [ ] `conditions`: the exact operating point the claim belongs to
- [ ] `source`: quote and location
- [ ] Uncertainty: SD, CI, number of replicates, and what the replicates were (same day? separate days?)
- [ ] Nominal or measured? Headline claims (e.g. ">10× efficiency") vs the table that backs them

## 14. Data, code and computational models (model card)

Any data-driven model the paper builds (GP, neural network, regression) becomes a `ModelCard`
→ `models[]`. The black-box twin uses the card to predict outputs from transport-resolved
conditions. The model gate (`detected_by: "gate_model"`) checks four levels:
**specified** (can it be rebuilt?), **trainable** (is the exact training set available?),
**reproduced** (does a rebuild hit the paper's metrics?) and **transferable** (does it predict
our rig?). Read the paper's code as well as its text: the code often settles what the text leaves open.

- [ ] Data availability statement; repository URL **pinned to a commit**; licence (no licence →
      fetch at run time, don't vendor) → `code`, `training_data`, `training_data_sha256`
- [ ] Family and purpose → `family`, `purpose`
- [ ] **Every input**: the paper's formula (`definition`), how to compute it from the rig
      (`kind`: flow_fraction / residence_time / temperature / constant, plus `node`,
      `numerator`, `denominator`), unit and `scale` from the twin's base unit, the training
      column, and the **normalization bounds** (`low`, `high`)
- [ ] **Every output**: definition, unit, column, normalization (watch for inverted scales,
      e.g. FWHM = (FWHM − 110)/(10 − 110))
- [ ] Same symbol, two meanings? (e.g. "X1 = 0.30" raw in the text vs normalized X1 in the model)
- [ ] [M] Library **and version**. Library defaults change between releases (BoTorch ≥ 0.12
      changed SingleTaskGP's default kernel, priors and outcome transform), so record what
      the code actually calls.
- [ ] GP: kernel (and whether the stated kernel matches the code's defaults for that
      version), mean function, likelihood/noise, priors, output transform, independent vs
      multitask outputs, hyperparameter fitting
- [ ] Neural network: architecture (layers, widths), activations, optimizer, learning rate,
      epochs, batch size, initialization, regularization, early stopping
- [ ] Training set: which rows (all ramps? 30 s sampled?), how many, whether pre-normalized
      → `n_training_points`, `training_data_normalized`; check the stated sampling against the data
- [ ] Validation as written (`validation`) **and** as code (`validation_protocol`: folds,
      shuffle seeds, metric). Note the R² definition (coefficient of determination vs squared
      Pearson correlation) → `metric_definitions`
- [ ] Seeds: data shuffling, splits, model fitting
- [ ] Every reported model metric becomes a claim (`cv_r2_<output>`, with a `tolerance`)
- [ ] Optimization settings, if claimed: acquisition function, budget, objective and weights,
      constraints. Check weights stated in different places agree.
- [ ] Claims about outputs at a condition (e.g. steady state at τ = 3 min) carry `at: {"tau": 3}`
      so the twin can read its prediction there, plus a `tolerance` with its basis

## 15. Cross-checks (consistency gate)

Do each one. A disagreement becomes a gap that quotes both values.

- [ ] Volume vs π(ID/2)²·length for every tube and reactor
- [ ] Stated residence time vs volume / total flow
- [ ] Flow rows in tables vs τ: do Σ Q · τ give one reactor volume?
- [ ] Numbers repeated in text vs caption vs SI vs tables (same value, same condition label?)
- [ ] Recipe → concentration vs any stated concentration
- [ ] Headline ratios vs the table they come from (e.g. "10×" vs 12.3× / 15.6×)
- [ ] Figure, table and section cross-references point where they claim to
- [ ] Definitions used the same way throughout (τ, t_avg, dead volume, "steady state")
- [ ] Physically plausible: solvent below its boiling point at that pressure, flows within
      pump range, Bo/Re/Dean numbers reasonable

## Gaps papers commonly leave out

Check these explicitly. They are rarely reported and often matter:

- Tubing ID, length and material for every connection other than the reactor
- Dead volume between reactor and detector, and whether timing corrects for it
- Mixer internal volume
- Flow-cell path length and cell volume
- Pump calibration, and the pumps used in characterization runs
- Tracer or standard concentrations in calibration or RTD runs
- Equilibration and recording durations
- Thermal expansion of the solvent in heated sections vs flow rates set at room temperature
- Back-pressure regulator presence and setting
- Ambient conditions; reagent lots and solution age
- Library versions for ML models; whether the stated kernel or architecture matches the code
- Which figure legend label belongs to which output (rebuild and check)
- The data-sampling interval actually used for training vs the stated one

## Output

- `examples/<paper>/<experiment>/extraction.json`: an `Extraction` (`features` + `gaps`).
  Prefer a small builder script like `examples/dfe_rtd/build_extractions.py`, so values and
  quotes are reviewable as code.
- `examples/<paper>/<experiment>/resolutions.json`: only the values *we* choose
  (`assumed` / `inferred` / `measured`), each with a note.
- Gap entries: `id = "extraction:<target>"`, a `target` path, a one-sentence `description`
  that quotes the conflicting or missing text, and `blocking` (true only if the twin can't
  run without it).

## Final self-check

- [ ] `python -m xp_plus gate <extraction.json>` runs; every blocking gap is a real omission,
      not an extraction miss
- [ ] Every `paper_stated` value has a quote; every `inferred` value has its arithmetic
- [ ] No `assumed` values in the extraction (they belong in resolutions)
- [ ] Every claim has a unit (or is dimensionless), a condition and a source
- [ ] Every contradiction found in section 15 is a gap
- [ ] A colleague could find each quoted value in the paper from `source` alone
