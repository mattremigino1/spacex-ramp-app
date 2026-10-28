# Context for AI coding agents (Cursor, etc.)

## What this is and why it exists

I'm Matt, interviewing for a Business Operations role on SpaceX's AI satellites team. The final round is a case on the **AI satellite launch ramp, 2028–33**. I deliver three things:

1. An Excel model, sent in advance. The current version is "20261028 AI Satellite Ramp Case Model 0120.xlsx", which is not in this repo.
2. A PowerPoint of about 10–15 minutes, which includes an "About me" section.
3. **A live web-app demo of about 30 minutes. This repo is that app.**

The case rules constrain what the app can do:

- **The dataset is fictional.** Use only the case's Excel data. Any input the case doesn't give (all the costs, for example) must be an explicit, labeled assumption.
- The app must be hosted on a free public tool (Streamlit Community Cloud) and must also run locally as a fallback.
- **The app must show the same answer as the Excel model.** This is the most important rule in the repo.
- Required features:
  - charts;
  - tables, yearly (monthly is a plus);
  - toggles, at minimum constrained vs. unconstrained;
  - a comparison of cases;
  - a recommended strategy in priority order.
- The brief says, in its words: *"Do not build a slide deck in a browser — build a decision tool."* Every section should help someone make a decision, not just display numbers.

## The business problem, in one paragraph

SpaceX wants to put AI compute into orbit on satellites. The target is **168.4 GW** of compute launched over 2028–33, reaching 75 GW in 2033.

There are four satellite classes: SSO-A, SSO-B, LEO-A and LEO-B. Each combines an orbit with a generation (Helios-A or Helios-B) and has its own kW, kW per ton, solar multiplier and life.

Three resources limit the ramp:

- **Starship flights** to SSO and to LEO. Payload per flight depends on the vehicle: V3 from 2028, V4 from 2031.
- **Solar cell supply**, in GW. Solar is sized for end of life and degrades 4%/yr.
- **AI chips:** Orion is in-house, 1,600 W at 75% utilization. Vega is bought, 2,500 W at 80% utilization, from 2030.

With the case's resources and an optimized class mix, only **49.9 GW (30%)** gets launched. Flights bind in 2028–31; SSO flights and solar bind in 2032–33.

A linear-program "target solver" picks the cheapest added launch capacity and solar fab. With those additions the plan reaches **163.7 GW (97%)**. The remaining roughly 4.7 GW of shortfall in 2029–30 is chip-limited.

The economics are illustrative because the cost inputs are added assumptions:

| Measure | Value |
|---|---|
| PV cost | ~$4.16T |
| PV value | ~$7.40T, at $15/W/yr contribution |
| Indicative NPV | ~$3.24T |
| Solver objective | $4,125.7B |

## Architecture

```
app.py                 Streamlit UI (Ramp tab with 9 numbered sections, Data and assumptions tab, sidebar toggles)
model/engine.py        The Excel model ported row by row: run(inp, solver=None) -> dict of per-year lists
model/solver.py        Target solver LP (scipy HiGHS): solve(inp) -> plan, costs, PV, undiscounted totals
model/economics.py     Selected-case economics; mirrors section J of the Excel Summary tab
model/defaults.json    Case data + toggles + added cost assumptions (the single source of inputs)
model/scenarios.py     Presets: base, unconstrained, seed mix, recommended plan, 6 risk cases
tests/test_model.py    Regression test vs. results that tie to the Excel workbook
tests/expected.json    Expected values for that test
.streamlit/config.toml Dark theme
```

### How the code flows

1. `load_defaults()` returns the inputs.
2. The sidebar edits `st.session_state.inp`.
3. `compute(json)` is cached with `st.cache_data`. It solves the plan for both mix settings (optimized and fixed), runs `run(inp, sol)`, runs three comparison variants (Unconstrained, Base case (constrained), Optimized (constrained)), and re-solves once per recommended addition with that addition blocked to value it.
4. The sections render from `R` (the engine output), `sol` (the solver output) and `selected_case_economics()` (section 7).

### Engine concepts

- **Greedy allocation:** satellites are allocated with whole-satellite trim. Chip priority goes to whichever chip is cheaper per watt; currently that is Orion.
- **Mix toggle:** "Optimized" maximizes compute under the active limits. "Custom" uses the seed mix from the case's Annual series tab.
- **Additions toggle:** `toggles.apply_solver = 1` feeds the solver's added flights, solar and mix back into the engine, so the plan is run in whole satellites.
- **Unconstrained:** `R["unconstrained"]` is the resource requirement to hit the target with no limits.

### Solver formulation

The solver must stay identical to the Excel Solver setup.

- **Variables:** 16 per year: flights by class ×4, Orion satellites ×4, Vega satellites ×4, new SSO capacity, new LEO capacity, new fab capacity, and shortfall.
- **Objective:** discounted cost plus a penalty on shortfall. The penalty is the lifetime value per GW (`e72`) times shortfall times the discount factor.
- **Capex timing:**
  - Spend before 2028 is grown to 2028 with (1+r)^-(j−L).
  - Base-capacity capex excludes spend before 2028.
- **Lead times:** launch capacity has a 2-year lead (first usable 2029); the fab has a 2-year lead (first usable 2030).

## Hard rules

1. **Parity with Excel is non-negotiable.**
   - Any change to `engine.py`, `solver.py` or `defaults.json` must keep `python3 tests/test_model.py` passing.
   - Headline numbers that must not move unless an input changes:

     | Measure | Value |
     |---|---|
     | Constrained | 49.9 GW |
     | Seed mix | 42.9 GW |
     | Plan | 163.7 GW |
     | Objective | $4,125.7B |
     | NPV | $3,242.5B |

   - If you intentionally change model logic, say so explicitly. The Excel model must then be changed the same way, and I do that separately.
2. **The UI layer must not "fix" model results.** No rounding hacks and no overriding values in `app.py`. Display only.
3. **Monthly mode:** values are annual ÷ 12, labeled "per month". **No cumulative views when monthly is on.**
4. **Labels and notes use plain English. Never use Excel cell or row references** such as "row 113" or "E72" in anything a user sees.
5. **Costs are labeled illustrative.** They are added assumptions, not case data.
6. **No Excel badge or branding.** Keep the SpaceX-like look: black background, white text, one blue accent (#4A90E2), Barlow font, uppercase section headers.
7. Every chart labels its values on the marks and has a "Show the numbers" expander with the table that feeds it.
8. Keep it simple. This is a 30-minute interview demo that must not break live. Prefer robustness over cleverness, and never add a dependency that isn't in `requirements.txt` without a reason.

## Run and test

```bash
pip3 install -r requirements.txt
streamlit run app.py                 # http://localhost:8501
python3 tests/test_model.py          # must print OK for all cases
```

The engine takes ~1 ms per run and the solver ~5 ms, so recomputing every interaction is fine.

## Known open items / ideas (ask me before doing large ones)

- **Satellite count in the recommended plan.** In the case comparison it shows ~1.04M satellites and ~22.7k flights. The unconstrained case shows ~231k satellites. This matches Excel, but it needs a clear explanation (or a better display, e.g. compute per satellite by class), because an interviewer will ask.
- **Section 2 tabs.** "What binds today" is used÷available for the selected case; "What is needed" is Solver uses ÷ case supply (additions excluded). Chip outline marks where shortfall > 0.01 and chips ≥ 99.5%.
- **Small segments.** Bar labels on small segments are hidden (`uniformtext_mode="hide"`). Consider hover-only for those.
- **"60-second story" mode.** An optional guided walkthrough for the demo could step through the sections in order.
- **Mobile layout.** Not a priority; the demo is on a laptop.

## How I like changes handled

- **Before multi-file or logic changes:** tell me the plan first.
- **Afterward:** list every change you made, then run the test.
- **Keep it concise.** No padding, and lead with what changed.
