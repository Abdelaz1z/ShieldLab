"""
views.py
========
The Streamlit screens. `calculator_tab()` collects inputs, builds the source
term and barrier, runs the engine and shows the results. `references_tab()` and
`limitations_tab()` show the bibliography and the documented caveats.

Kept separate from app.py so the entry point stays tiny and this file can grow.
"""

import streamlit as st

from shieldlab import data_loader as dl
from shieldlab.physics import beams as bm, barriers as ba, sources as src, solver, optimize
from shieldlab.regulatory import limits as reg
from shieldlab.report import report as rpt
from . import modality_config as mc
from .i18n import t, term


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
    builder = cfg["builder"]

    if builder == "diagnostic":
        kvp = st.selectbox(
            t("maximum_tube_potential"),
            mc.KVP_OPTIONS,
            index=(
                mc.KVP_OPTIONS.index(cfg["default_kvp"])
                if cfg["default_kvp"] in mc.KVP_OPTIONS
                else 5
            ),
            key="calc_diag_kvp",
        )
        patients = st.number_input(
            t("patients_week"),
            1,
            100000,
            cfg["default_patients"],
            1,
            key="calc_diag_patients",
        )
        primary_distance = st.number_input(
            t("distance_source_primary"),
            0.3,
            50.0,
            float(cfg["default_d_primary"]),
            0.1,
            key="calc_diag_primary_distance",
        )
        secondary_distance = st.number_input(
            t("distance_patient_secondary"),
            0.3,
            50.0,
            float(cfg["default_d_secondary"]),
            0.1,
            key="calc_diag_secondary_distance",
        )
        geometry_labels = {
            "leak_forward_back": "Leakage + Forward/Back (conservative)",
            "forward_back": "Forward/Back scatter",
            "leak_side_scatter": "Leakage + Side-scatter",
        }
        localized_geometry_labels = {
            geometry: term(label)
            for geometry, label in geometry_labels.items()
        }
        secondary_geometry = st.selectbox(
            t("secondary_geometry"),
            list(geometry_labels),
            format_func=lambda geometry: localized_geometry_labels[geometry],
            key="calc_diag_geometry",
        )
        include_primary = st.checkbox(
            t("include_primary"),
            value=True,
            help=t("include_primary_help"),
            key="calc_diag_include_primary",
        )
        return src.diagnostic_source(
            cfg["distribution"],
            patients,
            primary_distance,
            secondary_distance,
            kvp=kvp,
            include_primary=include_primary,
            secondary_geometry=secondary_geometry,
        )

    if builder == "ct":
        return _build_ct_source(cfg)

    if builder == "linac":
        energy = st.selectbox(
            t("maximum_energy"),
            mc.MV_OPTIONS,
            index=mc.MV_OPTIONS.index(cfg["default_mv"]),
            key="calc_linac_energy",
        )
        workload = st.number_input(
            t("workload_isocentre"),
            1.0,
            100000.0,
            float(cfg["default_W"]),
            10.0,
            key="calc_linac_workload",
        )
        barrier_labels = {
            "primary": "Primary barrier (beam can point here)",
            "secondary": "Secondary barrier (leakage + scatter)",
        }
        localized_barrier_labels = {
            barrier: term(label)
            for barrier, label in barrier_labels.items()
        }
        barrier_type = st.radio(
            t("barrier_type"),
            list(barrier_labels),
            horizontal=True,
            format_func=lambda barrier: localized_barrier_labels[barrier],
            key="calc_linac_barrier_type",
        )
        primary_distance = st.number_input(
            t("distance_isocentre_primary"),
            0.3,
            50.0,
            float(cfg["default_d_primary"]),
            0.1,
            key="calc_linac_primary_distance",
        )
        secondary_distance = st.number_input(
            t("distance_isocentre_secondary"),
            0.3,
            50.0,
            float(cfg["default_d_secondary"]),
            0.1,
            key="calc_linac_secondary_distance",
        )
        use_factor = st.number_input(
            t("use_factor"),
            0.0,
            1.0,
            float(cfg["default_U"]),
            0.01,
            key="calc_linac_use_factor",
        )
        imrt_factor = st.number_input(
            t("imrt_factor"),
            1.0,
            10.0,
            1.0,
            0.1,
            key="calc_linac_imrt_factor",
        )
        scatter_angle = st.selectbox(
            t("scatter_angle"),
            [10, 20, 30, 45, 60, 90, 135, 150],
            index=5,
            key="calc_linac_scatter_angle",
        )
        source_term = src.linac_source(
            workload,
            energy,
            primary_distance,
            secondary_distance,
            U_primary=use_factor,
            imrt_factor=imrt_factor,
            scatter_angle_deg=scatter_angle,
        )
        if barrier_type == "secondary":
            source_term.components = [
                component
                for component in source_term.components
                if component.name != "primary"
            ]
        return source_term

    if builder == "radionuclide":
        nuclide = cfg["nuclide"]
        activity = st.number_input(
            t("activity_room", nuclide=nuclide),
            0.1,
            100000.0,
            float(cfg["default_activity"]),
            1.0,
            key=f"calc_{mod_key}_activity",
        )
        distance = st.number_input(
            t("distance_source_barrier"),
            0.3,
            50.0,
            float(cfg["default_d"]),
            0.1,
            key=f"calc_{mod_key}_distance",
        )
        occupied_hours = st.number_input(
            t("occupied_hours"),
            1.0,
            168.0,
            float(cfg["default_hours"]),
            1.0,
            key=f"calc_{mod_key}_hours",
        )
        return src.radionuclide_point_source(
            nuclide,
            activity,
            distance,
            hours_per_week=occupied_hours,
        )

    if builder == "i131":
        activity = st.number_input(
            t("retained_activity"),
            0.1,
            100000.0,
            float(cfg["default_activity"]),
            10.0,
            key="calc_i131_retained_activity",
        )
        distance = st.number_input(
            t("distance_patient_barrier"),
            0.3,
            50.0,
            float(cfg["default_d"]),
            0.1,
            key="calc_i131_barrier_distance",
        )
        occupied_hours = st.number_input(
            t("occupied_hours"),
            1.0,
            168.0,
            float(cfg["default_hours"]),
            1.0,
            key="calc_i131_occupied_hours",
        )
        return src.radionuclide_point_source(
            "I-131",
            activity,
            distance,
            hours_per_week=occupied_hours,
        )

    st.error(t("unknown_builder", builder=builder))
    return None


def _build_ct_source(cfg):
    """Collect one or more exam-specific CT workloads."""
    st.caption(t("ct_intro"))

    def exam_label(exam_type: str) -> str:
        localized_label = term(exam_type)
        return (
            localized_label
            if localized_label != exam_type
            else exam_type.replace("_", " ").title()
        )

    exam_labels = {
        exam_type: exam_label(exam_type)
        for exam_type in cfg["ct_exam_options"]
    }
    exam_types = st.multiselect(
        t("examinations"),
        cfg["ct_exam_options"],
        default=[cfg["ct_exam_options"][0]],
        format_func=lambda exam_type: exam_labels[exam_type],
        key="calc_ct_exam_types",
    )
    if not exam_types:
        st.error(t("ct_select_error"))
        st.stop()

    ct_defaults = dl.scatter()["ct"]["dlp_defaults_mGy_cm"]
    workloads = []
    for exam_type in exam_types:
        exam_default = ct_defaults.get(exam_type, {})
        default_dlp = exam_default.get("DLP", cfg["default_dlp"])
        dlp_col, exams_col = st.columns(2)
        dlp = dlp_col.number_input(
            t("dlp_exam", exam=exam_labels[exam_type]),
            1.0,
            100000.0,
            float(default_dlp),
            10.0,
            key=f"ct_dlp_{exam_type}",
            help=t("dlp_help"),
        )
        exams = exams_col.number_input(
            t("exams_week", exam=exam_labels[exam_type]),
            1,
            100000,
            cfg["default_exams"],
            1,
            key=f"ct_exams_{exam_type}",
        )
        workloads.append(src.CTExamWorkload(exam_type, dlp, exams))

    distance_col, kvp_col = st.columns(2)
    distance = distance_col.number_input(
        t("distance_scanner_barrier"),
        0.3,
        50.0,
        float(cfg["default_d_secondary"]),
        0.1,
        key="calc_ct_distance",
    )
    # Selects the broad-beam secondary transmission dataset for the barrier; CT
    # scatter used to be shielded with a generic 70 keV narrow-beam model.
    kvp = kvp_col.selectbox(
        t("ct_kvp"),
        [80, 100, 120, 140],
        index=2,
        help=t("ct_kvp_help"),
        key="calc_ct_kvp",
    )
    return src.ct_source(workloads, distance, kvp)


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

    # cost / material optimiser: the cheapest single-material wall that meets the goal,
    # with the weight and space trade-offs a designer actually decides on.
    st.markdown("**💰 Cost & material optimiser** — cheapest single-material wall that meets "
                "goal/T, with the weight and space trade-offs:")
    options = optimize.rank_options(source, goal)
    head = optimize.headline(options)
    if head:
        st.success(head)
    orows = []
    for o in options:
        best = "  ".join(t for t, on in [("💰 cheapest", o.is_cheapest),
                                         ("🪶 lightest", o.is_lightest),
                                         ("📏 thinnest", o.is_thinnest)] if on)
        if o.already_met:
            orows.append({"Material": o.label, "Wall thickness": "not needed",
                          "Installed $/m²": "—", "Weight kg/m²": "—",
                          "Best for": "goal already met"})
        elif o.feasible:
            orows.append({"Material": o.label, "Wall thickness": f"{o.preferred_mm:g} mm",
                          "Installed $/m²": f"${o.cost_per_m2_usd:,.0f}",
                          "Weight kg/m²": f"{o.weight_per_m2_kg:,.0f}", "Best for": best})
        else:
            orows.append({"Material": o.label,
                          "Wall thickness": f">{o.preferred_mm:g} mm (impractical)",
                          "Installed $/m²": "—", "Weight kg/m²": "—",
                          "Best for": "cannot meet goal"})
    if orows:
        st.dataframe(orows, width="stretch", hide_index=True)
        st.caption("Installed cost = representative 2026 estimate (materials + labour) × required "
                   "thickness, editable in `shieldlab/data/materials_cost.json`. **Relative comparison "
                   "only** — confirm with local quotations and a structural engineer for the areal load.")

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
    prepared_by = c1.text_input("Report prepared by", value="")
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
                       file_name="shieldlab_report.html", mime="text/html",
                       help="Open in a browser and print to PDF for your design file.")


def _transmission_plot(source):
    """Plot total transmitted dose vs thickness for lead and concrete."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    import numpy as np

    with st.expander(t("transmission_plot")):
        figure, axes = plt.subplots(figsize=(6, 3.2))
        for material, color in [("lead", "#444"), ("concrete", "#1f77b4")]:
            thicknesses, transmitted_doses = [], []
            maximum_thickness = 30 if material == "lead" else 1500
            for thickness in np.linspace(0, maximum_thickness, 60):
                transmitted_total = 0.0
                material_supported = True
                for component in source.components:
                    try:
                        transmission = bm.transmission_of_layer(
                            component.beam,
                            material,
                            float(thickness),
                        )
                        transmitted_total += component.unshielded * transmission
                    except ValueError:
                        material_supported = False
                if material_supported:
                    thicknesses.append(thickness)
                    transmitted_doses.append(transmitted_total)
            if thicknesses:
                axes.semilogy(
                    thicknesses,
                    transmitted_doses,
                    label=term(material),
                    color=color,
                )
        axes.set_xlabel(t("thickness_mm"))
        axes.set_ylabel(t("transmitted_unit", unit=source.unit))
        axes.legend()
        axes.grid(True, which="both", alpha=0.3)
        st.pyplot(figure)


def _show_i131_release(_cfg):
    """Extra panel: RG 8.39 released-patient integrated dose."""
    with st.expander(t("i131_release_title"), expanded=True):
        biokinetics = dl.radionuclides()["i131_biokinetics"]["medical_conditions"]
        activity_col, condition_col, distance_col = st.columns(3)
        activity = activity_col.number_input(
            t("administered_activity"),
            1.0,
            100000.0,
            200.0,
            10.0,
            key="i131_A",
        )
        condition_labels = {
            condition_key: term(condition_key)
            for condition_key in biokinetics
        }
        condition = condition_col.selectbox(
            t("condition"),
            list(biokinetics),
            format_func=lambda condition_key: condition_labels[condition_key],
            key="i131_cond",
        )
        distance = distance_col.number_input(
            t("distance_person"),
            0.3,
            10.0,
            1.0,
            0.1,
            key="i131_d",
        )
        release_assessment = src.i131_released_patient_dose(
            activity,
            condition,
            distance,
        )
        message_parameters = {
            "dose": release_assessment["dose_mSv"],
            "limit": release_assessment["release_limit_mSv"],
        }
        if release_assessment["may_release"]:
            st.success(t("release_pass", **message_parameters))
        else:
            st.error(t("release_fail", **message_parameters))
        if release_assessment["instructions_required"]:
            st.info(t("alara_required"))
        st.caption(
            t(
                "i131_method",
                sources="; ".join(dl.citations(["RG839"])),
            )
        )


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
        "to one of these sources and is editable in `shieldlab/data/`."
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
3. **CT scatter normalization** uses NCRP 147's separate head and body factors.
   Replace them with scanner isodose data when available and enter the complete
   DLP workload, including contrast or repeated acquisitions; no automatic 1.4
   multiplier is applied.
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




