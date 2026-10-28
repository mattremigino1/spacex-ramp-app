"""AI satellite launch ramp: Python port of the Excel model (version 2115).

Every function mirrors a block of the workbook. Row numbers in comments refer to the
'Satellite ramp (constrained)' tab unless stated otherwise, so each number can be audited
against the Excel file.
"""
import math, copy, json, os

BIG = 9_000_000_000.0
_HERE = os.path.dirname(os.path.abspath(__file__))


def load_defaults():
    with open(os.path.join(_HERE, "defaults.json")) as f:
        return json.load(f)


def ru(x):
    """Excel ROUNDUP(x, 0) on a value already cleaned of float noise."""
    x = round(x, 9)
    return math.ceil(x) if x >= 0 else math.floor(x)


def rd(x):
    """Excel ROUNDDOWN(x, 0)."""
    x = round(x, 9)
    return math.floor(x) if x >= 0 else math.ceil(x)


def lifetime_value_per_gw(c, compute_deg, avg_life):
    """Assumptions E72: lifetime contribution per GW ($M), mid-year cash and compute degradation."""
    r = c["wacc"]
    q = (1 - compute_deg) / (1 + r)
    if abs(q - 1) < 1e-15:
        f = avg_life
    else:
        f = q ** 0.5 * (1 - q ** avg_life) / (1 - q)
    return c["contribution"] * 1000 * f


def derive(inp):
    """Assumptions tab derived columns K:Q and chip / vehicle helpers."""
    t = inp["toggles"]
    sd, cd = inp["solar_deg"], inp["compute_deg"]
    orion, vega = inp["chips"][0], inp["chips"][1]
    oW, vW = orion["tdp"] * orion["util"], vega["tdp"] * vega["util"]
    cls = []
    for c in inp["classes"]:
        G, I, life = c["kw"], c["solar_mult"], c["life"]
        K = ru(G / (oW / 1000))
        Lc = ru(G / (vW / 1000))
        Mv = G * (1 - cd) ** life
        Nv = Mv * (1 + (I - 1) * t["aux_share"]) + G * (I - 1) * (1 - t["aux_share"])
        O = max(G * I, Nv / (1 - sd) ** life) if t["eol_sizing"] == 1 else G * I
        cls.append(dict(c, K=K, L=Lc, M=Mv, N=Nv, O=O, P=O / G, Q=O * (1 - sd) ** life, mass=G / c["kw_per_t"]))
    costs = inp["costs"]
    prio = orion["name"] if costs["orion"] / oW <= costs["vega"] / vW else vega["name"]
    avg_life = sum(c["life"] for c in inp["classes"]) / 4
    e72 = lifetime_value_per_gw(costs, cd, avg_life)
    return dict(cls=cls, oW=oW, vW=vW, prio=prio, e72=e72,
                H24=orion["first_year"], H25=vega["first_year"], oname=orion["name"], vname=vega["name"])


def payload(inp, year, orbit):
    v3, v4 = inp["vehicles"]
    v = v4 if year >= v4["year"] else v3
    return v["leo"] if orbit == "LEO" else v["sso"]


def run(inp, solver=None):
    """Run the whole model. `solver` is the Target solver result (needed when Apply Solver additions is on)."""
    inp = copy.deepcopy(inp)
    t = inp["toggles"]
    d = derive(inp)
    cls = d["cls"]
    yrs = inp["years"]
    n = len(yrs)
    T = inp["target"]
    custom = [[inp["custom_mix"][c["id"]][j] for c in cls] for j in range(n)]
    opt = str(t["mix"]).strip() == "Optimized"
    sso = [i for i in range(4) if cls[i]["orbit"] == "SSO"]
    leo = [i for i in range(4) if cls[i]["orbit"] == "LEO"]
    G = [c["kw"] for c in cls]
    Pm = [c["P"] for c in cls]
    Kc = [c["K"] for c in cls]
    Lc = [c["L"] for c in cls]
    prio, H24, H25 = d["prio"], d["H24"], d["H25"]
    Hprio = H24 if prio == d["oname"] else H25
    apply = t.get("apply_solver", 0) == 1 and solver is not None

    # feed from the Target solver (rows 299-303) and the selected mix (Compute ramp rows 20-23)
    add_sso = [solver["feed_sso"][j] if apply else 0 for j in range(n)]
    add_leo = [solver["feed_leo"][j] if apply else 0 for j in range(n)]
    add_sol = [solver["feed_solar"][j] if apply else 0 for j in range(n)]

    R = {k: [None] * n for k in [
        "gpf", "k", "avail", "mix", "max_sso", "max_leo", "fixed_mix", "orion_new", "orion_tot", "orion_exc", "vega_new", "vega_tot", "vega_exc",
        "cap_launch", "cap_solar", "cap_chip", "constrained", "sats", "flights_sso", "flights_leo", "solar_used", "orion_used", "vega_used",
        "realized", "comp_cls", "mass_sso", "mass_leo", "boards", "boards_ai", "fleet_compute", "fleet_solar", "opt_compute", "opt_shares",
        "custom_cap", "binds", "binds_flags", "lever", "strongest", "marg_sso", "marg_leo", "marg_solar", "solar_supply", "solar_new",
        "opt_solar_supply", "cust_solar_supply", "sso_avail", "leo_avail", "chipcap_cls", "pieces", "trim", "round_up", "target_met",
        "sso_best_gpf", "sso_best_P", "leo_best_gpf", "leo_best_P", "sso_sb_P", "leo_sb_P", "orion_compute", "vega_compute", "chip_shortfall",
        "launch_ceiling", "solar_ceiling", "chip_ceiling", "cap_sso_total", "cap_leo_total", "fill", "opt_orion_used", "opt_vega_used"]}

    # carried state
    prev = dict(orion_exc=0, vega_exc=0, sol_carry=0, opt_sol_carry=0, cust_sol_carry=0, opt_o_carry=0, opt_v_carry=0,
                cust_o_carry=0, cust_v_carry=0, fleet_c=0, fleet_s=0)
    sats_hist = []

    for j, y in enumerate(yrs):
        # ---- per-class flight packing (rows 11-14, 247-253) and availability (125-131)
        gpf, kk, av = [], [], []
        hb = 1 if y >= t["heliosb_year"] else 0
        for i, c in enumerate(cls):
            p = payload(inp, y, c["orbit"])
            k_ = rd(p / c["mass"])
            kk.append(k_)
            gpf.append(k_ * G[i] / 1e6)
        for i, c in enumerate(cls):
            av.append(0 if gpf[i] == 0 else (hb if c["gen"] == "Helios-B" else 1))
        R["gpf"][j], R["k"][j], R["avail"][j] = gpf, kk, av

        fl_sso = inp["flights_sso"][j] + add_sso[j]       # row 301
        fl_leo = inp["flights_leo"][j] + add_leo[j]       # row 302
        R["sso_avail"][j], R["leo_avail"][j] = fl_sso, fl_leo

        # ---- solar supply (rows 234-244)
        sol_new = inp["solar"][j] + add_sol[j]
        sol_tot = sol_new + prev["sol_carry"]
        opt_sol = sol_new + prev["opt_sol_carry"]
        cust_sol = sol_new + prev["cust_sol_carry"]
        R["solar_new"][j], R["solar_supply"][j], R["opt_solar_supply"][j], R["cust_solar_supply"][j] = sol_new, sol_tot, opt_sol, cust_sol

        # ---- chips new supply (rows 22, 25) and optimizer-case supply (285, 288)
        o_new = inp["orion"][j] if y >= H24 else 0
        v_new = inp["vega"][j] if y >= H25 else 0
        opt_o = o_new + prev["opt_o_carry"]
        opt_v = v_new + prev["opt_v_carry"]
        cust_o = o_new + prev["cust_o_carry"]
        cust_v = v_new + prev["cust_v_carry"]

        # ---- optimizer (rows 134-195)
        chipcap = [(opt_o * G[i] / Kc[i] + opt_v * G[i] / Lc[i]) / 1e6 for i in range(4)]
        R["chipcap_cls"][j] = chipcap

        def best(orb, flights):
            idx = [i for i in range(4) if cls[i]["orbit"] == orb and av[i] == 1]
            lb = max([gpf[i] for i in idx], default=0)                                            # 141
            lbP = BIG if lb == 0 else min([Pm[i] for i in idx if gpf[i] == lb], default=0)        # 142
            lbC = BIG if lb == 0 else min([chipcap[i] for i in idx if gpf[i] == lb and Pm[i] == lbP], default=0)  # 143
            sbP = BIG if not idx else min(Pm[i] for i in idx)                                     # 144
            sbG = 0 if sbP == BIG else max([gpf[i] for i in idx if Pm[i] == sbP], default=0)     # 145
            sbC = BIG if sbG == 0 else min([chipcap[i] for i in idx if gpf[i] == sbG and Pm[i] == sbP], default=0)  # 146
            return lb, lbP, lbC, sbP, sbG, sbC

        J141, J142, J143, J144, J145, J146 = best("SSO", fl_sso)
        J148, J149, J150, J151, J152, J153 = best("LEO", fl_leo)
        J140, J147 = fl_sso, fl_leo
        lon, son, con = t["launch_on"] == 1, t["solar_on"] == 1, t["chips_on"] == 1
        J155 = 0 if J145 == 0 else (J140 * J145 if lon else BIG)
        J156 = J140 * (J141 - J145) if (lon and J141 > J145) else 0
        J157 = 0 if J152 == 0 else (J147 * J152 if lon else BIG)
        J158 = J147 * (J148 - J152) if (lon and J148 > J152) else 0
        J160 = J144
        J161 = (J142 * J141 - J144 * J145) / (J141 - J145) if J141 > J145 else BIG
        J162 = J151
        J163 = (J149 * J148 - J151 * J152) / (J148 - J152) if J148 > J152 else BIG
        eff = [J160, J161, J162, J163]
        J165 = sum(1 for e in eff if e < J160) + 1
        J166 = sum(1 for e in eff if e < J161) + (1 if J160 == J161 else 0) + 1
        J167 = sum(1 for e in eff if e < J162) + sum(1 for e in eff[:2] if e == J162) + 1
        J168 = sum(1 for e in eff if e < J163) + sum(1 for e in eff[:3] if e == J163) + 1
        order = [J165, J166, J167, J168]
        steps = [order.index(k) for k in (1, 2, 3, 4)]          # rows 170-173 (0-based piece index)
        cap_pieces = [J155, J156, J157, J158]
        J174 = min(T[j], min(J143, J146, J150, J153) if con else BIG)
        solar_lim = opt_sol if son else BIG
        added, used = [], []
        for s_, pc in enumerate(steps):
            a = max(0, min(cap_pieces[pc], J174 - sum(added), (solar_lim - sum(used)) / eff[pc]))
            added.append(a); used.append(a * eff[pc])
        by_piece = [0, 0, 0, 0]
        for s_, pc in enumerate(steps): by_piece[pc] += added[s_]
        J183 = by_piece[1] * J141 / (J141 - J145) if J141 > J145 else 0
        J184 = by_piece[0] + by_piece[1] - J183
        J185 = by_piece[3] * J148 / (J148 - J152) if J148 > J152 else 0
        J186 = by_piece[2] + by_piece[3] - J185
        J190 = J183 + J184 + J185 + J186
        R["opt_compute"][j] = J190
        R["fill"][j] = dict(steps=steps, added=added, used=used)

        def cnt(orb, g_, p_):
            return sum(1 for i in range(4) if cls[i]["orbit"] == orb and av[i] == 1 and gpf[i] == g_ and Pm[i] == p_)
        if J190 == 0:
            shares = list(custom[j])
        else:
            shares = []
            for i in range(4):
                v = 0
                if av[i] == 1 and cls[i]["orbit"] == "SSO" and gpf[i] == J141 and Pm[i] == J142: v += J183 / cnt("SSO", J141, J142)
                if av[i] == 1 and cls[i]["orbit"] == "SSO" and gpf[i] == J145 and Pm[i] == J144: v += J184 / cnt("SSO", J145, J144)
                if av[i] == 1 and cls[i]["orbit"] == "LEO" and gpf[i] == J148 and Pm[i] == J149: v += J185 / cnt("LEO", J148, J149)
                if av[i] == 1 and cls[i]["orbit"] == "LEO" and gpf[i] == J152 and Pm[i] == J151: v += J186 / cnt("LEO", J152, J151)
                shares.append(v / J190)
        R["opt_shares"][j] = shares

        # optimizer-case chip use and carry (rows 286-290)
        nK = J190 * 1e6 * sum(shares[i] * Kc[i] / G[i] for i in range(4))
        nL = J190 * 1e6 * sum(shares[i] * Lc[i] / G[i] for i in range(4))
        if not con:
            ou_o = nK if ((prio == d["oname"] and y >= H24) or (prio != d["oname"] and y < H25)) else 0
            vu_o = nL if ((prio == d["vname"] and y >= H25) or (prio != d["vname"] and y < H24)) else 0
        elif prio == d["oname"]:
            ou_o = min(nK, opt_o)
            vu_o = nL if nK == 0 else (1 - min(1, opt_o / nK)) * nL
        else:
            vu_o = min(nL, opt_v)
            ou_o = nK if nL == 0 else (1 - min(1, opt_v / nL)) * nK
        R["opt_orion_used"][j], R["opt_vega_used"][j] = ou_o, vu_o

        # custom-mix case (rows 198-201, 242-244, 291-296)
        cm = custom[j]
        def cust_launch(orb, flights):
            idx = [i for i in range(4) if cls[i]["orbit"] == orb]
            sm = sum(cm[i] for i in idx)
            if sm == 0: return BIG
            if any(cm[i] > 0 and gpf[i] == 0 for i in idx): return 0
            return flights / sum(cm[i] / (gpf[i] + (gpf[i] == 0)) for i in idx)
        J198 = min(cust_launch("SSO", J140), cust_launch("LEO", J147)) if lon else BIG
        J199 = cust_sol / sum(cm[i] * Pm[i] for i in range(4)) if son else BIG
        J200 = (cust_o / sum(cm[i] * Kc[i] / G[i] for i in range(4)) + cust_v / sum(cm[i] * Lc[i] / G[i] for i in range(4))) / 1e6 if con else BIG
        J201 = min(T[j], J198, J199, J200)
        R["custom_cap"][j] = J201
        cnK = J201 * 1e6 * sum(cm[i] * Kc[i] / G[i] for i in range(4))
        cnL = J201 * 1e6 * sum(cm[i] * Lc[i] / G[i] for i in range(4))
        if not con:
            ou_c = cnK if ((prio == d["oname"] and y >= H24) or (prio != d["oname"] and y < H25)) else 0
            vu_c = cnL if ((prio == d["vname"] and y >= H25) or (prio != d["vname"] and y < H24)) else 0
        elif prio == d["oname"]:
            ou_c = min(cnK, cust_o)
            vu_c = cnL if cnK == 0 else (1 - min(1, cust_o / cnK)) * cnL
        else:
            vu_c = min(cnL, cust_v)
            ou_c = cnK if cnL == 0 else (1 - min(1, cust_v / cnL)) * cnK
        cust_sol_used = J201 * sum(cm[i] * Pm[i] for i in range(4))

        # ---- selected mix (Compute ramp rows 20-23)
        if apply and solver["compute"][j] > 0:
            mix = [solver["comp_cls"][j][i] / solver["compute"][j] for i in range(4)]
        elif opt:
            mix = shares
        else:
            mix = list(cm)
        R["mix"][j] = mix

        # ---- capacity at the selected mix (rows 15-34)
        def max_orb(idx, flights):
            sm = sum(mix[i] for i in idx)
            if sm == 0: return flights * max(gpf[i] for i in idx)
            if any(mix[i] > 0 and gpf[i] == 0 for i in idx): return 0
            return flights / sum(mix[i] / (gpf[i] + (gpf[i] == 0)) for i in idx) * sm
        J15, J16 = max_orb(sso, fl_sso), max_orb(leo, fl_leo)
        sS, sL = sum(mix[i] for i in sso), sum(mix[i] for i in leo)
        J18 = min(BIG if sS == 0 else J15 / sS, BIG if sL == 0 else J16 / sL)
        J23 = o_new + prev["orion_exc"]
        J26 = v_new + prev["vega_exc"]
        J30 = J18 if lon else BIG
        J31 = sol_tot / sum(mix[i] * Pm[i] for i in range(4)) if son else BIG
        J32 = (J23 / sum(mix[i] * Kc[i] / G[i] for i in range(4)) + J26 / sum(mix[i] * Lc[i] / G[i] for i in range(4))) / 1e6 if con else BIG
        J34 = min(J30, J31, J32, T[j])
        R["max_sso"][j], R["max_leo"][j], R["fixed_mix"][j] = J15, J16, J18
        R["cap_launch"][j], R["cap_solar"][j], R["cap_chip"][j], R["constrained"][j] = J30, J31, J32, J34
        R["orion_tot"][j], R["vega_tot"][j], R["orion_new"][j], R["vega_new"][j] = J23, J26, o_new, v_new

        # ---- whole satellites with the flight trim (rows 255-277, 50-53)
        J277 = 1 if T[j] <= min(J30, J31, J32) - 2 * sum(G[i] for i in range(4) if mix[i] > 0) / 1e6 else 0
        cand = [(ru if J277 == 1 else rd)(J34 * mix[i] / (G[i] / 1e6)) for i in range(4)]
        fbc = [0 if cand[i] == 0 else (ru(cand[i] / kk[i]) if kk[i] else BIG) for i in range(4)]
        trim = {}
        for orb, (ia, ib), flights in (("SSO", sso, fl_sso), ("LEO", leo, fl_leo)):
            over = max(0, fbc[ia] + fbc[ib] - flights) if lon else 0
            if over == 0: trim[orb] = 0
            else:
                la = 9e18 if fbc[ia] == 0 else (cand[ia] - (fbc[ia] - 1) * kk[ia]) * G[ia]
                lb = 9e18 if fbc[ib] == 0 else (cand[ib] - (fbc[ib] - 1) * kk[ib]) * G[ib]
                trim[orb] = 1 if la <= lb else 2
        sats = list(cand)
        for orb, (ia, ib) in (("SSO", sso), ("LEO", leo)):
            if trim[orb] == 1: sats[ia] = (fbc[ia] - 1) * kk[ia]
            if trim[orb] == 2: sats[ib] = (fbc[ib] - 1) * kk[ib]
        R["trim"][j], R["round_up"][j], R["sats"][j] = trim, J277, sats
        flc = [0 if sats[i] == 0 else (ru(sats[i] / kk[i]) if kk[i] else BIG) for i in range(4)]
        R["flights_sso"][j] = sum(flc[i] for i in sso)
        R["flights_leo"][j] = sum(flc[i] for i in leo)
        comp_cls = [sats[i] * G[i] / 1e6 for i in range(4)]
        R["comp_cls"][j] = comp_cls
        R["realized"][j] = sum(comp_cls)
        R["mass_sso"][j] = sum(sats[i] * cls[i]["mass"] for i in sso)
        R["mass_leo"][j] = sum(sats[i] * cls[i]["mass"] for i in leo)
        R["solar_used"][j] = sum(sats[i] * G[i] * Pm[i] for i in range(4)) / 1e6

        # ---- chips used (rows 83-92)
        nKs, nLs = sum(sats[i] * Kc[i] for i in range(4)), sum(sats[i] * Lc[i] for i in range(4))
        if not con:
            ou = nKs if ((prio == d["oname"] and y >= H24) or (prio != d["oname"] and y < Hprio)) else 0
            vu = nLs if ((prio == d["vname"] and y >= H25) or (prio != d["vname"] and y < Hprio)) else 0
        elif prio == d["oname"]:
            ou = min(nKs, J23)
            vu = nLs if nKs == 0 else ru((1 - min(1, J23 / nKs)) * nLs)
        else:
            vu = min(nLs, J26)
            ou = nKs if nLs == 0 else ru((1 - min(1, J26 / nLs)) * nKs)
        R["orion_used"][j], R["vega_used"][j] = ou, vu
        gsum = sum(sats[i] * G[i] for i in range(4)) / 1e6
        R["orion_compute"][j] = (0 if nKs == 0 else ou / nKs) * gsum
        R["vega_compute"][j] = (0 if nLs == 0 else vu / nLs) * gsum
        R["chip_shortfall"][j] = (0 if nKs == 0 else max(ou - J23, 0) / nKs) * gsum + (0 if nLs == 0 else max(vu - J26, 0) / nLs) * gsum

        # ---- boards (rows 95-102)
        nA = sum(sats[i] for i in range(4) if cls[i]["gen"] == "Helios-A")
        nB = sum(sats[i] for i in range(4) if cls[i]["gen"] == "Helios-B")
        bds = [nA * b["a"] + nB * b["b"] for b in inp["boards"]]
        R["boards"][j] = sum(bds)
        R["boards_ai"][j] = sum(x for x, b in zip(bds, inp["boards"]) if b["ai"])

        # ---- fleet (rows 105-114)
        sats_hist.append(sats)
        ret = [sats_hist[j - cls[i]["life"]][i] if j - cls[i]["life"] >= 0 else 0 for i in range(4)]
        cd, sd = inp["compute_deg"], inp["solar_deg"]
        fc = prev["fleet_c"] * (1 - cd) + (sum(sats[i] * G[i] for i in range(4)) - sum(ret[i] * cls[i]["M"] for i in range(4))) * (1 - cd) ** 0.5 / 1e6
        fs = prev["fleet_s"] * (1 - sd) + (sum(sats[i] * cls[i]["O"] for i in range(4)) - sum(ret[i] * cls[i]["Q"] for i in range(4))) * (1 - sd) ** 0.5 / 1e6
        R["fleet_compute"][j], R["fleet_solar"][j] = fc, fs

        # ---- binding constraints and lever strength (rows 209-231)
        J209 = BIG if not lon else (BIG if sS == 0 else J15 / sS)
        J210 = BIG if not lon else (BIG if sL == 0 else J16 / sL)
        J211 = 1 if R["realized"][j] >= T[j] * (1 - 1e-9) else 0
        J220 = 1 if (son and sum(used) >= opt_sol * (1 - 1e-9)) else 0
        J221 = 1 if J190 >= J174 * (1 - 1e-9) else 0
        last = 3 if added[3] > 1e-9 else (2 if added[2] > 1e-9 else (1 if added[1] > 1e-9 else 0))
        J222 = eff[steps[last]]
        J223 = 1 / J222 if (J220 == 1 and J221 == 0) else 0
        J224 = 0 if J221 == 1 else ((J145 * (1 - (J160 / J222 if J220 == 1 else 0)) if (J155 > 0 and by_piece[0] >= J155 * (1 - 1e-9)) else 0)
                                    + ((J141 - J145) * (1 - (J161 / J222 if J220 == 1 else 0)) if (J156 > 0 and by_piece[1] >= J156 * (1 - 1e-9)) else 0))
        J225 = 0 if J221 == 1 else ((J152 * (1 - (J162 / J222 if J220 == 1 else 0)) if (J157 > 0 and by_piece[2] >= J157 * (1 - 1e-9)) else 0)
                                    + ((J148 - J152) * (1 - (J163 / J222 if J220 == 1 else 0)) if (J158 > 0 and by_piece[3] >= J158 * (1 - 1e-9)) else 0))
        chipbind_opt = 1 if (J221 == 1 and J174 < T[j] * (1 - 1e-9)) else 0
        if J211 == 1: flags = [0, 0, 0, 0]
        elif opt:
            flags = [1 if J224 > 0 else 0, 1 if J225 > 0 else 0, 1 if J223 > 0 else 0, chipbind_opt]
        else:
            flags = [1 if J209 <= J34 * (1 + 1e-6) else 0, 1 if J210 <= J34 * (1 + 1e-6) else 0,
                     1 if J31 <= J34 * (1 + 1e-6) else 0, 1 if J32 <= J34 * (1 + 1e-6) else 0]
        labels = ["SSO launch", "LEO launch", "Solar", "Chips"]
        binds = "Target met" if J211 == 1 else ("Within rounding of target" if sum(flags) == 0 else " + ".join(l for l, f in zip(labels, flags) if f))
        R["binds"][j], R["binds_flags"][j], R["target_met"][j] = binds, flags, J211
        if opt:
            lev = [0 if J190 == 0 else J140 * J224 / J190, 0 if J190 == 0 else J147 * J225 / J190,
                   0 if J190 == 0 else opt_sol * J223 / J190, chipbind_opt]
        else:
            s4 = sum(flags)
            lev = [0 if s4 == 0 else f / s4 for f in flags]
        R["lever"][j] = lev
        llabels = ["SSO flights", "LEO flights", "Solar", "Chips"]
        R["strongest"][j] = "Target met" if J211 == 1 else (("Within rounding of target" if J190 >= T[j] * (1 - 1e-9) else "n/a") if sum(lev) == 0 else llabels[lev.index(max(lev))])
        R["marg_sso"][j], R["marg_leo"][j], R["marg_solar"][j] = J224, J225, J223
        R["sso_best_gpf"][j], R["sso_best_P"][j], R["leo_best_gpf"][j], R["leo_best_P"][j] = J141, J142, J148, J149
        R["sso_sb_P"][j], R["leo_sb_P"][j] = J144, J151
        R["cap_sso_total"][j], R["cap_leo_total"][j] = J209, J210

        # ---- ceilings (Summary rows 101-103)
        R["launch_ceiling"][j] = min(T[j], J140 * J141 + J147 * J148 if lon else BIG)
        R["solar_ceiling"][j] = min(T[j], opt_sol / min(J144, J151) if son else BIG)
        R["chip_ceiling"][j] = min(T[j], max([chipcap[i] for i in range(4) if av[i] == 1], default=0) if con else BIG)

        # ---- carry state forward
        prev["orion_exc"] = max(J23 - ou, 0) * t["chip_carry"]
        prev["vega_exc"] = max(J26 - vu, 0) * t["chip_carry"]
        prev["sol_carry"] = max(sol_tot - R["solar_used"][j], 0) * t["solar_carry"]
        prev["opt_sol_carry"] = max(opt_sol - sum(used), 0) * t["solar_carry"]
        prev["cust_sol_carry"] = max(cust_sol - cust_sol_used, 0) * t["solar_carry"]
        prev["opt_o_carry"] = max(opt_o - ou_o, 0) * t["chip_carry"]
        prev["opt_v_carry"] = max(opt_v - vu_o, 0) * t["chip_carry"]
        prev["cust_o_carry"] = max(cust_o - ou_c, 0) * t["chip_carry"]
        prev["cust_v_carry"] = max(cust_v - vu_c, 0) * t["chip_carry"]
        prev["fleet_c"], prev["fleet_s"] = fc, fs

    # ---- gap decomposition (Summary rows 105-110)
    gap = {k: [] for k in ("gap", "mix", "flights", "solar", "together", "chips")}
    for j in range(n):
        g_ = T[j] - R["realized"][j]
        m_ = R["opt_compute"][j] - R["realized"][j]
        f_ = max(0, min(T[j], R["solar_ceiling"][j], R["chip_ceiling"][j]) - R["opt_compute"][j]) if (R["marg_sso"][j] > 0 or R["marg_leo"][j] > 0) else 0
        s_ = max(0, min(T[j], R["launch_ceiling"][j], R["chip_ceiling"][j]) - R["opt_compute"][j]) if R["marg_solar"][j] > 0 else 0
        tg = min(T[j], R["chip_ceiling"][j]) - R["opt_compute"][j] - f_ - s_
        gap["gap"].append(g_); gap["mix"].append(m_); gap["flights"].append(f_); gap["solar"].append(s_); gap["together"].append(tg)
        gap["chips"].append(g_ - m_ - f_ - s_ - tg)
    R["gap_parts"] = gap

    R["unconstrained"] = unconstrained(inp, d, R)
    R["derived"] = d
    R["inputs"] = inp
    return R


def unconstrained(inp, d, R):
    """'Satellite ramp (unconstrained)' tab: what the target needs at the selected mix."""
    cls = d["cls"]; yrs = inp["years"]; n = len(yrs); T = inp["target"]
    G = [c["kw"] for c in cls]
    out = {k: [] for k in ("sats", "sats_cls", "comp_cls", "flights_sso", "flights_leo", "solar", "orion", "vega", "boards", "boards_ai",
                           "mass_sso", "mass_leo", "fleet_compute", "fleet_solar")}
    prio, H24, H25 = d["prio"], d["H24"], d["H25"]
    Hprio = H24 if prio == d["oname"] else H25
    fc = fs = 0; hist = []
    cd, sd = inp["compute_deg"], inp["solar_deg"]
    for j, y in enumerate(yrs):
        mix = R["mix"][j]; kk = R["k"][j]
        comp = [T[j] * mix[i] for i in range(4)]
        sats = [ru(comp[i] / (G[i] / 1e6)) for i in range(4)]
        fl = [0 if sats[i] == 0 else (ru(sats[i] / kk[i]) if kk[i] else BIG) for i in range(4)]
        out["sats_cls"].append(sats); out["sats"].append(sum(sats)); out["comp_cls"].append(comp)
        out["flights_sso"].append(sum(fl[i] for i in range(4) if cls[i]["orbit"] == "SSO"))
        out["flights_leo"].append(sum(fl[i] for i in range(4) if cls[i]["orbit"] == "LEO"))
        out["solar"].append(sum(sats[i] * G[i] * cls[i]["P"] for i in range(4)) / 1e6)
        okO = (prio == d["oname"] and y >= H24) or (prio != d["oname"] and y < Hprio)
        okV = (prio == d["vname"] and y >= H25) or (prio != d["vname"] and y < Hprio)
        out["orion"].append(sum(sats[i] * cls[i]["K"] for i in range(4)) if okO else 0)
        out["vega"].append(sum(sats[i] * cls[i]["L"] for i in range(4)) if okV else 0)
        nA = sum(sats[i] for i in range(4) if cls[i]["gen"] == "Helios-A"); nB = sum(sats[i] for i in range(4) if cls[i]["gen"] == "Helios-B")
        bds = [nA * b["a"] + nB * b["b"] for b in inp["boards"]]
        out["boards"].append(sum(bds)); out["boards_ai"].append(sum(x for x, b in zip(bds, inp["boards"]) if b["ai"]))
        out["mass_sso"].append(sum(sats[i] * cls[i]["mass"] for i in range(4) if cls[i]["orbit"] == "SSO"))
        out["mass_leo"].append(sum(sats[i] * cls[i]["mass"] for i in range(4) if cls[i]["orbit"] == "LEO"))
        hist.append(sats)
        ret = [hist[j - cls[i]["life"]][i] if j - cls[i]["life"] >= 0 else 0 for i in range(4)]
        fc = fc * (1 - cd) + (sum(sats[i] * G[i] for i in range(4)) - sum(ret[i] * cls[i]["M"] for i in range(4))) * (1 - cd) ** 0.5 / 1e6
        fs = fs * (1 - sd) + (sum(sats[i] * cls[i]["O"] for i in range(4)) - sum(ret[i] * cls[i]["Q"] for i in range(4))) * (1 - sd) ** 0.5 / 1e6
        out["fleet_compute"].append(fc); out["fleet_solar"].append(fs)
    return out
