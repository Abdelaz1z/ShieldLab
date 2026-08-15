"""Room Designer engine comparison, safety hierarchy, costing, and exports."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from shieldlab.room import cost as room_cost
from shieldlab.room import diagram, engines, field_surrogate, report_regulatory, report_room
from shieldlab.room.decision_support import (
    explain_failures,
    shap_failure_explanations,
    summarize_results,
)
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine
from shieldlab.room.model import WALL_NAMES, RoomDesign

from . import i18n
from . import product_shell as ds


@dataclass(frozen=True)
class RoomAssessment:
    design: RoomDesign
    mode: str
    analytical_results: list
    surrogate_results: list | None
    decision_results: list
    surrogate_engine: SurrogateEngine

    @property
    def review_reasons(self) -> list[str]:
        return _assessment_review_reasons(self)

    @property
    def status(self) -> str:
        summary_status = summarize_results(self.decision_results)["status"]
        if summary_status == "FAIL":
            return "FAIL"
        if summary_status == "PASS" and not self.review_reasons:
            return "PASS"
        return "REVIEW"


def build_assessment(
    room_design: RoomDesign,
    assessment_mode: str,
    surrogate_engine: SurrogateEngine,
) -> RoomAssessment:
    analytical_results = AnalyticalEngine(room_design).evaluate_all(assessment_mode)
    surrogate_results = (
        surrogate_engine.evaluate_all(assessment_mode, analytical_results)
        if surrogate_engine.available() else None
    )
    decision_results = surrogate_results or analytical_results
    return RoomAssessment(
        room_design,
        assessment_mode,
        analytical_results,
        surrogate_results,
        decision_results,
        surrogate_engine,
    )



def _format_transmission(transmission) -> str:
    return f"{transmission:.2e}" if isinstance(transmission, (int, float)) else "—"


def _display_path_label(label: str) -> str:
    if not label.startswith("Wall "):
        return i18n.term(label)
    wall_text, separator, opening_text = label.partition("·")
    wall_tokens = wall_text.split()
    wall_id = wall_tokens[1] if len(wall_tokens) > 1 else wall_text
    translated_wall = i18n.t(
        "wall_label",
        wall=wall_id,
        name=i18n.term(WALL_NAMES.get(wall_id, wall_id)),
    )
    if not separator:
        return translated_wall
    return f"{translated_wall} · {i18n.term(opening_text.strip())}"


def _assurance_for(barrier_result) -> tuple[str, str]:
    engine_name = (barrier_result.engine or "").lower()
    if barrier_result.geometry_bias:
        return i18n.t("surrogate_point"), i18n.t("potential_underprediction")
    if "deep tail" in engine_name:
        return i18n.t("surrogate_point"), i18n.t("interval_withdrawn_detail")
    if "ood fallback" in engine_name:
        return i18n.t("analytical_fallback"), i18n.t("surrogate_outside_domain")
    if "needs mc" in engine_name:
        return i18n.t("not_evaluated_basis"), i18n.t("detailed_mc_required")
    if "corner" in engine_name:
        return i18n.t("corner_surrogate"), i18n.t("in_domain_interval")
    if "surrogate" in engine_name:
        interval_state = (
            i18n.t("interval_available")
            if barrier_result.ci_low is not None
            else i18n.t("point_estimate_only")
        )
        return i18n.t("mc_surrogate"), i18n.t(
            "validated_domain_state",
            state=interval_state,
        )
    return i18n.t("analytical"), i18n.t("published_method")

def _uncertainty_crosses_limit(barrier_result) -> bool:
    if (
        barrier_result.ci_high is None
        or not barrier_result.B_achieved
        or barrier_result.dose_mSv_wk is None
        or barrier_result.goal_over_T is None
    ):
        return False
    upper_dose = (
        barrier_result.dose_mSv_wk
        * barrier_result.ci_high
        / barrier_result.B_achieved
    )
    return upper_dose > barrier_result.goal_over_T



def row_status_for(barrier_result) -> tuple[str, str, str]:
    if barrier_result.passes is False:
        return "fail", "×", i18n.t("fail")
    engine_name = (barrier_result.engine or "").lower()
    incomplete_assurance = (
        barrier_result.passes is None
        or barrier_result.geometry_bias
        or "deep tail" in engine_name
    )
    narrow_margin = barrier_result.margin is not None and barrier_result.margin < 1.20
    if incomplete_assurance or narrow_margin or _uncertainty_crosses_limit(barrier_result):
        return "review", "!", i18n.t("review")
    return "pass", "✓", i18n.t("pass")


def _interval_text(barrier_result) -> str:
    if barrier_result.ci_low is not None and barrier_result.ci_high is not None:
        return f"{barrier_result.ci_low:.1e} – {barrier_result.ci_high:.1e}"
    if "deep tail" in (barrier_result.engine or "").lower():
        return i18n.term("Withdrawn")
    return "—"


def _wall_build_text(
    room_design: RoomDesign,
    analytical_result,
    assessment_mode: str,
) -> tuple[str, str]:
    wall_id = analytical_result.label.split()[1]
    wall = room_design.wall(wall_id)
    if assessment_mode == "design":
        suggested = analytical_result.suggested_thickness_mm
        material = i18n.term(
            (analytical_result.material or wall.material1).replace("_", " ").title()
        )
        if suggested is None:
            return i18n.t("not_determined"), i18n.t("suggested_unavailable")
        return f"{suggested:g} mm {material}", i18n.t("suggested_build")

    layers = [f"{wall.thickness1_mm:g} mm {i18n.term(wall.material1)}"]
    if wall.material2 and wall.thickness2_mm > 0:
        layers.append(f"{wall.thickness2_mm:g} mm {i18n.term(wall.material2)}")
    opening_kind = analytical_result.label.partition("·")[2].strip()
    if not opening_kind:
        return " + ".join(layers), i18n.t("declared_build")

    matching_openings = [
        opening for opening in wall.openings if opening.kind == opening_kind
    ]
    if opening_kind in ("door", "window"):
        protection = ", ".join(
            f"{opening.lead_equiv_mm:g} mm Pb-eq" for opening in matching_openings
        )
    elif opening_kind == "duct":
        protection = ", ".join(
            i18n.t("radius_value", radius=opening.radius_mm)
            for opening in matching_openings
        )
    elif opening_kind == "maze":
        protection = ", ".join(
            i18n.t(
                "return_value",
                thickness=opening.ret_thickness_mm,
                material=i18n.term(opening.ret_material),
            )
            for opening in matching_openings
        )
    else:
        protection = ""
    detail = i18n.t(
        "opening_protection",
        kind=i18n.term(opening_kind),
        protection=protection or i18n.t("not_declared"),
    )
    return " + ".join(layers), detail


def _dose_goal_text(barrier_result, framework: str) -> tuple[str, str]:
    if barrier_result.dose_mSv_wk is None or barrier_result.goal_over_T is None:
        return i18n.t("dose_not_evaluated"), i18n.t("dose_limit_unavailable")
    dose = barrier_result.dose_mSv_wk
    goal = barrier_result.goal_over_T
    if framework == "NCRP":
        return (
            f"{dose:.3g} mSv/week",
            i18n.t("photon_goal_detail", dose=dose, goal=goal),
        )
    return f"{dose:.3g} mSv/week", i18n.t("limit_detail", goal=goal)

def _barrier_row_html(
    room_design: RoomDesign,
    analytical_result,
    decision_result,
    assessment_mode: str,
) -> str:
    basis, assurance = _assurance_for(decision_result)
    status_class, status_symbol, status_label = row_status_for(decision_result)
    build, build_detail = _wall_build_text(
        room_design,
        analytical_result,
        assessment_mode,
    )
    dose, dose_detail = _dose_goal_text(decision_result, room_design.framework)
    margin = f"×{decision_result.margin:.2f}" if decision_result.margin is not None else "—"
    return (
        "<tr>"
        f'<th scope="row">{escape(_display_path_label(analytical_result.label))}</th>'
        f'<td>{escape(build)}<span class="subtle">{escape(build_detail)}</span></td>'
        f'<td>{escape(dose)}<span class="subtle">{escape(dose_detail)}</span></td>'
        f'<td class="num">{escape(_format_transmission(analytical_result.B_achieved))}</td>'
        f'<td class="num">{escape(_format_transmission(decision_result.B_achieved))}</td>'
        f'<td class="num">{escape(_interval_text(decision_result))}</td>'
        f'<td>{escape(basis)}<span class="subtle">{escape(assurance)}</span></td>'
        f'<td><span class="sl-table-status {status_class}">{status_symbol} {status_label}</span></td>'
        f'<td class="num">{escape(margin)}</td>'
        "</tr>"
    )


def _decision_result_at(
    assessment: RoomAssessment,
    result_index: int,
    analytical_result,
):
    if assessment.surrogate_results and result_index < len(assessment.surrogate_results):
        surrogate_result = assessment.surrogate_results[result_index]
        if surrogate_result.label == analytical_result.label:
            return surrogate_result
    return analytical_result



def results_table_html(assessment: RoomAssessment) -> str:
    rows = "".join(
        _barrier_row_html(
            assessment.design,
            analytical_result,
            _decision_result_at(assessment, result_index, analytical_result),
            assessment.mode,
        )
        for result_index, analytical_result in enumerate(assessment.analytical_results)
    )
    headers = (
        i18n.t("column_barrier"),
        i18n.t("column_build"),
        i18n.t("column_dose_limit"),
        i18n.t("column_analytical_b"),
        i18n.t("column_decision_b"),
        i18n.t("column_range"),
        i18n.t("column_basis"),
        i18n.t("column_status"),
        i18n.t("column_margin"),
    )
    header_html = "".join(
        f'<th scope="col">{escape(header)}</th>' for header in headers
    )
    return (
        f'<div class="sl-table-scroll" role="region" {i18n.html_attributes()} '
        f'aria-label="{escape(i18n.t("barrier_table_aria"))}" tabindex="0">'
        '<table class="sl-results-table">'
        f'<caption>{escape(i18n.t("barrier_table_caption"))}</caption>'
        f'<thead><tr>{header_html}</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )

def _solid_wall_transmissions(assessment: RoomAssessment) -> dict:
    surrogate_by_label = {
        barrier_result.label: barrier_result
        for barrier_result in (assessment.surrogate_results or [])
    }
    transmissions = {}
    for analytical_result in assessment.analytical_results:
        if not analytical_result.label.startswith("Wall ") or "·" in analytical_result.label:
            continue
        surrogate_result = surrogate_by_label.get(analytical_result.label)
        decision_transmission = (
            surrogate_result.B_achieved
            if surrogate_result and surrogate_result.B_achieved is not None
            else analytical_result.B_achieved
        )
        if decision_transmission:
            transmissions[analytical_result.label.split()[1]] = decision_transmission
    return transmissions



def _duct_streaming_notices(assessment: RoomAssessment) -> list[str]:
    if not assessment.surrogate_results:
        return []
    surrogate_by_label = {
        barrier_result.label: barrier_result for barrier_result in assessment.surrogate_results
    }
    solid_transmissions = _solid_wall_transmissions(assessment)
    notices = []
    for analytical_result in assessment.analytical_results:
        if "duct" not in analytical_result.label:
            continue
        surrogate_result = surrogate_by_label.get(analytical_result.label)
        wall_id = analytical_result.label.split()[1]
        solid_transmission = solid_transmissions.get(wall_id)
        if not surrogate_result or surrogate_result.B_achieved is None or surrogate_result.ci_low is None:
            continue
        if not solid_transmission or surrogate_result.B_achieved <= 3 * solid_transmission:
            continue
        notices.append(
            i18n.t(
                "duct_warning",
                path=_display_path_label(analytical_result.label),
                duct=surrogate_result.B_achieved,
                ratio=surrogate_result.B_achieved / solid_transmission,
                solid=solid_transmission,
            )
        )
    return notices


def _finite_beam_notice(assessment: RoomAssessment) -> str | None:
    affected_results = [
        barrier_result
        for barrier_result in (assessment.surrogate_results or [])
        if getattr(barrier_result, "geometry_bias", False)
    ]
    if not affected_results:
        return None
    rows = "\n".join(
        f"- **{_display_path_label(barrier_result.label)}** — μx ≈ {barrier_result.mu_x:.1f}"
        f"{f', {i18n.term(barrier_result.material)}' if barrier_result.material else ''}"
        for barrier_result in sorted(
            affected_results,
            key=lambda candidate: -(candidate.mu_x or 0),
        )
    )
    return i18n.t("finite_beam_warning", paths=rows)

def _assurance_groups(assessment: RoomAssessment) -> tuple[list, list, list]:
    fallbacks, withdrawn_intervals, unresolved_paths = [], [], []
    for barrier_result in assessment.surrogate_results or []:
        engine_name = (barrier_result.engine or "").lower()
        if "ood fallback" in engine_name:
            fallbacks.append(barrier_result)
        elif "deep tail" in engine_name:
            withdrawn_intervals.append(barrier_result)
        elif barrier_result.passes is None:
            unresolved_paths.append(barrier_result)
    if not assessment.surrogate_results:
        unresolved_paths = [
            barrier_result
            for barrier_result in assessment.decision_results
            if barrier_result.passes is None
        ]
    return fallbacks, withdrawn_intervals, unresolved_paths



def _named_paths(barrier_results: list) -> str:
    return ", ".join(
        _display_path_label(barrier_result.label)
        for barrier_result in barrier_results
    )

def _review_path_groups(assessment: RoomAssessment) -> tuple[list, list]:
    uncertainty_paths = [
        barrier_result
        for barrier_result in assessment.decision_results
        if _uncertainty_crosses_limit(barrier_result)
    ]
    narrow_margin_paths = [
        barrier_result
        for barrier_result in assessment.decision_results
        if (
            barrier_result.passes is True
            and barrier_result.margin is not None
            and barrier_result.margin < 1.20
        )
    ]
    return uncertainty_paths, narrow_margin_paths


def _assessment_review_reasons(assessment: RoomAssessment) -> list[str]:
    reasons: list[str] = []
    fallbacks, withdrawn_intervals, unresolved_paths = _assurance_groups(assessment)
    if any(
        barrier_result.geometry_bias
        for barrier_result in assessment.decision_results
    ):
        reasons.append("known finite-beam geometry bias")
    if withdrawn_intervals:
        reasons.append("withdrawn uncertainty interval")
    if unresolved_paths:
        reasons.append("unresolved barrier path")
    uncertainty_paths, narrow_margin_paths = _review_path_groups(assessment)
    if uncertainty_paths:
        reasons.append(
            f"95% upper bound crosses the applied limit ({_named_paths(uncertainty_paths)})"
        )
    if narrow_margin_paths:
        reasons.append(
            f"margin below ×1.20 ({_named_paths(narrow_margin_paths)})"
        )
    if _duct_streaming_notices(assessment):
        reasons.append("duct-streaming path requires penetration review")
    return reasons



def render_safety_notices(assessment: RoomAssessment) -> list[str]:
    finite_beam_notice = _finite_beam_notice(assessment)
    fallbacks, withdrawn_intervals, unresolved_paths = _assurance_groups(assessment)
    uncertainty_paths, narrow_margin_paths = _review_path_groups(assessment)
    if finite_beam_notice:
        st.error(finite_beam_notice)
    if withdrawn_intervals:
        st.warning(
            i18n.t(
                "interval_withdrawn_warning",
                paths=_named_paths(withdrawn_intervals),
            )
        )
    if unresolved_paths:
        st.error(
            i18n.t(
                "not_fully_evaluated_warning",
                paths=_named_paths(unresolved_paths),
            )
        )
    if uncertainty_paths:
        st.warning(
            i18n.t(
                "uncertainty_review_warning",
                paths=_named_paths(uncertainty_paths),
            )
        )
    if narrow_margin_paths:
        st.warning(
            i18n.t(
                "narrow_margin_warning",
                paths=_named_paths(narrow_margin_paths),
            )
        )
    for duct_notice in _duct_streaming_notices(assessment):
        st.warning(duct_notice)
    if fallbacks:
        st.info(
            i18n.t(
                "fallback_warning",
                paths=_named_paths(fallbacks),
            )
        )
    return assessment.review_reasons


def _review_reasons_for_display(review_reasons: list[str]) -> list[str]:
    localized = []
    exact_keys = {
        "known finite-beam geometry bias": "reason_geometry_bias",
        "withdrawn uncertainty interval": "reason_withdrawn_interval",
        "unresolved barrier path": "reason_unresolved_path",
        "duct-streaming path requires penetration review": "reason_duct",
    }
    for reason in review_reasons:
        if reason in exact_keys:
            localized.append(i18n.t(exact_keys[reason]))
        elif reason.startswith("95% upper bound crosses"):
            paths = reason.partition("(")[2].rpartition(")")[0]
            localized.append(i18n.t("reason_uncertainty", paths=paths))
        elif reason.startswith("margin below"):
            paths = reason.partition("(")[2].rpartition(")")[0]
            localized.append(i18n.t("reason_narrow_margin", paths=paths))
        else:
            localized.append(reason)
    return localized


def _critical_path_meta(summary: dict, framework: str) -> str:
    critical_path = summary["critical"]
    if critical_path is None:
        return i18n.t("no_evaluable_path")
    path_label = _display_path_label(critical_path.label)
    if critical_path.margin is None:
        return i18n.t("critical_path", path=path_label)
    dose_text, goal_text = _dose_goal_text(critical_path, framework)
    return i18n.t(
        "critical_path_detail",
        path=path_label,
        dose=dose_text,
        goal=goal_text,
        margin=critical_path.margin,
    )


def _render_standard_decision(summary: dict, framework: str) -> None:
    decision_titles = {
        "PASS": i18n.t("all_paths_pass"),
        "FAIL": i18n.t("path_failed"),
        "MARGINAL": i18n.t("paths_need_review"),
    }
    summary_messages = {
        "PASS": i18n.t("summary_pass_message"),
        "FAIL": i18n.t("summary_fail_message"),
        "MARGINAL": i18n.t("summary_review_message"),
    }
    ds.status_card(
        summary["status"],
        decision_titles[summary["status"]],
        summary_messages[summary["status"]],
        _critical_path_meta(summary, framework),
    )


def _render_model_review_decision(
    summary: dict,
    review_reasons: list[str],
    framework: str,
) -> None:
    localized_reasons = _review_reasons_for_display(review_reasons)
    ds.status_card(
        "REVIEW",
        i18n.t("independent_review"),
        i18n.t("model_limits"),
        i18n.t(
            "review_basis",
            reasons=", ".join(localized_reasons),
            critical=_critical_path_meta(summary, framework),
        ),
    )


def _render_summary_metrics(summary: dict) -> None:
    critical_margin = summary["critical"].margin if summary["critical"] else None
    metric_cols = st.columns(4)
    metric_cols[0].metric(i18n.t("evaluated_paths"), str(summary["evaluated_count"]))
    metric_cols[1].metric(i18n.t("failed_paths"), str(summary["failed_count"]))
    metric_cols[2].metric(i18n.t("unresolved_paths"), str(summary["unknown_count"]))
    metric_cols[3].metric(
        i18n.t("critical_margin"),
        f"×{critical_margin:.2f}" if critical_margin is not None else "—",
    )

@st.cache_resource(show_spinner=False)
def _field_model():
    return field_surrogate.FieldModel()


@st.cache_data(show_spinner=False)
def _field_prediction(design_json: str):
    field_model = _field_model()
    if not field_model.available():
        return None
    return field_model.predict(RoomDesign.from_json(design_json))



def _render_field_prediction(room_design: RoomDesign, design_json: str) -> None:
    try:
        field_prediction = _field_prediction(design_json)
    except ValueError as error:
        st.info(i18n.t("field_error", error=error))
        return
    if field_prediction is None:
        st.info(i18n.t("field_unavailable"))
        return
    st.image(
        field_surrogate.render_field_slice(field_prediction, room_design),
        caption=i18n.t("field_caption"),
        width="stretch",
    )
    if field_prediction.shell_p95_log is not None:
        st.caption(
            i18n.t(
                "shell_field_level",
                level=field_prediction.shell_p95_log,
            )
        )
    for prediction_warning in field_prediction.warnings:
        st.info(prediction_warning)


def _render_field_map(room_design: RoomDesign) -> None:
    with st.expander(i18n.t("field_view"), expanded=False):
        design_json = room_design.to_json()
        if st.button(
            i18n.t("compute_field"),
            key="fieldmap_btn",
            help=i18n.t("compute_field_help"),
        ):
            st.session_state._fieldmap_sig = design_json
        if st.session_state.get("_fieldmap_sig") != design_json:
            st.caption(i18n.t("field_ready_note"))
            return
        with st.spinner(i18n.t("computing_field")):
            _render_field_prediction(room_design, design_json)

def _plan_status_by_label(assessment: RoomAssessment) -> dict[str, str]:
    return {
        barrier_result.label: row_status_for(barrier_result)[0]
        for barrier_result in assessment.decision_results
    }



def render_preview(assessment: RoomAssessment) -> None:
    st.image(
        diagram.render(
            assessment.design,
            assessment.decision_results,
            status_by_label=_plan_status_by_label(assessment),
        ),
        caption=i18n.t("plan_status_caption"),
        width="stretch",
    )
    if assessment.surrogate_engine.available():
        st.caption(i18n.t("surrogate_caption"))
    else:
        st.caption(i18n.t("analytical_caption"))
    _render_field_map(assessment.design)


def render_wall_summary(assessment: RoomAssessment) -> None:
    decisions_by_label = {
        barrier_result.label: barrier_result for barrier_result in assessment.decision_results
    }
    summary_items = []
    for wall in assessment.design.walls:
        wall_result = decisions_by_label.get(f"Wall {wall.id}")
        status_label = (
            row_status_for(wall_result)[2]
            if wall_result
            else i18n.t("not_evaluated")
        )
        summary_items.append(
            (
                i18n.t(
                    "wall_label",
                    wall=wall.id,
                    name=i18n.term(WALL_NAMES[wall.id]),
                ),
                i18n.t(
                    "wall_summary_value",
                    status=status_label,
                    area=wall.adjacent.name or i18n.t("unnamed_area"),
                    count=len(wall.openings),
                ),
            )
        )
    ds.context_strip(summary_items)


def _render_failure_explanations(assessment: RoomAssessment) -> None:
    failure_explanations = explain_failures(assessment.design, assessment.decision_results)
    if not failure_explanations:
        return
    shap_explanations = shap_failure_explanations(
        assessment.surrogate_engine,
        assessment.design,
        assessment.mode,
        assessment.analytical_results,
        assessment.surrogate_results or [],
    )
    st.markdown(f"### {i18n.t('why_attention')}")
    for explanation in failure_explanations:
        explanation_text = shap_explanations.get(
            explanation["barrier"],
            explanation["message"],
        )
        barrier_label = _display_path_label(explanation["barrier"])
        if i18n.is_arabic():
            st.error(f"**{barrier_label}:** {i18n.t('path_attention_generic')}")
            with st.expander(i18n.t("engine_detail_english"), expanded=False):
                st.write(explanation_text)
        else:
            st.error(f"**{barrier_label}:** {explanation_text}")


def _render_engine_notes(assessment: RoomAssessment) -> None:
    noted_results = [
        barrier_result
        for barrier_result in assessment.decision_results
        if barrier_result.note
    ]
    if not noted_results:
        return
    with st.expander(i18n.t("engine_notes"), expanded=False):
        for barrier_result in noted_results:
            st.markdown(
                f"**{_display_path_label(barrier_result.label)} · "
                f"{barrier_result.engine}**"
            )
            st.write(barrier_result.note)

def render_evidence_panel(assessment: RoomAssessment) -> None:
    st.markdown(results_table_html(assessment), unsafe_allow_html=True)
    _render_failure_explanations(assessment)
    _render_engine_notes(assessment)



def _cost_rows(room_costs: dict) -> list[dict]:
    rows = []
    for wall_cost in room_costs["walls"]:
        current_option, cheapest_option = wall_cost.current, wall_cost.cheapest
        if current_option is None:
            current_build = "—"
        elif wall_cost.declared is not None:
            current_build = wall_cost.declared.label
        else:
            current_build = (
                f"{current_option.preferred_mm:g} mm "
                f"{i18n.term(current_option.material)}"
            )
        rows.append(
            {
                i18n.t("column_barrier"): _display_path_label(wall_cost.label),
                i18n.t("column_area"): f"{wall_cost.area_m2:.1f} m²",
                i18n.t("column_current_build"): current_build,
                i18n.t("column_estimated_cost"): (
                    f"${wall_cost.cost_of(current_option):,.0f}" if current_option else "—"
                ),
                i18n.t("column_material_load"): (
                    f"{wall_cost.weight_of(current_option):,.0f} kg" if current_option else "—"
                ),
                i18n.t("column_lowest_cost"): (
                    f"{cheapest_option.preferred_mm:g} mm "
                    f"{i18n.term(cheapest_option.material)} "
                    f"(${wall_cost.cost_of(cheapest_option):,.0f})"
                    if cheapest_option else "—"
                ),
            }
        )
    return rows


def _material_rows(wall_cost) -> list[dict]:
    return [
        {
            i18n.t("column_material"): i18n.term(option.label),
            i18n.t("column_thickness"): f"{option.preferred_mm:g} mm",
            i18n.t("column_cost"): f"${option.cost_per_m2_usd * wall_cost.area_m2:,.0f}",
            i18n.t("column_load"): f"{option.weight_per_m2_kg * wall_cost.area_m2:,.0f} kg",
            i18n.t("column_best_for"): ", ".join(
                i18n.t(label_key)
                for label_key, enabled in (
                    ("lowest_cost", option.is_cheapest),
                    ("lowest_load", option.is_lightest),
                    ("smallest_footprint", option.is_thinnest),
                )
                if enabled
            ),
        }
        for option in wall_cost.options
        if option.feasible
    ]


def _render_all_materials(room_costs: dict) -> None:
    with st.expander(i18n.t("all_materials"), expanded=False):
        for wall_cost in room_costs["walls"]:
            st.markdown(
                f"**{_display_path_label(wall_cost.label)} · "
                f"{wall_cost.area_m2:.1f} m²**"
            )
            material_rows = _material_rows(wall_cost)
            if material_rows:
                st.dataframe(
                    material_rows,
                    width="stretch",
                    hide_index=True,
                    row_height=44,
                )


def render_cost_panel(assessment: RoomAssessment, room_costs: dict) -> None:
    cost_headline = room_cost.headline(room_costs)
    if not cost_headline:
        ds.empty_state(i18n.t("room_cost_unavailable"))
        return
    st.info(i18n.t("room_cost_intro") if i18n.is_arabic() else cost_headline)
    st.dataframe(
        _cost_rows(room_costs),
        width="stretch",
        hide_index=True,
        row_height=44,
    )
    _render_all_materials(room_costs)
    cost_basis = (
        i18n.t("declared_thickness_basis")
        if assessment.mode == "check"
        else i18n.t("required_thickness_basis")
    )
    st.caption(i18n.t("cost_basis_note", basis=cost_basis))


def _facility_metadata() -> dict:
    return {
        "facility": st.text_input(
            i18n.t("facility"),
            "",
            key="rg_fac",
            placeholder=i18n.t("facility_placeholder"),
            autocomplete="off",
        ),
        "room_ref": st.text_input(
            i18n.t("room_reference"),
            "",
            key="rg_room",
            placeholder=i18n.t("room_reference_placeholder"),
            autocomplete="off",
        ),
        "licence": st.text_input(
            i18n.t("licence_number"),
            "",
            key="rg_lic",
            placeholder=i18n.t("if_applicable"),
            autocomplete="off",
        ),
    }


def _approval_metadata() -> dict:
    return {
        "prepared_by": st.text_input(
            i18n.t("prepared_rso"),
            "",
            key="rg_prep",
            placeholder=i18n.t("credentials_placeholder"),
            autocomplete="off",
        ),
        "reviewed_by": st.text_input(
            i18n.t("reviewed_by"),
            "",
            key="rg_rev",
            placeholder=i18n.t("reviewer_placeholder"),
            autocomplete="off",
        ),
        "doc_ref": st.text_input(
            i18n.t("document_reference"),
            "",
            key="rg_ref",
            placeholder=i18n.t("document_placeholder"),
            autocomplete="off",
        ),
    }

def _project_metadata() -> dict:
    left_col, right_col = st.columns(2)
    with left_col:
        project_metadata = _facility_metadata()
    with right_col:
        project_metadata.update(_approval_metadata())
    project_metadata["revision"] = st.text_input(
        i18n.t("revision"), "0", key="rg_revno", autocomplete="off"
    )
    return project_metadata


def _build_room_report(assessment: RoomAssessment):
    plan_png = diagram.render(
        assessment.design,
        assessment.decision_results,
        status_by_label=_plan_status_by_label(assessment),
    )
    return report_room.build_report(
        assessment.design,
        assessment.analytical_results,
        assessment.mode,
        plan_png,
        surrogate_results=assessment.surrogate_results,
        overall_status=assessment.status,
        review_reasons=assessment.review_reasons,
        status_by_label=_plan_status_by_label(assessment),
    )



def _detailed_report_downloads(room_report) -> None:
    format_col, report_col, summary_col = st.columns([0.8, 1, 1])
    output_format = format_col.selectbox(
        i18n.t("detailed_format"),
        ["PDF", "Excel", "HTML"],
        key="room_report_format",
    )
    report_bytes, mime_type, extension = report_room.export(room_report, output_format)
    report_col.download_button(
        i18n.t("download_report", format=output_format),
        data=report_bytes,
        file_name=f"ShieldLab_RoomReport.{extension}",
        mime=mime_type,
        width="stretch",
    )
    summary_col.download_button(
        i18n.t("download_summary"),
        data=report_room.to_summary_pdf(room_report),
        file_name="ShieldLab_ClinicalSummary.pdf",
        mime="application/pdf",
        width="stretch",
    )


def render_export_panel(assessment: RoomAssessment, room_costs: dict) -> None:
    # Preserve the established export contract while separating preparation from delivery.
    with st.container(border=True, key="sl_export_identity"):
        st.markdown(f"### {i18n.t('project_identification')}")
        if i18n.is_arabic():
            ds.assurance_note(i18n.t("exports_english_note"))
        project_metadata = _project_metadata()
        include_costs = st.checkbox(
            i18n.t("include_costs"),
            value=True,
            key="rg_cost",
        )
        export_signature = (
            assessment.design.to_json(),
            assessment.mode,
            tuple(sorted(project_metadata.items())),
            include_costs,
        )
        prepare_export = st.button(
            i18n.t("prepare_export"),
            type="primary",
            key="prepare_room_exports",
            width="stretch",
        )

    if prepare_export:
        st.session_state["_room_export_signature"] = export_signature
    if st.session_state.get("_room_export_signature") != export_signature:
        st.caption(i18n.t("prepare_export_note"))
        return

    with st.spinner(i18n.t("preparing_package")):
        room_report = _build_room_report(assessment)
        submission_html = report_regulatory.build_submission_html(
            room_report,
            project_metadata,
            costs=room_costs if include_costs else None,
        )
    with st.container(border=True, key="sl_export_delivery"):
        st.markdown(f"### {i18n.t('download_package')}")
        _detailed_report_downloads(room_report)
        st.download_button(
            i18n.t("download_submission"),
            data=submission_html,
            file_name="ShieldLab_RegulatorySubmission.html",
            mime="text/html",
            type="primary",
            width="stretch",
            help=i18n.t("submission_help"),
        )

def render_assessment_review(assessment: RoomAssessment) -> None:
    with st.container(border=True, key="sl_decision_panel"):
        st.markdown(f"## {i18n.t('assessment_review')}")
        review_reasons = render_safety_notices(assessment)
        assessment_summary = summarize_results(assessment.decision_results)
        if assessment.status == "REVIEW":
            _render_model_review_decision(
                assessment_summary,
                review_reasons,
                assessment.design.framework,
            )
        else:
            _render_standard_decision(
                assessment_summary,
                assessment.design.framework,
            )
        if assessment.design.framework == "NCRP":
            ds.assurance_note(i18n.t("ncrp_decision_note"))
        _render_summary_metrics(assessment_summary)

    room_costs = room_cost.room_costs(assessment.design, assessment.mode)
    with st.container(key="sl_result_tabs"):
        evidence_tab, cost_tab, export_tab = st.tabs(
            [
                i18n.t("tab_barrier_evidence"),
                i18n.t("tab_cost_materials"),
                i18n.t("tab_export_center"),
            ]
        )
    with evidence_tab:
        render_evidence_panel(assessment)
    with cost_tab:
        render_cost_panel(assessment, room_costs)
    with export_tab:
        render_export_panel(assessment, room_costs)


