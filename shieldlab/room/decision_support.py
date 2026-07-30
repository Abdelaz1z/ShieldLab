"""Decision-oriented summaries and safe, physics-aware failure explanations."""

from __future__ import annotations

from typing import Dict, Iterable, List

from .engines import EngineResult
from .geometry import all_paths
from .model import RoomDesign


MARGINAL_MARGIN = 1.20


def summarize_results(results: Iterable[EngineResult]) -> Dict:
    """Return the safety status for a set of barrier-path evaluations.

    Every barrier path has its own point of interest and regulatory threshold, so
    the room verdict is governed by the path with the smallest safety margin.
    """
    evaluated = [result for result in results if result.dose_mSv_wk is not None
                 and result.goal_over_T is not None]
    unknown = [result for result in results if result.passes is None]
    failed = [result for result in evaluated if result.passes is False]
    critical = min(
        evaluated,
        key=lambda result: result.margin if result.margin is not None else float("inf"),
        default=None,
    )

    ci_over_limit = False
    if critical and critical.ci_high and critical.B_achieved and critical.B_achieved > 0:
        upper_dose = critical.dose_mSv_wk * critical.ci_high / critical.B_achieved
        ci_over_limit = upper_dose > critical.goal_over_T

    if failed:
        status, message = "FAIL", "At least one evaluated barrier exceeds its regulatory design goal."
    elif unknown:
        status, message = "MARGINAL", "One or more paths require detailed Monte-Carlo evaluation."
    elif critical is None:
        status, message = "MARGINAL", "No barrier path could be evaluated."
    elif critical.margin is not None and critical.margin < MARGINAL_MARGIN:
        status, message = "MARGINAL", "The critical barrier is within 20% of its regulatory design goal."
    elif ci_over_limit:
        status, message = "MARGINAL", "The surrogate 95% upper confidence bound crosses the design goal."
    else:
        status, message = "PASS", "All evaluated barrier paths meet their regulatory design goals."

    return {
        "status": status,
        "message": message,
        "critical": critical,
        "evaluated_count": len(evaluated),
        "unknown_count": len(unknown),
        "failed_count": len(failed),
        "ci_over_limit": ci_over_limit,
    }


def explain_failures(design: RoomDesign, results: Iterable[EngineResult]) -> List[Dict[str, str]]:
    """Produce transparent engineering explanations for failed barrier paths.

    The deployed surrogate bundle does not contain SHAP artifacts. These messages
    deliberately use the model inputs and shielding physics rather than presenting
    an unverified attribution as a SHAP value.
    """
    explanations = []
    for result in results:
        if result.passes is not False:
            continue
        wall_id = result.label.split()[1] if result.label.startswith("Wall ") else None
        wall = design.wall(wall_id) if wall_id else None
        label = result.label
        if "duct" in label.lower():
            body = (
                "Duct radius is the dominant leakage driver: the air channel bypasses the "
                "solid barrier. Reduce the duct diameter, add a shielded bend/maze, or obtain "
                "a detailed Monte-Carlo assessment before approval."
            )
        elif "door" in label.lower() or "window" in label.lower():
            body = (
                "The opening's lead-equivalent shielding is insufficient for this workload. "
                "Increase the rated lead equivalence or relocate the protected point."
            )
        elif wall is not None:
            material = wall.material1.replace("_", " ")
            body = (
                f"The {wall.thickness1_mm:g} mm {material} barrier does not provide enough "
                "attenuation for the selected activity and weekly workload. Increase shielding, "
                "reduce workload, or increase separation from the occupied area."
            )
        else:
            body = "The calculated shielding margin is below the regulatory design goal."
        explanations.append({"barrier": label, "message": body})
    return explanations


def shap_failure_explanations(surrogate_engine, design: RoomDesign, mode: str,
                              analytical_results: Iterable[EngineResult],
                              surrogate_results: Iterable[EngineResult]) -> Dict[str, str]:
    """Return TreeSHAP explanations for failed, in-domain surrogate predictions.

    The explanation is only available when the deployed Extra-Trees surrogate and
    the optional ``shap`` package are both present. Other paths retain the safer
    physics-aware explanation from :func:`explain_failures`.
    """
    try:
        import numpy as np
        import shap
    except ImportError:
        return {}

    if not surrogate_engine.available():
        return {}
    model = surrogate_engine.bundle.get("model")
    feature_names = surrogate_engine.bundle.get("features", [])
    if model is None or not feature_names:
        return {}

    analytical = {result.label: result for result in analytical_results}
    surrogate = {result.label: result for result in surrogate_results}
    walls = {wall.id: wall for wall in design.walls}
    labels = {
        "primary_energy_keV": "photon energy",
        "thickness_mm": "barrier thickness",
        "duct_radius_mm": "duct radius",
        "det_offset_mm": "detector offset",
        "zeff": "primary material atomic number",
        "density_gcm3": "primary material density",
        "layer2_thickness_mm": "second-layer thickness",
        "layer2_zeff": "second-layer atomic number",
    }
    try:
        explainer = shap.TreeExplainer(model)
    except Exception:
        return {}
    explanations = {}
    for path in all_paths(design):
        result = surrogate.get(path.label)
        if not result or result.passes is not False or result.engine != "surrogate":
            continue
        wall = walls[path.wall_id]
        analytical_result = analytical.get(path.label)
        if path.kind in ("door", "window"):
            thickness = path.lead_equiv_mm
        elif mode == "design" and analytical_result and analytical_result.suggested_thickness_mm is not None:
            thickness = analytical_result.suggested_thickness_mm
        else:
            thickness = wall.thickness1_mm
        features = surrogate_engine._features(path, wall, thickness)
        if features is None:
            continue
        try:
            values = np.asarray(explainer.shap_values(features), dtype=float).reshape(-1)
        except Exception:
            continue
        if len(values) != len(feature_names):
            continue
        feature_index = max(range(len(values)), key=lambda index: values[index])
        shap_value = values[feature_index]
        if shap_value <= 0:
            feature_index = max(range(len(values)), key=lambda index: abs(values[index]))
            shap_value = values[feature_index]
            qualifier = "largest model influence"
        else:
            qualifier = "largest dose-increasing driver"
        feature = labels.get(feature_names[feature_index], feature_names[feature_index])
        explanations[path.label] = (
            f"The MC surrogate's SHAP attribution identifies {feature} as the {qualifier} "
            f"(SHAP {shap_value:+.2f} in log10 transmission)."
        )
    return explanations
