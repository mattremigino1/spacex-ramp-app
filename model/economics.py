"""Economics of the selected case. Mirrors section J of the Excel Summary tab."""


def selected_case_economics(inp, R, sol):
    """Economics of the selected case. Mirrors section J of the Excel Summary tab."""
    costs = inp["costs"]
    tg = inp["toggles"]
    apply = tg.get("apply_solver", 0) == 1
    n = len(inp["years"])
    value, new_capex, base_capex = [], [], []
    ops, cells, chips, hardware = [], [], [], []
    total, npv, npv_ex_base = [], [], []
    for j in range(n):
        v = R["realized"][j] * sol["e72"] / 1000
        nc = (sol["cost"]["new_launch"][j] + sol["cost"]["new_fab"][j]) if apply else 0.0
        bc = sol["cost"]["base_launch"][j] + sol["cost"]["base_fab"][j] + sol["cost"]["base_terafab"][j]
        op = (R["flights_sso"][j] + R["flights_leo"][j]) * costs["ops"] / 1000
        ce = R["solar_used"][j] * costs["cells"] / 1000
        ch = (R["orion_used"][j] * costs["orion"] + R["vega_used"][j] * costs["vega"]) / 1000
        hw = (R["mass_sso"][j] + R["mass_leo"][j]) * costs["hardware"] / 1000
        tot = nc + bc + op + ce + ch + hw
        value.append(v)
        new_capex.append(nc)
        base_capex.append(bc)
        ops.append(op)
        cells.append(ce)
        chips.append(ch)
        hardware.append(hw)
        total.append(tot)
        npv.append(v - tot)
        npv_ex_base.append(v - (tot - bc))
    yearly = dict(value=value, new_capex=new_capex, base_capex=base_capex, ops=ops, cells=cells,
                  chips=chips, hardware=hardware, total=total, npv=npv, npv_ex_base=npv_ex_base)
    DF = [1 / (1 + costs["wacc"]) ** j for j in range(n)]
    pv = {k: sum(a * b for a, b in zip(vals, DF)) for k, vals in yearly.items()}
    meaningful = tg["launch_on"] == 1 and tg["solar_on"] == 1 and tg["chips_on"] == 1
    return {"yearly": yearly, "pv": pv, "meaningful": meaningful}
