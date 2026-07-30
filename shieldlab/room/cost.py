"""
cost.py
=======
Room-level cost roll-up — the Room Designer's answer to "what will this room COST to
build, and is there a cheaper way?".

For every solid wall it asks the same optimiser the single-barrier calculator uses
(shieldlab.physics.optimize) for the thickness each candidate material needs to meet
THAT wall's own design goal, then multiplies by the real wall area to get money and
structural load. Two totals are reported: the room built from the materials currently
selected, and the room built from each wall's cheapest option.

Openings (doors, windows, ducts, mazes) are NOT costed here — they are specified by
lead equivalence or need the Monte-Carlo tier, and their price is a supplier quote
rather than an area x thickness calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .. import data_loader as dl
from ..physics import optimize
from ..physics.optimize import MaterialOption
from .engines import AnalyticalEngine
from .geometry import all_paths
from .model import RoomDesign, WALL_NAMES


@dataclass
class WallCost:
    wall_id: str
    label: str
    area_m2: float
    current_material: str
    options: List[MaterialOption] = field(default_factory=list)
    declared: Optional[MaterialOption] = None   # Check mode: the wall's DECLARED build-up
    note: str = ""

    @property
    def current(self) -> Optional[MaterialOption]:
        """The build currently on this wall.

        In Check mode this is the user's DECLARED build-up (their thickness and layers),
        so cost, load and description reflect what they actually specified — including a
        0 mm, oversized or laminated wall. In Design mode there is no declared thickness,
        so it is the ranked optimiser entry for the wall's chosen material (the suggestion).
        """
        if self.declared is not None:
            return self.declared
        return next((o for o in self.options
                     if o.material == self.current_material and o.feasible), None)

    @property
    def cheapest(self) -> Optional[MaterialOption]:
        return next((o for o in self.options if o.is_cheapest), None)

    def cost_of(self, opt: Optional[MaterialOption]) -> Optional[float]:
        return None if opt is None else opt.cost_per_m2_usd * self.area_m2

    def weight_of(self, opt: Optional[MaterialOption]) -> Optional[float]:
        return None if opt is None else opt.weight_per_m2_kg * self.area_m2


def _declared_build(wall) -> Optional[MaterialOption]:
    """A synthetic MaterialOption describing a wall's DECLARED build-up: cost, areal load
    and depth are summed over the layers the user entered, NOT a recomputed required
    thickness. Returns None only if the wall names no known material."""
    mats = dl.materials()["materials"]
    costs = dl.materials_cost()["materials"]
    raw = [(wall.material1, wall.thickness1_mm)]
    if wall.material2:
        raw.append((wall.material2, wall.thickness2_mm))
    layers = [(m, max(float(t), 0.0)) for m, t in raw if m and m in mats]
    if not layers:
        return None

    total_mm = cost_pm2 = lo_pm2 = hi_pm2 = weight_pm2 = 0.0
    labels: List[str] = []
    unpriced: List[str] = []
    for m, t in layers:
        thick_m = t / 1000.0
        total_mm += t
        weight_pm2 += thick_m * mats[m]["density_kg_m3"]
        labels.append(f"{t:g} mm {mats[m].get('label', m)}")
        c = costs.get(m)
        if c and "installed_cost_usd_per_m3" in c:
            cpm3 = c["installed_cost_usd_per_m3"]
            lo, hi = c.get("range_usd_per_m3", [cpm3, cpm3])
            cost_pm2 += thick_m * cpm3
            lo_pm2 += thick_m * lo
            hi_pm2 += thick_m * hi
        else:
            unpriced.append(m)

    return MaterialOption(
        material=" + ".join(dict.fromkeys(m for m, _ in layers)),
        label=" + ".join(labels),
        required_mm=total_mm, preferred_mm=total_mm,
        cost_per_m2_usd=cost_pm2, cost_low_usd=lo_pm2, cost_high_usd=hi_pm2,
        weight_per_m2_kg=weight_pm2, space_mm=total_mm,
        feasible=True, already_met=(total_mm <= 0.0),
        note=("no cost data for " + ", ".join(unpriced)) if unpriced else "")


def wall_area_m2(design: RoomDesign, wall_id: str) -> float:
    """N/S walls span the room width, E/W walls span its length; both use the height."""
    span = design.room.width_m if wall_id in ("N", "S") else design.room.length_m
    return span * design.room.height_m


def room_costs(design: RoomDesign, mode: str = "design") -> Dict:
    """Per-wall ranked options + whole-room totals.

    `mode` : "check" costs each wall's DECLARED build (the thickness/layers the user
    entered); "design" costs the optimiser's suggested build for the wall's material.

    Returns {"walls": [WallCost], "total_current_usd", "total_cheapest_usd",
             "saving_usd", "total_current_weight_kg", "priced_walls", "total_walls"}.
    """
    engine = AnalyticalEngine(design)
    wall_by_id = {w.id: w for w in design.walls}
    walls: List[WallCost] = []

    for path in all_paths(design):
        if path.kind != "wall":
            continue                              # openings are quoted, not area-costed
        wall = wall_by_id[path.wall_id]
        wc = WallCost(wall_id=wall.id,
                      label=f"Wall {wall.id} — {WALL_NAMES.get(wall.id, '')}",
                      area_m2=wall_area_m2(design, wall.id),
                      current_material=wall.material1)
        try:
            source = engine._source(path)
            goal = engine._goal(wall)
            wc.options = optimize.rank_options(source, goal)
        except Exception as exc:                  # keep the room costable if one wall fails
            wc.note = f"Not costed: {exc}"
        if mode == "check":                       # cost what the user declared, not a re-solve
            wc.declared = _declared_build(wall)
        walls.append(wc)

    cur = [w.cost_of(w.current) for w in walls]
    chp = [w.cost_of(w.cheapest) for w in walls]
    wgt = [w.weight_of(w.current) for w in walls]
    priced = sum(1 for c in cur if c is not None)
    total_cur = sum(c for c in cur if c is not None)
    total_chp = sum(c for c in chp if c is not None)
    return {
        "walls": walls,
        "total_current_usd": total_cur,
        "total_cheapest_usd": total_chp,
        "saving_usd": max(total_cur - total_chp, 0.0),
        "total_current_weight_kg": sum(w for w in wgt if w is not None),
        "priced_walls": priced,
        "total_walls": len(walls),
    }


def headline(costs: Dict) -> Optional[str]:
    """One-line room-level summary, or None if nothing could be priced."""
    if not costs["priced_walls"]:
        return None
    cur, save = costs["total_current_usd"], costs["saving_usd"]
    msg = (f"Shielding for the {costs['priced_walls']} solid walls as currently specified: "
           f"**~${cur:,.0f}** ({costs['total_current_weight_kg']:,.0f} kg of material).")
    if save > 0.01 * max(cur, 1):
        msg += (f"  Switching each wall to its cheapest qualifying material would cost "
                f"**~${costs['total_cheapest_usd']:,.0f}** — a saving of **~${save:,.0f}**.")
    else:
        msg += "  The current material choice is already at (or within 1% of) the cheapest option."
    return msg
