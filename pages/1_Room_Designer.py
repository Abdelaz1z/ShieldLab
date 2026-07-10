"""
Room Designer (ShieldCAD MVP) — a ShieldLab page.
=================================================
Draw a nuclear-medicine room parametrically (dimensions + source + four walls with
their adjacent areas and openings). The app either SUGGESTS the shielding each wall
needs (Design mode) or EVALUATES the shielding you declare (Check mode), shows a
live top-view diagram that re-renders on every change, and exports a report as
PDF / Excel / HTML.

Engine: the validated NCRP-151 / TG-108 analytical tier (radshield.physics). The
Monte-Carlo-trained surrogate tier (ducts, off-axis, laminates) is added in Phase B.
"""

from __future__ import annotations

import streamlit as st

from radshield.room.model import (
    RoomDesign, Opening, WALL_IDS, WALL_NAMES, ISOTOPES, OCCUPANCY_MENU,
)
from radshield.room.engines import AnalyticalEngine, SurrogateEngine, usable_wall_materials
from radshield.room import diagram, report_room

st.set_page_config(page_title="ShieldLab — Room Designer", page_icon="🏗️", layout="wide")


def _occ_index(value: float) -> int:
    """Index of the occupancy-menu entry closest to `value`."""
    vals = list(OCCUPANCY_MENU.values())
    return min(range(len(vals)), key=lambda i: abs(vals[i] - value))


def _bfmt(x):
    return f"{x:.2e}" if isinstance(x, (int, float)) else "—"


def _results_table_html(results, surrogate_results, mode) -> str:
    """Theme-proof HTML results table showing the analytical AND surrogate tiers
    side by side (dark text, green/red verdicts). The surrogate column carries the
    95% CI; the verdict is the geometry-aware (surrogate) one where trusted, else
    the analytical fallback."""
    smap = {r.label: r for r in (surrogate_results or [])}
    have_sur = bool(surrogate_results)
    sur_hdr = ("<th style='padding:6px 9px'>Surrogate B (95% CI)</th>"
               "<th style='padding:6px 9px'>Tier</th>") if have_sur else ""
    head = ("<tr style='background:#305496;color:#fff'>"
            "<th style='padding:6px 9px;text-align:left'>Barrier</th>"
            "<th style='padding:6px 9px'>Material</th>"
            "<th style='padding:6px 9px'>Suggested&nbsp;mm</th>"
            "<th style='padding:6px 9px'>Analytical&nbsp;B</th>"
            f"{sur_hdr}"
            "<th style='padding:6px 9px'>Verdict</th>"
            "<th style='padding:6px 9px'>Margin&nbsp;×</th></tr>")
    body = ""
    for a in results:
        s = smap.get(a.label)
        prim = s if s is not None else a          # verdict source
        if prim.passes is True:
            bg, vtxt, vcol = "#e6f4ea", "PASS", "#1b5e20"
        elif prim.passes is False:
            bg, vtxt, vcol = "#fdecea", "FAIL", "#b71c1c"
        else:
            bg, vtxt, vcol = "#f3f4f6", "needs MC", "#8a6d1b"
        sug = (f"{a.suggested_thickness_mm:g}"
               if (mode == "design" and a.suggested_thickness_mm is not None) else "—")
        marg = f"{prim.margin:.2f}" if prim.margin is not None else "—"
        cell = "padding:6px 9px;color:#1a1a1a;border-bottom:1px solid #d9dde3"
        sur_cells = ""
        if have_sur:
            if s is not None and s.ci_low is not None:
                sB = f"{s.B_achieved:.2e}<br><span style='color:#555;font-size:11px'>[{s.ci_low:.1e}, {s.ci_high:.1e}]</span>"
                tier = "MC surrogate"
                tcol = "#1b5e20"
            elif s is not None and s.ood:
                sB = _bfmt(s.B_achieved)
                tier = "OOD→analytical" if s.B_achieved is not None else "needs MC"
                tcol = "#8a6d1b"
            else:
                sB, tier, tcol = "—", "—", "#555"
            sur_cells = (f"<td style='{cell};text-align:center'>{sB}</td>"
                         f"<td style='{cell};text-align:center;color:{tcol};font-size:11px'>{tier}</td>")
        body += (
            f"<tr style='background:{bg}'>"
            f"<td style='{cell};text-align:left;font-weight:600'>{a.label}</td>"
            f"<td style='{cell};text-align:center'>{a.material or '—'}</td>"
            f"<td style='{cell};text-align:center'>{sug}</td>"
            f"<td style='{cell};text-align:center'>{_bfmt(a.B_achieved)}</td>"
            f"{sur_cells}"
            f"<td style='{cell};text-align:center;color:{vcol};font-weight:700'>{vtxt}</td>"
            f"<td style='{cell};text-align:center'>{marg}</td></tr>")
    return (f"<table style='width:100%;border-collapse:collapse;font-size:13px;"
            f"font-family:Arial,Helvetica,sans-serif'>{head}{body}</table>")


def _leakage_banners(results, surrogate_results):
    """Warn where a duct's surrogate transmission far exceeds the same wall's solid B —
    the safety-critical streaming effect the analytical model misses entirely."""
    if not surrogate_results:
        return []
    smap = {r.label: r for r in surrogate_results}
    wallB = {}
    for a in results:
        if a.label.startswith("Wall ") and "·" not in a.label:
            s = smap.get(a.label)
            b = s.B_achieved if (s and s.B_achieved is not None) else a.B_achieved
            if b:
                wallB[a.label.split()[1]] = b
    out = []
    for a in results:
        if "duct" in a.label:
            s = smap.get(a.label)
            if s and s.B_achieved is not None and s.ci_low is not None:
                wid = a.label.split()[1]
                wb = wallB.get(wid)
                if wb and s.B_achieved > 3 * wb:
                    out.append(
                        f"⚠️ **{a.label}:** the surrogate predicts duct-streaming transmission "
                        f"B≈{s.B_achieved:.1e} — about **{s.B_achieved/wb:.0f}× the solid wall** "
                        f"({wb:.1e}). Duct penetrations dominate the dose here; the analytical "
                        f"model misses this entirely.")
    return out


st.title("🏗️ Room Designer")
st.caption("Draw a nuclear-medicine room → get the shielding each wall needs, with a live "
           "plan view and an exportable report. Analytical (NCRP-151 / TG-108) engine.")

# --- session state ----------------------------------------------------------
if "design" not in st.session_state:
    st.session_state.design = RoomDesign.default()
design: RoomDesign = st.session_state.design

# ============================================================================ #
# Top controls: mode, framework, save/load
# ============================================================================ #
c1, c2, c3, c4 = st.columns([1.3, 1.2, 1, 1])
with c1:
    mode = st.radio("Mode", ["Design (suggest shielding)", "Check (evaluate my design)"],
                    horizontal=False, key="mode_radio")
    mode = "design" if mode.startswith("Design") else "check"
with c2:
    design.framework = st.selectbox("Regulatory framework", ["NCRP", "IAEA_NRRC"],
                                    index=0 if design.framework == "NCRP" else 1,
                                    help="NCRP = weekly air-kerma goals. IAEA_NRRC = annual "
                                         "constraint / weeks (Saudi NRRC / IAEA BSS basis).")
with c3:
    up = st.file_uploader("Load design (.json)", type=["json"], key="load_json")
    if up is not None:
        try:
            st.session_state.design = RoomDesign.from_json(up.getvalue().decode("utf-8"))
            st.success("Design loaded."); st.rerun()
        except Exception as exc:
            st.error(f"Could not load: {exc}")
with c4:
    st.download_button("💾 Save design (.json)", data=design.to_json(),
                       file_name="room_design.json", mime="application/json",
                       use_container_width=True)

st.divider()
left, right = st.columns([1, 1.35])

# ============================================================================ #
# LEFT: controls
# ============================================================================ #
with left:
    with st.expander("📐 Floor-plan reference image (optional — JPG/PNG)", expanded=False):
        plan_img = st.file_uploader("Upload your room drawing to trace from",
                                    type=["png", "jpg", "jpeg"], key="planimg")
        if plan_img is not None:
            st.image(plan_img, use_container_width=True,
                     caption="Reference only — read the dimensions/openings off this image and enter "
                             "them below. Automatic extraction from a drawing is on the roadmap "
                             "(DXF/IFC import — Phase C).")

    st.subheader("Room & source")
    rc1, rc2, rc3 = st.columns(3)
    design.room.width_m = rc1.number_input("Width W→E (m)", 1.0, 40.0, design.room.width_m, 0.5)
    design.room.length_m = rc2.number_input("Length S→N (m)", 1.0, 40.0, design.room.length_m, 0.5)
    design.room.height_m = rc3.number_input("Height (m)", 2.0, 8.0, design.room.height_m, 0.1)

    sc1, sc2 = st.columns(2)
    design.source.isotope = sc1.selectbox("Isotope", ISOTOPES,
                                          index=ISOTOPES.index(design.source.isotope)
                                          if design.source.isotope in ISOTOPES else 0)
    design.source.activity_MBq = sc2.number_input("Activity / patient (MBq)", 1.0, 100000.0,
                                                  design.source.activity_MBq, 10.0)
    sc3, sc4 = st.columns(2)
    design.source.patients_per_week = sc3.number_input("Patients / week", 1.0, 2000.0,
                                                       design.source.patients_per_week, 1.0)
    design.source.residence_min = sc4.number_input("Residence (min/patient)", 1.0, 600.0,
                                                   design.source.residence_min, 5.0)
    px, py = st.columns(2)
    design.source.x_m = px.slider("Source X (m from West)", 0.0, design.room.width_m,
                                  min(design.source.x_m, design.room.width_m), 0.1)
    design.source.y_m = py.slider("Source Y (m from South)", 0.0, design.room.length_m,
                                  min(design.source.y_m, design.room.length_m), 0.1)

    materials = usable_wall_materials(design.source.isotope) or ["concrete"]

    st.subheader("Walls")
    for w in design.walls:
        with st.expander(f"Wall {w.id} — {WALL_NAMES[w.id]}", expanded=(w.id == "N")):
            w.adjacent.name = st.text_input("Adjacent area name", w.adjacent.name, key=f"nm_{w.id}")
            oc1, oc2 = st.columns(2)
            occ_label = oc1.selectbox("Occupancy factor T", list(OCCUPANCY_MENU),
                                      index=_occ_index(w.adjacent.occupancy_T), key=f"occ_{w.id}")
            w.adjacent.occupancy_T = OCCUPANCY_MENU[occ_label]
            w.adjacent.kind = oc2.selectbox("Area type", ["public", "controlled"],
                                            index=0 if w.adjacent.kind == "public" else 1,
                                            key=f"kind_{w.id}")
            use_override = st.checkbox("Override design goal P", key=f"ovck_{w.id}",
                                       value=w.adjacent.design_goal_P_mSv_wk is not None)
            if use_override:
                w.adjacent.design_goal_P_mSv_wk = st.number_input(
                    "P (mSv or mGy / week)", 0.0001, 10.0,
                    w.adjacent.design_goal_P_mSv_wk or 0.02, 0.001, format="%.4f", key=f"ov_{w.id}")
            else:
                w.adjacent.design_goal_P_mSv_wk = None

            mc1, mc2 = st.columns(2)
            w.material1 = mc1.selectbox("Material (layer 1)", materials,
                                        index=materials.index(w.material1) if w.material1 in materials else 0,
                                        key=f"m1_{w.id}")
            if mode == "check":
                w.thickness1_mm = mc2.number_input("Thickness 1 (mm)", 0.0, 3000.0,
                                                   w.thickness1_mm, 5.0, key=f"t1_{w.id}")
            else:
                mc2.caption("Thickness suggested →")
            lam = st.checkbox("Add a second layer (laminate)", key=f"lamck_{w.id}",
                              value=bool(w.material2))
            if lam:
                lc1, lc2 = st.columns(2)
                w.material2 = lc1.selectbox("Material (layer 2)", materials,
                                            index=materials.index(w.material2) if w.material2 in materials else 0,
                                            key=f"m2_{w.id}")
                w.thickness2_mm = lc2.number_input("Thickness 2 (mm)", 0.0, 3000.0,
                                                   w.thickness2_mm or 0.0, 5.0, key=f"t2_{w.id}")
            else:
                w.material2, w.thickness2_mm = None, 0.0

            # openings
            st.markdown("**Openings**")
            span = design.room.width_m if w.id in ("N", "S") else design.room.length_m
            add1, add2, add3, add4 = st.columns(4)
            if add1.button("➕ Door", key=f"ad_{w.id}"):
                w.openings.append(Opening(kind="door", center_along_wall_m=span / 2, lead_equiv_mm=1.0))
            if add2.button("➕ Window", key=f"aw_{w.id}"):
                w.openings.append(Opening(kind="window", center_along_wall_m=span / 2, lead_equiv_mm=2.0))
            if add3.button("➕ Duct", key=f"au_{w.id}"):
                w.openings.append(Opening(kind="duct", center_along_wall_m=span / 2, radius_mm=25.0))
            if add4.button("➕ Maze", key=f"am_{w.id}"):
                w.openings.append(Opening(kind="maze", center_along_wall_m=span / 2))
            for i, op in enumerate(list(w.openings)):
                k = f"{w.id}_{i}"
                st.markdown(f"*{op.kind}*")
                pc1, pc2, pc3 = st.columns([1.1, 1.1, 0.6])
                op.center_along_wall_m = pc1.number_input("Position along wall (m)", 0.0, float(span),
                                                          float(op.center_along_wall_m), 0.1, key=f"pos_{k}")
                if op.kind == "duct":
                    op.radius_mm = pc2.number_input("Radius (mm)", 1.0, 300.0, float(op.radius_mm or 25), 1.0,
                                                    key=f"rad_{k}")
                elif op.kind == "maze":
                    op.corridor_m = pc2.number_input("Corridor length (m)", 0.2, 3.0,
                                                     float(op.corridor_m or 0.8), 0.1, key=f"cor_{k}")
                    mzc1, mzc2, mzc3 = st.columns(3)
                    op.shadow_offset_m = mzc1.number_input("Shadow offset (m)", 0.1, 2.0,
                                                           float(op.shadow_offset_m or 0.5), 0.1,
                                                           key=f"sho_{k}")
                    op.ret_material = mzc2.selectbox("Return wall", materials,
                                                     index=materials.index(op.ret_material)
                                                     if op.ret_material in materials else 0,
                                                     key=f"rm_{k}")
                    op.ret_thickness_mm = mzc3.number_input("Return t (mm)", 10.0, 1000.0,
                                                            float(op.ret_thickness_mm or 150), 10.0,
                                                            key=f"rt_{k}")
                else:
                    op.lead_equiv_mm = pc2.number_input("Lead equiv (mm)", 0.0, 100.0,
                                                        float(op.lead_equiv_mm or 1.0), 0.5, key=f"le_{k}")
                if pc3.button("🗑", key=f"del_{k}"):
                    w.openings.pop(i); st.rerun()

# ============================================================================ #
# Compute
# ============================================================================ #
errs = design.validate()
engine = AnalyticalEngine(design)
results = engine.evaluate_all(mode) if not errs else []
surrogate = SurrogateEngine(design)
surrogate_results = (surrogate.evaluate_all(mode, results)
                     if (results and surrogate.available()) else None)
# the diagram + report use the geometry-aware (surrogate) verdict where available
primary_results = surrogate_results if surrogate_results else results

# ============================================================================ #
# RIGHT: diagram + results + export
# ============================================================================ #
with right:
    st.subheader("Plan view")
    if errs:
        for e in errs:
            st.warning(e)
    else:
        st.image(diagram.render(design, primary_results), use_container_width=True)
        if surrogate.available():
            st.caption("Walls coloured by the geometry-aware **Monte-Carlo surrogate** where it is "
                       "trusted; **analytical fallback** (amber-edged / OOD) elsewhere.")
        else:
            st.caption("Surrogate model not loaded — analytical tier only. "
                       "(Add `models/surrogate_bundle.joblib` to enable the MC tier.)")

    st.subheader("Per-barrier results")
    if results:
        st.markdown(_results_table_html(results, surrogate_results, mode),
                    unsafe_allow_html=True)

        # duct leakage warning: surrogate duct B >> the same wall's solid B
        for banner in _leakage_banners(results, surrogate_results):
            st.warning(banner)

        # honest flags for anything undetermined by BOTH tiers
        prim = {r.label: r for r in primary_results}
        for r in primary_results:
            if r.passes is None and r.dose_mSv_wk is None:
                st.info(f"**{r.label}:** {r.note}")

        st.subheader("Export report")
        ec1, ec2 = st.columns([1, 1.4])
        fmt = ec1.selectbox("Format", ["PDF", "Excel", "HTML"])
        png = diagram.render(design, primary_results)
        report = report_room.build_report(design, results, mode, png,
                                          surrogate_results=surrogate_results)
        data, mime, ext = report_room.export(report, fmt)
        ec2.download_button(f"⬇ Download {fmt} report", data=data,
                            file_name=f"ShieldLab_RoomReport.{ext}", mime=mime,
                            use_container_width=True)

st.divider()
st.caption("Decision-support output — requires review and sign-off by a qualified RSO / medical "
           "physicist. Analytical tier: NCRP-151 / TG-108 broad-beam (ShieldLab, validated). "
           "Surrogate tier: Monte-Carlo-trained Extra-Trees with conformal 95% intervals and an "
           "out-of-domain guard (thesis, 2026) — handles ducts, off-axis points and laminates.")
