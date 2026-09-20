"""Per-modality source-term input panels for the barrier assessment workspace.

Everything here collects operator input and returns a `SourceTerm` (or renders the
I-131 released-patient panel, which is a patient-as-source calculation rather than a
barrier). Extracted from the former ui/views.py: the commercial shell replaced that
module's screens, but four of its functions were still on the live path while the
rest -- roughly 400 lines including a second, diverging copy of the Limitations text
-- had become unreachable.
"""

from __future__ import annotations

import streamlit as st

from shieldlab import data_loader as dl
from shieldlab.physics import beams as bm
from shieldlab.physics import sources as src
from . import modality_config as mc
from .i18n import t, term


def build_source(mod_key, cfg):
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
        return build_ct_source(cfg)

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


def build_ct_source(cfg):
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


def transmission_plot(source):
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


def show_i131_release(_cfg):
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
