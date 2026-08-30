"""Coverage for the TreeSHAP failure explanation an RSO actually reads.

Audit finding F-09. `decision_support.shap_failure_explanations` had zero coverage:
it returns early unless `shap` is importable, and shap is deliberately excluded from
the runtime requirements because it is heavy. So the branch only ever executed in
environments where somebody had installed it by hand -- never in the test suite.

shap is now declared in requirements-dev.txt and installed by CI, so this module
exercises the real path. It still skips cleanly where shap or the trained bundle is
absent, so an analytical-only deployment stays green.
"""

from __future__ import annotations

import pytest

from shieldlab.room.decision_support import (
    explain_failures,
    shap_failure_explanations,
    summarize_results,
)
from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine
from shieldlab.room.model import AdjacentArea, RoomDesign

shap = pytest.importorskip("shap", reason="shap is an optional explanation dependency")


def _under_shielded_room(thickness_mm: float = 40.0) -> RoomDesign:
    """A room thin enough that barriers fail, which is what triggers an explanation."""
    design = RoomDesign.default()
    design.source.isotope = "F-18"
    design.source.activity_MBq = 370.0
    design.room.width_m, design.room.length_m = 7.0, 5.0
    design.source.x_m, design.source.y_m = 3.5, 2.5
    for wall in design.walls:
        wall.material1 = "concrete"
        wall.thickness1_mm = thickness_mm
    design.wall("N").adjacent = AdjacentArea("Control", 1.0, "controlled", None)
    return design


@pytest.fixture
def failing_case():
    design = _under_shielded_room()
    engine = SurrogateEngine(design)
    if not engine.available():
        pytest.skip("surrogate_bundle.joblib is not available")
    analytical = AnalyticalEngine(design).evaluate_all("check")
    surrogate = engine.evaluate_all("check", analytical)
    if not any(result.passes is False for result in surrogate):
        pytest.skip("no failing barrier in this configuration")
    return design, engine, analytical, surrogate


def test_the_room_verdict_is_a_failure(failing_case):
    _design, _engine, _analytical, surrogate = failing_case
    assert summarize_results(surrogate)["status"] in {"FAIL", "MARGINAL"}


def test_shap_explanations_are_produced_for_failing_surrogate_paths(failing_case):
    design, engine, analytical, surrogate = failing_case
    explanations = shap_failure_explanations(
        engine, design, "check", analytical, surrogate
    )
    surrogate_failures = [
        result.label for result in surrogate
        if result.passes is False and result.engine == "surrogate"
    ]
    if not surrogate_failures:
        pytest.skip("every failing path fell back to the analytical engine")

    assert explanations, "shap is installed and paths failed, so an attribution is due"
    for label, message in explanations.items():
        assert label in surrogate_failures
        assert "SHAP" in message
        assert "log10 transmission" in message
        # The attribution must name a real feature, in the reader's language rather
        # than the model's column name.
        assert not any(raw in message for raw in ("zeff", "det_offset_mm", "layer2_"))


def test_no_explanations_when_nothing_fails(failing_case):
    """A comfortably shielded room must not manufacture a driver for a passing path."""
    design, _engine, _analytical, _surrogate = failing_case
    for wall in design.walls:
        wall.thickness1_mm = 600.0
    engine = SurrogateEngine(design)
    analytical = AnalyticalEngine(design).evaluate_all("check")
    surrogate = engine.evaluate_all("check", analytical)
    assert shap_failure_explanations(engine, design, "check", analytical, surrogate) == {}


def test_physics_explanations_remain_available_alongside_shap(failing_case):
    """The physics-aware text is the fallback and must not be displaced by shap."""
    design, _engine, _analytical, surrogate = failing_case
    physics = explain_failures(design, surrogate)
    assert physics, "a failing barrier must always carry an actionable explanation"
    for entry in physics:
        assert entry["barrier"] and entry["message"]


def test_missing_shap_degrades_to_no_attribution(failing_case, monkeypatch):
    """Removing shap must return {} rather than raising: the app ships without it."""
    import builtins

    design, engine, analytical, surrogate = failing_case
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "shap":
            raise ImportError("shap disabled for this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert shap_failure_explanations(engine, design, "check", analytical, surrogate) == {}
