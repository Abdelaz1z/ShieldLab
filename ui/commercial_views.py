"""Commercial single-barrier workspace and supporting method views."""

from __future__ import annotations

import streamlit as st

from shieldlab import data_loader as dl
from shieldlab.physics import solver

from . import calculator_results, calculator_setup
from . import product_shell as ds
from . import source_inputs
from .i18n import is_arabic, t, term


def _label_english_technical_detail() -> None:
    if is_arabic():
        st.caption(f"{t('calculation_notes')} · English")


def calculator_tab() -> None:
    setup = calculator_setup.sidebar_setup()
    ds.context_strip(setup.context_items())

    source_col, barrier_col = st.columns([1.08, 0.92], gap="large")
    with source_col:
        with st.container(border=True, key="sl_source_inputs"):
            ds.section_header(
                "03",
                t("source_workload"),
                term(setup.modality_config["label"]),
            )
            source = source_inputs.build_source(setup.modality_key, setup.modality_config)
    with barrier_col:
        with st.container(border=True, key="sl_barrier_builder"):
            ds.section_header(
                "04",
                t("barrier_assembly"),
                t("barrier_assembly_help"),
            )
            # The source is passed in so the material list can be restricted to
            # what this beam actually has transmission data for.
            barrier = calculator_setup.barrier_builder(source)

    if source is None:
        return
    if setup.modality_config["builder"] == "i131":
        source_inputs.show_i131_release(setup.modality_config)

    ds.live_note(t("live_recalculate"))
    try:
        evaluation = solver.evaluate(source, barrier, setup.design_goal)
    except ValueError as exc:
        # A data gap is a missing dataset, not a crash: say which combination has
        # no data and leave the rest of the workspace intact.
        st.error(f"**{t('barrier_not_evaluated')}** — {t('barrier_not_evaluated_help', reason=exc)}")
        return
    calculator_results.render(
        calculator_results.CalculatorAssessment(
            source,
            barrier,
            setup.design_goal,
            evaluation,
        )
    )


def _method_intro() -> None:
    with st.container(border=True):
        ds.section_header("A", t("method_library"), t("method_library_help"))
        st.markdown(t("method_intro"))
        st.caption(t("method_data_note"))


def _reference_entries() -> None:
    for reference_key, reference in dl.references().items():
        if reference_key.startswith("_") or not isinstance(reference, dict):
            continue
        local_state = f" · {t('local_source')}" if reference.get("provided_by_user") else ""
        with st.expander(f"{reference_key}{local_state}"):
            st.markdown(f"**{reference.get('citation', '')}**")
            if reference.get("role"):
                _label_english_technical_detail()
                st.write(term(reference["role"]))
            if reference.get("publisher"):
                # The standards are not redistributed with the app, so say where
                # a copy is obtained rather than implying one ships with it.
                st.caption(f"{t('obtain_from')}: {reference['publisher']}")
            if reference.get("url"):
                st.markdown(f"[{t('open_reference')}]({reference['url']})")


def references_tab() -> None:
    _method_intro()
    _reference_entries()


def _limitation_columns() -> None:
    scope_col, assumptions_col = st.columns(2, gap="large")
    with scope_col:
        with st.container(border=True):
            ds.section_header("01", t("independent_assessment"))
            st.markdown(
                "\n".join(
                    f"- {t(message_key)}"
                    for message_key in (
                        "scope_photons",
                        "scope_streaming",
                        "scope_construction",
                    )
                )
            )
    with assumptions_col:
        with st.container(border=True):
            ds.section_header("02", t("model_assumptions"))
            st.markdown(
                "\n".join(
                    f"- {t(message_key)}"
                    for message_key in (
                        "assumption_multilayer",
                        "assumption_ct",
                        "assumption_archer",
                    )
                )
            )


def _workspace_capability() -> None:
    with st.container(border=True):
        ds.section_header("03", t("workspace_capability"))
        st.markdown(t("workspace_capability_body"))


def _regulatory_validation() -> None:
    with st.container(border=True):
        ds.section_header("04", t("regulatory_validation"))
        st.markdown(t("regulatory_validation_body"))
        st.success(t("validation_success"))


def limitations_tab() -> None:
    st.warning(t("qualified_signoff_warning"))
    _limitation_columns()
    _workspace_capability()
    _regulatory_validation()



