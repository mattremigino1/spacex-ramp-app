"""Target solver: lowest-cost plan to hit the compute target (Python version of the Excel 'Target solver' tab).

Minimizes discounted cost + discounted value of compute not delivered, choosing each year's flights by class,
the chip type on each satellite, new launch capacity by orbit, new solar fab capacity and any shortfall.
Same linear program as the Excel Solver setup (Simplex LP, variables non-negative).
"""
import math
import numpy as np
from scipy.optimize import linprog
from .engine import derive, payload, rd

C4 = range(4)
NV = 16
F_, O_, V_, BS, BL, BF, SH = 0, 4, 8, 12, 13, 14, 15


def ix(j, k):
    return j * NV + k


def params(inp):
    d = derive(inp); cls = d["cls"]; t = inp["toggles"]; c = inp["costs"]; yrs = inp["years"]; n = len(yrs)
    r = c["wacc"]
    P = dict(n=n, T=list(inp["target"]), DF=[1 / (1 + r) ** j for j in range(n)],
             aL=[1 if y >= c["launch_first"] else 0 for y in yrs], aF=[1 if y >= c["fab_first"] else 0 for y in yrs],
             aO=[1 if y >= d["H24"] else 0 for y in yrs], aV=[1 if y >= d["H25"] else 0 for y in yrs],
             cust=[1 if str(t["mix"]).strip() == "Custom" else 0] * n,
             FS=[inp["flights_sso"][j] if t["launch_on"] == 1 else 1e7 for j in range(n)],
             FL=[inp["flights_leo"][j] if t["launch_on"] == 1 else 1e7 for j in range(n)],
             S=[inp["solar"][j] if t["solar_on"] == 1 else 1e6 for j in range(n)],
             OS=[inp["orion"][j] if yrs[j] >= d["H24"] else 0 for j in range(n)],
             VS=[inp["vega"][j] if yrs[j] >= d["H25"] else 0 for j in range(n)],
             pL=c["launch_capex"], pOps=c["ops"], pFab=c["fab_capex"], pCell=c["cells"], pO=c["orion"], pV=c["vega"], pHW=c["hardware"],
             pen=d["e72"], e55=t["solar_carry"], cf=t["chip_carry"], chipon=t["chips_on"], L74=int(c["launch_lead"]), L73=int(c["fab_lead"]), r=r,
             tps=[cl["mass"] for cl in cls], orb=[cl["orbit"] for cl in cls])
    av, gpf, k, Ps, K, L, sh = ([[0] * n for _ in C4] for _ in range(7))
    for j, y in enumerate(yrs):
        hb = 1 if y >= t["heliosb_year"] else 0
        for i, cl in enumerate(cls):
            kk = rd(payload(inp, y, cl["orbit"]) / cl["mass"])
            k[i][j] = kk; gpf[i][j] = kk * cl["kw"] / 1e6
            av[i][j] = 0 if gpf[i][j] == 0 else (hb if cl["gen"] == "Helios-B" else 1)
            Ps[i][j] = cl["P"]; K[i][j] = cl["K"]; L[i][j] = cl["L"]; sh[i][j] = inp["custom_mix"][cl["id"]][j]
    P.update(av=av, gpf=gpf, k=k, Ps=Ps, K=K, L=L, sh=sh)
    return P, d


def build(P):
    Y = P["n"]; n = Y * NV; c = np.zeros(n); Aub = []; bub = []; Aeq = []; beq = []
    orb = P["orb"]

    def used_solar(j):
        r = np.zeros(n)
        for i in C4: r[ix(j, F_ + i)] = P["av"][i][j] * P["gpf"][i][j] * P["Ps"][i][j]
        return r
    for j in range(Y):
        d = P["DF"][j]; dL = (1 + P["r"]) ** -(j - P["L74"]); dF = (1 + P["r"]) ** -(j - P["L73"])
        for i in C4:
            c[ix(j, F_ + i)] += d * (P["av"][i][j] * P["pOps"] / 1000 + P["av"][i][j] * P["gpf"][i][j] * P["Ps"][i][j] * P["pCell"] / 1000
                                     + P["av"][i][j] * P["k"][i][j] * P["tps"][i] * P["pHW"] / 1000)
            c[ix(j, O_ + i)] += d * P["K"][i][j] * P["aO"][j] * P["pO"] / 1000
            c[ix(j, V_ + i)] += d * P["L"][i][j] * P["aV"][j] * P["pV"] / 1000
        c[ix(j, BS)] += dL * P["aL"][j] * P["pL"] / 1000; c[ix(j, BL)] += dL * P["aL"][j] * P["pL"] / 1000
        c[ix(j, BF)] += dF * P["aF"][j] * P["pFab"] / 1000; c[ix(j, SH)] += d * P["pen"] / 1000
        r = np.zeros(n)
        for i in C4: r[ix(j, F_ + i)] = -P["av"][i][j] * P["gpf"][i][j]
        r[ix(j, SH)] = -1; Aub.append(r); bub.append(-P["T"][j])
        for o, base, B in (("SSO", P["FS"], BS), ("LEO", P["FL"], BL)):
            r = np.zeros(n)
            for i in C4:
                if orb[i] == o: r[ix(j, F_ + i)] = P["av"][i][j]
            for tt in range(j + 1): r[ix(tt, B)] = -P["aL"][tt]
            Aub.append(r); bub.append(base[j])
        r = np.zeros(n); rhs = 0
        for tt in range(j + 1):
            w = P["e55"] ** (j - tt); r += w * used_solar(tt); rhs += w * P["S"][tt]
            for u in range(tt + 1): r[ix(u, BF)] -= w * P["aF"][u]
        Aub.append(r); bub.append(rhs)
        for off, KK, flag, sup in ((O_, "K", "aO", "OS"), (V_, "L", "aV", "VS")):
            r = np.zeros(n); rhs = 0
            for tt in range(j + 1):
                w = P["cf"] ** (j - tt); rhs += w * ((P[sup][tt] / 1e6) if P["chipon"] == 1 else 1e6)
                for i in C4: r[ix(tt, off + i)] += w * P[KK][i][tt] * P[flag][tt] / 1e6
            Aub.append(r); bub.append(rhs)
        for i in C4:
            r = np.zeros(n); r[ix(j, F_ + i)] = P["av"][i][j] * P["k"][i][j]; r[ix(j, O_ + i)] = -P["aO"][j]; r[ix(j, V_ + i)] = -P["aV"][j]
            Aeq.append(r); beq.append(0)
        if P["cust"][j]:
            for i in C4:
                r = np.zeros(n)
                for m in C4: r[ix(j, F_ + m)] = -P["sh"][i][j] * P["av"][m][j] * P["gpf"][m][j]
                r[ix(j, F_ + i)] += P["av"][i][j] * P["gpf"][i][j]; Aeq.append(r); beq.append(0)
    return c, Aub, bub, Aeq, beq


def _bounds(nv, P, block):
    b = [(0, None)] * nv
    for name in (block or ()):
        k = {"sso": BS, "leo": BL, "fab": BF}[name]
        for j in range(P["n"]):
            b[ix(j, k)] = (0, 0)
    return b


def solve(inp, block=None):
    """Solve the target LP.

    block = optional list of additions to forbid ("sso", "leo", "fab"), used by the app to value each recommended action. Not part of the Excel model.
    """
    P, d = params(inp)
    c, Aub, bub, Aeq, beq = build(P)
    res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq if Aeq else None, b_eq=beq if beq else None, bounds=_bounds(len(c), P, block), method="highs")
    if res.status != 0:
        raise RuntimeError("Solver failed: " + res.message)
    x = res.x.copy()
    Y = P["n"]
    for j in range(Y):
        for i in C4:
            if not P["av"][i][j]: x[ix(j, F_ + i)] = 0
            if not P["aO"][j]: x[ix(j, O_ + i)] = 0
            if not P["aV"][j]: x[ix(j, V_ + i)] = 0
        if not P["aL"][j]: x[ix(j, BS)] = 0; x[ix(j, BL)] = 0
        if not P["aF"][j]: x[ix(j, BF)] = 0
    x[np.abs(x) < 1e-9] = 0
    return summarize(inp, P, d, x, res.fun)


def summarize(inp, P, d, x, obj):
    Y = P["n"]; v = lambda j, k: float(x[ix(j, k)]); c = inp["costs"]; r = P["r"]
    out = dict(objective=obj, decisions=x.tolist())
    flights = [[v(j, F_ + i) * P["av"][i][j] for i in C4] for j in range(Y)]
    comp_cls = [[flights[j][i] * P["gpf"][i][j] for i in C4] for j in range(Y)]
    sats = [[flights[j][i] * P["k"][i][j] for i in C4] for j in range(Y)]
    out["flights_cls"], out["comp_cls"], out["sats_cls"] = flights, comp_cls, sats
    out["compute"] = [sum(cc) for cc in comp_cls]
    out["flights_sso"] = [sum(flights[j][i] for i in C4 if P["orb"][i] == "SSO") for j in range(Y)]
    out["flights_leo"] = [sum(flights[j][i] for i in C4 if P["orb"][i] == "LEO") for j in range(Y)]
    out["shortfall"] = [v(j, SH) for j in range(Y)]
    out["new_sso"] = [v(j, BS) * P["aL"][j] for j in range(Y)]
    out["new_leo"] = [v(j, BL) * P["aL"][j] for j in range(Y)]
    out["new_fab"] = [v(j, BF) * P["aF"][j] for j in range(Y)]
    cum = lambda arr, j: sum(arr[:j + 1])
    out["cap_sso"] = [cum(out["new_sso"], j) for j in range(Y)]
    out["cap_leo"] = [cum(out["new_leo"], j) for j in range(Y)]
    out["cap_fab"] = [cum(out["new_fab"], j) for j in range(Y)]
    out["feed_sso"] = [math.ceil(round(out["cap_sso"][j], 6)) + 1 if out["cap_sso"][j] > 1e-6 else 0 for j in range(Y)]
    out["feed_leo"] = [math.ceil(round(out["cap_leo"][j], 6)) + 1 if out["cap_leo"][j] > 1e-6 else 0 for j in range(Y)]
    out["feed_solar"] = [out["cap_fab"][j] + 0.01 if out["cap_fab"][j] > 1e-9 else 0 for j in range(Y)]
    out["solar_used"] = [sum(comp_cls[j][i] * P["Ps"][i][j] for i in C4) for j in range(Y)]
    out["orion_used"] = [sum(v(j, O_ + i) * P["K"][i][j] for i in C4) * P["aO"][j] / 1e6 for j in range(Y)]
    out["vega_used"] = [sum(v(j, V_ + i) * P["L"][i][j] for i in C4) * P["aV"][j] / 1e6 for j in range(Y)]
    out["sats"] = [sum(s) for s in sats]

    def paid(build_arr, flag, price, lead):
        res = [0.0] * Y
        for tt in range(Y):
            amt = build_arr[tt] * flag[tt] * price / 1000
            pj = tt - lead
            if pj >= 0: res[pj] += amt
            else: res[0] += amt * (1 + r) ** (-pj)        # paid before 2028: grown to 2028 dollars
        return res
    launch_build = [v(j, BS) + v(j, BL) for j in range(Y)]
    cost = {}
    cost["new_launch"] = paid(launch_build, P["aL"], P["pL"], P["L74"])
    cost["new_fab"] = paid([v(j, BF) for j in range(Y)], P["aF"], P["pFab"], P["L73"])
    cost["ops"] = [(out["flights_sso"][j] + out["flights_leo"][j]) * P["pOps"] / 1000 for j in range(Y)]
    cost["cells"] = [out["solar_used"][j] * P["pCell"] / 1000 for j in range(Y)]
    cost["chips"] = [(out["orion_used"][j] * P["pO"] + out["vega_used"][j] * P["pV"]) * 1000 for j in range(Y)]
    cost["hardware"] = [sum(sats[j][i] * P["tps"][i] for i in C4) * P["pHW"] / 1000 for j in range(Y)]
    # base capacity not yet built (fixed): growth from 2029, paid lead years ahead; spend before 2028 excluded (committed)
    base = {"base_launch": [0.0] * Y, "base_fab": [0.0] * Y, "base_terafab": [0.0] * Y}
    fs, fl, so, oo = inp["flights_sso"], inp["flights_leo"], inp["solar"], inp["orion"]
    for j in range(1, Y):
        for key, inc, price, lead in (("base_launch", max(0, fs[j] - fs[j - 1]) + max(0, fl[j] - fl[j - 1]), c["launch_capex"], c["launch_lead"]),
                                      ("base_fab", max(0, so[j] - so[j - 1]), c["fab_capex"], c["fab_lead"]),
                                      ("base_terafab", max(0, oo[j] - oo[j - 1]) / 1e6, c["terafab_capex"], c["terafab_lead"])):
            pj = j - int(lead)
            if pj >= 0: base[key][pj] += inc * price / 1000
    cost.update(base)
    cost["capex"] = [cost["new_launch"][j] + cost["new_fab"][j] + base["base_launch"][j] + base["base_fab"][j] + base["base_terafab"][j] for j in range(Y)]
    cost["variable"] = [cost["ops"][j] + cost["cells"][j] + cost["chips"][j] + cost["hardware"][j] for j in range(Y)]
    cost["total"] = [cost["capex"][j] + cost["variable"][j] for j in range(Y)]
    cost["value"] = [out["compute"][j] * d["e72"] / 1000 for j in range(Y)]
    cost["npv"] = [cost["value"][j] - cost["total"][j] for j in range(Y)]
    cost["npv_ex_base"] = [cost["npv"][j] + base["base_launch"][j] + base["base_fab"][j] + base["base_terafab"][j] for j in range(Y)]
    DF = P["DF"]
    out["pv"] = {k: sum(a * b for a, b in zip(vals, DF)) for k, vals in cost.items()}
    # undiscounted: actual cash, no time-value markup on spend paid before 2028
    raw_new = sum(launch_build[j] * P["aL"][j] * P["pL"] / 1000 + v(j, BF) * P["aF"][j] * P["pFab"] / 1000 for j in range(Y))
    out["undiscounted"] = dict(new_capex=raw_new, base_capex=sum(sum(base[k]) for k in base), variable=sum(cost["variable"]))
    out["undiscounted"]["total"] = sum(out["undiscounted"].values())
    out["cost"] = cost
    out["e72"] = d["e72"]
    return out
