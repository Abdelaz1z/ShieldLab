"""
test_room_geometry.py — hand-computed geometry checks for the Room Designer.
Run: py -3.11 tests/test_room_geometry.py   (also pytest-compatible)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radshield.room.model import RoomDesign, Opening
from radshield.room.geometry import all_paths, POP_STANDOFF_M


def _design():
    d = RoomDesign.default()
    d.room.width_m, d.room.length_m = 6.0, 4.0
    d.source.x_m, d.source.y_m = 3.0, 2.0     # centred in x, mid in y
    return d


def test_wall_distances():
    d = _design()
    paths = {p.wall_id: p for p in all_paths(d) if p.kind == "wall"}
    # perpendicular: N=4-2=2, S=2, E=6-3=3, W=3 ; d_pop = perp + 0.3
    assert abs(paths["N"].perp_m - 2.0) < 1e-9
    assert abs(paths["S"].perp_m - 2.0) < 1e-9
    assert abs(paths["E"].perp_m - 3.0) < 1e-9
    assert abs(paths["W"].perp_m - 3.0) < 1e-9
    for wid, perp in (("N", 2.0), ("S", 2.0), ("E", 3.0), ("W", 3.0)):
        assert abs(paths[wid].d_pop_m - (perp + POP_STANDOFF_M)) < 1e-9
        assert abs(paths[wid].offset_m) < 1e-9   # walls are on-axis


def test_opening_offset_and_slant():
    d = _design()
    # duct on Wall N, 1 m East of the source's x (source x=3 -> duct at x=4)
    d.wall("N").openings.append(Opening(kind="duct", center_along_wall_m=4.0, radius_mm=25))
    duct = [p for p in all_paths(d) if p.kind == "duct"][0]
    assert abs(duct.offset_m - 1.0) < 1e-9            # |4 - 3|
    # slant distance = hypot(perp+0.3, offset) = hypot(2.3, 1.0)
    assert abs(duct.d_pop_m - (2.3 ** 2 + 1.0 ** 2) ** 0.5) < 1e-9
    assert abs(duct.duct_radius_mm - 25) < 1e-9


def test_pop_beyond_wall():
    d = _design()
    paths = {p.wall_id: p for p in all_paths(d) if p.kind == "wall"}
    # POP sits 0.3 m beyond the outer face
    assert abs(paths["N"].pop_xy[1] - (4.0 + 0.3)) < 1e-9
    assert abs(paths["S"].pop_xy[1] - (-0.3)) < 1e-9
    assert abs(paths["E"].pop_xy[0] - (6.0 + 0.3)) < 1e-9
    assert abs(paths["W"].pop_xy[0] - (-0.3)) < 1e-9


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"[PASS] {name}")
            except AssertionError as e:
                fails += 1; print(f"[FAIL] {name}: {e}")
    print("\nALL PASS" if fails == 0 else f"\n{fails} FAILED")
    sys.exit(fails)
