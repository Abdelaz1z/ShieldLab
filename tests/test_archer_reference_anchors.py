"""Numerical anchors derived from NCRP 147 B.1/C.1, not the JSON being tested.

Printed pp. 133-134 and 147-148, locally licensed copy, rechecked 2026-11-03.
These cover transcription regressions; they do not validate a scanner spectrum.
"""

import pytest

from shieldlab.physics import beams as bm
from shieldlab.physics import barriers, solver, sources
from shieldlab.regulatory import limits


@pytest.mark.parametrize("component,distribution,material,thickness,expected", [
    ("primary", "rad_room_all", "concrete", 100, 0.00139494474814),
    ("primary", "mammography", "lead", 0.1, 0.000437306447621),
    ("primary", "mammography", "gypsum", 20, 0.00190561518825),
    ("primary", "chest_room", "wood", 100, 0.511912510339),
    ("secondary", "rad_room_all", "concrete", 100, 0.00188579283505),
    ("secondary", "chest_room", "wood", 100, 0.511703314058),
    ("secondary", "mammography", "wood", 30, 0.209760425018),
    ("secondary", 125, "wood", 100, 0.562523100305),
    ("secondary", 30, "concrete", 10, 0.000621059526221),
])
def test_reference_transmission_catches_exponent_sign_and_row_errors(
    component, distribution, material, thickness, expected,
):
    beam = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component=component)
    if isinstance(distribution, int):
        beam.kvp = distribution
    else:
        beam.distribution = distribution
    assert bm.transmission_of_layer(beam, material, thickness) == pytest.approx(expected, rel=1e-9)


def test_ct_mixed_workload_matches_dlp_and_125kvp_table_calculation():
    # NCRP head/body example normalization plus independently calculated C.1 values.
    # This checks the implemented approximation, not a scanner-specific spectrum.
    source = sources.ct_source([
        sources.CTExamWorkload("body_average", 770, 150),
        sources.CTExamWorkload("head", 1680, 30),
    ], 3, kvp=120)
    goal = limits.design_goal("NCRP", "uncontrolled")
    evaluation = solver.evaluate(source, barriers.Barrier().add("concrete", 150), goal)
    assert evaluation.transmitted_total == pytest.approx(0.00695529137468, rel=1e-9)
    assert solver.required_thickness(source, "concrete", goal) == pytest.approx(120.399372, abs=.002)
    assert evaluation.verdict.status == "REVIEW"
