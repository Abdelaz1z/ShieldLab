"""Single-barrier calculator setup controls and barrier editor."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from uuid import uuid4

import streamlit as st

from shieldlab import data_loader as dl
from shieldlab.physics import barriers as ba
from shieldlab.regulatory import limits as reg

from . import modality_config as mc
from .i18n import t, term


@dataclass(frozen=True)
class CalculatorSetup:
    modality_key: str
    modality_config: dict
    framework_label: str
    area_label: str
    occupancy_t: float
    design_goal: object

    def context_items(self) -> list[tuple[str, str]]:
        applied_limit = self.design_goal.P_weekly / self.occupancy_t
        return [
            (t("modality"), term(self.modality_config["label"])),
            (t("framework"), term(self.framework_label)),
            (t("area"), term(self.area_label)),
            (t("occupancy_t"), f"{self.occupancy_t:g}"),
            (t("design_limit_pt"), f"{applied_limit:.4g} {self.design_goal.unit}"),
        ]


def _sidebar_step(number: str, title: str, description: str) -> None:
    st.sidebar.markdown(
        f'<div style="margin:18px 0 8px">'
        f'<div style="color:#76aeb4;font-size:13px;font-weight:800;letter-spacing:.12em">'
        f'{escape(t("step", number=number))}</div>'
        f'<div style="color:#fff;font-size:16px;font-weight:750;margin-top:2px">'
        f'{escape(title)}</div>'
        f'<div style="color:#9fb3bf;font-size:14px;line-height:1.5;margin-top:3px">'
        f'{escape(description)}</div></div>',
        unsafe_allow_html=True,
    )


def _equipment_setup() -> tuple[str, dict]:
    _sidebar_step("01", t("equipment"), t("equipment_help"))
    modality_groups = mc.groups()
    group_labels = {group: term(group) for group in modality_groups}
    modality_group = st.sidebar.selectbox(
        t("facility_type"),
        modality_groups,
        format_func=lambda group: group_labels[group],
        key="calc_modality_group",
    )
    modality_options = mc.modalities_in_group(modality_group)
    labels_by_key = {
        modality_key: term(label)
        for modality_key, label in modality_options
    }
    modality_key = st.sidebar.selectbox(
        t("modality_energy"),
        [key for key, _ in modality_options],
        format_func=lambda key: labels_by_key[key],
        key="calc_modality_key",
    )
    modality_config = mc.MODALITIES[modality_key]
    if modality_config.get("note"):
        st.sidebar.info(term(modality_config["note"]))
    return modality_key, modality_config


def _occupancy_control() -> float:
    occupancy_rows = dl.limits()["occupancy_factors"]["table"]
    occupancy_labels = [
        f"{row['fraction']} · {term(row['areas'])[:47]}"
        f"{'…' if len(term(row['areas'])) > 47 else ''}"
        for row in occupancy_rows
    ]
    selected_index = st.sidebar.selectbox(
        t("suggested_occupancy"),
        range(len(occupancy_rows)),
        format_func=lambda index: occupancy_labels[index],
        help=t("suggested_occupancy_help"),
        key="calc_suggested_occupancy",
    )
    return st.sidebar.number_input(
        t("applied_occupancy"),
        min_value=0.001,
        max_value=1.0,
        value=float(occupancy_rows[selected_index]["T"]),
        step=0.005,
        format="%.3f",
        help=t("applied_occupancy_help"),
        key="calc_applied_occupancy",
    )


def _custom_goal(framework: str, area_type: str, occupancy_t: float):
    default_goal = reg.design_goal(framework, area_type, occupancy_T=occupancy_t)
    custom_goal_enabled = st.sidebar.checkbox(
        t("custom_goal_toggle"),
        value=False,
        help=t("custom_goal_help"),
        key="calc_custom_goal_enabled",
    )
    if not custom_goal_enabled:
        return default_goal
    custom_goal = st.sidebar.number_input(
        t("custom_goal", unit=default_goal.unit),
        min_value=0.0,
        max_value=100.0,
        value=float(round(default_goal.P_weekly, 5)),
        format="%.5f",
        help=t("custom_goal_input_help"),
        key=f"calc_custom_goal_{framework}_{area_type}",
    )
    st.sidebar.warning(t("custom_goal_warning"))
    return reg.design_goal(
        framework,
        area_type,
        occupancy_T=occupancy_t,
        override_P_weekly=custom_goal,
    )


def _compliance_setup() -> tuple[str, str, float, object]:
    _sidebar_step("02", t("compliance_basis"), t("compliance_help"))
    framework_labels = {
        "NCRP": "NCRP Weekly Design Goals",
        "IAEA_NRRC": "IAEA GSR Part 3 / Saudi NRRC",
    }
    localized_framework_labels = {
        key: term(label)
        for key, label in framework_labels.items()
    }
    framework = st.sidebar.radio(
        t("regulatory_framework"),
        list(framework_labels),
        format_func=lambda key: localized_framework_labels[key],
        key="calc_framework",
    )
    area_labels = {
        "controlled": term("Controlled"),
        "uncontrolled": term("Uncontrolled / Public"),
    }
    area_type = st.sidebar.radio(
        t("area_classification"),
        list(area_labels),
        format_func=lambda classification: area_labels[classification],
        key="calc_area_type",
    )
    occupancy_t = _occupancy_control()
    design_goal = _custom_goal(framework, area_type, occupancy_t)
    applied_limit = design_goal.P_weekly / occupancy_t
    st.sidebar.markdown(
        f'<div class="sl-sidebar-context"><span>{escape(t("applied_design_limit"))}</span>'
        f'<strong>{applied_limit:.4g} {escape(design_goal.unit)}</strong></div>',
        unsafe_allow_html=True,
    )
    return framework_labels[framework], area_type, occupancy_t, design_goal


def sidebar_setup() -> CalculatorSetup:
    st.sidebar.markdown(
        f'<div class="sl-sidebar-label">{escape(t("assessment_setup"))}</div>',
        unsafe_allow_html=True,
    )
    modality_key, modality_config = _equipment_setup()
    framework_label, area_type, occupancy_t, design_goal = _compliance_setup()
    area_label = "Controlled" if area_type == "controlled" else "Uncontrolled / Public"
    return CalculatorSetup(
        modality_key,
        modality_config,
        framework_label,
        area_label,
        occupancy_t,
        design_goal,
    )


def _new_layer(material: str, thickness: float) -> dict:
    return {
        "_id": uuid4().hex,
        "material": material,
        "thickness": float(thickness),
    }


def _clear_layer_widget_state(layer_ids: list[str]) -> None:
    for layer_id in layer_ids:
        for prefix in ("premium_mat", "premium_thk", "premium_rm"):
            st.session_state.pop(f"{prefix}_{layer_id}", None)


def _prepare_layer_state() -> None:
    if "layers" not in st.session_state:
        st.session_state.layers = [_new_layer("concrete", 150.0)]
    for layer in st.session_state.layers:
        layer.setdefault("_id", uuid4().hex)

    if st.session_state.pop("_pending_layer_reset", False):
        old_ids = [layer["_id"] for layer in st.session_state.layers]
        _clear_layer_widget_state(old_ids)
        st.session_state.layers = [_new_layer("concrete", 150.0)]
        st.session_state.pop("_pending_layer_remove", None)
        return

    removal_id = st.session_state.pop("_pending_layer_remove", None)
    if removal_id is None:
        return
    _clear_layer_widget_state([removal_id])
    st.session_state.layers = [
        layer for layer in st.session_state.layers if layer["_id"] != removal_id
    ]


def _layer_row(layer: dict, layer_index: int, material_names: list[str]) -> str | None:
    layer_id = layer["_id"]
    st.markdown(f"**{t('layer', number=layer_index + 1)}**")
    material_col, thickness_col, action_col = st.columns([2.4, 1.55, 0.85])
    material_labels = {material: term(material) for material in material_names}
    layer["material"] = material_col.selectbox(
        t("layer_material", number=layer_index + 1),
        material_names,
        index=(
            material_names.index(layer["material"])
            if layer["material"] in material_names else 0
        ),
        format_func=lambda material: material_labels[material],
        key=f"premium_mat_{layer_id}",
        label_visibility="collapsed",
    )
    layer["thickness"] = thickness_col.number_input(
        t("layer_thickness", number=layer_index + 1),
        0.0,
        100000.0,
        float(layer["thickness"]),
        1.0,
        key=f"premium_thk_{layer_id}",
        label_visibility="collapsed",
    )
    remove_clicked = action_col.button(
        t("remove"),
        key=f"premium_rm_{layer_id}",
        disabled=len(st.session_state.layers) == 1,
        help=t("remove_layer", number=layer_index + 1),
        width="stretch",
    )
    return layer_id if remove_clicked else None


def _layer_actions() -> None:
    add_col, reset_col = st.columns(2)
    if add_col.button(t("add_layer"), key="calc_add_layer", width="stretch"):
        st.session_state.layers.append(_new_layer("lead", 1.0))
        st.rerun()
    if reset_col.button(t("reset_layers"), key="calc_reset_layers", width="stretch"):
        st.session_state["_pending_layer_reset"] = True
        st.rerun()


def barrier_builder() -> ba.Barrier:
    _prepare_layer_state()
    material_names = list(dl.materials()["materials"].keys())
    removal_candidates = [
        _layer_row(layer, layer_index, material_names)
        for layer_index, layer in enumerate(st.session_state.layers)
    ]
    removal_id = next(
        (candidate for candidate in removal_candidates if candidate is not None),
        None,
    )
    if removal_id is not None:
        st.session_state["_pending_layer_remove"] = removal_id
        st.rerun()
    _layer_actions()

    barrier = ba.Barrier()
    for layer in st.session_state.layers:
        barrier.add(layer["material"], layer["thickness"])
    build_description = " + ".join(
        f"{layer['thickness']:g} mm {term(layer['material'])}"
        for layer in st.session_state.layers
    )
    st.caption(
        f"{t('current_build_up')}: **{build_description}** · "
        f"{t('areal_load')} ≈ **{barrier.areal_density_kg_m2():,.0f} kg/m²**"
    )
    return barrier





