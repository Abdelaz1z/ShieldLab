"""Room Designer input controls and project-file actions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

import streamlit as st

from shieldlab.room.engines import usable_wall_materials
from shieldlab.room.model import (
    ISOTOPES,
    OCCUPANCY_MENU,
    WALL_IDS,
    WALL_NAMES,
    Opening,
    RoomDesign,
    Wall,
)

from . import i18n
from . import product_shell as ds


@dataclass(frozen=True)
class OpeningEditContext:
    wall: Wall
    span_m: float
    materials: list[str]


def _term_labels(options: list[str] | tuple[str, ...]) -> dict[str, str]:
    return {option: i18n.term(option) for option in options}


def _number_in_range(value: object, minimum: float, maximum: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
        and minimum <= float(value) <= maximum
    )


def _design_numeric_errors(room_design: RoomDesign) -> list[str]:
    numeric_fields = (
        (room_design.room.width_m, 1.0, 40.0, "Room width must be between 1 and 40 m."),
        (room_design.room.length_m, 1.0, 40.0, "Room length must be between 1 and 40 m."),
        (room_design.room.height_m, 2.0, 8.0, "Room height must be between 2 and 8 m."),
        (room_design.source.activity_MBq, 1.0, 100000.0, "Activity must be between 1 and 100,000 MBq."),
        (room_design.source.patients_per_week, 1.0, 2000.0, "Patients per week must be between 1 and 2,000."),
        (room_design.source.residence_min, 1.0, 600.0, "Residence time must be between 1 and 600 minutes."),
    )
    return [
        message
        for value, minimum, maximum, message in numeric_fields
        if not _number_in_range(value, minimum, maximum)
    ]


def _source_position_errors(room_design: RoomDesign) -> list[str]:
    errors = []
    room_width_valid = _number_in_range(room_design.room.width_m, 1.0, 40.0)
    room_length_valid = _number_in_range(room_design.room.length_m, 1.0, 40.0)
    if room_width_valid and not _number_in_range(
        room_design.source.x_m, 0.0, float(room_design.room.width_m)
    ):
        errors.append("Source X must be inside the room.")
    if room_length_valid and not _number_in_range(
        room_design.source.y_m, 0.0, float(room_design.room.length_m)
    ):
        errors.append("Source Y must be inside the room.")
    return errors


def _opening_load_errors(
    opening: Opening,
    wall_label: str,
    available_materials: set[str],
) -> list[str]:
    opening_label = f"Wall {wall_label} {opening.kind}"
    if opening.kind not in ("door", "window", "duct", "maze"):
        return [f"{opening_label} has an unsupported opening type."]

    errors = []
    if not _number_in_range(opening.width_m, 0.1, 40.0):
        errors.append(f"{opening_label} width must be between 0.1 and 40 m.")
    if opening.kind in ("door", "window") and not _number_in_range(
        opening.lead_equiv_mm, 0.0, 100.0
    ):
        errors.append(f"{opening_label} lead equivalence must be between 0 and 100 mm.")
    if opening.kind == "duct" and not _number_in_range(
        opening.radius_mm, 1.0, 300.0
    ):
        errors.append(f"{opening_label} radius must be between 1 and 300 mm.")
    if opening.kind != "maze":
        return errors

    maze_fields = (
        (opening.corridor_m, 0.2, 3.0, "corridor length"),
        (opening.shadow_offset_m, 0.1, 2.0, "shadow offset"),
        (opening.ret_thickness_mm, 10.0, 1000.0, "return thickness"),
    )
    errors.extend(
        f"{opening_label} {field_label} is outside the editor range."
        for value, minimum, maximum, field_label in maze_fields
        if not _number_in_range(value, minimum, maximum)
    )
    if opening.ret_material not in available_materials:
        errors.append(f"{opening_label} return-wall material is unsupported.")
    return errors


def _wall_load_errors(wall: Wall, available_materials: set[str]) -> list[str]:
    wall_label = str(wall.id)
    errors = []
    if wall.material1 not in available_materials:
        errors.append(f"Wall {wall_label} uses an unsupported primary material.")
    if wall.material2 is not None and wall.material2 not in available_materials:
        errors.append(f"Wall {wall_label} uses an unsupported second material.")
    if not _number_in_range(wall.thickness1_mm, 0.0, 3000.0):
        errors.append(f"Wall {wall_label} primary thickness must be between 0 and 3,000 mm.")
    if not _number_in_range(wall.thickness2_mm, 0.0, 3000.0):
        errors.append(f"Wall {wall_label} second thickness must be between 0 and 3,000 mm.")
    if wall.adjacent.kind not in ("public", "controlled"):
        errors.append(f"Wall {wall_label} has an unsupported area classification.")
    if not _number_in_range(wall.adjacent.occupancy_T, 0.0001, 1.0):
        errors.append(f"Wall {wall_label} occupancy factor must be between 0.0001 and 1.")
    custom_goal = wall.adjacent.design_goal_P_mSv_wk
    if custom_goal is not None and not _number_in_range(custom_goal, 0.0001, 10.0):
        errors.append(f"Wall {wall_label} custom design goal is outside the editor range.")
    for opening in wall.openings:
        errors.extend(_opening_load_errors(opening, wall_label, available_materials))
    return errors


def _design_load_errors(room_design: RoomDesign) -> list[str]:
    wall_ids = [wall.id for wall in room_design.walls]
    errors = _design_numeric_errors(room_design)
    errors.extend(_source_position_errors(room_design))
    if len(wall_ids) != len(WALL_IDS) or set(wall_ids) != set(WALL_IDS):
        errors.append("The project must contain exactly one North, East, South, and West wall.")
    if room_design.framework not in ("NCRP", "IAEA_NRRC"):
        errors.append("The regulatory framework is not supported.")
    if room_design.source.isotope not in ISOTOPES:
        errors.append("The radionuclide is not supported.")

    available_materials = set(
        usable_wall_materials(room_design.source.isotope)
        if room_design.source.isotope in ISOTOPES
        else []
    )
    for wall in room_design.walls:
        errors.extend(_wall_load_errors(wall, available_materials))
    try:
        errors.extend(room_design.validate())
    except (AttributeError, TypeError):
        errors.append("The project contains invalid value types.")
    return list(dict.fromkeys(errors))

def _occupancy_choice(occupancy: float) -> tuple[list[str], int]:
    labels = list(OCCUPANCY_MENU)
    for index, value in enumerate(OCCUPANCY_MENU.values()):
        if isclose(float(occupancy), value, rel_tol=0.0, abs_tol=1e-9):
            return labels + ["Custom Project Value"], index
    return labels + ["Custom Project Value"], len(labels)


def _clear_project_session_state() -> None:
    locale_keys = {i18n.LANGUAGE_KEY, i18n.LANGUAGE_CONTROL_KEY}
    for session_key in tuple(st.session_state):
        if session_key not in locale_keys:
            del st.session_state[session_key]


def load_or_create_design() -> RoomDesign:
    if "_pending_design" in st.session_state:
        pending_design = st.session_state.pop("_pending_design")
        pending_origin = st.session_state.pop(
            "_pending_design_origin", "Loaded project file"
        )
        _clear_project_session_state()
        st.session_state.design = pending_design
        st.session_state.design_origin = pending_origin
    if "design" not in st.session_state:
        st.session_state.design = RoomDesign.default()
        st.session_state.design_origin = "Representative starting values"
    return st.session_state.design


def _mode_control() -> str:
    mode_options = ("Design", "Check")
    mode_labels = _term_labels(mode_options)
    selected_mode = st.radio(
        i18n.t("assessment_mode"),
        mode_options,
        horizontal=True,
        format_func=mode_labels.__getitem__,
        help=i18n.t("assessment_mode_help"),
        key="mode_radio",
    )
    return selected_mode.lower()


def _framework_control(room_design: RoomDesign) -> None:
    framework_options = ("NCRP", "IAEA_NRRC")
    framework_labels = {
        "NCRP": i18n.term("NCRP Weekly Goals"),
        "IAEA_NRRC": i18n.term("IAEA / Saudi NRRC"),
    }
    room_design.framework = st.selectbox(
        i18n.t("regulatory_framework"),
        framework_options,
        index=0 if room_design.framework == "NCRP" else 1,
        format_func=framework_labels.__getitem__,
        help=i18n.t("framework_help"),
        key="room_framework",
    )


def _load_design_control() -> None:
    with st.popover(i18n.t("open_design"), width="stretch"):
        uploaded_design = st.file_uploader(
            i18n.t("select_json"),
            type=["json"],
            key="load_json",
        )
        if not st.button(
            i18n.t("load_design"),
            disabled=uploaded_design is None,
            width="stretch",
            type="primary",
            key="load_selected_design",
        ):
            return
        try:
            decoded_json = uploaded_design.getvalue().decode("utf-8")
            candidate_design = RoomDesign.from_json(decoded_json)
            validation_errors = _design_load_errors(candidate_design)
        except (AttributeError, UnicodeDecodeError, ValueError, KeyError, TypeError) as error:
            st.error(i18n.t("load_error", error=error))
            return
        if validation_errors:
            error_list = "\n".join(
                f"- {i18n.validation_message(message)}" for message in validation_errors
            )
            st.error(f"{i18n.t('invalid_design')}\n\n{error_list}")
            return
        st.session_state["_pending_design"] = candidate_design
        st.session_state["_pending_design_origin"] = "Loaded project file"
        st.rerun()


def _save_design_control(room_design: RoomDesign) -> None:
    st.download_button(
        i18n.t("save_design"),
        data=room_design.to_json(),
        file_name="ShieldLab_RoomDesign.json",
        mime="application/json",
        key="save_room_design",
        width="stretch",
    )


def command_bar(room_design: RoomDesign) -> str:
    with st.container(border=True, key="sl_command_bar"):
        mode_col, framework_col, open_col, save_col = st.columns([1.25, 1.15, 0.85, 0.85])
        with mode_col:
            assessment_mode = _mode_control()
        with framework_col:
            _framework_control(room_design)
        with open_col:
            _load_design_control()
        with save_col:
            _save_design_control(room_design)
    return assessment_mode


def _room_dimensions(room_design: RoomDesign) -> None:
    width_col, length_col, height_col = st.columns(3)
    room_design.room.width_m = width_col.number_input(
        i18n.t("room_width"),
        1.0,
        40.0,
        room_design.room.width_m,
        0.5,
        key="room_width_m",
    )
    room_design.room.length_m = length_col.number_input(
        i18n.t("room_length"),
        1.0,
        40.0,
        room_design.room.length_m,
        0.5,
        key="room_length_m",
    )
    room_design.room.height_m = height_col.number_input(
        i18n.t("room_height"),
        2.0,
        8.0,
        room_design.room.height_m,
        0.1,
        key="room_height_m",
    )


def _source_workload(room_design: RoomDesign) -> None:
    isotope_col, activity_col = st.columns(2)
    room_design.source.isotope = isotope_col.selectbox(
        i18n.t("radionuclide"),
        ISOTOPES,
        index=(
            ISOTOPES.index(room_design.source.isotope)
            if room_design.source.isotope in ISOTOPES else 0
        ),
        key="room_isotope",
    )
    room_design.source.activity_MBq = activity_col.number_input(
        i18n.t("activity_patient"),
        1.0,
        100000.0,
        room_design.source.activity_MBq,
        10.0,
        help="37 MBq = 1 mCi.",
        key="room_activity_mbq",
    )
    patient_col, residence_col = st.columns(2)
    room_design.source.patients_per_week = patient_col.number_input(
        i18n.t("patients_per_week"),
        1.0,
        2000.0,
        room_design.source.patients_per_week,
        1.0,
        key="room_patients_per_week",
    )
    room_design.source.residence_min = residence_col.number_input(
        i18n.t("residence_patient"),
        1.0,
        600.0,
        room_design.source.residence_min,
        5.0,
        key="room_residence_min",
    )


def _source_slider_default(
    key: str,
    model_value: float,
    maximum: float,
) -> float | None:
    if key not in st.session_state:
        return min(max(model_value, 0.0), maximum)
    widget_value = float(st.session_state[key])
    bounded_value = min(max(widget_value, 0.0), maximum)
    if not isclose(widget_value, bounded_value, rel_tol=0.0, abs_tol=1e-9):
        st.session_state[key] = bounded_value
    return None


def _source_position(room_design: RoomDesign) -> None:
    source_x = _source_slider_default(
        "room_source_x_m", room_design.source.x_m, room_design.room.width_m
    )
    source_y = _source_slider_default(
        "room_source_y_m", room_design.source.y_m, room_design.room.length_m
    )
    x_col, y_col = st.columns(2)
    room_design.source.x_m = x_col.slider(
        i18n.t("source_x"),
        0.0,
        room_design.room.width_m,
        source_x,
        0.1,
        key="room_source_x_m",
    )
    room_design.source.y_m = y_col.slider(
        i18n.t("source_y"),
        0.0,
        room_design.room.length_m,
        source_y,
        0.1,
        key="room_source_y_m",
    )


def _floor_plan_reference() -> None:
    with st.expander(i18n.t("floor_plan_reference"), expanded=False):
        plan_image = st.file_uploader(
            i18n.t("upload_plan"),
            type=["png", "jpg", "jpeg"],
            key="planimg",
        )
        if plan_image is None:
            return
        st.image(
            plan_image,
            caption=i18n.t("plan_caption"),
            width="stretch",
        )
        st.caption(i18n.t("plan_note"))


def room_source_editor(room_design: RoomDesign) -> None:
    with st.container(border=True, key="sl_room_source"):
        ds.section_header(
            "01",
            i18n.t("room_source"),
            i18n.t("room_source_help"),
        )
        _room_dimensions(room_design)
        _source_workload(room_design)
        _source_position(room_design)
        _floor_plan_reference()


def _selected_wall(room_design: RoomDesign):
    wall_labels = {
        wall_id: i18n.t(
            "wall_label",
            wall=wall_id,
            name=i18n.term(WALL_NAMES[wall_id]),
        )
        for wall_id in WALL_IDS
    }
    with st.container(key="sl_wall_selector"):
        wall_id = st.radio(
            i18n.t("select_barrier"),
            WALL_IDS,
            horizontal=True,
            format_func=wall_labels.__getitem__,
            key="active_wall_id",
        )
    return room_design.wall(wall_id)


def _custom_goal_editor(room_design: RoomDesign, wall) -> None:
    goal_unit = "mGy/week" if room_design.framework == "NCRP" else "mSv/week"
    custom_goal_enabled = st.checkbox(
        i18n.t("wall_goal_toggle"),
        key=f"ovck_{wall.id}",
        value=wall.adjacent.design_goal_P_mSv_wk is not None,
        help=i18n.t("wall_goal_help"),
    )
    if not custom_goal_enabled:
        wall.adjacent.design_goal_P_mSv_wk = None
        return
    wall.adjacent.design_goal_P_mSv_wk = st.number_input(
        i18n.t("wall_goal", unit=goal_unit),
        0.0001,
        10.0,
        (
            wall.adjacent.design_goal_P_mSv_wk
            if wall.adjacent.design_goal_P_mSv_wk is not None
            else 0.02
        ),
        0.001,
        format="%.4f",
        key=f"ov_{wall.id}",
    )
    st.warning(i18n.t("wall_goal_warning"))


def _adjacent_area_editor(room_design: RoomDesign, wall) -> None:
    name_col, occupancy_col, classification_col = st.columns([1.4, 1, 1])
    wall.adjacent.name = name_col.text_input(
        i18n.t("adjacent_area"),
        wall.adjacent.name,
        key=f"nm_{wall.id}",
        placeholder=i18n.t("adjacent_placeholder"),
        autocomplete="off",
    )
    occupancy_options, occupancy_index = _occupancy_choice(
        wall.adjacent.occupancy_T
    )
    occupancy_labels = _term_labels(occupancy_options)
    occupancy_label = occupancy_col.selectbox(
        i18n.t("occupancy_factor"),
        occupancy_options,
        index=occupancy_index,
        format_func=occupancy_labels.__getitem__,
        key=f"occ_{wall.id}",
    )
    if occupancy_label == "Custom Project Value":
        wall.adjacent.occupancy_T = occupancy_col.number_input(
            i18n.t("custom_occupancy"),
            0.0001,
            1.0,
            float(wall.adjacent.occupancy_T),
            0.01,
            format="%.4f",
            key=f"occ_custom_{wall.id}",
        )
    else:
        wall.adjacent.occupancy_T = OCCUPANCY_MENU[occupancy_label]
    classification_options = ("public", "controlled")
    classification_labels = {
        "public": i18n.term("Uncontrolled / Public"),
        "controlled": i18n.term("Controlled"),
    }
    wall.adjacent.kind = classification_col.selectbox(
        i18n.t("area_classification"),
        classification_options,
        index=0 if wall.adjacent.kind == "public" else 1,
        format_func=classification_labels.__getitem__,
        key=f"kind_{wall.id}",
    )
    _custom_goal_editor(room_design, wall)


def _primary_layer_editor(wall, assessment_mode: str, materials: list[str]) -> None:
    material_labels = _term_labels(materials)
    material_col, thickness_col = st.columns(2)
    wall.material1 = material_col.selectbox(
        i18n.t("primary_material"),
        materials,
        index=materials.index(wall.material1) if wall.material1 in materials else 0,
        format_func=material_labels.__getitem__,
        key=f"m1_{wall.id}",
    )
    if assessment_mode == "check":
        wall.thickness1_mm = thickness_col.number_input(
            i18n.t("declared_thickness"),
            0.0,
            3000.0,
            wall.thickness1_mm,
            5.0,
            key=f"t1_{wall.id}",
        )
    else:
        thickness_col.info(i18n.t("required_in_table"))


def _second_layer_editor(wall, materials: list[str]) -> None:
    material_labels = _term_labels(materials)
    laminate_enabled = st.checkbox(
        i18n.t("add_second_layer"),
        key=f"lamck_{wall.id}",
        value=bool(wall.material2),
    )
    if not laminate_enabled:
        wall.material2, wall.thickness2_mm = None, 0.0
        return
    material_col, thickness_col = st.columns(2)
    wall.material2 = material_col.selectbox(
        i18n.t("second_material"),
        materials,
        index=materials.index(wall.material2) if wall.material2 in materials else 0,
        format_func=material_labels.__getitem__,
        key=f"m2_{wall.id}",
    )
    wall.thickness2_mm = thickness_col.number_input(
        i18n.t("second_thickness"),
        0.0,
        3000.0,
        wall.thickness2_mm or 0.0,
        5.0,
        key=f"t2_{wall.id}",
    )


def _barrier_layers_editor(wall, assessment_mode: str, materials: list[str]) -> None:
    st.markdown(f"### {i18n.t('barrier_build_up')}")
    _primary_layer_editor(wall, assessment_mode, materials)
    _second_layer_editor(wall, materials)


def _append_opening(wall, span_m: float, opening_kind: str) -> None:
    opening_defaults = {
        "door": {"lead_equiv_mm": 1.0},
        "window": {"lead_equiv_mm": 2.0},
        "duct": {"radius_mm": 25.0},
        "maze": {},
    }
    wall.openings.append(
        Opening(
            kind=opening_kind,
            center_along_wall_m=span_m / 2,
            **opening_defaults[opening_kind],
        )
    )


def _opening_add_control(wall, span_m: float) -> None:
    opening_options = ("door", "window", "duct", "maze")
    opening_labels = {
        opening_type: i18n.term(opening_type.title())
        for opening_type in opening_options
    }
    type_col, action_col = st.columns([1.4, 0.8])
    opening_kind = type_col.selectbox(
        i18n.t("opening_type"),
        opening_options,
        format_func=opening_labels.__getitem__,
        key=f"opening_type_{wall.id}",
    )
    if action_col.button(
        i18n.t("add_opening"),
        key=f"add_opening_{wall.id}",
        width="stretch",
    ):
        _append_opening(wall, span_m, opening_kind)
        st.rerun()


def _maze_properties(opening, opening_key: str, materials: list[str]) -> None:
    material_labels = _term_labels(materials)
    maze_cols = st.columns(3)
    opening.shadow_offset_m = maze_cols[0].number_input(
        i18n.t("shadow_offset"),
        0.1,
        2.0,
        float(opening.shadow_offset_m or 0.5),
        0.1,
        key=f"sho_{opening_key}",
    )
    opening.ret_material = maze_cols[1].selectbox(
        i18n.t("return_material"),
        materials,
        index=(
            materials.index(opening.ret_material)
            if opening.ret_material in materials else 0
        ),
        format_func=material_labels.__getitem__,
        key=f"rm_{opening_key}",
    )
    opening.ret_thickness_mm = maze_cols[2].number_input(
        i18n.t("return_thickness"),
        10.0,
        1000.0,
        float(opening.ret_thickness_mm or 150),
        10.0,
        key=f"rt_{opening_key}",
    )


def _reconciled_opening_width(
    opening_context: OpeningEditContext,
    opening: Opening,
    opening_key: str,
) -> float:
    width_key = f"width_{opening_key}"
    requested_width = float(st.session_state.get(width_key, opening.width_m))
    clamped_width = min(max(requested_width, 0.1), float(opening_context.span_m))
    if not isclose(requested_width, clamped_width, rel_tol=0.0, abs_tol=1e-9):
        st.warning(i18n.t("opening_width_warning"))
    if width_key in st.session_state:
        st.session_state[width_key] = clamped_width
    return clamped_width


def _reconciled_opening_position(
    opening: Opening,
    opening_width: float,
    span_m: float,
    opening_key: str,
) -> float:
    minimum_center = opening_width / 2.0
    maximum_center = span_m - opening_width / 2.0
    position_key = f"pos_{opening_key}"
    requested_position = float(
        st.session_state.get(position_key, opening.center_along_wall_m)
    )
    clamped_position = min(max(requested_position, minimum_center), maximum_center)
    if not isclose(requested_position, clamped_position, rel_tol=0.0, abs_tol=1e-9):
        st.warning(i18n.t("opening_position_warning"))
    if position_key in st.session_state:
        st.session_state[position_key] = clamped_position
    return clamped_position


def _opening_type_property(
    property_column,
    opening: Opening,
    opening_key: str,
    materials: list[str],
) -> None:
    if opening.kind == "duct":
        radius_value = opening.radius_mm if opening.radius_mm is not None else 25.0
        opening.radius_mm = property_column.number_input(
            i18n.t("duct_radius"), 1.0, 300.0, float(radius_value), 1.0,
            key=f"rad_{opening_key}",
        )
        return
    if opening.kind == "maze":
        corridor_value = opening.corridor_m if opening.corridor_m is not None else 0.8
        opening.corridor_m = property_column.number_input(
            i18n.t("corridor_length"), 0.2, 3.0, float(corridor_value), 0.1,
            key=f"cor_{opening_key}",
        )
        _maze_properties(opening, opening_key, materials)
        return
    lead_value = opening.lead_equiv_mm if opening.lead_equiv_mm is not None else 1.0
    opening.lead_equiv_mm = property_column.number_input(
        i18n.t("lead_equivalence"), 0.0, 100.0, float(lead_value), 0.5,
        key=f"le_{opening_key}",
    )


def _opening_properties(
    opening_context: OpeningEditContext,
    opening: Opening,
    opening_key: str,
) -> None:
    span_m = float(opening_context.span_m)
    clamped_width = _reconciled_opening_width(
        opening_context,
        opening,
        opening_key,
    )
    property_cols = st.columns(3)
    opening.width_m = property_cols[0].number_input(
        i18n.t("opening_width"), 0.1, span_m, clamped_width, 0.1,
        key=f"width_{opening_key}",
    )
    clamped_position = _reconciled_opening_position(
        opening,
        opening.width_m,
        span_m,
        opening_key,
    )
    opening.center_along_wall_m = property_cols[1].number_input(
        i18n.t("opening_position"),
        opening.width_m / 2.0,
        span_m - opening.width_m / 2.0,
        clamped_position,
        0.1,
        key=f"pos_{opening_key}",
    )
    _opening_type_property(
        property_cols[2],
        opening,
        opening_key,
        opening_context.materials,
    )


def _opening_card(opening_context: OpeningEditContext, opening, index: int) -> None:
    opening_key = f"{opening_context.wall.id}_{index}"
    with st.container(border=True):
        title_col, remove_col = st.columns([1.5, 0.7])
        title_col.markdown(
            f"**{i18n.t('opening_title', kind=i18n.term(opening.kind.title()), number=index + 1)}**"
        )
        if remove_col.button(
            i18n.t("remove_opening"),
            key=f"del_{opening_key}",
            width="stretch",
        ):
            opening_context.wall.openings.pop(index)
            st.rerun()
        _opening_properties(opening_context, opening, opening_key)


def _openings_editor(room_design: RoomDesign, wall, materials: list[str]) -> None:
    st.markdown(f"### {i18n.t('openings_penetrations')}")
    wall_span = (
        room_design.room.width_m
        if wall.id in ("N", "S")
        else room_design.room.length_m
    )
    _opening_add_control(wall, wall_span)
    if not wall.openings:
        ds.empty_state(i18n.t("no_openings"))
        return
    opening_context = OpeningEditContext(wall, wall_span, materials)
    for opening_index, opening in enumerate(list(wall.openings)):
        _opening_card(opening_context, opening, opening_index)


def wall_editor(
    room_design: RoomDesign,
    assessment_mode: str,
    materials: list[str],
) -> None:
    selected_wall = _selected_wall(room_design)
    with st.container(border=True, key="sl_wall_editor"):
        ds.section_header(
            "02",
            i18n.t(
                "wall_label",
                wall=selected_wall.id,
                name=i18n.term(WALL_NAMES[selected_wall.id]),
            ),
            i18n.t("wall_editor_help"),
        )
        _adjacent_area_editor(room_design, selected_wall)
        _barrier_layers_editor(selected_wall, assessment_mode, materials)
        _openings_editor(room_design, selected_wall, materials)



