"""
test_optimize.py
================
Tests for the cost / material optimiser (shieldlab.physics.optimize).

Run:  py -3.11 -m pytest tests/test_optimize.py -v
or:   py -3.11 tests/test_optimize.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shieldlab.physics import sources as src, optimize
from shieldlab.regulatory import limits as reg


def _i131_case():
    source = src.radionuclide_point_source("I-131", 200.0, 3.0, hours_per_week=40.0)
    goal = reg.design_goal("NCRP", "controlled", occupancy_T=1.0)
    return optimize.rank_options(source, goal)


def test_returns_common_materials():
    """Lead, concrete and steel all have a transmission path + cost -> must appear."""
    opts = _i131_case()
    mats = {o.material for o in opts}
    assert {"lead", "concrete", "steel"} <= mats


def test_sorted_cheapest_first_among_feasible():
    opts = _i131_case()
    feas = [o for o in opts if o.feasible]
    costs = [o.cost_per_m2_usd for o in feas]
    assert costs == sorted(costs), "feasible options must be ranked cheapest-first"


def test_exactly_one_winner_per_axis():
    opts = _i131_case()
    assert sum(o.is_cheapest for o in opts) == 1
    assert sum(o.is_lightest for o in opts) == 1
    assert sum(o.is_thinnest for o in opts) == 1


def test_physics_sanity():
    """For a 364 keV source: concrete is the cheapest, lead the thinnest & lightest."""
    opts = _i131_case()
    by = {o.material: o for o in opts}
    assert by["concrete"].is_cheapest
    assert by["lead"].is_thinnest and by["lead"].is_lightest
    # lead needs far less thickness but costs much more per m^2 than concrete
    assert by["lead"].preferred_mm < by["concrete"].preferred_mm
    assert by["lead"].cost_per_m2_usd > by["concrete"].cost_per_m2_usd


def test_all_feasible_have_positive_numbers():
    for o in _i131_case():
        if o.feasible and not o.already_met:
            assert o.preferred_mm > 0 and o.weight_per_m2_kg > 0 and o.cost_per_m2_usd > 0
            assert o.cost_low_usd <= o.cost_per_m2_usd <= o.cost_high_usd


def test_headline_nonempty():
    assert optimize.headline(_i131_case())


def test_diagnostic_source_also_ranks():
    """A diagnostic (Archer) beam must also produce a ranking (lead + concrete at least)."""
    source = src.diagnostic_source("rad_room", 200, 2.0, 1.5, kvp=100,
                                   include_primary=True, secondary_geometry="leak_forward_back")
    goal = reg.design_goal("NCRP", "uncontrolled", occupancy_T=1.0)
    opts = optimize.rank_options(source, goal)
    mats = {o.material for o in opts if o.feasible}
    assert {"lead", "concrete"} <= mats


# --- room-level cost roll-up -------------------------------------------------

def _room_costs():
    from shieldlab.room.model import RoomDesign
    from shieldlab.room import cost
    return cost.room_costs(RoomDesign.default()), cost


def test_room_prices_all_four_walls():
    c, _ = _room_costs()
    assert c["total_walls"] == 4 and c["priced_walls"] == 4


def test_room_wall_areas_follow_room_dimensions():
    from shieldlab.room.model import RoomDesign
    from shieldlab.room import cost
    d = RoomDesign.default()
    # N/S span the width, E/W span the length; both use the height
    assert cost.wall_area_m2(d, "N") == d.room.width_m * d.room.height_m
    assert cost.wall_area_m2(d, "E") == d.room.length_m * d.room.height_m


def test_room_totals_are_consistent():
    c, _ = _room_costs()
    assert c["total_current_usd"] > 0 and c["total_current_weight_kg"] > 0
    # the cheapest-mix total can never exceed the as-specified total
    assert c["total_cheapest_usd"] <= c["total_current_usd"] + 1e-6
    assert abs(c["saving_usd"] - max(c["total_current_usd"] - c["total_cheapest_usd"], 0)) < 1e-6


def test_room_every_wall_has_a_cheapest_flag():
    c, _ = _room_costs()
    for w in c["walls"]:
        assert w.cheapest is not None, f"{w.label} has no cheapest option"
        assert w.cost_of(w.cheapest) <= w.cost_of(w.current) + 1e-6


def test_room_headline_nonempty():
    c, cost_mod = _room_costs()
    assert cost_mod.headline(c)


# --- regulatory submission document ------------------------------------------

def _submission(costs=True, meta=None):
    from shieldlab.room.model import RoomDesign
    from shieldlab.room.engines import AnalyticalEngine, SurrogateEngine
    from shieldlab.room import diagram, report_room, cost, report_regulatory
    design = RoomDesign.default()
    eng = AnalyticalEngine(design)
    results = eng.evaluate_all("design")
    sur = SurrogateEngine(design)
    sur_res = sur.evaluate_all("design", results) if sur.available() else None
    png = diagram.render(design, sur_res or results)
    report = report_room.build_report(design, results, "design", png, surrogate_results=sur_res)
    rc = cost.room_costs(design) if costs else None
    m = meta or {"facility": "Test Hospital", "room_ref": "PET-1", "licence": "L-1",
                 "prepared_by": "RSO", "reviewed_by": "QE", "doc_ref": "D-1", "revision": "0"}
    return report_regulatory.build_submission_html(report, m, costs=rc).decode("utf-8")


def test_submission_contains_all_required_sections():
    html = _submission()
    for section in ["1. Identification", "2. Purpose, scope and regulatory basis",
                    "3. Design assumptions", "5. Method", "6. Barrier-by-barrier compliance",
                    "7. Findings", "8. Assumptions, limitations", "Declaration"]:
        assert section in html, f"missing section: {section}"


def test_submission_cost_appendix_is_optional():
    assert "Appendix A" in _submission(costs=True)
    assert "Appendix A" not in _submission(costs=False)


def test_submission_escapes_user_supplied_metadata():
    """Facility/room fields are free text — they must never inject markup."""
    meta = {"facility": "<script>alert(1)</script>", "room_ref": "R&D <b>x</b>",
            "licence": "L", "prepared_by": "P", "reviewed_by": "R",
            "doc_ref": "D", "revision": "0"}
    html = _submission(meta=meta)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_brick_is_offered_as_a_wall_material():
    """Brick gained TVL data, so it must now appear in the Room Designer palette."""
    from shieldlab.room.engines import usable_wall_materials
    assert "brick" in usable_wall_materials("F-18")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS {fn.__name__}"); passed += 1
        except Exception as exc:
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{passed}/{len(fns)} passed")
