"""
test_transport_engine.py - the Monte Carlo room tier: the 3D room it builds from a design, and its
transport (deterministic for a design and a seed). Skips the transport checks without numba.
Run: py -3.11 -m pytest tests/test_transport_engine.py
"""
import itertools
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shieldlab.room import transport_engine as te
from shieldlab.room.model import Opening, RoomDesign


def _design():
    d = RoomDesign.default()
    d.room.width_m, d.room.length_m, d.room.height_m = 5.0, 4.0, 2.8
    d.source.x_m, d.source.y_m = 2.0, 1.5
    for w in d.walls:
        w.thickness1_mm = 200.0
    d.wall("N").material2, d.wall("N").thickness2_mm = "lead", 4.0
    d.wall("E").openings.append(Opening(kind="door", center_along_wall_m=2.5, width_m=1.0, lead_equiv_mm=2.0))
    d.wall("S").openings.append(Opening(kind="window", center_along_wall_m=1.0, width_m=1.2, lead_equiv_mm=3.0))
    d.wall("W").openings.append(Opening(kind="duct", center_along_wall_m=2.0, radius_mm=50))
    return d


def _overlap(a, b) -> float:
    return math.prod(max(0.0, min(a.hi[k], b.hi[k]) - max(a.lo[k], b.lo[k])) for k in range(3))


def test_boxes_do_not_overlap():
    room = te.build_room(_design())
    for a, b in itertools.combinations(room.boxes, 2):
        assert _overlap(a, b) < 1e-12, (a, b)


def test_walls_close_the_room():
    """Every ray from the source to a point outside passes through material: the wall boxes
    cover each wall's whole face, less its openings, and the slabs cover the corners."""
    d = _design()
    room = te.build_room(d)
    volume = {m: 0.0 for m in room.densities}
    for b in room.boxes:
        volume[b.material] += math.prod(h - l for l, h in zip(b.lo, b.hi))
    r = d.room
    t = {"N": 0.204, "E": 0.2, "S": 0.2, "W": 0.2}
    walls = ((r.width_m + t["E"] + t["W"]) * (t["N"] + t["S"]) + r.length_m * (t["E"] + t["W"])) * r.height_m
    door = 1.0 * 2.1 * 0.2
    window = 1.2 * 1.0 * 0.2
    lead_in_n = (r.width_m + t["E"] + t["W"]) * 0.004 * r.height_m
    slabs = 2 * (r.width_m + t["E"] + t["W"]) * (r.length_m + t["N"] + t["S"]) * te.SLAB_M
    assert volume["concrete"] == pytest.approx(walls - lead_in_n - door - window + slabs, rel=1e-9)
    assert volume["lead"] == pytest.approx(lead_in_n + 1.0 * 2.1 * 0.002 + 1.2 * 1.0 * 0.003, rel=1e-9)


def test_points_beyond_the_outer_face_at_source_height():
    room = te.build_room(_design())
    pts = {p.label: p.xyz for p in room.points}
    assert pts["Wall N"] == pytest.approx((2.0, 4.0 + 0.204 + 0.3, 1.0))
    assert pts["Wall S"] == pytest.approx((2.0, -0.5, 1.0))
    assert pts["Wall E · door"] == pytest.approx((5.5, 2.5, 1.0))
    assert pts["Wall S · window"] == pytest.approx((1.0, -0.5, 1.0))
    assert "Wall W · duct" not in pts


def test_layer_override_changes_only_that_wall():
    d = _design()
    room = te.build_room(d, {"S": [("lead", 5.0)]})
    pts = {p.label: p.xyz for p in room.points}
    assert pts["Wall S"][1] == pytest.approx(-0.305)
    assert pts["Wall N"][1] == pytest.approx(4.504)


def test_densities_are_the_products():
    room = te.build_room(_design())
    assert room.densities == {"concrete": 2.35, "lead": 11.35}


needs_numba = pytest.mark.skipif(not te.available(), reason="numba or transport tables missing")


@needs_numba
def test_transport_is_deterministic_and_sane(monkeypatch):
    monkeypatch.setattr(te, "MAX_HISTORIES", 20_000)
    monkeypatch.setattr(te, "CHUNK", 10_000)
    d = _design()
    first, kerma = te.TransportEngine(d).evaluate_all()
    second, _ = te.TransportEngine(d).evaluate_all()
    assert [r.dose_mSv_wk for r in first] == [r.dose_mSv_wk for r in second]
    by = {r.label: r for r in first}
    assert by["Wall W · duct"].dose_mSv_wk is None
    assert kerma.histories == 20_000
    # 4 mm lead on N transmits less than the bare 200 mm concrete on S at a similar distance
    assert by["Wall N"].B_achieved < by["Wall S"].B_achieved
    for r in first:
        if r.dose_mSv_wk is not None:
            assert 0.0 < r.B_achieved < 1.5


@needs_numba
def test_free_air_kerma_matches_an_empty_room():
    """No barrier: the transported kerma at 2 m equals the inverse square (air only)."""
    d = RoomDesign.default()
    d.room.width_m, d.room.length_m, d.room.height_m = 40.0, 40.0, 40.0
    d.source.x_m = d.source.y_m = 20.0
    for w in d.walls:
        w.thickness1_mm = 0.0
    room = te.build_room(d)
    room.boxes = []
    room.points = [te.TallyPoint("p", (22.0, 20.0, 1.0))]
    kerma = te.transport(room, "F-18")
    assert kerma.total_gy[0] / te.free_air_gy("F-18", 2.0) == pytest.approx(1.0, abs=0.02)
