"""One-click scenario presets. Each takes the case defaults and returns a modified copy."""
import copy


def _scale(arr, f):
    return [x * f for x in arr]


def base(d):
    return d


def unconstrained(d):
    d["toggles"].update(launch_on=0, solar_on=0, chips_on=0)
    return d


def seed_mix(d):
    d["toggles"]["mix"] = "Custom"
    return d


def recommended(d):
    d["toggles"]["apply_solver"] = 1
    return d


def v4_slip(d):
    d["vehicles"][1]["year"] = 2032
    return d


def flights_short(d):
    d["flights_sso"] = [round(x * 0.8) for x in d["flights_sso"]]
    d["flights_leo"] = [round(x * 0.8) for x in d["flights_leo"]]
    return d


def solar_share(d):
    d["solar"] = _scale(d["solar"], 0.8)
    return d


def chips_short(d):
    d["orion"] = [round(x * 0.75) for x in d["orion"]]
    d["vega"] = [round(x * 0.75) for x in d["vega"]]
    return d


def heliosb_late(d):
    d["toggles"]["heliosb_year"] = 2032
    return d


def no_reuse(d):
    d["costs"]["ops"] = 100
    return d


PRESETS = {
    "Base case (case resources, optimized mix)": base,
    "Unconstrained (all limits off)": unconstrained,
    "Seed mix (Annual series tab)": seed_mix,
    "Recommended plan (Solver additions applied)": recommended,
    "Risk: Starship V4 slips to 2032": v4_slip,
    "Risk: flights 20% below plan": flights_short,
    "Risk: only 80% of solar for AI": solar_share,
    "Risk: chip supply 25% short": chips_short,
    "Risk: Helios-B delayed to 2032": heliosb_late,
    "Risk: no reuse ($100M per flight)": no_reuse,
}


def apply(name, defaults):
    return PRESETS[name](copy.deepcopy(defaults))
