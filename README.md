# AI Satellite Launch Ramp — planning tool

Interactive version of the case model (2028–33): how much AI compute the launch, solar and chip limits allow, what binds each year, and the cheapest plan to close the gap. Same logic and answers as the Excel model (v2115).

## Run it locally (fallback for the live demo)

```bash
pip3 install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. No internet needed once the packages are installed.

## Deploy (free)

1. Push this repo to GitHub (public or private).
2. Go to https://share.streamlit.io, sign in with GitHub, **Create app** → pick this repo, branch `main`, file `app.py` → **Deploy**.
3. Free apps sleep after ~12 hours without traffic; open the link shortly before the interview so it is awake.

## What's in the app

| Section | What it shows |
|---|---|
| Headline | Selected scenario vs. target, what binds by year, big numbers (per-month averages when monthly is on) |
| Compute vs. target | Annual or cumulative; total, by orbit, generation, or class |
| Constraint utilization | Heat map, two tabs: what binds in the selected case today, and what the recommended plan needs vs. case supply; drill into any row for units |
| Annual resource gaps | Stacked bars by year: resource available in the selected scenario (gray) plus the gap to the optimized plan (blue), with 2028-33 totals |
| Annual bottlenecks | Share of the next unit of compute each limit would unlock |
| Annual satellites launched by class | Number or compute, annual or cumulative |
| Annual gigawatts of compute constrained by resource | Gap split into mix, flights alone, solar alone, flights + solar together, chips, with 2028-33 totals per resource |
| Recommended plan | Optimizer actions ranked by value at stake, plus a scenario comparison |
| Scenario economics | Value, cost, NPV, and how much the recommended plan adds (costs are added assumptions) |
| Detailed plan | Year-by-year table with CSV download |

The sidebar holds the scenario dropdown (Base case for now) and all toggles: switch the three limits off for the unconstrained case, or switch on Run optimizer for the optimized case. Every case input and cost assumption is editable on the Data and assumptions tab. Six risk presets remain in `model/scenarios.py` (`RISK_PRESETS`) but are not in the dropdown.

## Files

- `app.py` — the interface
- `model/engine.py` — the model, ported row by row from the Excel workbook
- `model/solver.py` — the target solver (linear program, same formulation as the Excel Solver setup)
- `model/defaults.json` — case data and added cost assumptions
- `model/economics.py` — selected-case economics (mirrors section J of the Excel Summary tab)
- `model/scenarios.py` — presets
- `tests/test_model.py` — regression test against the workbook's results (`python3 tests/test_model.py`)

Case data is fictional.
