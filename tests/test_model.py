"""Regression test: the app engine must reproduce the Excel model (v2115) on the case data.

Expected values were saved from this engine after it matched the Excel workbook cell by cell (413 checks x 12 scenarios);
headline totals tie to the workbook (49.9 GW constrained, 42.9 GW seed mix, 163.7 GW plan, $4,125.7B objective). Run:  python3 tests/test_model.py   (or pytest)
"""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from model.engine import run, load_defaults
from model.solver import solve
from model.economics import selected_case_economics

EXP = json.load(open(os.path.join(os.path.dirname(__file__), "expected.json")))


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1, abs(b))


def check(name, inp):
    sol = solve(inp); R = run(inp, sol); e = EXP[name]; bad = []
    for k in ("realized", "flights_sso", "flights_leo", "solar_used", "orion_used", "vega_used"):
        for j, (a, b) in enumerate(zip(R[k], e[k])):
            if not close(a, b): bad.append((k, j, a, b))
    for j in range(6):
        for i in range(4):
            if not close(R["sats"][j][i], e["sats"][j][i]): bad.append(("sats", j, i))
    for k in ("objective",):
        if not close(sol[k], e[k], 1e-5): bad.append((k, sol[k], e[k]))
    for k in ("total", "value", "npv", "npv_ex_base"):
        if not close(sol["pv"][k], e["pv"][k], 1e-5): bad.append(("pv", k, sol["pv"][k], e["pv"][k]))
    for j, (a, b) in enumerate(zip(sol["compute"], e["solver_compute"])):
        if not close(a, b, 1e-5): bad.append(("solver_compute", j, a, b))
    return bad


def cases():
    d = load_defaults()
    a = copy.deepcopy(d); a["toggles"]["apply_solver"] = 1
    c = copy.deepcopy(d); c["toggles"]["mix"] = "Custom"
    return {"defaults": d, "additions_applied": a, "custom_mix": c}


def test_parity():
    for name, inp in cases().items():
        bad = check(name, inp)
        assert not bad, (name, bad[:5])


def test_selected_case_matches_solver_plan():
    """With additions applied, selected-case NPV matches the Solver plan NPV (whole-satellite rounding)."""
    inp = copy.deepcopy(load_defaults())
    inp["toggles"]["apply_solver"] = 1
    sol = solve(inp)
    R = run(inp, sol)
    econ = selected_case_economics(inp, R, sol)
    a, b = econ["pv"]["npv"], sol["pv"]["npv"]
    assert abs(a - b) <= 0.001 * abs(b), (a, b)


if __name__ == "__main__":
    tot = 0
    for name, inp in cases().items():
        bad = check(name, inp); tot += len(bad)
        print(f"{name:20} {'OK' if not bad else bad[:5]}")
    try:
        test_selected_case_matches_solver_plan()
        print(f"{'selected_case_econ':20} OK")
    except AssertionError as ex:
        print(f"{'selected_case_econ':20} FAIL {ex}")
        tot += 1
    sys.exit(1 if tot else 0)
