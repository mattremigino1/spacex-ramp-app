"""AI Satellite Launch Ramp: live planning tool (Streamlit).

Run locally:  streamlit run app.py
"""
import copy, json, math
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
.hovtip { position: relative; cursor: help; display: inline-block; border-bottom: 1px dotted #595959; }
.hovtip .tiptext { visibility: hidden; opacity: 0; transition: opacity 0.15s; position: absolute; z-index: 1000; left: 0; top: 100%; margin-top: 6px; background: #1A1A1A; color: #FFFFFF; border: 1px solid #4A90E2; border-radius: 6px; padding: 8px 12px; font-size: 0.85rem; font-weight: 400; line-height: 1.5; white-space: nowrap; text-transform: none; letter-spacing: normal; }
.hovtip:hover .tiptext { visibility: visible; opacity: 1; }
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
  min-width: 14rem !important; /* fits the longest preset label */
}
/* "+ Add scenario" overlays the right end of the tab bar */
div.st-key-plus_row { padding-top: 1.35rem; margin-bottom: -4.45rem; position: relative; z-index: 5; pointer-events: none; }
div.st-key-plus_row button, div.st-key-plus_row .uitag { pointer-events: auto; }
div.st-key-plus_row [data-testid="stColumn"]:last-child { display: flex; justify-content: flex-end; }
div.st-key-plus_row button { padding: 0.15rem 0.7rem; min-height: 0; font-size: 0.85rem; }
.uitag { display:inline-block; background:#FFD400; color:#000; font:700 11px/1.4 Menlo, monospace; padding:0 6px; border-radius:4px; margin:2px 0; letter-spacing:0; text-transform:none; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------------------------- label overlay (for review only)
# Add ?labels=1 to the app's address to tag every element (e.g. "3-chart") so edits can point at it. Off by default.
try:
    LABELS = str(st.query_params.get("labels", "")).strip() == "1"
except Exception:
    LABELS = False


def tag_html(t):
    return f"<span class='uitag'>{t}</span> " if LABELS else ""


def tag(t):
    if LABELS:
        st.markdown(tag_html(t), unsafe_allow_html=True)


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
# Scenarios hold the case data (Data tabs); the sidebar settings are shared across scenarios.
DEFAULTS = load_defaults()
YEARS = DEFAULTS["years"]
BASE = "Base case"
if "scen" not in st.session_state:
    st.session_state.scen = [{"id": 0, "name": BASE, "data": copy.deepcopy(DEFAULTS)}]
    st.session_state.next_id = 1
    st.session_state.tg = copy.deepcopy(DEFAULTS["toggles"])
    st.session_state.v4 = DEFAULTS["vehicles"][1]["year"]
    st.session_state.preset = BASE
    st.session_state.ver = 0


def scen_names():
    return [sc["name"] for sc in st.session_state.scen]


def get_scen(name):
    return next((sc for sc in st.session_state.scen if sc["name"] == name), st.session_state.scen[0])


def set_preset():
    st.session_state.preset = st.session_state.preset_box


def reset():
    """Sidebar settings and Base case data back to the case; added scenarios are kept."""
    st.session_state.tg = copy.deepcopy(DEFAULTS["toggles"])
    st.session_state.v4 = DEFAULTS["vehicles"][1]["year"]
    st.session_state.scen[0]["data"] = copy.deepcopy(DEFAULTS)
    st.session_state.preset = BASE
    st.session_state.ver += 1


def scen_file():
    """Everything needed to restore the scenarios and settings later."""
    return json.dumps({"app": "spacex-ramp-app", "version": 1, "scenarios": [{"name": sc["name"], "data": sc["data"]} for sc in st.session_state.scen],
                       "toggles": st.session_state.tg, "v4": st.session_state.v4, "selected": st.session_state.preset}, indent=1)


def load_scen_file():
    f = st.session_state.get("scen_upload")
    if f is None:
        return
    try:
        blob = json.loads(f.getvalue().decode("utf-8"))
        scs = blob["scenarios"]
        assert scs and all("name" in x and "data" in x for x in scs)
        used, names_ = {BASE, "Ramp"}, [BASE]          # keep names unique: the tabs and dropdown select by name
        for x in scs[1:]:
            nm, i = str(x["name"]).strip() or "Scenario", 2
            cand = nm
            while cand in used:
                cand = f"{nm} ({i})"; i += 1
            used.add(cand); names_.append(cand)
        st.session_state.scen = [{"id": n, "name": names_[n], "data": x["data"]} for n, x in enumerate(scs)]
        st.session_state.next_id = len(scs)
        st.session_state.tg = {**DEFAULTS["toggles"], **blob.get("toggles", {})}
        st.session_state.v4 = int(blob.get("v4", DEFAULTS["vehicles"][1]["year"]))
        st.session_state.preset = blob.get("selected", BASE) if blob.get("selected") in scen_names() else BASE
        st.session_state.ver += 1
        st.session_state.load_msg = f"Loaded {len(scs)} scenario(s)."
    except Exception as ex:
        st.session_state.load_msg = f"Could not read that file: {ex}"


@st.dialog("Add a scenario")
def add_scenario_dialog():
    name = st.text_input("Scenario name", placeholder="e.g. V4 slips to 2032")
    src = st.selectbox("Start from a copy of", scen_names())
    if st.button("Create", type="primary"):
        nm = (name or "").strip()
        if not nm:
            st.error("Type a name for the scenario.")
        elif nm in scen_names() or nm == "Ramp":
            st.error("That name is already used.")
        else:
            st.session_state.scen.append({"id": st.session_state.next_id, "name": nm, "data": copy.deepcopy(get_scen(src)["data"])})
            st.session_state.next_id += 1
            st.session_state.open_tab = nm
            st.rerun()


V = st.session_state.ver
k = lambda name: f"{name}_{V}"
t = st.session_state.tg

# ----------------------------------------------------------------------------------------------- sidebar: inputs
with st.sidebar:
    st.markdown("### Scenario")
    names = scen_names()
    if st.session_state.preset not in names:
        st.session_state.preset = BASE
    tag("S-preset")
    st.selectbox("Scenario", names, index=names.index(st.session_state.preset), key=f"preset_box_{len(names)}_{V}", on_change=None, label_visibility="collapsed")
    st.session_state.preset = st.session_state[f"preset_box_{len(names)}_{V}"]
    tag("S-reset")
    st.button("Reset to case data", on_click=reset, use_container_width=True,
              help="Resets the sidebar settings and the Base case data to the case. Added scenarios are kept.")
    tag("S-optimizer")
    t["apply_solver"] = int(st.toggle("Run optimizer", value=t.get("apply_solver", 0) == 1, key=k("apply"),
                                      help="Adds optimal levels of launch and solar capacity to unlock compute and maximize economic value"))
    monthly = False   # monthly view removed from the UI (an even split of each year is not a real monthly ramp)

    st.markdown("### Constraints")
    tag("S-flight-limit")
    t["launch_on"] = int(st.toggle("Starship flight limit", value=t["launch_on"] == 1, key=k("lon")))
    tag("S-solar-limit")
    t["solar_on"] = int(st.toggle("Solar limit", value=t["solar_on"] == 1, key=k("son")))
    tag("S-chip-limit")
    t["chips_on"] = int(st.toggle("AI chip limit", value=t["chips_on"] == 1, key=k("con")))
    tag("S-mix")
    _mix = st.radio("Class and orbit mix", ["Flexible/optimized", "Fixed"], index=0 if t["mix"] == "Optimized" else 1, horizontal=True, key=k("mix"),
                    help="Flexible/optimized lets the model and the optimizer pick the class split that maximizes compute or minimizes cost. Fixed holds each year's split at the scenario's seed mix table, for both the selected case and the optimizer's plan.")
    t["mix"] = "Optimized" if _mix == "Flexible/optimized" else "Custom"

    st.markdown("### Operations")
    tag("S-eol")
    t["eol_sizing"] = int(st.toggle("Size solar for end of life", value=t["eol_sizing"] == 1, key=k("eol")))
    tag("S-chip-carry")
    t["chip_carry"] = int(st.toggle("Carry unused chips forward", value=t["chip_carry"] == 1, key=k("cc")))
    tag("S-solar-carry")
    t["solar_carry"] = int(st.toggle("Carry unused solar forward", value=t["solar_carry"] == 1, key=k("sc")))
    tag("S-heliosb")
    t["heliosb_year"] = int(st.selectbox("First year Helios-B can launch", list(range(2028, 2035)), index=list(range(2028, 2035)).index(t["heliosb_year"]), key=k("hb")))
    tag("S-v4")
    st.session_state.v4 = int(st.selectbox("First year of Starship V4", list(range(2028, 2035)), index=list(range(2028, 2035)).index(st.session_state.v4), key=k("v4")))
    tag("S-aux")
    t["aux_share"] = st.slider("Auxiliary load that scales with compute", 0.0, 1.0, float(t["aux_share"]), 0.05, key=k("aux"))


# ----------------------------------------------------------------------------------------------- tabs: plan + one data tab per scenario
if st.session_state.get("open_tab"):
    st.session_state["main_tabs"] = st.session_state.pop("open_tab")
with st.container(key="plus_row"):          # sits on the right end of the tab bar (see CSS)
    _pc = st.columns([10, 2])
    with _pc[1]:
        tag("T-plus")
        if st.button("＋ Add scenario", key="add_scen", help="Add a scenario: copies an existing scenario's data into a new tab you can edit"):
            add_scenario_dialog()
all_tabs = st.tabs(["Ramp"] + scen_names(), key="main_tabs", on_change="rerun")
tab_plan, scen_tabs = all_tabs[0], all_tabs[1:]


def _n(v, old, cast=float):
    """A table cell as a number; a cleared (blank) cell keeps its previous value."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return old
    return old if math.isnan(x) else cast(x)


def year_table(rows, key):
    df = pd.DataFrame({r: vals for r, vals in rows.items()}, index=[str(y) for y in YEARS]).T
    cols = {str(y): st.column_config.NumberColumn(str(y), format="localized") for y in YEARS}
    out = st.data_editor(df, key=k(key), use_container_width=True, column_config=cols)
    return {r: [_n(out.loc[r, str(y)], rows[r][j]) for j, y in enumerate(YEARS)] for r in rows}


def data_tab(sc):
    """Editable case data for one scenario; edits write straight into that scenario."""
    d, p_ = sc["data"], f"s{sc['id']}_"
    if sc["id"] != 0:
        mc = st.columns([3, 1, 4])
        new_nm = mc[0].text_input("Scenario name", value=sc["name"], key=k(p_ + "name"))
        if new_nm.strip() and new_nm.strip() != sc["name"] and new_nm.strip() not in scen_names() and new_nm.strip() != "Ramp":
            if st.session_state.preset == sc["name"]:
                st.session_state.preset = new_nm.strip()
            sc["name"] = new_nm.strip()
            st.session_state.open_tab = sc["name"]
            st.rerun()
        mc[1].markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if mc[1].button("Delete scenario", key=k(p_ + "del")):
            st.session_state.scen = [x for x in st.session_state.scen if x["id"] != sc["id"]]
            if st.session_state.preset == sc["name"]:
                st.session_state.preset = BASE
            st.session_state.ver += 1
            st.rerun()
    st.caption("Case inputs and added cost assumptions for this scenario. Pick it in the sidebar's scenario dropdown to see it on the Ramp tab.")
    tag("D1-case-inputs")
    with st.expander("Target, flights, solar, chips", expanded=True):
        e = year_table({"Compute target (GW)": d["target"], "SSO flights": d["flights_sso"], "LEO flights": d["flights_leo"],
                        "Solar (GW/yr)": d["solar"], "Orion chips": d["orion"], "Vega chips": d["vega"]}, p_ + "case")
        d["target"], d["flights_sso"], d["flights_leo"] = e["Compute target (GW)"], e["SSO flights"], e["LEO flights"]
        d["solar"], d["orion"], d["vega"] = e["Solar (GW/yr)"], e["Orion chips"], e["Vega chips"]
    tag("D2-seed-mix")
    with st.expander("Seed (custom) mix, share of compute", expanded=True):
        e = year_table(d["custom_mix"], p_ + "mix_tbl")
        d["custom_mix"] = e
        bad = [y for j, y in enumerate(YEARS) if abs(sum(e[c][j] for c in e) - 1) > 1e-6]
        if bad: st.warning("Mix does not sum to 100% in " + ", ".join(map(str, bad)))
    tag("D3-classes")
    with st.expander("Satellite classes", expanded=True):
        cdf = pd.DataFrame(d["classes"]).set_index("id")[["orbit", "gen", "kw", "kw_per_t", "solar_mult", "life"]]
        cdf.columns = ["Orbit", "Generation", "Compute (kW)", "kW per ton", "Solar multiplier", "Life (yrs)"]
        num = lambda lab: st.column_config.NumberColumn(lab, format="localized")
        ce = st.data_editor(cdf, key=k(p_ + "cls"), disabled=["Orbit", "Generation"], use_container_width=True,
                            column_config={lab: num(lab) for lab in ("Compute (kW)", "kW per ton", "Solar multiplier", "Life (yrs)")})
        for c_ in d["classes"]:
            c_["kw"], c_["kw_per_t"], c_["solar_mult"], c_["life"] = (_n(ce.loc[c_["id"], "Compute (kW)"], c_["kw"]), _n(ce.loc[c_["id"], "kW per ton"], c_["kw_per_t"]),
                                                                      _n(ce.loc[c_["id"], "Solar multiplier"], c_["solar_mult"]), _n(ce.loc[c_["id"], "Life (yrs)"], c_["life"], int))
    tag("D4-starship-chips")
    with st.expander("Starship, chips, degradation", expanded=True):
        vdf = pd.DataFrame(d["vehicles"]).set_index("name")[["leo", "sso"]]; vdf.columns = ["Payload to LEO (t)", "Payload to SSO (t)"]
        ve = st.data_editor(vdf, key=k(p_ + "veh"), use_container_width=True,
                            column_config={lab: st.column_config.NumberColumn(lab, format="localized")
                                           for lab in ("Payload to LEO (t)", "Payload to SSO (t)")})
        for v in d["vehicles"]:
            v["leo"], v["sso"] = _n(ve.loc[v["name"], "Payload to LEO (t)"], v["leo"]), _n(ve.loc[v["name"], "Payload to SSO (t)"], v["sso"])
        chdf = pd.DataFrame(d["chips"]).set_index("name")[["tdp", "util", "first_year"]]; chdf.columns = ["TDP (W)", "Utilization", "First year"]
        che = st.data_editor(chdf, key=k(p_ + "chips"), use_container_width=True,
                             column_config={lab: st.column_config.NumberColumn(lab, format="localized")
                                            for lab in ("TDP (W)", "Utilization", "First year")})
        for c_ in d["chips"]:
            c_["tdp"], c_["util"], c_["first_year"] = (_n(che.loc[c_["name"], "TDP (W)"], c_["tdp"]), _n(che.loc[c_["name"], "Utilization"], c_["util"]),
                                                       _n(che.loc[c_["name"], "First year"], c_["first_year"], int))
        d["solar_deg"] = st.number_input("Solar degradation per year", 0.0, 0.5, float(d["solar_deg"]), 0.005, format="%.3f", key=k(p_ + "sd"))
        d["compute_deg"] = st.number_input("Compute degradation per year", 0.0, 0.5, float(d["compute_deg"]), 0.005, format="%.3f", key=k(p_ + "cd"))
    tag("D5-boards")
    with st.expander("Circuit boards per satellite"):
        bdf = pd.DataFrame(d["boards"]).set_index("name"); bdf.columns = ["Helios-A", "Helios-B", "AI-related"]
        be = st.data_editor(bdf, key=k(p_ + "boards"), use_container_width=True,
                            column_config={"Helios-A": st.column_config.NumberColumn("Helios-A", format="localized"),
                                           "Helios-B": st.column_config.NumberColumn("Helios-B", format="localized")})
        for b in d["boards"]:
            b["a"], b["b"], b["ai"] = _n(be.loc[b["name"], "Helios-A"], b["a"]), _n(be.loc[b["name"], "Helios-B"], b["b"]), bool(be.loc[b["name"], "AI-related"])
    tag("D6-costs")
    with st.expander("Costs and value"):
        c_ = d["costs"]
        fields = [("launch_capex", "New launch capacity, $M per extra flight/yr", 1.0), ("ops", "Operating cost per flight, $M", 1.0),
                  ("fab_capex", "Solar fab capex, $M per GW/yr", 10.0), ("cells", "Solar cell production cost, $M per GW", 10.0),
                  ("orion", "Orion chip production cost, $M per chip", 0.0005), ("vega", "Vega chip price, $M per chip", 0.005),
                  ("hardware", "Satellite hardware ex chips and cells, $M per ton", 0.05), ("terafab_capex", "Terafab capex, $M per million chips/yr", 250.0),
                  ("wacc", "Discount rate", 0.005), ("contribution", "Contribution, $ per W per year", 0.5)]
        for key_, lab, step in fields:
            c_[key_] = st.number_input(lab, value=float(c_[key_]), step=step, format="%.4f" if c_[key_] < 1 else "%.2f", key=k(p_ + "c_" + key_))
        for key_, lab in (("launch_first", "First year new launch capacity usable"), ("fab_first", "First year new fab capacity usable"),
                          ("launch_lead", "Launch capacity lead time (yrs)"), ("fab_lead", "Fab lead time (yrs)"), ("terafab_lead", "Terafab lead time (yrs)")):
            c_[key_] = int(st.number_input(lab, value=int(c_[key_]), step=1, key=k(p_ + "c_" + key_)))


for tab_, sc in zip(scen_tabs, list(st.session_state.scen)):
    with tab_:
        data_tab(sc)


def build_inp(sc):
    """A scenario's data with the shared sidebar settings applied."""
    x = copy.deepcopy(sc["data"])
    x["toggles"] = copy.deepcopy(st.session_state.tg)
    x["vehicles"][1]["year"] = st.session_state.v4
    return x


inp = build_inp(get_scen(st.session_state.preset))

# Save / load goes last in the sidebar so the file includes this run's data edits
with st.sidebar:
    st.markdown("### Save / load scenarios")
    tag("S-save-load")
    st.download_button("Download scenarios", scen_file().encode(), "spacex-ramp-scenarios.json", "application/json", use_container_width=True,
                       help="Saves every scenario and the sidebar settings to a file you can load back later.")
    st.file_uploader("Load scenarios", type=["json"], key="scen_upload", on_change=load_scen_file, label_visibility="collapsed")
    if st.session_state.get("load_msg"):
        st.caption(st.session_state.pop("load_msg"))


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
    # Unconstrained = the Excel "Satellite ramp (unconstrained)" tab: the target built at the selected case's mix
    U_ = R["unconstrained"]
    variants["Unconstrained"] = {"realized": [sum(c_) for c_ in U_["comp_cls"]], "sats": U_["sats_cls"],
                                 "flights_sso": U_["flights_sso"], "flights_leo": U_["flights_leo"],
                                 "solar_used": U_["solar"], "orion_used": U_["orion"], "vega_used": U_["vega"]}
    for name, mod in (("Base case (constrained)", dict(apply_solver=0)),
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
    # What each orbit's flights alone could unlock: rerun with that orbit's flights effectively unlimited
    # (same as typing a very large number into that orbit's flights row in the Excel case data).
    base_gw = sum(R["realized"])
    for key, fkey in (("leo", "flights_leo"), ("sso", "flights_sso"), ("fab", "solar")):
        v_al = copy.deepcopy(inp); v_al[fkey] = [1e7] * len(inp[fkey])
        action_vals.setdefault("alone", {})[key] = max(0.0, sum(run(v_al, sol)["realized"]) - base_gw)
    # What lifting each limit unlocks: full re-runs at the current settings, exactly as if the sidebar toggle were
    # switched off (flights off, solar off, both off). Chips = what is left once flights and solar are unlimited.
    def _lifted(**tg):
        v = copy.deepcopy(inp); v["toggles"].update(tg)
        return run(v, solve(v))["realized"]
    T_ = inp["target"]; b_ = R["realized"]
    lo_, so_, bo_ = _lifted(launch_on=0), _lifted(solar_on=0), _lifted(launch_on=0, solar_on=0)
    fx_ = copy.deepcopy(inp); fx_["toggles"]["mix"] = "Optimized"
    flex_ = R["realized"] if str(inp["toggles"]["mix"]).strip() == "Optimized" else run(fx_, sol_opt)["realized"]
    action_vals["lift"] = {
        "flights": [lo_[j] - b_[j] for j in range(len(T_))],
        "solar": [so_[j] - b_[j] for j in range(len(T_))],
        "together": [bo_[j] - lo_[j] - so_[j] + b_[j] for j in range(len(T_))],
        "chips": [T_[j] - bo_[j] for j in range(len(T_))],
        "gap": [T_[j] - b_[j] for j in range(len(T_))],
        "mix": [flex_[j] - b_[j] for j in range(len(T_))],      # flexible vs. selected mix; overlaps the pieces, not additive
    }
    return sol, R, variants, sol_opt, sol_cust, opt_mix_R, action_vals


@st.cache_data(show_spinner=False)
def scenario_row(inp_json):
    """Another scenario with the current sidebar settings (for the scenario comparison table)."""
    x = json.loads(inp_json)
    return run(x, solve(x))


def input_problems(x):
    """Inputs the model cannot divide by, named in plain English for the data tab."""
    p = [f"{c['id']}: {lab} must be above zero" for c in x["classes"] for key, lab in (("kw", "compute (kW)"), ("kw_per_t", "kW per ton")) if not c[key] > 0]
    p += [f"{c['name']}: TDP and utilization must be above zero" for c in x["chips"] if not c["tdp"] * c["util"] > 0]
    if not sum(x["target"]) > 0:
        p.append("the compute target must be above zero in at least one year")
    return p


_probs = input_problems(inp)
if _probs:
    st.error(f"The model can't run with the **{st.session_state.preset}** data: " + "; ".join(_probs) + ". Fix it in that scenario's data tab.")
    st.stop()
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
    """Headline name: always the scenario selected in the dropdown."""
    return st.session_state.preset

with tab_plan:
    # ----------------------------------------------------------------------------------------------- header + answer
    tag("H-title")
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


    tag("H-answer")
    st.markdown(f"<div class='answer'><b>{case_name()}:</b> delivers <b>{cum_r:,.1f} GW</b> of the {cum_t:,.1f} GW 2028-33 target "
                f"(<b>{cum_r / cum_t:.0%}</b>).<br>What binds: {binds_story()}.<br>"
                f"<span class='muted'>The recommended plan (most economic added launch capacity and solar fab) reaches {sum(sol['compute']):,.1f} GW "
                f"({sum(sol['compute']) / cum_t:.0%}); see the recommendation section.</span></div>", unsafe_allow_html=True)

    tag("H-tiles")
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
    st.markdown("## Compute launched vs. target")
    c1, c2 = st.columns([5.5, 1])
    with c2:
        tag("1-controls")
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
            gc_ = gcol.get(gname, CLASS_COL.get(gname, WHITE))
            fig.add_bar(x=YEARS, y=vals, name=gname, marker_color=gc_,
                        text=(None if split == "Total" else [fmt(v, 2 if monthly else 1) for v in vals]), textposition="inside", insidetextanchor="end",
                        insidetextfont=dict(color="#000000" if gc_ in (WHITE, G1, ACC2) else WHITE))
        tot1 = acc([sum(R["comp_cls"][j][i] for i in range(4)) * mf for j in range(6)])
        tv = acc([x * mf for x in T])
        fig.add_scatter(x=YEARS, y=tv, name="Target", mode="lines+markers+text", line=dict(color=G2, dash="dash", width=2), text=[fmt(v, 2 if monthly else 1) for v in tv], textposition="top center", textfont=dict(color=G1))
        # Bar totals as annotations; if one would sit on the target label, lift the bar total above it.
        H1, MT, MB = 400, 20, 90                       # figure height and top/bottom margins (see style_fig)
        ymax1 = max(tot1 + tv + [1e-9]) * 1.15
        ppu = (H1 - MT - MB) / ymax1                    # pixels per y-unit
        for j, y_ in enumerate(YEARS):
            bar_px, tgt_px = tot1[j] * ppu, tv[j] * ppu
            shift = 4                                   # default gap above the bar
            if abs((bar_px + 4) - (tgt_px + 6)) < 17:   # labels would overlap (each ~16 px tall)
                shift = tgt_px + 24 - bar_px            # place the bar total just above the target label
            fig.add_annotation(x=y_, y=tot1[j], text=fmt(tot1[j], 2 if monthly else 1), showarrow=False, yanchor="bottom", yshift=shift,
                               font=dict(color=WHITE, size=13))
        fig.update_layout(barmode="stack", yaxis_title=("Cumulative GW" if cum else unit_gw))
        fig = style_fig(fig, H1)
        fig.update_yaxes(range=[0, ymax1])
        tag("1-chart")
        st.plotly_chart(fig, use_container_width=True)
    tag("1-table")
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
    st.markdown("## Constraint utilization")
    tag("2-tabs")
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
        tag("2a-heatmap")
        st.plotly_chart(style_fig(fig, 300, legend=False), use_container_width=True)
        st.caption("Selected case: share of each resource used. White outline = the limit holding compute back that year.")
        tag("2a-table")
        with st.expander("Show the numbers"):
            st.dataframe(pd.DataFrame(txt, index=rowsn, columns=YEARS), use_container_width=True)
        tag("2a-drill")
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
            "Orion chips": [_ratio(sol["orion_used"][j] * 1e6, inp["orion"][j]) for j in range(6)],
            "Vega chips": [_ratio(sol["vega_used"][j] * 1e6, inp["vega"][j]) for j in range(6)],
        }
        tg = inp["toggles"]
        row_labels = []
        for r in ratios:
            lab = r
            if r in ("SSO flights", "LEO flights") and tg.get("launch_on", 1) == 0: lab += " (limit off)"
            if r == "Solar" and tg.get("solar_on", 1) == 0: lab += " (limit off)"
            if r.endswith("chips") and tg.get("chips_on", 1) == 0: lab += " (limit off)"
            row_labels.append(lab)
        row_keys = list(ratios)
        z2, txt2, outline2 = [], [], []
        for r in row_keys:
            zr, tr, br = [], [], []
            for j in range(6):
                u = ratios[r][j]
                zr.append(None if u is None else min(u, 1.5))
                tr.append("n/a" if u is None else f"{u:.0%}")
                chip_out = r.endswith("chips") and u is not None and u >= 0.995 and sol["shortfall"][j] > 0.01
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
        tag("2b-heatmap")
        st.plotly_chart(style_fig(fig2, 300, legend=False), use_container_width=True)
        st.caption("Amount of current planned resources required to achieve optimizer plan. White outline = limit holding compute back.")
        tag("2b-table")
        with st.expander("Show the numbers"):
            st.dataframe(pd.DataFrame(txt2, index=row_labels, columns=YEARS), use_container_width=True)

        # Plain-English read-out from the ratios
        bits = []
        for r, lab in zip(row_keys, row_labels):
            vals = [(ratios[r][j], YEARS[j]) for j in range(6) if ratios[r][j] is not None]
            if not vals:
                continue
            mx, ymx = max(vals, key=lambda t: t[0])
            short = {"SSO flights": "SSO flights", "LEO flights": "LEO flights", "Solar": "solar",
                     "Orion chips": "Orion chips", "Vega chips": "Vega chips"}[r]
            if mx <= 1.005:
                bits.append(f"{short} stays at the case level")
            else:
                bits.append(f"up to {mx:.1f}x the case's {short} ({ymx})")
        # chips cap the plan in a year when every chip type with supply that year is outlined (fully used while short)
        cy = [YEARS[j] for j in range(6)
              if any(outline2[row_keys.index(ck)][j] for ck in ("Orion chips", "Vega chips"))
              and all(outline2[row_keys.index(ck)][j] or ratios[ck][j] is None for ck in ("Orion chips", "Vega chips"))]
        story = "Plan needs " + "; ".join(bits) + "."
        if cy:
            if len(cy) >= 2 and cy[-1] - cy[0] == len(cy) - 1:
                chip_span = f"{cy[0]}-{str(cy[-1])[2:]}"
            else:
                chip_span = ", ".join(str(y) for y in cy)
            story += f" Chips cap the plan in {chip_span}."
        tag("2b-readout")
        st.markdown(f"<p class='answer'>{story}</p>", unsafe_allow_html=True)

        tag("2b-drill")
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
            elif rkey == "Orion chips":
                supply = [x / 1e6 for x in inp["orion"]]; uses = sol["orion_used"]; unit = "M chips"
            else:
                supply = [x / 1e6 for x in inp["vega"]]; uses = sol["vega_used"]; unit = "M chips"
            dd2 = pd.DataFrame({
                "Base supply": [supply[j] * f for j in range(6)],
                "Recommended plan uses": [uses[j] * f for j in range(6)],
                "To add (plan − case, floor 0)": [max(0, uses[j] - supply[j]) * f for j in range(6)],
            }, index=YEARS).T
            st.markdown(f"**{pick2}** ({unit}{' per month' if monthly else ' per year'})")
            st.dataframe(dd2.map(lambda v: fmt(v, 1 if unit == "flights" else 2)), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 3. units needed
    st.markdown("## Annual resource gaps")
    OPT = VAR["Optimized (constrained)"]
    # (unit, available in the selected case [each year's new supply], used by the optimized plan, scale)
    res_opts = {
        "SSO flights": ("flights", lambda Rx: Rx["sso_avail"], lambda Rx: Rx["flights_sso"], 1),
        "LEO flights": ("flights", lambda Rx: Rx["leo_avail"], lambda Rx: Rx["flights_leo"], 1),
        "Solar GW": ("GW", lambda Rx: Rx["solar_new"], lambda Rx: Rx["solar_used"], 1),
        "Orion chips": ("M chips", lambda Rx: Rx["orion_new"], lambda Rx: Rx["orion_used"], 1e-6),
        "Vega chips": ("M chips", lambda Rx: Rx["vega_new"], lambda Rx: Rx["vega_used"], 1e-6),
    }
    uc1, uc2 = st.columns([5.5, 1])
    with uc2:
        tag("3-controls")
        res_pick = st.radio("Resource", list(res_opts), key="res_pick")
    unit_r, get_avail, get_used, scale = res_opts[res_pick]
    sel_v = [get_avail(R)[j] * scale * mf for j in range(6)]          # available in the selected case
    opt_v = [get_used(OPT)[j] * scale * mf for j in range(6)]          # needed (used) by the optimized plan
    gap_v = [max(0.0, o - s_) for o, s_ in zip(opt_v, sel_v)]
    tot_v = [s_ + g for s_, g in zip(sel_v, gap_v)]                    # bar height = max(available, needed)
    dp = 2 if unit_r != "flights" else 0
    with uc1:
        fig = go.Figure()
        fig.add_bar(x=YEARS, y=sel_v, name=f"{case_name()}: available", marker_color=G1,
                    text=[f"{v:,.{dp}f}" if v > 0 and g > 1e-9 else "" for v, g in zip(sel_v, gap_v)],   # no gap: the total above already says it
                    textposition="inside", insidetextfont=dict(color="#000000"))
        fig.add_bar(x=YEARS, y=gap_v, name="Gap to optimized plan", marker_color=ACC,
                    text=[f"{v:,.{dp}f}" if v > 0 else "" for v in gap_v], textposition="inside", insidetextfont=dict(color=WHITE))
        fig.add_scatter(x=YEARS, y=tot_v, mode="text", text=[f"{v:,.{dp}f}" for v in tot_v], textposition="top center",
                        textfont=dict(color=WHITE), showlegend=False, hoverinfo="skip")
        fig.update_layout(barmode="stack", yaxis_title=f"{unit_r} / {'month' if monthly else 'year'}")
        fig = style_fig(fig, 380)
        fig.update_yaxes(range=[0, max(tot_v + [1e-9]) * 1.15])
        tag("3-chart")
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Units of the chosen resource used each year by the selected case and by the optimized case.")
    tag("3-totals")
    if monthly:
        k_ = 72; lab_sfx = "avg / month, 2028-33"
    else:
        k_ = 1; lab_sfx = "2028-33"
    big = lambda v: f"{v:,.{dp}f}"
    sp, nd, gp_ = sum(sel_v) * (12 if monthly else 1) / k_, sum(opt_v) * (12 if monthly else 1) / k_, sum(gap_v) * (12 if monthly else 1) / k_
    bc = st.columns(3)
    for col, lab, val, color in ((bc[0], f"Available, {lab_sfx}", sp, WHITE), (bc[1], f"Needed for optimized plan, {lab_sfx}", nd, WHITE),
                                 (bc[2], f"Gap, {lab_sfx}", gp_, ACC)):
        col.markdown(f"<div style='text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;line-height:1.35;min-height:2.7em;color:#BFBFBF'>{lab}</div>"
                     f"<div style='font-size:2.0rem;font-weight:600;color:{color}'>{big(val)} <span style='font-size:1rem;color:#8C8C8C'>{unit_r}</span></div>",
                     unsafe_allow_html=True)
    tag("3-table")
    with st.expander("Show the numbers"):
        udf = pd.DataFrame({f"{case_name()}: available": sel_v, "Needed for optimized plan": opt_v, "Gap to optimized plan": gap_v}, index=YEARS).T
        if not monthly:
            udf["2028-33"] = udf.sum(axis=1)
        st.markdown(f"**{res_pick}** ({unit_r}{' per month' if monthly else ' per year'})")
        st.dataframe(udf.map(lambda v: f"{v:,.{dp}f}"), use_container_width=True)
        st.download_button("Download CSV", udf.to_csv().encode(), "resources.csv", key="dl3")

    # ----------------------------------------------------------------------------------------------- 4. lever strength
    st.markdown("## Annual bottlenecks")
    lev = R["lever"]; labels = ["SSO flights", "LEO flights", "Solar", "Chips"]; lc = [WHITE, ACC, G1, G3]
    fig = go.Figure()
    for i, l in enumerate(labels):
        vals = [lev[j][i] * 100 for j in range(6)]
        fig.add_bar(x=YEARS, y=vals, name=l, marker_color=lc[i], text=[f"{v:.0f}%" if v >= 4 else "" for v in vals], textposition="inside", insidetextfont=dict(color="#000000" if lc[i] in (WHITE, G1) else WHITE))
    fig.update_layout(barmode="stack", yaxis=dict(range=[0, 100], ticksuffix="%"))
    tag("4-chart")
    st.plotly_chart(style_fig(fig, 360), use_container_width=True)
    if inp["toggles"]["mix"] == "Optimized":
        st.caption("Share of the next unit of compute each limit would unlock (marginal view). A year at 0% everywhere has met its target.")
    else:
        st.caption("Fixed mix: compute is set by the tightest limit, so it gets 100% (split equally if tied); relieving any other limit adds nothing. A year at 0% everywhere has met its target.")
    tag("4-table")
    with st.expander("Show the numbers"):
        ldf = pd.DataFrame({l: [f"{lev[j][i]:.0%}" for j in range(6)] for i, l in enumerate(labels)}, index=YEARS).T
        ldf.loc["What binds"] = R["binds"]
        st.dataframe(ldf, use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 4. satellites
    st.markdown("## Annual satellites launched by class")
    cc1, cc2 = st.columns([5.5, 1])
    with cc2:
        tag("5-controls")
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
        is_num = measure.startswith("Number")
        base_t = [sum((R["sats"][j][i] if is_num else R["comp_cls"][j][i]) for i in range(4)) for j in range(6)]
        tot5 = [sum(base_t[:j + 1]) for j in range(6)] if cum4 else [b * mf for b in base_t]
        fig.add_scatter(x=YEARS, y=tot5, mode="text", text=[(f"{v:,.0f}" if is_num else f"{v:,.1f}") for v in tot5], textposition="top center",
                        textfont=dict(color=WHITE), showlegend=False, hoverinfo="skip")
        fig.update_layout(barmode="stack")
        fig = style_fig(fig, 360)
        fig.update_yaxes(range=[0, max(tot5 + [1e-9]) * 1.15])
        tag("5-chart")
        st.plotly_chart(fig, use_container_width=True)
    # 2028-33 totals by class, font colored to match the legend
    tag("5-totals")
    lab_sfx5 = "avg / month, 2028-33" if monthly else "2028-33"
    sc5 = st.columns(4)
    for col_, i in zip(sc5, range(4)):
        tot_i = sum((R["sats"][j][i] if is_num else R["comp_cls"][j][i]) for j in range(6))
        val = tot_i / 72 if monthly else tot_i
        unit5 = "satellites" if is_num else "GW"
        txt5 = (f"{val:,.0f}" if not monthly else f"{val:,.1f}") if is_num else f"{val:,.{2 if monthly else 1}f}"
        col_.markdown(f"<div style='text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;line-height:1.35;min-height:2.7em;color:#BFBFBF'>{cls[i]['id']}, {lab_sfx5}</div>"
                      f"<div style='font-size:2.0rem;font-weight:600;color:{CLASS_COL[cls[i]['id']]}'>{txt5} <span style='font-size:1rem;color:#8C8C8C'>{unit5}</span></div>",
                      unsafe_allow_html=True)
    tag("5-table")
    with st.expander("Show the numbers"):
        sdf = pd.DataFrame({cls[i]["id"]: ([sum((R["sats"][jj][i] if measure.startswith("Number") else R["comp_cls"][jj][i]) for jj in range(j + 1)) for j in range(6)] if cum4
                                            else [(R["sats"][j][i] if measure.startswith("Number") else R["comp_cls"][j][i]) * mf for j in range(6)]) for i in range(4)}, index=YEARS).T
        sdf.loc["Total"] = sdf.sum(axis=0)
        if not monthly and not cum4:
            sdf["2028-33"] = sdf.sum(axis=1)
        st.dataframe(sdf.map(lambda v: f"{v:,.0f}" if measure.startswith("Number") else f"{v:,.2f}"), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 5. closing the gap
    st.markdown("## Annual gigawatts of compute constrained by resource")
    gp = action_vals["lift"]          # full re-runs with each limit lifted (same as switching the toggle off)
    parts = [("Flights only", "flights", WHITE), ("Solar only", "solar", G1), ("Needs both flights and solar", "together", ACC), ("Chips", "chips", ACC2)]
    gc1, gc2 = st.columns([5.5, 1])
    with gc2:
        tag("6-controls")
        gap_mode = st.radio("Show", ["GW", "% of gap"], key="gaprel")
    rel_gap = gap_mode.startswith("%")
    # pieces can dip below zero in a year (e.g., with solar carry-forward, lifting flights spends banked solar earlier),
    # so the bars stack relative to zero and the totals use the true values; the pieces add exactly to the gap
    pos = {key_: list(gp[key_]) for _, key_, _ in parts}
    gap_yr = [sum(pos[key_][j] for _, key_, _ in parts) for j in range(6)]          # equals the gap to target
    share = {key_: [pos[key_][j] / gap_yr[j] * 100 if gap_yr[j] > 1e-9 else 0 for j in range(6)] for _, key_, _ in parts}
    with gc1:
        fig = go.Figure()
        for lab, key_, col in parts:
            if rel_gap:
                vals = share[key_]
                texts = [f"{v:.0f}%" if abs(v) > 3 else "" for v in vals]
            else:
                vals = [v * mf for v in pos[key_]]
                texts = [fmt(v, 1) if abs(v) > 0.05 * max(T) * mf else "" for v in vals]
            if sum(abs(v) for v in vals) > 1e-6:
                fig.add_bar(x=YEARS, y=vals, name=lab, marker_color=col, text=texts, textposition="inside",
                            insidetextfont=dict(color="#000000" if col in (WHITE, G1, ACC2) else WHITE))
        if not rel_gap:
            fig.add_scatter(x=YEARS, y=[x * mf for x in T], name="Target", mode="markers",
                            marker=dict(symbol="line-ew", size=40, line=dict(width=3, color=G2)))
        fig.update_layout(barmode="relative", yaxis_title=("% of gap" if rel_gap else unit_gw))
        fig = style_fig(fig, 400)
        if rel_gap and min(min(share[k_]) for _, k_, _ in parts) >= -1e-9:
            fig.update_yaxes(range=[0, 100], ticksuffix="%")
        tag("6-chart")
        st.plotly_chart(fig, use_container_width=True)
    # 2028-33 totals per resource, font colored to match the legend.
    # Cumulative % of gap = resource's 2028-33 GW / total 2028-33 gap (not an average of yearly %).
    tag("6-totals")
    lab_sfx6 = "avg / month, 2028-33" if monthly else "2028-33"
    gap_total = sum(gap_yr)
    tc = st.columns(len(parts) + 1)
    _al = action_vals.get("alone", {})
    _tip = (f"SSO alone: {_al.get('sso', 0):,.1f} GW<br>LEO alone: {_al.get('leo', 0):,.1f} GW<br>Note: not additive")
    for col_, (lab, key_, colr) in zip(tc, parts):
        tot_gw = sum(pos[key_])
        gw_txt = f"{(tot_gw / 72 if monthly else tot_gw):,.{2 if monthly else 1}f}"
        pct = tot_gw / gap_total if gap_total > 1e-9 else 0
        if rel_gap:
            main_txt, small_txt = f"{pct:.0%}", f"{gw_txt} GW"
        else:
            main_txt, small_txt = f"{gw_txt} <span style='font-size:1rem;color:#8C8C8C'>GW</span>", f"{pct:.0%} of cumulative gap"
        if key_ == "flights":   # hover shows what each orbit's flights unlock on their own
            main_txt = f"<span class='hovtip'>{main_txt}<span class='tiptext'>{_tip}</span></span>"
        col_.markdown(f"<div style='text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;line-height:1.35;min-height:2.7em;color:#BFBFBF'>{lab}, {lab_sfx6}</div>"
                      f"<div style='font-size:2.0rem;font-weight:600;color:{colr}'>{main_txt}</div>"
                      f"<div style='font-size:0.8rem;color:#8C8C8C'>{small_txt}</div>", unsafe_allow_html=True)
    mix_gw = sum(gp["mix"])
    tc[-1].markdown(f"<div style='text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;line-height:1.35;min-height:2.7em;color:#BFBFBF'>Orbit and satellite mix, {lab_sfx6}</div>"
                    f"<div style='font-size:2.0rem;font-weight:600;color:{G2}'>{mix_gw:,.1f} <span style='font-size:1rem;color:#8C8C8C'>GW</span></div>"
                    f"<div style='font-size:0.8rem;color:#8C8C8C'>Not additive: overlaps the pieces in the chart</div>", unsafe_allow_html=True)
    tag("6-table")
    with st.expander("Show the numbers"):
        if rel_gap:
            gdf = pd.DataFrame({lab: share[key_] for lab, key_, _ in parts}, index=YEARS).T
            gdf["2028-33"] = [sum(pos[key_]) / gap_total * 100 if gap_total > 1e-9 else 0 for _, key_, _ in parts]
            gdf.loc["Gap to target"] = [100.0 if gap_yr[j] > 1e-9 else 0 for j in range(6)] + [100.0 if gap_total > 1e-9 else 0]
            st.markdown("**Share of each year's gap** (2028-33 column = share of the cumulative gap)")
            st.dataframe(gdf.map(lambda v: f"{v:.1f}%"), use_container_width=True)
        else:
            gdf = pd.DataFrame({lab: [gp[key_][j] * mf for j in range(6)] for lab, key_, _ in parts}, index=YEARS).T
            gdf.loc["Gap to target"] = [gp["gap"][j] * mf for j in range(6)]
            if not monthly: gdf["2028-33"] = gdf.sum(axis=1)
            st.dataframe(gdf.map(lambda v: fmt(v, 2)), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 6. recommendation
    st.markdown("## Optimized plan")
    st.markdown("<span class='muted'>Optimization determines how much launch and solar capacity needs to be added, given targets and orbital + satellite mix requirements, to maximize economic value.</span>", unsafe_allow_html=True)
    c = inp["costs"]

    def _worth_line(worth_B, gw_lost, alone_gw=None):
        base = f"Worth ${worth_B:,.0f}B NPV"
        if gw_lost > 0.05:
            base += f"; without it the plan delivers {gw_lost:,.1f} GW less"
        else:
            base += "; without it the target is still met, but at higher cost"
        if alone_gw is not None:
            base += (f", and alone, this could unlock {alone_gw:,.1f} GW" if alone_gw > 0.05
                     else ", but alone it would unlock no extra compute")
        return base

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
    # valued like the other cards: the optimizer's plan at the optimized mix vs. at the seed mix (each re-planned)
    mix_gw_plan = sum(sol_opt["compute"]) - sum(sol_cust["compute"])
    if inp["toggles"]["mix"] == "Optimized":
        action_cards.append((mix_v["worth_B"], "Keep the optimized class and orbit mix (already applied)",
                             _worth_line(mix_v["worth_B"], mix_gw_plan), "", "Now"))
    else:
        held = (f"; the plan delivers {mix_gw_plan:,.1f} GW less" if mix_gw_plan > 0.05 else "; the plan reaches the same compute, at higher cost")
        action_cards.append((mix_v["worth_B"], "Class mix held at the seed mix",
                             f"Holding it costs ${mix_v['worth_B']:,.0f}B NPV" + held, "", "Your choice"))

    action_cards.sort(key=lambda t: t[0], reverse=True)

    for i, (worth_B, title, worth_line, detail, pill) in enumerate(action_cards, 1):
        body = worth_line if not detail else f"{worth_line}<br>{detail}"
        st.markdown(f"<div class='rec'>{tag_html(f'7-card-{i}')}<span class='pill'>{i}</span><b>{title}</b><br>"
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
        st.markdown(f"<div class='rec'>{tag_html('7-gap-card')}<span class='pill'>{n}</span><b>{title}</b><br>"
                    f"<span class='muted'>{' '.join(parts)}</span></div>", unsafe_allow_html=True)

    st.caption("Ranked by value at stake: the NPV lost if that action is dropped and the optimizer re-plans without it.")

    def _row(Rv, tgt):
        return {"2028-33 compute (GW)": sum(Rv["realized"]), "% of target": f"{sum(Rv['realized']) / tgt:.0%}" if tgt else "n/a", "2033 compute (GW)": Rv["realized"][-1],
                "Satellites": sum(sum(s) for s in Rv["sats"]), "Starship flights": sum(Rv["flights_sso"]) + sum(Rv["flights_leo"]),
                "Solar used (GW)": sum(Rv["solar_used"]), "Orion chips (M)": sum(Rv["orion_used"]) / 1e6, "Vega chips (M)": sum(Rv["vega_used"]) / 1e6}
    sel_nm = case_name()
    labels7 = {"Unconstrained": f"{sel_nm}: unconstrained", "Base case (constrained)": f"{sel_nm}: constrained", "Optimized (constrained)": f"{sel_nm}: optimized"}
    comp_rows = {labels7[name]: _row(Rv, cum_t) for name, Rv in VAR.items()}
    comp_rows[labels7["Unconstrained"]]["% of target"] = "100%"
    # every other scenario, run with the current sidebar settings
    for sc_ in st.session_state.scen:
        if sc_["name"] == sel_nm:
            continue
        x_ = build_inp(sc_)
        try:
            Rx = scenario_row(json.dumps(x_, sort_keys=True))
            comp_rows[f"{sc_['name']} (current settings)"] = _row(Rx, sum(x_["target"]))
        except Exception:
            pass
    cdf = pd.DataFrame(comp_rows).T
    st.markdown("**Scenario comparison**")
    tag("7-table")
    st.dataframe(cdf.map(fmt_cell), use_container_width=True)

    # ----------------------------------------------------------------------------------------------- 7. economics
    st.markdown("## Scenario economics")
    econ = selected_case_economics(inp, R, sol)
    if not econ["meaningful"]:
        tag("8-note")
        st.info("Economics not shown: with a limit switched off, that resource is treated as unlimited and free, so costs and NPV are not meaningful. Turn the limits back on to see the economics.")
    else:
        pv = econ["pv"]
        y = econ["yearly"]
        plan_npv = sol["pv"]["npv"]
        plan_adds = plan_npv - pv["npv"]
        tag("8-tiles")
        e = st.columns(4)
        e[0].metric("Value of compute (PV)", f"${pv['value']:,.0f}B", delta_color="off", delta_arrow="off")
        e[1].metric("Total cost (PV)", f"${pv['total']:,.0f}B", delta_color="off", delta_arrow="off")
        e[2].markdown(f"<div style='padding-top:0.375rem'><div style='text-transform:uppercase;letter-spacing:0.08em;font-size:0.72rem;color:#BFBFBF'>NPV</div>"
                      f"<div style='font-size:2.25rem;font-weight:600;color:{ACC};line-height:1.15;margin-top:0.1rem'>${pv['npv']:,.0f}B</div></div>", unsafe_allow_html=True)
        gain_txt = "≈ $0B" if abs(plan_adds) < 5 else (f"+${plan_adds:,.0f}B" if plan_adds > 0 else f"−${abs(plan_adds):,.0f}B")
        e[3].metric("NPV gain from optimized plan", gain_txt)
        tag("8-table")
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
                ("NPV, including base capacity capex", "npv"),
                ("NPV, excluding base capacity capex", "npv_ex_base"),
            ]
            edf = pd.DataFrame({lab: [y[k_][j] * mf for j in range(6)] for lab, k_ in rows}, index=YEARS).T
            edf["PV (2028 $)"] = [pv[k_] for _, k_ in rows]
            st.dataframe(edf.map(lambda v: fmt(v, 1)), use_container_width=True)
            st.download_button("Download CSV", edf.to_csv().encode(), "economics.csv", key="dl7")

    # ----------------------------------------------------------------------------------------------- 8. detail
    st.markdown("## Detailed plan")
    tag("9-table")
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
