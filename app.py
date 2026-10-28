"""AI Satellite Launch Ramp: live planning tool (Streamlit).

Run locally:  streamlit run app.py
"""
import copy, json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from model.engine import run, load_defaults
from model.solver import solve
from model.economics import selected_case_economics
from model import scenarios

st.set_page_config(page_title="AI Satellite Launch Ramp", page_icon="🛰️", layout="wide")

# ----------------------------------------------------------------------------------------------- style
WHITE, G1, G2, G3, G4, BG, PANEL = "#FFFFFF", "#BFBFBF", "#8C8C8C", "#595959", "#262626", "#000000", "#0D0D0D"
ACC, ACC2 = "#4A90E2", "#9CC3F0"
CLASS_COL = {"SSO-A": WHITE, "SSO-B": G1, "LEO-A": ACC, "LEO-B": ACC2}
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stMetric { font-family: 'Barlow', 'Helvetica Neue', Arial, sans-serif; }
h1, h2, h3 { text-transform: uppercase; letter-spacing: 0.12em; font-weight: 600 !important; }
h1 { font-size: 1.9rem !important; } h2 { font-size: 1.15rem !important; margin-top: 1.6rem; } h3 { font-size: 0.95rem !important; }
[data-testid="stMetricValue"] { font-size: 2.0rem; font-weight: 600; }
[data-testid="stMetricLabel"] p { text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem; color: #BFBFBF; }
.answer { font-size: 1.15rem; line-height: 1.5; border-left: 0; padding: 0.2rem 0 0.6rem 0; color: #FFFFFF; }
.muted { color: #8C8C8C; font-size: 0.85rem; }
.rec { background: #0D0D0D; border: 1px solid #262626; border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 0.6rem; }
.rec b { letter-spacing: 0.03em; }
.pill { display:inline-block; border:1px solid #595959; border-radius: 999px; padding: 0.05rem 0.6rem; font-size: 0.78rem; color:#BFBFBF; margin-right:0.4rem; }
/* Transparent header must not steal clicks over the sidebar collapse control */
header[data-testid="stHeader"] {
  background: transparent !important;
  pointer-events: none !important;
}
div[data-testid="stToolbar"] {
  background: transparent !important;
  pointer-events: none !important;
}
/* ⋮ menu on the right — do NOT use the broad headerNoPadding selector
   (that also matches #MainMenu and was pinning the menu on the left). */
header[data-testid="stHeader"] #MainMenu {
  position: fixed !important;
  top: 0.55rem !important;
  right: 1rem !important;
  left: unset !important;
  z-index: 1000100 !important;
  pointer-events: auto !important;
}
header[data-testid="stHeader"] #MainMenu button {
  pointer-events: auto !important;
}
/* Header ignores clicks (see above), so re-enable the open-sidebar control */
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] * {
  pointer-events: auto !important;
}
/* Sidebar sits beside the page (pushes content over); fixed width so the scenario dropdown fits */
section[data-testid="stSidebar"][aria-expanded="true"],
section[data-testid="stSidebar"][data-collapsed="false"] {
  width: 24rem !important;
  min-width: 24rem !important;
  max-width: 24rem !important;
}
div[data-testid="stMainBlockContainer"], .block-container {
  max-width: 100% !important;
  padding-left: 2.5rem !important;
  padding-right: 2.5rem !important;
}
div[data-baseweb="popover"], div[data-baseweb="menu"], [data-testid="stSelectboxVirtualDropdown"],
ul[role="listbox"], div.st-key-preset_box [role="listbox"] {
  z-index: 1000000 !important;
}
/* Scenario select: only as wide as the longest option label */
div.st-key-preset_box,
div.st-key-preset_box div.stSelectbox,
div.st-key-preset_box div.react-aria-ComboBox,
div.st-key-preset_box [data-testid="stSelectbox"] {
  width: fit-content !important;
  max-width: 100% !important;
}
div.st-key-preset_box input {
  width: auto !important;
  min-width: 14rem !important; /* fits "Optimized (constrained)" */
}
</style>
""", unsafe_allow_html=True)


def style_fig(fig, h=380, legend=True):
    # Legend below the plot so it never overlaps bars (any toggle / wrap length)
    fig.update_layout(uniformtext_minsize=10, uniformtext_mode="hide", template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h, margin=dict(l=10, r=10, t=20, b=90),
                      font=dict(family="Barlow, Arial", color=WHITE, size=13), showlegend=legend,
                      legend=dict(orientation="h", y=-0.22, x=0, yanchor="top", bgcolor="rgba(0,0,0,0)"), hoverlabel=dict(bgcolor="#111111"))
    fig.update_xaxes(showgrid=False, linecolor=G3, tickfont=dict(color=G1))
    fig.update_yaxes(showgrid=True, gridcolor="#1A1A1A", zeroline=False, tickfont=dict(color=G2))
    return fig


def fmt(x, d=1):
    if isinstance(x, str): return x
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if xf.is_integer():
        return f"{xf:,.0f}"
    if abs(xf) >= 1000:
        return f"{xf:,.0f}"
    return f"{xf:,.{d}f}"


def fmt_cell(v):
    """Format dataframe cells; handles numpy int/float that are not Python int/float."""
    if isinstance(v, str) or isinstance(v, bool) or v is None:
        return v
    try:
        float(v)
    except (TypeError, ValueError):
        return v
    return fmt(v, 1)


# ----------------------------------------------------------------------------------------------- state
DEFAULTS = load_defaults()
YEARS = DEFAULTS["years"]
if "inp" not in st.session_state:
    st.session_state.inp = copy.deepcopy(DEFAULTS)
    st.session_state.ver = 0
    st.session_state.preset = list(scenarios.PRESETS)[0]


def set_preset():
    st.session_state.inp = scenarios.apply(st.session_state.preset_box, DEFAULTS)
    st.session_state.preset = st.session_state.preset_box
    st.session_state.ver += 1


def reset():
    st.session_state.inp = copy.deepcopy(DEFAULTS)
    st.session_state.preset = list(scenarios.PRESETS)[0]
    st.session_state.ver += 1


inp = st.session_state.inp
V = st.session_state.ver
k = lambda name: f"{name}_{V}"

# ----------------------------------------------------------------------------------------------- sidebar: inputs
with st.sidebar:
    st.markdown("### Scenario")
    names = list(scenarios.PRESETS)
    if st.session_state.preset not in names:
        st.session_state.preset = names[0]
    st.selectbox("Preset", names, index=names.index(st.session_state.preset), key="preset_box", on_change=set_preset, label_visibility="collapsed")
    st.button("Reset to case data", on_click=reset, use_container_width=True)
    monthly = st.toggle("Show flows per month", value=False, help="Monthly = average monthly pace (each year split evenly). Cumulative views are switched off.")

    st.markdown("### Toggles")
    t = inp["toggles"]
    t["launch_on"] = int(st.toggle("Starship flight limit", value=t["launch_on"] == 1, key=k("lon")))
    t["solar_on"] = int(st.toggle("Solar limit", value=t["solar_on"] == 1, key=k("son")))
    t["chips_on"] = int(st.toggle("AI chip limit", value=t["chips_on"] == 1, key=k("con")))
    _mix = st.radio("Class and orbit mix", ["Optimized", "Fixed"], index=0 if t["mix"] == "Optimized" else 1, horizontal=True, key=k("mix"),
                    help="Optimized lets the model and the optimizer pick the class split that maximizes compute or minimizes cost. Fixed holds each year's split at the seed mix table (editable on the Data and assumptions tab), for both the selected case and the optimizer's plan.")
    t["mix"] = "Optimized" if _mix == "Optimized" else "Custom"
    t["apply_solver"] = int(st.toggle("Run optimizer", value=t.get("apply_solver", 0) == 1, key=k("apply"),
                                      help="Adds the launch capacity and solar fab the Solver recommends, then runs the plan in whole satellites."))
    with st.expander("More toggles"):
        t["eol_sizing"] = int(st.toggle("Size solar for end of life", value=t["eol_sizing"] == 1, key=k("eol")))
        t["chip_carry"] = int(st.toggle("Carry unused chips forward", value=t["chip_carry"] == 1, key=k("cc")))
        t["solar_carry"] = int(st.toggle("Carry unused solar forward", value=t["solar_carry"] == 1, key=k("sc")))
        t["heliosb_year"] = int(st.selectbox("First year Helios-B can launch", list(range(2028, 2035)), index=list(range(2028, 2035)).index(t["heliosb_year"]), key=k("hb")))
        inp["vehicles"][1]["year"] = int(st.selectbox("First year of Starship V4", list(range(2028, 2035)), index=list(range(2028, 2035)).index(inp["vehicles"][1]["year"]), key=k("v4")))
        t["aux_share"] = st.slider("Auxiliary load that scales with compute", 0.0, 1.0, float(t["aux_share"]), 0.05, key=k("aux"))

# ----------------------------------------------------------------------------------------------- tabs: plan vs editable case data
tab_plan, tab_data = st.tabs(["Ramp", "Data and assumptions"])


def year_table(label, rows, key):
    df = pd.DataFrame({r: vals for r, vals in rows.items()}, index=[str(y) for y in YEARS]).T
    cols = {str(y): st.column_config.NumberColumn(str(y), format="localized") for y in YEARS}
    out = st.data_editor(df, key=k(key), use_container_width=True, column_config=cols)
    return {r: [float(out.loc[r, str(y)]) for y in YEARS] for r in rows}


with tab_data:
    st.caption("Case inputs and added cost assumptions. Edits update the Ramp tab.")
    with st.expander("Target, flights, solar, chips", expanded=True):
        e = year_table("", {"Compute target (GW)": inp["target"], "SSO flights": inp["flights_sso"], "LEO flights": inp["flights_leo"],
                            "Solar (GW/yr)": inp["solar"], "Orion chips": inp["orion"], "Vega chips": inp["vega"]}, "case")
        inp["target"], inp["flights_sso"], inp["flights_leo"] = e["Compute target (GW)"], e["SSO flights"], e["LEO flights"]
        inp["solar"], inp["orion"], inp["vega"] = e["Solar (GW/yr)"], e["Orion chips"], e["Vega chips"]
    with st.expander("Seed (custom) mix, share of compute", expanded=True):
        e = year_table("", inp["custom_mix"], "mix_tbl")
        inp["custom_mix"] = e
        bad = [y for j, y in enumerate(YEARS) if abs(sum(e[c][j] for c in e) - 1) > 1e-6]
        if bad: st.warning("Mix does not sum to 100% in " + ", ".join(map(str, bad)))
    with st.expander("Satellite classes", expanded=True):
        cdf = pd.DataFrame(inp["classes"]).set_index("id")[["orbit", "gen", "kw", "kw_per_t", "solar_mult", "life"]]
        cdf.columns = ["Orbit", "Generation", "Compute (kW)", "kW per ton", "Solar multiplier", "Life (yrs)"]
        num = lambda lab: st.column_config.NumberColumn(lab, format="localized")
        ce = st.data_editor(cdf, key=k("cls"), disabled=["Orbit", "Generation"], use_container_width=True,
                            column_config={lab: num(lab) for lab in ("Compute (kW)", "kW per ton", "Solar multiplier", "Life (yrs)")})
        for c in inp["classes"]:
            c["kw"], c["kw_per_t"], c["solar_mult"], c["life"] = (float(ce.loc[c["id"], "Compute (kW)"]), float(ce.loc[c["id"], "kW per ton"]),
                                                                  float(ce.loc[c["id"], "Solar multiplier"]), int(ce.loc[c["id"], "Life (yrs)"]))
    with st.expander("Starship, chips, degradation", expanded=True):
        vdf = pd.DataFrame(inp["vehicles"]).set_index("name")[["leo", "sso"]]; vdf.columns = ["Payload to LEO (t)", "Payload to SSO (t)"]
        ve = st.data_editor(vdf, key=k("veh"), use_container_width=True,
                            column_config={lab: st.column_config.NumberColumn(lab, format="localized")
                                           for lab in ("Payload to LEO (t)", "Payload to SSO (t)")})
        for v in inp["vehicles"]:
            v["leo"], v["sso"] = float(ve.loc[v["name"], "Payload to LEO (t)"]), float(ve.loc[v["name"], "Payload to SSO (t)"])
        chdf = pd.DataFrame(inp["chips"]).set_index("name")[["tdp", "util", "first_year"]]; chdf.columns = ["TDP (W)", "Utilization", "First year"]
        che = st.data_editor(chdf, key=k("chips"), use_container_width=True,
                             column_config={lab: st.column_config.NumberColumn(lab, format="localized")
                                            for lab in ("TDP (W)", "Utilization", "First year")})
        for c in inp["chips"]:
            c["tdp"], c["util"], c["first_year"] = float(che.loc[c["name"], "TDP (W)"]), float(che.loc[c["name"], "Utilization"]), int(che.loc[c["name"], "First year"])
        inp["solar_deg"] = st.number_input("Solar degradation per year", 0.0, 0.5, float(inp["solar_deg"]), 0.005, format="%.3f", key=k("sd"))
        inp["compute_deg"] = st.number_input("Compute degradation per year", 0.0, 0.5, float(inp["compute_deg"]), 0.005, format="%.3f", key=k("cd"))
    with st.expander("Circuit boards per satellite"):
        bdf = pd.DataFrame(inp["boards"]).set_index("name"); bdf.columns = ["Helios-A", "Helios-B", "AI-related"]
        be = st.data_editor(bdf, key=k("boards"), use_container_width=True,
                            column_config={"Helios-A": st.column_config.NumberColumn("Helios-A", format="localized"),
                                           "Helios-B": st.column_config.NumberColumn("Helios-B", format="localized")})
        for b in inp["boards"]:
            b["a"], b["b"], b["ai"] = float(be.loc[b["name"], "Helios-A"]), float(be.loc[b["name"], "Helios-B"]), bool(be.loc[b["name"], "AI-related"])
    with st.expander("Costs and value"):
        c = inp["costs"]
        fields = [("launch_capex", "New launch capacity, $M per extra flight/yr", 1.0), ("ops", "Operating cost per flight, $M", 1.0),
                  ("fab_capex", "Solar fab capex, $M per GW/yr", 10.0), ("cells", "Solar cell production cost, $M per GW", 10.0),
                  ("orion", "Orion chip production cost, $M per chip", 0.0005), ("vega", "Vega chip price, $M per chip", 0.005),
                  ("hardware", "Satellite hardware ex chips and cells, $M per ton", 0.05), ("terafab_capex", "Terafab capex, $M per million chips/yr", 250.0),
                  ("wacc", "Discount rate", 0.005), ("contribution", "Contribution, $ per W per year", 0.5)]
        for key_, lab, step in fields:
            c[key_] = st.number_input(lab, value=float(c[key_]), step=step, format="%.4f" if c[key_] < 1 else "%.2f", key=k("c_" + key_))
        for key_, lab in (("launch_first", "First year new launch capacity usable"), ("fab_first", "First year new fab capacity usable"),
                          ("launch_lead", "Launch capacity lead time (yrs)"), ("fab_lead", "Fab lead time (yrs)"), ("terafab_lead", "Terafab lead time (yrs)")):
            c[key_] = int(st.number_input(lab, value=int(c[key_]), step=1, key=k("c_" + key_)))

# ----------------------------------------------------------------------------------------------- compute


@st.cache_data(show_spinner=False)
def compute(inp_json):
    inp = json.loads(inp_json)
    inp_opt = copy.deepcopy(inp); inp_opt["toggles"]["mix"] = "Optimized"
    inp_cust = copy.deepcopy(inp); inp_cust["toggles"]["mix"] = "Custom"
    sol_opt = solve(inp_opt)
    sol_cust = solve(inp_cust)
    sol = sol_opt if str(inp["toggles"]["mix"]).strip() == "Optimized" else sol_cust
    R = run(inp, sol)
    variants = {}
    # Table rows match the scenario dropdown; Optimized (constrained) = solver plan
    for name, mod in (("Unconstrained", dict(launch_on=0, solar_on=0, chips_on=0, apply_solver=0)),
                      ("Base case (constrained)", dict(apply_solver=0)),
                      ("Optimized (constrained)", dict(apply_solver=1))):
        v = copy.deepcopy(inp); v["toggles"].update(mod)
        variants[name] = run(v, sol)
    # Mix-only optimized run (no additions) for the mix-action GW delta — not shown in the table
    v_opt_mix = copy.deepcopy(inp)
    v_opt_mix["toggles"].update(dict(mix="Optimized", apply_solver=0))
    opt_mix_R = run(v_opt_mix, sol)
    # Value each recommended addition by re-solving with that addition forbidden
    action_vals = {}
    for key, cap_key in (("fab", "cap_fab"), ("leo", "cap_leo"), ("sso", "cap_sso")):
        if max(sol[cap_key]) > 1e-6:
            blocked = solve(inp, block=[key])
            action_vals[key] = {
                "worth_B": blocked["objective"] - sol["objective"],
                "gw_lost": sum(sol["compute"]) - sum(blocked["compute"]),
            }
    v_seed = copy.deepcopy(inp); v_seed["toggles"].update(dict(mix="Custom", apply_solver=0))
    gw_mix = sum(opt_mix_R["realized"]) - sum(run(v_seed, sol)["realized"])
    action_vals["mix"] = {
        "worth_B": sol_opt["pv"]["npv"] - sol_cust["pv"]["npv"],
        "gw": gw_mix,
    }
    return sol, R, variants, sol_opt, sol_cust, opt_mix_R, action_vals


try:
    sol, R, VAR, sol_opt, sol_cust, opt_mix_R, action_vals = compute(json.dumps(inp, sort_keys=True))
except Exception as ex:   # bad input (e.g., a zero payload)
    st.error(f"The model could not run with these inputs: {ex}")
    st.stop()

mf = 1 / 12 if monthly else 1
unit_gw = "GW / month" if monthly else "GW / year"
T = inp["target"]
real = R["realized"]
U = R["unconstrained"]
cum_t, cum_r = sum(T), sum(real)


def case_name():
    tg = inp["toggles"]
    if tg["launch_on"] == 0 and tg["solar_on"] == 0 and tg["chips_on"] == 0 and tg.get("apply_solver", 0) == 0: return "Unconstrained"
    nm = "Constrained, " + ("optimized mix" if tg["mix"] == "Optimized" else "seed mix")
    if tg.get("apply_solver", 0) == 1: nm += " + Solver additions"
    return nm


with tab_plan:
    # ----------------------------------------------------------------------------------------------- header + answer
    st.markdown("# AI Satellite Launch Ramp")
    binds = R["binds"]
    first_short = next((y for y, tm in zip(YEARS, R["target_met"]) if tm == 0), None)


    def binds_story():
        parts, cur, start = [], None, None
        for y, b in zip(YEARS, binds):
            b2 = "target met" if b == "Target met" else ("within rounding" if b.startswith("Within") else b.replace("SSO launch + LEO launch", "flights (both orbits)").replace("SSO launch", "SSO flights").replace("LEO launch", "LEO flights").replace("Solar", "solar").replace("Chips", "chips").replace(" + ", " and "))
            if b2 != cur:
                if cur is not None: parts.append((cur, start, prev))
                cur, start = b2, y
            prev = y
        parts.append((cur, start, prev))
        return "; ".join(f"{p[0]} {p[1]}" + (f"-{str(p[2])[2:]}" if p[2] != p[1] else "") for p in parts)


    st.markdown(f"<div class='answer'><b>{case_name()}:</b> delivers <b>{cum_r:,.1f} GW</b> of the {cum_t:,.1f} GW 2028-33 target "
                f"(<b>{cum_r / cum_t:.0%}</b>).<br>What binds: {binds_story()}.<br>"
                f"<span class='muted'>The recommended plan (most economic added launch capacity and solar fab) reaches {sum(sol['compute']):,.1f} GW "
                f"({sum(sol['compute']) / cum_t:.0%}); see the recommendation section.</span></div>", unsafe_allow_html=True)

    m = st.columns(5)
    if monthly:
        m[0].metric("Target, avg / month", f"{cum_t / 72:,.2f} GW"); m[1].metric("Delivered, avg / month", f"{cum_r / 72:,.2f} GW")
        m[2].metric("2033 target / month", f"{T[-1] / 12:,.2f} GW"); m[3].metric("2033 delivered / month", f"{real[-1] / 12:,.2f} GW")
    else:
        m[0].metric("Target, 2028-33", f"{cum_t:,.1f} GW", f"2033: {T[-1]:,.0f} GW", delta_color="off", delta_arrow="off")
        m[1].metric("Delivered, 2028-33", f"{cum_r:,.1f} GW", f"2033: {real[-1]:,.1f} GW", delta_color="off", delta_arrow="off")
        m[2].metric("Compute in orbit, end 2033", f"{R['fleet_compute'][-1]:,.1f} GW")
        m[3].metric("Satellites launched", f"{sum(sum(s) for s in R['sats']):,.0f}")
    m[4].metric("Shortfall vs target", f"{1 - cum_r / cum_t:.0%}", f"{cum_t - cum_r:,.1f} GW missed", delta_color="off", delta_arrow="off")

    # ----------------------------------------------------------------------------------------------- 1. ramp vs target
    st.markdown("## 1. Compute launched vs. target")
    c1, c2 = st.columns([5.5, 1])
    with c2:
        split = st.radio("Break out by", ["Total", "Orbit", "Generation", "Class and orbit"], key="split")
        cum = st.toggle("Cumulative", value=False, disabled=monthly, key="cum")
        cum = cum and not monthly
    cls = inp["classes"]
    groups = {"Total": {"Selected case": [0, 1, 2, 3]}, "Orbit": {"SSO": [0, 1], "LEO": [2, 3]},
              "Generation": {"Helios-A": [i for i in range(4) if cls[i]["gen"] == "Helios-A"], "Helios-B": [i for i in range(4) if cls[i]["gen"] == "Helios-B"]},
              "Class and orbit": {cls[i]["id"]: [i] for i in range(4)}}[split]
    gcol = {"Selected case": WHITE, "SSO": WHITE, "LEO": ACC, "Helios-A": WHITE, "Helios-B": ACC}
    def acc(a): return [sum(a[:j + 1]) for j in range(len(a))] if cum else a
    with c1:
        fig = go.Figure()
        for gname, idx in groups.items():
            vals = acc([sum(R["comp_cls"][j][i] for i in idx) * mf for j in range(6)])
            fig.add_bar(x=YEARS, y=vals, name=gname, marker_color=gcol.get(gname, CLASS_COL.get(gname, WHITE)), text=[fmt(v, 2 if monthly else 1) for v in vals], textposition="inside", insidetextanchor="end",
                        insidetextfont=dict(color="#000000" if gcol.get(gname, CLASS_COL.get(gname, WHITE)) in (WHITE, G1, ACC2) else WHITE))
        tv = acc([x * mf for x in T])
        fig.add_scatter(x=YEARS, y=tv, name="Target", mode="lines+markers+text", line=dict(color=G2, dash="dash", width=2), text=[fmt(v, 2 if monthly else 1) for v in tv], textposition="top center", textfont=dict(color=G1))
        fig.update_layout(barmode="stack", yaxis_title=("Cumulative GW" if cum else unit_gw))
        st.plotly_chart(style_fig(fig, 400), use_container_width=True)
    with st.expander("Show the numbers"):
        rows = {"Target": [x * mf for x in T]}
        for gname, idx in groups.items(): rows[gname] = [sum(R["comp_cls"][j][i] for i in idx) * mf for j in range(6)]
        rows["Gap to target"] = [(T[j] - real[j]) * mf for j in range(6)]
        rows["Share of target met"] = [f"{real[j] / T[j]:.0%}" if T[j] else "n/a" for j in range(6)]
        rows["What binds"] = binds
        df = pd.DataFrame(rows, index=YEARS).T
        if not monthly:
            df["2028-33"] = [sum(rows[r]) if not isinstance(rows[r][0], str) else "" for r in rows]
        st.dataframe(df.map(lambda v: fmt(v, 2) if isinstance(v, float) else v), use_container_width=True)
        st.download_button("Download CSV", df.to_csv().encode(), "ramp.csv", key="dl1")

    # ----------------------------------------------------------------------------------------------- 2. what binds
    st.markdown("## 2. Utilization of each constraint")
    tab_binds_today, tab_plan_needs = st.tabs(["What binds today", "What is needed"])

    with tab_binds_today:
        avail = {"SSO flights": R["sso_avail"], "LEO flights": R["leo_avail"], "Solar": R["solar_supply"], "Orion chips": R["orion_tot"], "Vega chips": R["vega_tot"]}
        used = {"SSO flights": R["flights_sso"], "LEO flights": R["flights_leo"], "Solar": R["solar_used"], "Orion chips": R["orion_used"], "Vega chips": R["vega_used"]}
        bindmap = {"SSO flights": 0, "LEO flights": 1, "Solar": 2, "Orion chips": 3, "Vega chips": 3}
        rowsn = list(avail)
        z, txt, isb = [], [], []
        for r in rowsn:
            zr, tr, br = [], [], []
            for j in range(6):
                a = avail[r][j]; num = used[r][j]
                u = None if a == 0 else num / a
                zr.append(None if u is None else u); tr.append("n/a" if u is None else f"{u:.0%}")
                b = R["binds_flags"][j][bindmap[r]] == 1 and (r != "Vega chips" or R["vega_used"][j] > 0) and (r != "Orion chips" or R["orion_used"][j] > 0)
                br.append(b)
            z.append(zr); txt.append(tr); isb.append(br)
        fig = go.Figure(go.Heatmap(z=z, x=[str(y) for y in YEARS], y=rowsn, text=txt, texttemplate="%{text}", textfont=dict(size=14, color=WHITE),
                                   colorscale=[[0, "#111111"], [0.5, "#3A3A3A"], [0.66, "#5A5A5A"], [1, ACC]], zmin=0, zmax=1, showscale=False, xgap=3, ygap=3,
                                   hovertemplate="%{y}, %{x}: %{text}<extra></extra>"))
        for i, r in enumerate(rowsn):
            for j in range(6):
                if isb[i][j]:
                    fig.add_shape(type="rect", x0=j - 0.5, x1=j + 0.5, y0=i - 0.5, y1=i + 0.5, line=dict(color=WHITE, width=3))
        fig.update_yaxes(autorange="reversed", showgrid=False)
        st.plotly_chart(style_fig(fig, 300, legend=False), use_container_width=True)
        st.caption("Selected case: share of each resource used. White outline = the limit holding compute back that year.")
        pick = st.segmented_control("Drill into a limit", rowsn, key="drill_today")
        if pick:
            unit = {"SSO flights": "flights", "LEO flights": "flights", "Solar": "GW", "Orion chips": "chips", "Vega chips": "chips"}[pick]
            f = mf
            dd = pd.DataFrame({"Available (incl. carry-forward)": [avail[pick][j] * f for j in range(6)],
                               "Used, selected case": [used[pick][j] * f for j in range(6)]}, index=YEARS).T
            if pick in ("SSO flights", "LEO flights"):
                orb = pick.split()[0]
                for i in range(4):
                    if cls[i]["orbit"] == orb:
                        kk = [R["k"][j][i] for j in range(6)]
                        dd.loc[f"  of which {cls[i]['id']} (selected case)"] = [0 if R['sats'][j][i] == 0 else -(-R['sats'][j][i] // kk[j]) * f for j in range(6)]
            if pick == "Solar":
                for i in range(4): dd.loc[f"  of which {cls[i]['id']} (selected case)"] = [R["sats"][j][i] * cls[i]["kw"] * R["derived"]["cls"][i]["P"] / 1e6 * f for j in range(6)]
            st.markdown(f"**{pick}** ({unit}{' per month' if monthly else ' per year'})")
            st.dataframe(dd.map(lambda v: fmt(v, 1)), use_container_width=True)

    with tab_plan_needs:
        Wo = inp["chips"][0]["tdp"] * inp["chips"][0]["util"]
        Wv = inp["chips"][1]["tdp"] * inp["chips"][1]["util"]
        case_sso, case_leo, case_sol = inp["flights_sso"], inp["flights_leo"], inp["solar"]
        plan_sso, plan_leo, plan_sol = sol["flights_sso"], sol["flights_leo"], sol["solar_used"]
        case_chip_w = [inp["orion"][j] * Wo + inp["vega"][j] * Wv for j in range(6)]
        plan_chip_w = [sol["orion_used"][j] * 1e6 * Wo + sol["vega_used"][j] * 1e6 * Wv for j in range(6)]

        def _ratio(num, den):
            return None if den == 0 else num / den

        ratios = {
            "SSO flights": [_ratio(plan_sso[j], case_sso[j]) for j in range(6)],
            "LEO flights": [_ratio(plan_leo[j], case_leo[j]) for j in range(6)],
            "Solar": [_ratio(plan_sol[j], case_sol[j]) for j in range(6)],
            "AI chips effective watts": [_ratio(plan_chip_w[j], case_chip_w[j]) for j in range(6)],
        }
        tg = inp["toggles"]
        row_labels = []
        for r in ratios:
            lab = r
            if r in ("SSO flights", "LEO flights") and tg.get("launch_on", 1) == 0: lab += " (limit off)"
            if r == "Solar" and tg.get("solar_on", 1) == 0: lab += " (limit off)"
            if r.startswith("AI chips") and tg.get("chips_on", 1) == 0: lab += " (limit off)"
            row_labels.append(lab)
        row_keys = list(ratios)
        z2, txt2, outline2 = [], [], []
        for r in row_keys:
            zr, tr, br = [], [], []
            for j in range(6):
                u = ratios[r][j]
                zr.append(None if u is None else min(u, 1.5))
                tr.append("n/a" if u is None else f"{u:.0%}")
                chip_out = r.startswith("AI chips") and u is not None and u >= 0.995 and sol["shortfall"][j] > 0.01
                br.append(chip_out)
            z2.append(zr); txt2.append(tr); outline2.append(br)
        fig2 = go.Figure(go.Heatmap(z=z2, x=[str(y) for y in YEARS], y=row_labels, text=txt2, texttemplate="%{text}", textfont=dict(size=14, color=WHITE),
                                    colorscale=[[0, "#111111"], [0.5, "#3A3A3A"], [0.66, "#5A5A5A"], [1, ACC]], zmin=0, zmax=1.5, showscale=False, xgap=3, ygap=3,
                                    hovertemplate="%{y}, %{x}: %{text}<extra></extra>"))
        for i in range(len(row_keys)):
            for j in range(6):
                if outline2[i][j]:
                    fig2.add_shape(type="rect", x0=j - 0.5, x1=j + 0.5, y0=i - 0.5, y1=i + 0.5, line=dict(color=WHITE, width=3))
        fig2.update_yaxes(autorange="reversed", showgrid=False)
        st.plotly_chart(style_fig(fig2, 300, legend=False), use_container_width=True)
        st.caption("Amount of current planned resource required to achieve optimal plan. White outline = limit holding compute back.")

        # Plain-English read-out from the ratios
        bits = []
        for r, lab in zip(row_keys, row_labels):
            vals = [(ratios[r][j], YEARS[j]) for j in range(6) if ratios[r][j] is not None]
            if not vals:
                continue
            mx, ymx = max(vals, key=lambda t: t[0])
            short = {"SSO flights": "SSO flights", "LEO flights": "LEO flights", "Solar": "solar",
                     "AI chips effective watts": "chips"}[r]
            if mx <= 1.005:
                bits.append(f"{short} stays at the case level")
            else:
                bits.append(f"up to {mx:.1f}x the case's {short} ({ymx})")
        cy = [YEARS[j] for j in range(6) if outline2[row_keys.index("AI chips effective watts")][j]]
        story = "Plan needs " + "; ".join(bits) + "."
        if cy:
            if len(cy) >= 2 and cy[-1] - cy[0] == len(cy) - 1:
                chip_span = f"{cy[0]}-{str(cy[-1])[2:]}"
            else:
                chip_span = ", ".join(str(y) for y in cy)
            story += f" Chips cap the plan in {chip_span}."
        st.markdown(f"<p class='answer'>{story}</p>", unsafe_allow_html=True)

        pick2 = st.segmented_control("Drill into a limit", row_labels, key="drill_plan")
        if pick2:
            rkey = row_keys[row_labels.index(pick2)]
            f = mf
            if rkey == "SSO flights":
                supply, uses = case_sso, plan_sso; unit = "flights"
            elif rkey == "LEO flights":
                supply, uses = case_leo, plan_leo; unit = "flights"
            elif rkey == "Solar":
                supply, uses = case_sol, plan_sol; unit = "GW"
            else:
                supply = [w / 1e9 for w in case_chip_w]  # watts -> GW
                uses = [w / 1e9 for w in plan_chip_w]
                unit = "effective GW"
            dd2 = pd.DataFrame({
                "Base supply": [supply[j] * f for j in range(6)],
                "Recommended plan uses": [uses[j] * f for j in range(6)],
                "To add (plan − case, floor 0)": [max(0, uses[j] - supply[j]) * f for j in range(6)],
            }, index=YEARS).T
            st.markdown(f"**{pick2}** ({unit}{' per month' if monthly else ' per year'})")
            st.dataframe(dd2.map(lambda v: fmt(v, 2 if unit.endswith("GW") else 1)), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 3. lever strength
    st.markdown("## 3. Annual bottlenecks")
    lev = R["lever"]; labels = ["SSO flights", "LEO flights", "Solar", "Chips"]; lc = [WHITE, ACC, G1, G3]
    fig = go.Figure()
    for i, l in enumerate(labels):
        vals = [lev[j][i] * 100 for j in range(6)]
        fig.add_bar(x=YEARS, y=vals, name=l, marker_color=lc[i], text=[f"{v:.0f}%" if v >= 4 else "" for v in vals], textposition="inside", insidetextfont=dict(color="#000000" if lc[i] in (WHITE, G1) else WHITE))
    fig.update_layout(barmode="stack", yaxis=dict(range=[0, 100], ticksuffix="%"))
    st.plotly_chart(style_fig(fig, 360), use_container_width=True)
    if inp["toggles"]["mix"] == "Optimized":
        st.caption("Share of the next unit of compute each limit would unlock (marginal view). A year at 0% everywhere has met its target.")
    else:
        st.caption("Fixed mix: compute is set by the tightest limit, so it gets 100% (split equally if tied); relieving any other limit adds nothing. A year at 0% everywhere has met its target.")

    # ----------------------------------------------------------------------------------------------- 4. satellites
    st.markdown("## 4. Satellites launched by class")
    cc1, cc2 = st.columns([5.5, 1])
    with cc2:
        measure = st.radio("Measure", ["Number of satellites", "Compute (GW)"], key="satm")
        cum4 = st.toggle("Cumulative", value=False, disabled=monthly, key="cum4") and not monthly
    with cc1:
        fig = go.Figure()
        for i in range(4):
            base = [R["sats"][j][i] if measure.startswith("Number") else R["comp_cls"][j][i] for j in range(6)]
            vals = [sum(base[:j + 1]) for j in range(6)] if cum4 else [b * mf for b in base]
            fig.add_bar(x=YEARS, y=vals, name=cls[i]["id"], marker_color=CLASS_COL[cls[i]["id"]],
                        text=[(f"{v:,.0f}" if measure.startswith("Number") else f"{v:,.1f}") if v > 0 else "" for v in vals], textposition="inside",
                        insidetextfont=dict(color="#000000" if CLASS_COL[cls[i]["id"]] in (WHITE, G1, ACC2) else WHITE))
        fig.update_layout(barmode="stack")
        st.plotly_chart(style_fig(fig, 360), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 5. closing the gap
    st.markdown("## 5. Constrained compute by resource")
    gp = R["gap_parts"]
    parts = [("Orbit and satellite mix", "mix", G2), ("Flights alone", "flights", WHITE), ("Solar alone", "solar", G1), ("Flights and solar together", "together", ACC), ("Chips", "chips", G3)]
    gc1, gc2 = st.columns([5.5, 1])
    with gc2:
        gap_mode = st.radio("Show", ["GW", "% of target"], key="gaprel")
    rel_gap = gap_mode.startswith("%")
    with gc1:
        fig = go.Figure()
        for lab, key_, col in parts:
            if rel_gap:
                vals = [max(0, gp[key_][j]) / T[j] * 100 if T[j] else 0 for j in range(6)]
                texts = [f"{v:.0f}%" if v > 3 else "" for v in vals]
            else:
                vals = [max(0, gp[key_][j]) * mf for j in range(6)]
                texts = [fmt(v, 1) if v > 0.05 * max(T) * mf else "" for v in vals]
            if sum(vals) > 1e-6:
                fig.add_bar(x=YEARS, y=vals, name=lab, marker_color=col, text=texts, textposition="inside",
                            insidetextfont=dict(color="#000000" if col in (WHITE, G1) else WHITE))
        if not rel_gap:
            fig.add_scatter(x=YEARS, y=[x * mf for x in T], name="Target", mode="markers",
                            marker=dict(symbol="line-ew", size=40, line=dict(width=3, color=G2)))
        fig.update_layout(barmode="stack", yaxis_title=("% of target" if rel_gap else unit_gw))
        fig = style_fig(fig, 400)
        if rel_gap:
            fig.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("Show the numbers"):
        if rel_gap:
            gdf = pd.DataFrame({lab: [max(0, gp[key_][j]) / T[j] * 100 if T[j] else 0 for j in range(6)] for lab, key_, _ in parts}, index=YEARS).T
            gdf.loc["Gap to target"] = [gp["gap"][j] / T[j] * 100 if T[j] else 0 for j in range(6)]
            st.dataframe(gdf.map(lambda v: f"{v:.1f}%"), use_container_width=True)
        else:
            gdf = pd.DataFrame({lab: [gp[key_][j] * mf for j in range(6)] for lab, key_, _ in parts}, index=YEARS).T
            gdf.loc["Gap to target"] = [gp["gap"][j] * mf for j in range(6)]
            if not monthly: gdf["2028-33"] = gdf.sum(axis=1)
            st.dataframe(gdf.map(lambda v: fmt(v, 2)), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 6. recommendation
    st.markdown("## 6. Recommended plan and scenario comparison")
    st.markdown("<span class='muted'>Optimization maximizes economic value by determining how much launch and solar capacity needs to be added given targets and orbital + satellite mix requirements.</span>", unsafe_allow_html=True)
    c = inp["costs"]

    def _worth_line(worth_B, gw_lost):
        base = f"Worth ${worth_B:,.0f}B NPV"
        if gw_lost > 0.05:
            return base + f"; without it the plan delivers {gw_lost:,.1f} GW less"
        return base + "; without it the target is still met, but at higher cost"

    def _flight_steps(cap):
        j0 = next(j for j in range(6) if cap[j] > 1e-6)
        steps = ", ".join(f"{cap[j]:,.0f} by {YEARS[j]}" for j in range(j0, 6) if j == j0 or cap[j] > cap[j - 1] + 1)
        return j0, steps

    def _chip_capped(j):
        """True if every chip type with supply > 0 is fully used in year j (or cumulatively with carry)."""
        if inp["toggles"]["chips_on"] != 1:
            return False
        carry = inp["toggles"]["chip_carry"] == 1
        checks = []
        for used_m, supply in ((sol["orion_used"], inp["orion"]), (sol["vega_used"], inp["vega"])):
            if carry:
                sup = sum(supply[: j + 1])
                if sup <= 0:
                    continue
                checks.append(sum(used_m[: j + 1]) * 1e6 >= 0.995 * sup)
            else:
                if supply[j] <= 0:
                    continue
                checks.append(used_m[j] * 1e6 >= 0.995 * supply[j])
        return bool(checks) and all(checks)

    def _short_phrase(pairs):
        parts = [f"{gw:.1f} GW in {y}" for y, gw in pairs]
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"

    # Pro-rate new-launch PV capex by orbit (new capacity × availability)
    aL = [1 if y >= c["launch_first"] else 0 for y in YEARS]
    sso_w = sum(sol["new_sso"][j] * aL[j] for j in range(6))
    leo_w = sum(sol["new_leo"][j] * aL[j] for j in range(6))
    launch_w = sso_w + leo_w
    sso_capex = sol["pv"]["new_launch"] * sso_w / launch_w if launch_w > 0 else 0.0
    leo_capex = sol["pv"]["new_launch"] * leo_w / launch_w if launch_w > 0 else 0.0

    action_cards = []  # (worth_B, title, worth_line, detail, pill)

    if "fab" in action_vals:
        fab = sol["cap_fab"]
        y0 = YEARS[next(j for j in range(6) if fab[j] > 1e-6)]
        av = action_vals["fab"]
        detail = (f"{fab[next(j for j in range(6) if fab[j] > 1e-6)]:,.1f} GW/yr usable in {y0}, "
                  f"growing to {fab[-1]:,.1f} GW/yr by {YEARS[-1]}; ${sol['pv']['new_fab']:,.0f}B capex (PV)")
        action_cards.append((av["worth_B"], "Commit a solar fab", _worth_line(av["worth_B"], av["gw_lost"]),
                             detail, f"Decide {y0 - c['fab_lead']}"))

    for orb, key, cap_key, new_key, orbit_capex in (
        ("LEO", "leo", "cap_leo", "new_leo", leo_capex),
        ("SSO", "sso", "cap_sso", "new_sso", sso_capex),
    ):
        if key not in action_vals:
            continue
        cap = sol[cap_key]
        j0, steps = _flight_steps(cap)
        av = action_vals[key]
        detail = f"Extra flights per year: {steps}"
        if orbit_capex > 0:
            detail += f"; ${orbit_capex:,.0f}B capex (PV)"
        action_cards.append((av["worth_B"], f"Add {orb} launch capacity", _worth_line(av["worth_B"], av["gw_lost"]),
                             detail, f"Start {YEARS[j0] - c['launch_lead']}"))

    mix_v = action_vals["mix"]
    if inp["toggles"]["mix"] == "Optimized":
        action_cards.append((mix_v["worth_B"], "Run the optimized class and orbit mix",
                             f"Worth ${mix_v['worth_B']:,.0f}B NPV and +{mix_v['gw']:.1f} GW at current resources, at no cost",
                             "", "Now"))
    else:
        action_cards.append((mix_v["worth_B"], "Class mix held at the seed mix",
                             f"Holding it costs ${mix_v['worth_B']:,.0f}B NPV and {mix_v['gw']:.1f} GW at current resources",
                             "", "Your choice"))

    action_cards.sort(key=lambda t: t[0], reverse=True)

    for i, (worth_B, title, worth_line, detail, pill) in enumerate(action_cards, 1):
        body = worth_line if not detail else f"{worth_line}<br>{detail}"
        st.markdown(f"<div class='rec'><span class='pill'>{i}</span><b>{title}</b><br>"
                    f"<span class='muted'>{body}</span></div>", unsafe_allow_html=True)

    # Remaining-gap card last (not ranked with actions)
    short = [(YEARS[j], sol["shortfall"][j], j) for j in range(6) if sol["shortfall"][j] > 0.01]
    if short:
        chip_yrs = [(y, g) for y, g, j in short if _chip_capped(j)]
        econ_yrs = [(y, g) for y, g, j in short if not _chip_capped(j)]
        parts = []
        if chip_yrs:
            parts.append(f"Short {_short_phrase(chip_yrs)}. Pull Vega forward or add early Orion volume.")
        if econ_yrs:
            contrib = inp["costs"]["contribution"]
            parts.append(f"Short {_short_phrase(econ_yrs)}: closing it would cost more than the compute is worth at ${contrib:g}/W/yr.")
        if chip_yrs and not econ_yrs:
            title = "Chips cap the plan"
        elif econ_yrs and not chip_yrs:
            title = "Remaining gap not worth closing at these economics"
        else:
            title = "Remaining gap"
        n = len(action_cards) + 1
        st.markdown(f"<div class='rec'><span class='pill'>{n}</span><b>{title}</b><br>"
                    f"<span class='muted'>{' '.join(parts)}</span></div>", unsafe_allow_html=True)

    st.caption("Ranked by value at stake: the NPV lost if that action is dropped and the optimizer re-plans without it. Illustrative economics.")

    comp_rows = {}
    for name, Rv in VAR.items():
        comp_rows[name] = {"2028-33 compute (GW)": sum(Rv["realized"]), "% of target": f"{sum(Rv['realized']) / cum_t:.0%}", "2033 compute (GW)": Rv["realized"][-1],
                           "Satellites": sum(sum(s) for s in Rv["sats"]), "Starship flights": sum(Rv["flights_sso"]) + sum(Rv["flights_leo"]),
                           "Solar used (GW)": sum(Rv["solar_used"]), "Orion chips (M)": sum(Rv["orion_used"]) / 1e6, "Vega chips (M)": sum(Rv["vega_used"]) / 1e6}
    cdf = pd.DataFrame(comp_rows).T
    cdf.loc["Unconstrained", "% of target"] = "100%"
    st.markdown("**Scenario comparison**")
    st.dataframe(cdf.map(fmt_cell), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 7. economics
    st.markdown("## 7. Economics of the selected case (illustrative)")
    st.markdown(f"<span class='muted'>Cost inputs and the ${inp['costs']['contribution']:g}/W/yr contribution are added assumptions; the case data has no costs. Present values in 2028 dollars at the discount rate. "
                "Pre-tax; capacity left after 2033 gets no value.</span>", unsafe_allow_html=True)
    econ = selected_case_economics(inp, R, sol)
    if not econ["meaningful"]:
        st.info("Economics not shown: with a limit switched off, that resource is treated as unlimited and free, so costs and NPV are not meaningful. Turn the limits back on to see the economics.")
    else:
        pv = econ["pv"]
        y = econ["yearly"]
        plan_npv = sol["pv"]["npv"]
        plan_adds = plan_npv - pv["npv"]
        e = st.columns(4)
        e[0].metric("Value of compute (PV)", f"${pv['value']:,.0f}B", delta_color="off", delta_arrow="off")
        e[1].metric("Total cost (PV)", f"${pv['total']:,.0f}B", delta_color="off", delta_arrow="off")
        e[2].metric("Indicative NPV", f"${pv['npv']:,.0f}B",
                    f"${pv['npv_ex_base']:,.0f}B if base capacity is sunk", delta_color="off", delta_arrow="off")
        if abs(plan_adds) < 5:
            e[3].metric("NPV the recommended plan adds", "≈ $0B",
                        "Selected case is the recommended plan", delta_color="off", delta_arrow="off")
        else:
            e[3].metric("NPV the recommended plan adds", f"${plan_adds:,.0f}B",
                        f"Plan NPV ${plan_npv:,.0f}B", delta_color="off", delta_arrow="off")
        with st.expander("Show the numbers"):
            rows = [
                ("Capex: new capacity added by the Solver (only when the additions are applied)", "new_capex"),
                ("Capex: base capacity not yet built (launch, solar fab, Terafab)", "base_capex"),
                ("Variable: flight operations", "ops"),
                ("Variable: solar cells (production cost)", "cells"),
                ("Variable: chips (Orion production cost; Vega purchase price)", "chips"),
                ("Variable: satellite hardware (excluding chips and solar cells)", "hardware"),
                ("Total cost", "total"),
                ("Value of compute delivered (lifetime contribution)", "value"),
                ("Indicative NPV, including base capacity capex", "npv"),
                ("Indicative NPV, excluding base capacity capex", "npv_ex_base"),
            ]
            edf = pd.DataFrame({lab: [y[k_][j] * mf for j in range(6)] for lab, k_ in rows}, index=YEARS).T
            edf["PV (2028 $)"] = [pv[k_] for _, k_ in rows]
            st.dataframe(edf.map(lambda v: fmt(v, 1)), use_container_width=True)
            st.download_button("Download CSV", edf.to_csv().encode(), "economics.csv", key="dl7")

    # ----------------------------------------------------------------------------------------------- 8. detail
    st.markdown("## 8. Detailed plan")
    with st.expander("Selected scenario by year", expanded=False):
        dr = {}
        dr["Compute launched (GW)"] = [x * mf for x in real]
        for i in range(4): dr[f"{cls[i]['id']} satellites"] = [R["sats"][j][i] * mf for j in range(6)]
        dr["SSO flights"] = [x * mf for x in R["flights_sso"]]; dr["LEO flights"] = [x * mf for x in R["flights_leo"]]
        dr["Solar used (GW)"] = [x * mf for x in R["solar_used"]]; dr["Orion chips used (M)"] = [x / 1e6 * mf for x in R["orion_used"]]
        dr["Vega chips used (M)"] = [x / 1e6 * mf for x in R["vega_used"]]; dr["AI-related boards (k)"] = [x / 1e3 * mf for x in R["boards_ai"]]
        dr["Mass to orbit (k tons)"] = [(R["mass_sso"][j] + R["mass_leo"][j]) / 1e3 * mf for j in range(6)]
        dr["Compute in orbit, end of year (GW)"] = R["fleet_compute"]
        ddf = pd.DataFrame(dr, index=YEARS).T
        if not monthly:
            ddf["2028-2033"] = ddf.sum(axis=1)
            ddf.loc["Compute in orbit, end of year (GW)", "2028-2033"] = R["fleet_compute"][-1]
        st.dataframe(ddf.map(lambda v: fmt(v, 2)), use_container_width=True)
        st.download_button("Download CSV", ddf.to_csv().encode(), "plan.csv", key="dl8")
