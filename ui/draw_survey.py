"""Draw & Survey: draw a room in Room Designer, give its barriers their materials, and get the
predicted survey at every numbered point from the validated ShieldLab engines."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from shieldlab.room.drawn_plan import OPENING_NAMES, DrawnPlan, parse_plan
from shieldlab.room.drawn_survey import (PointResult, SurveySetup, barrier_transmission,
                                         survey)
from shieldlab.room.engines import wall_layer_materials
from shieldlab.room.model import ISOTOPES, OCCUPANCY_MENU

from . import product_shell as ds

DRAW_HEIGHT = 760
NONE = "—"
OPENING_MATERIALS = ("lead", "lead_glass", "plate_glass", "steel", "wood", "concrete", "gypsum")
OCCUPANCY_LABELS = list(OCCUPANCY_MENU)
_DRAWER = components.declare_component(
    "room_drawer", path=str(Path(__file__).resolve().parent / "components" / "room_drawer"))


# ------------------------------------------------------------------------------ plan in

def _plan_from_drawer() -> dict | None:
    """The plan last sent from the drawing, or uploaded as a Room Designer .json file."""
    sent = _DRAWER(height=DRAW_HEIGHT, key="room_drawer", default=None)
    if sent and sent.get("sent_at") != st.session_state.get("drawn_sent_at"):
        st.session_state["drawn_sent_at"] = sent["sent_at"]
        st.session_state["drawn_plan"] = sent["plan"]
    upload = st.file_uploader("Or load a plan saved from Room Designer (Export → Plan file .json)",
                              type=["json"], key="drawn_upload")
    if upload is not None:
        digest = hashlib.sha1(upload.getvalue()).hexdigest()
        if digest != st.session_state.get("drawn_upload_digest"):
            st.session_state["drawn_upload_digest"] = digest
            st.session_state["drawn_plan"] = json.loads(upload.getvalue())
    return st.session_state.get("drawn_plan")


def _signature(plan: DrawnPlan) -> str:
    keys = [(s.key, round(s.length_m, 3), round(s.thickness_m, 3)) for s in plan.segments]
    keys += [(o.key, o.kind, o.segment_key) for o in plan.openings]
    keys += [(p.n, p.label) for p in plan.points]
    return hashlib.sha1(repr(keys).encode()).hexdigest()[:12]


# ------------------------------------------------------------------------------ tables

def _remembered(name: str, key: str, default: dict) -> dict:
    """A row the user edited before, for a barrier or point that is still in the plan."""
    return st.session_state.setdefault(f"drawn_{name}", {}).get(key, default)


def _wall_frame(plan: DrawnPlan) -> pd.DataFrame:
    rows = []
    for s in plan.segments:
        drawn = round(s.thickness_m * 1000.0)
        rows.append(_remembered("walls", s.key, {
            "Barrier": s.key, "Where": s.label, "Drawn (mm)": drawn,
            "Layer 1": "concrete", "mm 1": float(drawn), "Layer 2": NONE, "mm 2": 0.0,
            "Layer 3": NONE, "mm 3": 0.0}))
    return pd.DataFrame(rows)


def _opening_frame(plan: DrawnPlan) -> pd.DataFrame:
    rows = []
    for o in plan.openings:
        rows.append(_remembered("openings", o.key, {
            "Opening": o.key, "Type": OPENING_NAMES.get(o.kind, o.kind), "On": o.segment_key,
            "Width (m)": round(o.width_m, 2),
            "Material": NONE if o.kind == "gap" else "lead",
            "mm": 0.0 if o.kind == "gap" else 2.0,
            "Panel material": "lead_glass" if o.vision_panel else NONE,
            "Panel mm": 10.0 if o.vision_panel else 0.0}))
    return pd.DataFrame(rows)


def _point_frame(plan: DrawnPlan) -> pd.DataFrame:
    rows = [_remembered("points", str(p.n), {
        "No.": p.n, "Location": p.label or f"Point {p.n}",
        "Occupancy": OCCUPANCY_LABELS[0], "Controlled area": False}) for p in plan.points]
    return pd.DataFrame(rows)


def _edit(name: str, frame: pd.DataFrame, signature: str, columns: dict, fixed: list) -> pd.DataFrame:
    if frame.empty:
        return frame
    edited = st.data_editor(frame, key=f"drawn_editor_{name}_{signature}", hide_index=True,
                            use_container_width=True, column_config=columns, disabled=fixed)
    store = st.session_state.setdefault(f"drawn_{name}", {})
    for row in edited.to_dict("records"):
        store[str(row[frame.columns[0]])] = row
    return edited


def _material_columns(materials: list, with_none: bool) -> dict:
    options = ([NONE] if with_none else []) + materials
    return st.column_config.SelectboxColumn(options=options, required=True)


def _layers(row: dict, pairs) -> tuple:
    return tuple((row[m], float(row[t])) for m, t in pairs
                 if row.get(m) not in (None, NONE, "") and float(row.get(t) or 0) > 0)


# ------------------------------------------------------------------------------ setup

def _source_inputs() -> dict:
    cols = st.columns(5)
    return {
        "isotope": cols[0].selectbox("Radionuclide", ISOTOPES, index=ISOTOPES.index("F-18"),
                                     key="drawn_isotope"),
        "activity_MBq": cols[1].number_input("Activity per patient (MBq)", 1.0, 20000.0, 370.0,
                                             key="drawn_activity"),
        "patients_per_week": cols[2].number_input("Patients per week", 1.0, 500.0, 40.0,
                                                  key="drawn_ppw"),
        "residence_min": cols[3].number_input("Minutes per patient at the source", 1.0, 10080.0,
                                              60.0, key="drawn_residence"),
        "framework": cols[4].selectbox("Limits", ("NCRP", "IAEA_NRRC"), key="drawn_framework"),
    }


def _setup(source: dict, walls: pd.DataFrame, openings: pd.DataFrame,
           points: pd.DataFrame) -> SurveySetup:
    layer_pairs = (("Layer 1", "mm 1"), ("Layer 2", "mm 2"), ("Layer 3", "mm 3"))
    setup = SurveySetup(**source)
    for row in walls.to_dict("records"):
        setup.walls[row["Barrier"]] = _layers(row, layer_pairs)
    for row in openings.to_dict("records"):
        setup.openings[row["Opening"]] = _layers(row, (("Material", "mm"),))
        setup.panels[row["Opening"]] = _layers(row, (("Panel material", "Panel mm"),))
    for row in points.to_dict("records"):
        setup.occupancy[int(row["No."])] = OCCUPANCY_MENU[row["Occupancy"]]
        setup.controlled[int(row["No."])] = bool(row["Controlled area"])
    return setup


# ------------------------------------------------------------------------------ results

def _verdict(result: PointResult) -> str:
    if result.passes is None:
        return "Needs Monte Carlo"
    if not result.passes:
        return "Fails"
    if result.dose_upper_mSv_wk is not None and result.dose_upper_mSv_wk > result.goal_over_T:
        return "Passes (upper limit fails)"
    return "Passes"


def _usv(value) -> float | None:
    return None if value is None else round(value * 1000.0, 3)


def _results_frame(results: list[PointResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "No.": r.point.n, "Location": r.point.label or f"Point {r.point.n}",
            "Result": _verdict(r),
            "Dose (µSv/week)": _usv(r.dose_mSv_wk),
            "Limit P/T (µSv/week)": _usv(r.goal_over_T),
            "Dose at upper limit (µSv/week)": _usv(r.dose_upper_mSv_wk),
            "B (model)": r.B, "B low": r.B_low, "B high": r.B_high, "B (analytical)": r.B_analytical,
            "Distance (m)": round(r.distance_m, 2),
            "Barriers crossed": "; ".join(f"{c.barrier.split(',')[0]} at {c.angle_deg:.0f}°"
                                          for c in r.crossings) or "none",
            "Notes": " ".join(r.notes)})
    return pd.DataFrame(rows)


def _plan_figure(plan: DrawnPlan, results: list[PointResult]):
    fig, ax = plt.subplots(figsize=(7.5, 6.0))
    for s in plan.segments:
        ax.plot([s.a[0], s.b[0]], [s.a[1], s.b[1]], color="#3b4252",
                linewidth=max(1.5, s.thickness_m * 40), solid_capstyle="butt")
    for o in plan.openings:
        s = plan.segment(o.segment_key)
        cx, cy = s.a[0] + o.t * (s.b[0] - s.a[0]), s.a[1] + o.t * (s.b[1] - s.a[1])
        ax.plot(cx, cy, marker="s", color="#5e81ac", markersize=7)
    source = plan.sources[0]
    colours = {"Passes": "#2e7d32", "Fails": "#c62828", "Needs Monte Carlo": "#6d6d6d"}
    for r in results:
        verdict = _verdict(r)
        colour = colours.get(verdict, "#ef6c00")
        ax.plot([source[0], r.calc_xy[0]], [source[1], r.calc_xy[1]], color=colour,
                linewidth=0.6, alpha=0.5)
        ax.plot(*r.calc_xy, marker="o", color=colour, markersize=9)
        ax.annotate(str(r.point.n), r.calc_xy, xytext=(6, 6), textcoords="offset points",
                    fontsize=9)
    ax.plot(*source, marker="*", color="#f9a825", markersize=18, markeredgecolor="#333")
    ax.set_aspect("equal")
    ax.invert_yaxis()                      # Room Designer's y runs down the page
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    ax.grid(alpha=0.2)
    return fig


def _barrier_frame(plan: DrawnPlan, setup: SurveySetup) -> pd.DataFrame:
    rows = []
    entries = [(s.key, s.label, setup.walls.get(s.key, ())) for s in plan.segments]
    entries += [(o.key, o.label, setup.openings.get(o.key, ())) for o in plan.openings]
    for key, label, layers in entries:
        served, analytical = barrier_transmission(setup, key, layers)
        rows.append({
            "Barrier": label,
            "Build-up": " + ".join(f"{t:g} mm {m}" for m, t in layers) or "open",
            "B (model)": served.B_achieved if served else 1.0,
            "B low": served.ci_low if served else None,
            "B high": served.ci_high if served else None,
            "B (analytical)": analytical.B_achieved if analytical else 1.0,
            "Tier": served.engine if served else "open"})
    return pd.DataFrame(rows)


SCIENTIFIC = {name: st.column_config.NumberColumn(format="%.2e")
              for name in ("B (model)", "B low", "B high", "B (analytical)")}


def _render_results(plan: DrawnPlan, setup: SurveySetup) -> None:
    results = survey(plan, setup)
    ds.section_header("4", "Predicted survey",
                      "Weekly dose at each point from the source at the radiation symbol. "
                      "Model E5 serves each barrier, raised to a broad beam and corrected for "
                      "the angle of the line; the analytical (TVL) value is shown beside it.")
    left, right = st.columns([1.35, 1.0], gap="large")
    with left:
        st.dataframe(_results_frame(results), hide_index=True, use_container_width=True,
                     column_config=SCIENTIFIC)
    with right:
        st.pyplot(_plan_figure(plan, results), clear_figure=True)
    ds.section_header("5", "Transmission of each barrier",
                      "B at normal incidence for this radionuclide, independent of distance.")
    st.dataframe(_barrier_frame(plan, setup), hide_index=True, use_container_width=True,
                 column_config=SCIENTIFIC)
    st.caption(
        "Line-of-sight only: dose that scatters over or around a barrier (ceiling, floor, room "
        "return) is not included, and a line through several barriers multiplies their "
        "transmissions, which over-states the dose. Points drawn against a wall are calculated "
        "0.3 m beyond it on the side away from the source. A door with a glass panel is served as "
        "the weaker of the two.")


# ------------------------------------------------------------------------------ page

def render() -> None:
    ds.inject_styles()
    ds.render_sidebar("draw")
    ds.page_header("Room survey", "Draw & Survey",
                   "Draw the room, mark the source with the radiation symbol and number the survey "
                   "points, then press Send to survey. Give each wall, door and window its "
                   "materials and get the predicted dose at every point.",
                   badges=("Model E5", "Broad-beam corrected", "Oblique lines corrected"))
    raw = _plan_from_drawer()
    if raw is None:
        st.info("Draw the room above and press **Send to survey** (bottom right of the drawing).")
        return
    try:
        plan = parse_plan(raw)
    except ValueError as exc:
        st.error(str(exc))
        return
    for problem in plan.problems():
        st.warning(problem)
    if plan.problems():
        return

    signature = _signature(plan)
    ds.section_header("1", "Source", f"Plan: {plan.name}. The radiation symbol marks the source.")
    source = _source_inputs()
    if len(plan.sources) > 1:
        st.warning("The plan has more than one radiation symbol; the first one is used.")
    materials = wall_layer_materials(source["isotope"]) or ["concrete"]
    if "lead" not in materials:
        materials.append("lead")

    ds.section_header("2", "Walls", "Each side of every drawn wall. Layers run from the source side.")
    walls = _edit("walls", _wall_frame(plan), signature, {
        "Layer 1": _material_columns(materials, False),
        "Layer 2": _material_columns(materials, True),
        "Layer 3": _material_columns(materials, True)}, ["Barrier", "Where", "Drawn (mm)"])
    ds.section_header("3", "Doors, windows and points")
    openings = _edit("openings", _opening_frame(plan), signature, {
        "Material": _material_columns(list(OPENING_MATERIALS), True),
        "Panel material": _material_columns(list(OPENING_MATERIALS), True)},
        ["Opening", "Type", "On", "Width (m)"])
    points = _edit("points", _point_frame(plan), signature, {
        "Occupancy": st.column_config.SelectboxColumn(options=OCCUPANCY_LABELS, required=True)},
        ["No."])
    _render_results(plan, _setup(source, walls, openings, points))
    ds.render_sidebar_footer()
