"""Commercial Room Designer orchestration over the validated ShieldLab engines."""

from __future__ import annotations

import streamlit as st

from shieldlab.room.engines import SurrogateEngine, usable_wall_materials
from shieldlab.room.model import RoomDesign

from . import i18n
from . import product_shell as ds
from . import room_editor, room_results


def _page_intro() -> None:
    ds.render_sidebar("room")
    ds.page_header(
        i18n.t("room_eyebrow"),
        i18n.t("room_title"),
        i18n.t("room_description"),
        badges=(
            i18n.t("badge_dual_engine"),
            i18n.t("badge_intervals"),
            i18n.t("badge_exports"),
        ),
    )


def _assessment_context_items(
    room_design: RoomDesign,
    assessment_mode: str,
    surrogate_engine: SurrogateEngine,
) -> list[tuple[str, str]]:
    mode_key = "shielding_design" if assessment_mode == "design" else "existing_check"
    framework = "NCRP Weekly Goals" if room_design.framework == "NCRP" else "IAEA / Saudi NRRC"
    engine_key = "surrogate_available" if surrogate_engine.available() else "analytical_only"
    workload = i18n.t(
        "patients_per_week_value",
        count=room_design.source.patients_per_week,
    )
    return [
        (i18n.t("room_mode"), i18n.t(mode_key)),
        (i18n.t("framework"), i18n.term(framework)),
        (i18n.t("radionuclide"), room_design.source.isotope),
        (i18n.t("workload"), workload),
        (i18n.t("engine_state"), i18n.t(engine_key)),
    ]


def _assessment_context(
    room_design: RoomDesign,
    assessment_mode: str,
    surrogate_engine: SurrogateEngine,
) -> None:
    ds.context_strip(
        _assessment_context_items(room_design, assessment_mode, surrogate_engine)
    )
    origin = i18n.term(
        st.session_state.get("design_origin", i18n.t("origin_current"))
    )
    ds.assurance_note(i18n.t("starting_point", origin=origin))


def _render_workspace(
    room_design: RoomDesign,
    assessment_mode: str,
    surrogate_engine: SurrogateEngine,
):
    editor_col, preview_col = st.columns([0.95, 1.05], gap="large")
    with editor_col:
        room_editor.room_source_editor(room_design)
    with preview_col:
        preview_slot = st.container(border=True, key="sl_room_preview")

    wall_materials = usable_wall_materials(room_design.source.isotope) or ["concrete"]
    room_editor.wall_editor(room_design, assessment_mode, wall_materials)
    validation_errors = room_design.validate()

    with preview_slot:
        ds.section_header("P", i18n.t("live_plan"), i18n.t("live_plan_help"))
        if validation_errors:
            for validation_error in validation_errors:
                st.warning(i18n.term(validation_error))
            return None
        assessment = room_results.build_assessment(
            room_design,
            assessment_mode,
            surrogate_engine,
        )
        room_results.render_preview(assessment)
    return assessment


def _page_footer() -> None:
    st.caption(i18n.t("room_footer"))
    ds.render_sidebar_footer()


def render() -> None:
    ds.inject_styles()
    _page_intro()
    room_design = room_editor.load_or_create_design()
    assessment_mode = room_editor.command_bar(room_design)
    surrogate_engine = SurrogateEngine(room_design)
    context_slot = st.empty()
    assessment = _render_workspace(room_design, assessment_mode, surrogate_engine)
    with context_slot.container():
        _assessment_context(room_design, assessment_mode, surrogate_engine)
    if assessment is not None:
        room_results.render_wall_summary(assessment)
        ds.live_note(i18n.t("room_live_note"))
        room_results.render_assessment_review(assessment)
    _page_footer()



