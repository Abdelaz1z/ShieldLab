"""
geometry.py
===========
Turns a RoomDesign into the geometric quantities the shielding engines need:
per-wall perpendicular distances, the point of protection (POP) for each wall and
each opening, the source-to-POP distance for the inverse-square term, and the
lateral offset of each POP from the source's perpendicular foot (the feature the
surrogate tier uses for off-axis geometry).

Convention (top view, metres): origin at the SW corner, +x = East, +y = North.
The POP sits 0.3 m beyond the barrier's inner face on the line from the source
perpendicular to that wall (NCRP-151 point of protection). The wall thickness is
neglected in the source-to-POP distance — a small, conservative simplification
that keeps Design and Check modes on an identical distance so results are stable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .model import RoomDesign, Wall, Opening

POP_STANDOFF_M = 0.3   # NCRP: point of protection 0.3 m beyond the barrier surface


@dataclass
class BarrierPath:
    """One source -> occupied-point path (a wall, or an opening in a wall)."""
    wall_id: str
    kind: str                 # 'wall' | 'door' | 'window' | 'duct'
    label: str                # human label for tables/diagram
    d_pop_m: float            # source-to-POP straight-line distance (inverse square)
    perp_m: float             # perpendicular source-to-wall distance
    offset_m: float           # lateral offset of the POP from the perpendicular foot
    pop_xy: tuple             # (x, y) of the POP in room coords (for the diagram)
    duct_radius_mm: float = 0.0
    lead_equiv_mm: float = 0.0
    # maze-only pass-through (corner surrogate features):
    ret_material: str = ""
    ret_thickness_mm: float = 0.0
    corridor_m: float = 0.0
    shadow_offset_m: float = 0.0


def _perp_distance(design: RoomDesign, wid: str) -> float:
    """Perpendicular distance (m) from the source to a wall's inner face."""
    r, s = design.room, design.source
    return {
        "N": r.length_m - s.y_m,
        "S": s.y_m,
        "E": r.width_m - s.x_m,
        "W": s.x_m,
    }[wid]


def _along_coord(design: RoomDesign, wid: str) -> float:
    """The source's coordinate ALONG the wall (used to place POPs and offsets).

    For N/S walls the wall runs W->E, so the along-coordinate is x.
    For E/W walls the wall runs S->N, so the along-coordinate is y.
    """
    s = design.source
    return s.x_m if wid in ("N", "S") else s.y_m


def _pop_xy(design: RoomDesign, wid: str, along_m: float, out_m: float) -> tuple:
    """POP coordinates: `along_m` position on the wall, `out_m` beyond its face."""
    r = design.room
    if wid == "N":
        return (along_m, r.length_m + out_m)
    if wid == "S":
        return (along_m, -out_m)
    if wid == "E":
        return (r.width_m + out_m, along_m)
    return (-out_m, along_m)   # W


def wall_path(design: RoomDesign, wall: Wall) -> BarrierPath:
    """The on-axis barrier path for a wall (POP on the source perpendicular)."""
    perp = _perp_distance(design, wall.id)
    along = _along_coord(design, wall.id)          # POP directly out from the source
    d_pop = perp + POP_STANDOFF_M
    pop = _pop_xy(design, wall.id, along, POP_STANDOFF_M)
    return BarrierPath(
        wall_id=wall.id, kind="wall", label=f"Wall {wall.id}",
        d_pop_m=d_pop, perp_m=perp, offset_m=0.0, pop_xy=pop,
    )


def opening_path(design: RoomDesign, wall: Wall, op: Opening) -> BarrierPath:
    """The barrier path through an opening (POP at the opening's lateral position).

    For a MAZE the shadowed point sits `corridor_m` beyond the wall and
    `shadow_offset_m` laterally past the mouth (behind the return wall); the corner
    surrogate's B is referenced to the free field at exactly that point, so d_pop
    is the straight-line distance to it (documented approximation of the corner
    sub-study geometry)."""
    perp = _perp_distance(design, wall.id)
    src_along = _along_coord(design, wall.id)
    # opening centre is measured from the wall's start corner (W for N/S, S for E/W)
    op_along = op.center_along_wall_m
    if op.kind == "maze":
        out_m = POP_STANDOFF_M + op.corridor_m
        pop_along = op_along + op.shadow_offset_m
        offset = abs(pop_along - src_along)
        d_pop = math.hypot(perp + out_m, offset)
        pop = _pop_xy(design, wall.id, pop_along, out_m)
        return BarrierPath(
            wall_id=wall.id, kind="maze", label=f"Wall {wall.id} · maze",
            d_pop_m=d_pop, perp_m=perp, offset_m=offset, pop_xy=pop,
            ret_material=op.ret_material, ret_thickness_mm=op.ret_thickness_mm,
            corridor_m=op.corridor_m, shadow_offset_m=op.shadow_offset_m,
        )
    offset = abs(op_along - src_along)
    d_pop = math.hypot(perp + POP_STANDOFF_M, offset)   # true slant distance off-axis
    pop = _pop_xy(design, wall.id, op_along, POP_STANDOFF_M)
    return BarrierPath(
        wall_id=wall.id, kind=op.kind,
        label=f"Wall {wall.id} · {op.kind}",
        d_pop_m=d_pop, perp_m=perp, offset_m=offset, pop_xy=pop,
        duct_radius_mm=op.radius_mm, lead_equiv_mm=op.lead_equiv_mm,
    )


def all_paths(design: RoomDesign) -> List[BarrierPath]:
    """Every barrier path in the room: 4 walls + each opening."""
    paths: List[BarrierPath] = []
    for w in design.walls:
        paths.append(wall_path(design, w))
        for op in w.openings:
            paths.append(opening_path(design, w, op))
    return paths
