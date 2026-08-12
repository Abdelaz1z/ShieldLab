"""Decision-first results, material options, and reports for Barrier Assessment."""

from __future__ import annotations

from dataclasses import dataclass
from unicodedata import name as unicode_name

import streamlit as st

from shieldlab import data_loader as dl
from shieldlab.physics import optimize
from shieldlab.report import report as report_builder

from . import product_shell as ds
from . import views as legacy
from .i18n import is_arabic, t, term


@dataclass(frozen=True)
class CalculatorAssessment:
    source: object
    barrier: object
    design_goal: object
    evaluation: object


def _decision_status(assessment: CalculatorAssessment) -> str:
    if not assessment.evaluation.verdict.acceptable:
        return "FAIL"
    if assessment.evaluation.verdict.margin_ratio < 1.20:
        return "REVIEW"
    return "PASS"


def _render_decision(assessment: CalculatorAssessment) -> None:
    decision_status = _decision_status(assessment)
    decision_headlines = {
        "PASS": t("decision_pass"),
        "FAIL": t("decision_fail"),
        "REVIEW": t("decision_review"),
    }
    unit_note = (
        t("ncrp_unit_short")
        if assessment.design_goal.unit != assessment.evaluation.unit
        else ""
    )
    decision_basis = t("decision_basis", unit_note=unit_note)
    technical_detail = assessment.evaluation.verdict.message
    if is_arabic():
        technical_detail = f"{t('calculation_notes')} (English): {technical_detail}"
        decision_detail, decision_meta = decision_basis, technical_detail
    else:
        decision_detail, decision_meta = technical_detail, decision_basis
    ds.status_card(
        decision_status,
        decision_headlines[decision_status],
        decision_detail,
        decision_meta,
    )


def _render_metrics(assessment: CalculatorAssessment) -> None:
    evaluation = assessment.evaluation
    applied_limit = assessment.design_goal.P_weekly / assessment.design_goal.occupancy_T
    secondary_share = (
        100.0 * evaluation.transmitted_secondary / evaluation.transmitted_total
        if evaluation.transmitted_total > 0 else 0.0
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric(
        t("transmitted_total"),
        f"{evaluation.transmitted_total:.3g} {evaluation.unit}",
    )
    metric_cols[1].metric(
        t("applied_limit"),
        f"{applied_limit:.3g} {assessment.design_goal.unit}",
    )
    metric_cols[2].metric(
        t("safety_margin"),
        f"×{evaluation.verdict.margin_ratio:.3g}",
    )
    metric_cols[3].metric(t("secondary_contribution"), f"{secondary_share:.1f}%")
    if assessment.design_goal.unit != evaluation.unit:
        ds.assurance_note(
            t(
                "photon_unit_note",
                dose_unit=evaluation.unit,
                goal_unit=assessment.design_goal.unit,
            )
        )


def _component_rows(assessment: CalculatorAssessment) -> list[dict]:
    evaluation = assessment.evaluation
    return [
        {
            t("column_component"): term(component.name),
            t("column_unshielded"): f"{component.unshielded:.3g} {evaluation.unit}",
            t("column_transmission"): f"{component.transmission:.3g}",
            t("column_transmitted"): f"{component.transmitted:.3g} {evaluation.unit}",
            t("column_calculation_basis"): term(component.detail),
        }
        for component in evaluation.components
    ]


def _equivalence_note(assessment: CalculatorAssessment) -> None:
    if not assessment.evaluation.equivalents:
        return
    equivalence_text = " · ".join(
        f"{thickness:.2f} mm {term(material)}"
        for material, thickness in assessment.evaluation.equivalents.items()
    )
    ds.assurance_note(t("current_equivalence", equivalence=equivalence_text))


def _render_evidence(assessment: CalculatorAssessment) -> None:
    st.markdown(f"### {t('component_breakdown')}")
    st.dataframe(_component_rows(assessment), width="stretch", hide_index=True)
    _equivalence_note(assessment)
    legacy._transmission_plot(assessment.source)
    if assessment.evaluation.notes:
        with st.expander(t("calculation_notes"), expanded=False):
            for calculation_note in assessment.evaluation.notes:
                st.info(term(calculation_note))
    st.caption(t("sources", sources="; ".join(dl.citations(assessment.source.refs))))


def _best_for(option) -> str:
    return ", ".join(
        label
        for label, enabled in (
            (t("lowest_cost"), option.is_cheapest),
            (t("lowest_load"), option.is_lightest),
            (t("smallest_footprint"), option.is_thinnest),
        )
        if enabled
    )


def _material_option_row(option) -> dict:
    if option.already_met:
        return {
            t("column_material"): term(option.label),
            t("column_required_build"): t("not_required"),
            t("column_installed_cost"): "—",
            t("column_areal_load"): "—",
            t("column_best_for"): t("goal_already_met"),
        }
    if not option.feasible:
        return {
            t("column_material"): term(option.label),
            t("column_required_build"): (
                f">{option.preferred_mm:g} mm · {t('impractical')}"
            ),
            t("column_installed_cost"): "—",
            t("column_areal_load"): "—",
            t("column_best_for"): t("cannot_meet_goal"),
        }
    return {
        t("column_material"): term(option.label),
        t("column_required_build"): f"{option.preferred_mm:g} mm",
        t("column_installed_cost"): f"${option.cost_per_m2_usd:,.0f}",
        t("column_areal_load"): f"{option.weight_per_m2_kg:,.0f} kg/m²",
        t("column_best_for"): _best_for(option) or "—",
    }


def _render_material_options(assessment: CalculatorAssessment) -> None:
    st.markdown(f"### {t('cost_space_load')}")
    st.caption(t("material_options_intro"))
    ranked_options = optimize.rank_options(assessment.source, assessment.design_goal)
    options_headline = optimize.headline(ranked_options)
    if options_headline:
        headline = (
            f"{t('calculation_notes')} (English): {options_headline}"
            if is_arabic()
            else options_headline
        )
        st.info(headline)
    st.dataframe(
        [_material_option_row(option) for option in ranked_options],
        width="stretch",
        hide_index=True,
    )
    st.caption(t("cost_assumption"))


def _report_identity() -> tuple[str, str]:
    prepared_by = st.text_input(
        t("prepared_by"),
        value="",
        placeholder=t("prepared_placeholder"),
        autocomplete="off",
        key="calc_report_prepared_by",
    )
    facility = st.text_input(
        t("facility_room"),
        value="",
        placeholder=t("facility_room_placeholder"),
        autocomplete="off",
        key="calc_report_facility",
    )
    return prepared_by, facility


def _report_inputs(assessment: CalculatorAssessment) -> dict:
    return {
        "Modality": assessment.source.modality,
        "Barrier": assessment.barrier.describe(),
        "Framework": assessment.design_goal.framework,
        "Area type": assessment.design_goal.area_type,
        "Occupancy T": assessment.design_goal.occupancy_T,
        "Unit": assessment.source.unit,
    }


def _contains_arabic(text: str) -> bool:
    return any("ARABIC" in unicode_name(character, "") for character in text)


def _report_files(
    assessment: CalculatorAssessment,
    prepared_by: str,
    facility: str,
) -> tuple[str, bytes | None]:
    report_inputs = _report_inputs(assessment)
    html_report = report_builder.build_html(
        source=assessment.source,
        barrier=assessment.barrier,
        goal=assessment.design_goal,
        evaluation=assessment.evaluation,
        inputs=report_inputs,
        prepared_by=prepared_by,
        facility=facility,
    )
    pdf_report = None
    if not any(_contains_arabic(identifier) for identifier in (prepared_by, facility)):
        pdf_report = report_builder.build_pdf_summary(
            source=assessment.source,
            barrier=assessment.barrier,
            goal=assessment.design_goal,
            evaluation=assessment.evaluation,
            inputs=report_inputs,
            prepared_by=prepared_by,
            facility=facility,
        )
    return html_report, pdf_report


def _report_downloads(html_report: str, pdf_report: bytes | None) -> None:
    if pdf_report is not None:
        st.download_button(
            t("download_clinical_pdf"),
            data=pdf_report,
            key="calc_download_pdf",
            file_name="ShieldLab_ClinicalSummary.pdf",
            mime="application/pdf",
            type="primary",
            width="stretch",
            on_click="ignore",
        )
    st.download_button(
        t("download_audit_html"),
        data=html_report,
        key="calc_download_html",
        file_name="ShieldLab_AssessmentReport.html",
        mime="text/html",
        help=t("download_html_help"),
        type="primary" if pdf_report is None else "secondary",
        width="stretch",
        on_click="ignore",
    )


def _render_reports(assessment: CalculatorAssessment) -> None:
    st.markdown(f"### {t('assessment_report')}")
    st.caption(t("report_intro"))
    if is_arabic():
        st.info(t("exports_english_note"))
    identity_col, action_col = st.columns([1.3, 0.9], gap="large")
    with identity_col:
        prepared_by, facility = _report_identity()
    with action_col:
        prepare_report = st.button(
            t("prepare_report"),
            type="primary",
            width="stretch",
            help=t("prepare_report_help"),
            key="calc_prepare_report",
        )
        if not prepare_report:
            st.caption(t("report_deferred"))
    if _contains_arabic(prepared_by) or _contains_arabic(facility):
        st.warning(t("pdf_identifiers_english_warning"))
    if not prepare_report:
        return
    with st.spinner(t("preparing_reports")):
        html_report, pdf_report = _report_files(assessment, prepared_by, facility)
    with action_col:
        _report_downloads(html_report, pdf_report)


def render(assessment: CalculatorAssessment) -> None:
    # The decision receives its own visual surface; supporting proof follows below.
    with st.container(border=True, key="sl_decision_panel"):
        st.markdown(f"## {t('compliance_decision')}")
        _render_decision(assessment)
        _render_metrics(assessment)

    with st.container(key="sl_result_tabs"):
        evidence_tab, options_tab, report_tab = st.tabs(
            [t("tab_evidence"), t("tab_materials"), t("tab_report")]
        )
    with evidence_tab:
        _render_evidence(assessment)
    with options_tab:
        _render_material_options(assessment)
    with report_tab:
        _render_reports(assessment)




