"""
views.py
========
The Streamlit screens. `calculator_tab()` collects inputs, builds the source
term and barrier, runs the engine and shows the results. `references_tab()` and
`limitations_tab()` show the bibliography and the documented caveats.

Kept separate from app.py so the entry point stays tiny and this file can grow.
"""

import streamlit as st

from radshield import data_loader as dl
from radshield.physics import beams as bm, barriers as ba, sources as src, solver
from radshield.regulatory import limits as reg
from radshield.report import report as rpt
from . import modality_config as mc


# ===========================================================================
# CALCULATOR
# ===========================================================================

def calculator_tab():
    # --- 1. Modality & energy (sidebar) ------------------------------------
    st.sidebar.header("1 - Modality & Energy")
    group = st.sidebar.selectbox("Facility / modality group", mc.groups())
    options = mc.modalities_in_group(group)
    mod_key = st.sidebar.selectbox(
        "Modality", [k for k, _ in options],
        format_func=lambda k: dict(options)[k],
    )
    cfg = mc.MODALITIES[mod_key]
    if cfg.get("note"):
        st.sidebar.info(cfg["note"])

    # --- 2. Regulatory framework (sidebar) ---------------------------------
    st.sidebar.header("2 - Regulatory basis")
    fw_labels = {"NCRP": "NCRP weekly air-kerma goals",
                 "IAEA_NRRC": "IAEA GSR Part 3 / Saudi NRRC annual constraints"}
    framework = st.sidebar.radio("Framework", list(fw_labels),
                                 format_func=lambda k: fw_labels[k])
    area_type = st.sidebar.radio("Area type", ["controlled", "uncontrolled"],
                                 format_func=str.capitalize)

    # occupancy factor with the NCRP table as a guide
    occ = dl.limits()["occupancy_factors"]["table"]
    occ_labels = [f"{row['fraction']} - {row['areas'][:45]}..." for row in occ]
    occ_choice = st.sidebar.selectbox("Occupancy factor T (NCRP Table 4.1)",
                                      range(len(occ)), format_func=lambda i: occ_labels[i])
    T = occ[occ_choice]["T"]
    T = st.sidebar.number_input("...or set T directly", 0.001, 1.0, float(T), 0.005, format="%.3f")

    goal = reg.design_goal(framework, area_type, occupancy_T=T)
    P_override = st.sidebar.number_input(
        f"Design goal P ({goal.unit})", 0.0, 100.0, float(round(goal.P_weekly, 5)),
        format="%.5f",
        help="Editable. " + goal.basis,
    )
    goal = reg.design_goal(framework, area_type, occupancy_T=T, override_P_weekly=P_override)
    st.sidebar.caption(f"Goal/T = {goal.P_weekly/ T:.4g} {goal.unit}  •  {goal.basis}")

    # --- main area: modality-specific inputs -> source term ----------------
    col_in, col_bar = st.columns([1, 1])

    with col_in:
        st.subheader(f"Inputs — {cfg['label']}")
        source = _build_source(mod_key, cfg)

    # --- 5. Barrier builder ------------------------------------------------
    with col_bar:
        st.subheader("Barrier (mix materials)")
        barrier = _barrier_builder(source)

    if source is None:
        return

    # --- I-131 release dose is a separate (non-barrier) calculation --------
    if cfg["builder"] == "i131":
        _show_i131_release(cfg)

    st.divider()

    # --- 6. Evaluate & show results ----------------------------------------
    ev = solver.evaluate(source, barrier, goal)
    _show_results(source, barrier, goal, ev)


# ---------------------------------------------------------------------------
# input builders per modality
# ---------------------------------------------------------------------------

def _build_source(mod_key, cfg):
    """Collect inputs and return the SourceTerm for the chosen modality."""
    b = cfg["builder"]

    if b == "diagnostic":
        kvp = st.selectbox("Maximum tube potential (kVp)", mc.KVP_OPTIONS,
                           index=mc.KVP_OPTIONS.index(cfg["default_kvp"])
                           if cfg["default_kvp"] in mc.KVP_OPTIONS else 5)
        N = st.number_input("Patients per week (workload N)", 1, 100000,
                            cfg["default_patients"], 1)
        dP = st.number_input("Distance source → barrier, primary (m)", 0.3, 50.0,
                             float(cfg["default_d_primary"]), 0.1)
        dS = st.number_input("Distance patient → barrier, scatter/leakage (m)", 0.3, 50.0,
                             float(cfg["default_d_secondary"]), 0.1)
        geom = st.selectbox("Secondary geometry (NCRP 147 Table 4.7)",
                            ["leak_forward_back", "forward_back", "leak_side_scatter"],
                            format_func=lambda s: {"leak_forward_back": "Leakage + Forward/Back (conservative)",
                                                   "forward_back": "Forward/Back scatter",
                                                   "leak_side_scatter": "Leakage + Side-scatter"}[s])
        inc_primary = st.checkbox("Include primary beam on this barrier", value=True,
                                  help="Tick for a wall the useful beam can point at; untick for secondary-only barriers.")
        return src.diagnostic_source(cfg["distribution"], N, dP, dS, kvp=kvp,
                                     include_primary=inc_primary, secondary_geometry=geom)

    if b == "ct":
        ndrl = dl.workloads()["saudi_ndrl"]["ct_adult_20_70kg"]
        st.caption("CT is a scatter source. Use Saudi SFDA NDRL DLP values or your scanner's.")
        exam = st.selectbox("Examination", cfg["ct_exam_options"])
        ct_def = dl.scatter()["ct"]["dlp_defaults_mGy_cm"]
        default_dlp = ct_def.get(exam, {}).get("DLP", cfg["default_dlp"]) if isinstance(ct_def.get(exam), dict) else cfg["default_dlp"]
        dlp = st.number_input("DLP per exam (mGy·cm)", 1.0, 100000.0, float(default_dlp), 10.0,
                              help="NCRP 147 Table 5.2 defaults; Saudi NDRL: head 1026, abd/pelvis 706, chest 430.")
        exams = st.number_input("Exams per week", 1, 100000, cfg["default_exams"], 1)
        dS = st.number_input("Distance scanner → barrier (m)", 0.3, 50.0,
                             float(cfg["default_d_secondary"]), 0.1)
        return src.ct_source(dlp, exams, dS)

    if b == "linac":
        mv = st.selectbox("Maximum energy", mc.MV_OPTIONS,
                          index=mc.MV_OPTIONS.index(cfg["default_mv"]))
        W = st.number_input("Workload W (Gy/week at isocentre)", 1.0, 100000.0,
                            float(cfg["default_W"]), 10.0)
        comp = st.radio("Barrier type", ["primary", "secondary"], horizontal=True,
                        format_func=lambda s: "Primary barrier (beam can point here)"
                        if s == "primary" else "Secondary barrier (leakage + scatter)")
        dP = st.number_input("Distance isocentre → barrier, primary (m)", 0.3, 50.0,
                             float(cfg["default_d_primary"]), 0.1)
        dS = st.number_input("Distance isocentre → barrier, secondary (m)", 0.3, 50.0,
                             float(cfg["default_d_secondary"]), 0.1)
        U = st.number_input("Use factor U (primary)", 0.0, 1.0, float(cfg["default_U"]), 0.01)
        imrt = st.number_input("IMRT factor C_I (on leakage)", 1.0, 10.0, 1.0, 0.1)
        ang = st.selectbox("Patient scatter angle (deg)", [10, 20, 30, 45, 60, 90, 135, 150], index=5)
        st_term = src.linac_source(W, mv, dP, dS, U_primary=U, imrt_factor=imrt,
                                   scatter_angle_deg=ang)
        # if user wants a secondary-only barrier, drop the primary component
        if comp == "secondary":
            st_term.components = [c for c in st_term.components if c.name != "primary"]
        return st_term

    if b == "radionuclide":
        nuc = cfg["nuclide"]
        A = st.number_input(f"Activity in room ({nuc}, mCi)", 0.1, 100000.0,
                            float(cfg["default_activity"]), 1.0)
        d = st.number_input("Distance source → barrier (m)", 0.3, 50.0,
                            float(cfg["default_d"]), 0.1)
        hrs = st.number_input("Occupied hours per week behind barrier", 1.0, 168.0,
                              float(cfg["default_hours"]), 1.0)
        return src.radionuclide_point_source(nuc, A, d, hours_per_week=hrs)

    if b == "i131":
        nuc = "I-131"
        A = st.number_input("Administered/retained activity (mCi)", 0.1, 100000.0,
                            float(cfg["default_activity"]), 10.0)
        d = st.number_input("Distance patient → barrier (m)", 0.3, 50.0,
                            float(cfg["default_d"]), 0.1)
        hrs = st.number_input("Occupied hours per week behind barrier", 1.0, 168.0,
                              float(cfg["default_hours"]), 1.0)
        return src.radionuclide_point_source(nuc, A, d, hours_per_week=hrs)

    st.error(f"Unknown builder '{b}'")
    return None


# ---------------------------------------------------------------------------
# barrier builder (uses session_state to add/remove layers)
# ---------------------------------------------------------------------------

def _barrier_builder(source):
    """Interactive layer list -> Barrier. Returns the assembled Barrier."""
    if "layers" not in st.session_state:
        st.session_state.layers = [{"material": "concrete", "thickness": 150.0}]

    all_materials = list(dl.materials()["materials"].keys())

    # show editable rows
    remove_idx = None
    for i, layer in enumerate(st.session_state.layers):
        c1, c2, c3 = st.columns([3, 2, 1])
        layer["material"] = c1.selectbox(
            f"Material #{i+1}", all_materials,
            index=all_materials.index(layer["material"]) if layer["material"] in all_materials else 0,
            key=f"mat_{i}",
        )
        layer["thickness"] = c2.number_input(
            f"Thickness #{i+1} (mm)", 0.0, 100000.0, float(layer["thickness"]), 1.0,
            key=f"thk_{i}",
        )
        if c3.button("✖", key=f"rm_{i}", help="Remove this layer"):
            remove_idx = i
    if remove_idx is not None and len(st.session_state.layers) > 1:
        st.session_state.layers.pop(remove_idx)
        st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("➕ Add layer"):
        st.session_state.layers.append({"material": "lead", "thickness": 1.0})
        st.rerun()
    if c2.button("↻ Reset"):
        st.session_state.layers = [{"material": "concrete", "thickness": 150.0}]
        st.rerun()

    barrier = ba.Barrier()
    for layer in st.session_state.layers:
        barrier.add(layer["material"], layer["thickness"])
    st.caption(f"Barrier: **{barrier.describe()}**  •  "
               f"areal weight ≈ {barrier.areal_density_kg_m2():.0f} kg/m²")
    return barrier


# ---------------------------------------------------------------------------
# results display
# ---------------------------------------------------------------------------

def _show_results(source, barrier, goal, ev):
    st.subheader("Results")

    # headline verdict
    status = "PASS" if ev.verdict.acceptable else "FAIL"
    if ev.verdict.acceptable and ev.verdict.margin_ratio < 1.20:
        status = "MARGINAL"
    styles = {
        "PASS": ("#e8f5e9", "#1b5e20", "&#128994;"),
        "FAIL": ("#ffebee", "#b71c1c", "&#128308;"),
        "MARGINAL": ("#fff8e1", "#8a5a00", "&#128993;"),
    }
    background, color, icon = styles[status]
    st.markdown(
        f"<div style='background:{background};border-left:7px solid {color};padding:14px 18px;"
        f"border-radius:6px;margin:4px 0 14px'>"
        f"<div style='font-size:22px;font-weight:700;color:{color}'>{icon} {status}</div>"
        f"<div style='color:#202124;margin-top:4px'>{ev.verdict.message}</div></div>",
        unsafe_allow_html=True,
    )

    # dose breakdown
    c1, c2, c3 = st.columns(3)
    c1.metric("Transmitted TOTAL", f"{ev.transmitted_total:.3g}", help=ev.unit)
    c2.metric("Scattered + leakage (secondary)", f"{ev.transmitted_secondary:.3g}", help=ev.unit)
    c3.metric("Goal / T", f"{goal.P_weekly/goal.occupancy_T:.3g}", help=ev.unit)

    st.markdown("**Per-component breakdown** (unshielded → transmission B → transmitted):")
    rows = []
    for cr in ev.components:
        rows.append({
            "Component": cr.name,
            f"Unshielded ({ev.unit})": f"{cr.unshielded:.3g}",
            "Transmission B": f"{cr.transmission:.3g}",
            f"Transmitted ({ev.unit})": f"{cr.transmitted:.3g}",
            "How": cr.detail,
        })
    st.dataframe(rows, width="stretch", hide_index=True)

    # required & preferred thicknesses per material
    st.markdown("**Required thickness if built from a SINGLE material** "
                "(to bring total transmitted dose to the goal/T):")
    mats = bm.available_materials(source.components[0].beam) if source.components else []
    # always offer the common structural materials too
    for m in ["lead", "concrete", "steel"]:
        if m not in mats:
            mats.append(m)
    trows = []
    for m in mats:
        try:
            req = solver.required_thickness(source, m, goal)
            pref = solver.preferred_thickness(req, m)
            trows.append({"Material": m, "Required (mm)": f"{req:.2f}",
                          "Preferred (mm)": f"{pref:g}"})
        except Exception:
            pass
    if trows:
        st.dataframe(trows, width="stretch", hide_index=True)

    # equivalents of the current barrier
    if ev.equivalents:
        eq = "  •  ".join(f"{v:.2f} mm {k}" for k, v in ev.equivalents.items())
        st.caption(f"Current barrier is equivalent to: {eq}")

    # transmission vs thickness plot for the dominant material
    _transmission_plot(source)

    # notes & refs
    if ev.notes:
        for n in ev.notes:
            st.caption("ℹ️ " + n)
    st.caption("Sources: " + "; ".join(dl.citations(source.refs)))

    # downloadable audit-trail report (HTML -> print to PDF)
    st.divider()
    c1, c2 = st.columns([2, 1])
    prepared_by = c1.text_input("Report prepared by", value="Abdelaziz Habib")
    facility = c1.text_input("Facility / room (optional)", value="")
    inputs = {
        "Modality": source.modality,
        "Barrier": barrier.describe(),
        "Framework": goal.framework,
        "Area type": goal.area_type,
        "Occupancy T": goal.occupancy_T,
        "Unit": source.unit,
    }
    html_report = rpt.build_html(source=source, barrier=barrier, goal=goal,
                                 evaluation=ev, inputs=inputs,
                                 prepared_by=prepared_by, facility=facility)
    pdf_report = rpt.build_pdf_summary(source=source, barrier=barrier, goal=goal,
                                       evaluation=ev, inputs=inputs,
                                       prepared_by=prepared_by, facility=facility)
    c2.download_button("Download 1-page PDF summary", data=pdf_report,
                       file_name="ShieldLab_ClinicalSummary.pdf", mime="application/pdf")
    c2.download_button("⬇️ Download report (HTML)", data=html_report,
                       file_name="radshield_report.html", mime="text/html",
                       help="Open in a browser and print to PDF for your design file.")


def _transmission_plot(source):
    """Plot total transmitted dose vs thickness for lead and concrete."""
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    import numpy as np

    with st.expander("📈 Transmitted dose vs thickness (lead, concrete)"):
        fig, ax = plt.subplots(figsize=(6, 3.2))
        for m, color in [("lead", "#444"), ("concrete", "#1f77b4")]:
            xs, ys = [], []
            # choose a sensible thickness range from the dominant beam
            xmax = 30 if m == "lead" else 1500
            for x in np.linspace(0, xmax, 60):
                total = 0.0
                ok = True
                for c in source.components:
                    try:
                        total += c.unshielded * bm.transmission_of_layer(c.beam, m, float(x))
                    except Exception:
                        ok = False
                if ok:
                    xs.append(x); ys.append(total)
            if xs:
                ax.semilogy(xs, ys, label=m, color=color)
        ax.set_xlabel("thickness (mm)"); ax.set_ylabel(f"transmitted ({source.unit})")
        ax.legend(); ax.grid(True, which="both", alpha=0.3)
        st.pyplot(fig)


def _show_i131_release(cfg):
    """Extra panel: RG 8.39 released-patient integrated dose."""
    with st.expander("🧍 I-131 released-patient dose (RG 8.39 biokinetics)", expanded=True):
        bk = dl.radionuclides()["i131_biokinetics"]["medical_conditions"]
        c1, c2, c3 = st.columns(3)
        A = c1.number_input("Administered activity (mCi)", 1.0, 100000.0, 200.0, 10.0, key="i131_A")
        cond = c2.selectbox("Condition", list(bk), key="i131_cond")
        d = c3.number_input("Distance to person (m)", 0.3, 10.0, 1.0, 0.1, key="i131_d")
        res = src.i131_released_patient_dose(A, cond, d)
        if res["may_release"]:
            st.success(f"Integrated dose to nearby person ≈ {res['dose_mSv']:.2f} mSv "
                       f"(≤ {res['release_limit_mSv']} mSv → patient may be released).")
        else:
            st.error(f"Integrated dose ≈ {res['dose_mSv']:.2f} mSv exceeds the "
                     f"{res['release_limit_mSv']} mSv release limit.")
        if res["instructions_required"]:
            st.info("Written ALARA instructions to the patient are required (>1 mSv).")
        st.caption("Method: RG 8.39 Eq. B-5 three-component biokinetic model. "
                   + "; ".join(dl.citations(["RG839"])))


# ===========================================================================
# REFERENCES & LIMITATIONS
# ===========================================================================

def references_tab():
    st.subheader("References & method")
    st.markdown(
        "ShieldLab uses the **standard analytical formalism** prescribed by the "
        "references below: Archer broad-beam transmission for diagnostic beams, "
        "tenth-value-layer attenuation for megavoltage and radionuclide sources, "
        "inverse-square geometry, scatter fractions and (for generic materials) "
        "NIST mass attenuation coefficients. Every number in the tool is traceable "
        "to one of these sources and is editable in `radshield/data/`."
    )
    refs = dl.references()
    for key, entry in refs.items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        provided = " ✅ (provided by you)" if entry.get("provided_by_user") else ""
        with st.expander(f"{key}{provided}"):
            st.markdown(f"**{entry.get('citation','')}**")
            if entry.get("role"):
                st.caption(entry["role"])
            if entry.get("url"):
                st.markdown(f"[link]({entry['url']})")


def limitations_tab():
    st.subheader("Scope & limitations (read before relying on a result)")
    st.markdown(
        """
ShieldLab is a **planning / teaching / verification tool**. A qualified
expert must review any design used for construction.

1. **Photons only.** For LINAC energies **above 10 MV**, photoneutrons and
   capture gammas dominate at the maze/door and are **not** modelled here. The
   tool warns you and gives qualitative guidance, but full neutron design is out
   of scope (see IAEA SRS 47, Section 5.6–5.7).
2. **Multi-layer transmission** is the product of per-layer broad-beam factors.
   This is the standard approach and slightly **conservative** for the secondary
   component (it ignores spectral hardening between layers). Put the higher-Z
   layer (e.g. lead) on the source side for best agreement.
3. **CT scatter factor (κ)** and some workload/patient numbers are representative
   defaults — replace them with your scanner's isodose data and your facility's
   actual patient load (all values are editable).
4. **Mammography and angiography** Archer rows carry less-certain exponents
   (flagged in the data); validate against NCRP 147 before relying on them.
5. **Skyshine, ducts, penetrations and door/maze** design are not computed in
   v1.0 (qualitative guidance only).
6. **Saudi NRRC-R-01** sets practice-specific dose constraints rather than fixed
   numeric design goals; the IAEA/NRRC framework uses the internationally common
   6 mSv/y (controlled) and 0.3 mSv/y (uncontrolled) constraints as editable
   defaults consistent with NRRC-R-01 limits.
"""
    )
    st.caption("Validation: the engine reproduces the IAEA SRS 47 Co-60 primary "
               "barrier example (1034 mm vs 1033 mm concrete) and RG 8.39 I-131 "
               "Example 2 (4.53 mSv) — see tests/test_validation.py.")
