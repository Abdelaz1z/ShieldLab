"""
transport_engine.py
===================
The Monte Carlo room tier: the room is built in 3D and photons are transported through it
(`transport_mc`), so the dose at each point of protection includes what scatters off the floor,
the ceiling and the other walls and comes round a barrier, not only what goes straight through.

The analytical and surrogate tiers see one barrier at a time on a straight line. Behind thick
barriers that misses most of the dose (research Room-1, 2026-09-27: both scored 0 there). This tier
was validated against GATE in a second, pre-registered room (Room-2, 2026-09-28).

What the room is, since ShieldLab's design has no input for it (stated in every result):
  * the walls stand on a 200 mm concrete floor slab under a 200 mm concrete ceiling slab;
  * layer 1 of a wall is its inner (source-side) layer;
  * a door fills 0-2.1 m of the wall's height and a window 1.0-2.0 m, as a lead sheet of the
    opening's lead equivalent at the wall's inner face (air elsewhere in the opening);
  * the source is a bare point at 1.0 m above the floor; no patient body;
  * each point of protection is 0.3 m beyond the wall's OUTER face, at source height;
  * ducts and mazes are not built (their paths are left to the surrogate tier).

The dose at a point is the unshielded dose of the analytical tier at that point's distance times
the transported-to-free-air kerma ratio, so the source term (Gamma, workload) is the app's own.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from . import transport_mc
from .engines import AnalyticalEngine, EngineResult
from .geometry import BarrierPath, all_paths
from .model import RoomDesign, Wall
from .surrogate_e import PHOTON_LINES
from .transport_materials import product_density_gcm3

SLAB_M = 0.20
SLAB_MATERIAL = "concrete"
SOURCE_HEIGHT_M = 1.0
POP_STANDOFF_M = 0.30
TALLY_RADIUS_M = 0.10
WORLD_MARGIN_M = 2.0
OPENING_HEIGHTS_M = {"door": (0.0, 2.1), "window": (1.0, 2.0)}
MIN_LINE_KEV = 50.0
LINES = {"F-18": ((511.0, 1.935),), "Tc-99m": ((140.5, 0.885),), **PHOTON_LINES}
ENGINE_NAME = "transport (Monte Carlo)"

# run control: chunks of CHUNK histories until every point is at TARGET_REL or MAX_HISTORIES is reached.
# No time cap, so the answer does not depend on the machine: a design and a seed give one result.
CHUNK = 50_000
TARGET_REL = 0.05
MAX_HISTORIES = 1_000_000


@dataclass(frozen=True)
class Box:
    lo: tuple
    hi: tuple
    material: str


@dataclass(frozen=True)
class TallyPoint:
    label: str                 # the BarrierPath label it answers
    xyz: tuple


@dataclass
class TransportRoom:
    boxes: List[Box]
    world_lo: tuple
    world_hi: tuple
    source: tuple
    points: List[TallyPoint]
    densities: Dict[str, float]


def available() -> bool:
    return transport_mc.available()


def kerma_lines(nuclide: str) -> List[Tuple[float, float]]:
    return [(e, y) for e, y in LINES[nuclide] if e >= MIN_LINE_KEV]


# ------------------------------------------------------------------ geometry
def wall_layers(wall: Wall) -> List[Tuple[str, float]]:
    layers = [(wall.material1, wall.thickness1_mm)]
    if wall.material2 and wall.thickness2_mm > 0:
        layers.append((wall.material2, wall.thickness2_mm))
    return [(m, t) for m, t in layers if t > 0]


def _thickness_m(layers) -> float:
    return sum(t for _, t in layers) / 1000.0


class _Frame:
    """A wall's local frame: `along` runs with the wall, `depth` is metres outward from its inner
    face, z is height. `to_xyz` turns local ranges into a world box."""

    def __init__(self, wall_id: str, room, along_range: tuple):
        self.id, self.room, self.along_range = wall_id, room, along_range

    def to_box(self, along: tuple, depth: tuple, z: tuple, material: str) -> Box:
        r = self.room
        if self.id == "N":
            x, y = along, (r.length_m + depth[0], r.length_m + depth[1])
        elif self.id == "S":
            x, y = along, (-depth[1], -depth[0])
        elif self.id == "E":
            x, y = (r.width_m + depth[0], r.width_m + depth[1]), along
        else:
            x, y = (-depth[1], -depth[0]), along
        return Box((x[0], y[0], z[0]), (x[1], y[1], z[1]), material)

    def point(self, along: float, depth: float, z: float) -> tuple:
        b = self.to_box((along, along), (depth, depth), (z, z), "air")
        return b.lo


def _cells(span: tuple, cuts: List[float]) -> List[tuple]:
    edges = sorted({span[0], span[1], *[c for c in cuts if span[0] < c < span[1]]})
    return list(zip(edges[:-1], edges[1:]))


def _opening_rects(wall: Wall, height_m: float) -> List[tuple]:
    """((along lo, along hi), (z lo, z hi), lead mm) of each door and window."""
    rects = []
    for op in wall.openings:
        if op.kind not in OPENING_HEIGHTS_M:
            continue
        z0, z1 = OPENING_HEIGHTS_M[op.kind]
        half = op.width_m / 2.0
        rects.append(((op.center_along_wall_m - half, op.center_along_wall_m + half),
                      (z0, min(z1, height_m)), op.lead_equiv_mm))
    return rects


def wall_boxes(frame: _Frame, layers, rects, height_m: float) -> List[Box]:
    """The wall's layers, cut around its openings, plus each opening's lead sheet."""
    along_cuts = [a for (along, _, _) in rects for a in along]
    z_cuts = [z for (_, zr, _) in rects for z in zr]
    boxes, depth = [], 0.0
    for material, mm in layers:
        d = (depth, depth + mm / 1000.0)
        for a in _cells(frame.along_range, along_cuts):
            for z in _cells((0.0, height_m), z_cuts):
                inside = any(al[0] <= a[0] and a[1] <= al[1] and zr[0] <= z[0] and z[1] <= zr[1]
                             for al, zr, _ in rects)
                if not inside:
                    boxes.append(frame.to_box(a, d, z, material))
        depth = d[1]
    for along, z, lead_mm in rects:
        if lead_mm > 0:
            boxes.append(frame.to_box(along, (0.0, lead_mm / 1000.0), z, "lead"))
    return boxes


def build_room(design: RoomDesign, layers_by_wall: Optional[Dict[str, list]] = None) -> TransportRoom:
    """The 3D room for a design. `layers_by_wall` overrides a wall's layers (Design mode's
    suggested build); a wall absent from it keeps its declared layers."""
    r = design.room
    layers = {w.id: (layers_by_wall or {}).get(w.id, wall_layers(w)) for w in design.walls}
    t = {wid: _thickness_m(layers.get(wid, [])) for wid in ("N", "E", "S", "W")}
    x_span, y_span = (-t["W"], r.width_m + t["E"]), (-t["S"], r.length_m + t["N"])
    frames = {"N": _Frame("N", r, x_span), "S": _Frame("S", r, x_span),
              "E": _Frame("E", r, (0.0, r.length_m)), "W": _Frame("W", r, (0.0, r.length_m))}
    boxes = [Box((x_span[0], y_span[0], -SLAB_M), (x_span[1], y_span[1], 0.0), SLAB_MATERIAL),
             Box((x_span[0], y_span[0], r.height_m), (x_span[1], y_span[1], r.height_m + SLAB_M), SLAB_MATERIAL)]
    for wall in design.walls:
        boxes += wall_boxes(frames[wall.id], layers[wall.id], _opening_rects(wall, r.height_m), r.height_m)
    z_src = min(SOURCE_HEIGHT_M, r.height_m - 0.1)
    points = [TallyPoint(p.label, _pop_xyz(p, frames[p.wall_id], t[p.wall_id], z_src))
              for p in all_paths(design) if p.kind in ("wall", "door", "window")]
    margin = WORLD_MARGIN_M
    return TransportRoom(
        boxes=boxes,
        world_lo=(x_span[0] - margin, y_span[0] - margin, -SLAB_M - margin),
        world_hi=(x_span[1] + margin, y_span[1] + margin, r.height_m + SLAB_M + margin),
        source=(design.source.x_m, design.source.y_m, z_src),
        points=points,
        densities={m: product_density_gcm3(m) for m in {b.material for b in boxes}})


def _pop_xyz(path: BarrierPath, frame: _Frame, thickness_m: float, z: float) -> tuple:
    along = path.pop_xy[0] if path.wall_id in ("N", "S") else path.pop_xy[1]
    return frame.point(along, thickness_m + POP_STANDOFF_M, z)


# ------------------------------------------------------------------ transport
@dataclass
class KermaResult:
    total_gy: List[float]           # air kerma per decay at each point (uncollided + scattered)
    se_gy: List[float]              # MC standard error of the scattered part
    histories: int
    seconds: float


def transport(room: TransportRoom, nuclide: str, seed: int = 1) -> KermaResult:
    """Uncollided kerma plus scattered kerma in chunks until every point reaches TARGET_REL or
    MAX_HISTORIES is reached."""
    mc = transport_mc.Room(room.boxes, room.world_lo, room.world_hi, room.densities)
    lines = kerma_lines(nuclide)
    pts = [p.xyz for p in room.points]
    radii = [TALLY_RADIUS_M] * len(pts)
    start = time.time()
    unc = mc.uncollided(room.source, lines, pts, radii)
    means, variances, n = [], [], 0
    while True:
        m, se = mc.scattered(room.source, lines, pts, radii, CHUNK, seed=seed + len(means))
        means.append(m)
        variances.append(se ** 2)
        n += CHUNK
        k = len(means)
        mean = sum(means) / k
        se_total = (sum(variances) ** 0.5) / k
        total = unc + mean
        worst = max((s / t for s, t in zip(se_total, total) if t > 0), default=0.0)
        if worst <= TARGET_REL or n >= MAX_HISTORIES:
            return KermaResult(list(total), list(se_total), n, time.time() - start)


def free_air_gy(nuclide: str, distance_m: float) -> float:
    """Unshielded air kerma per decay (Gy) at distance_m, without air attenuation."""
    d_cm = distance_m * 100.0
    per_decay = sum(y * transport_mc.kerma_factor(e) for e, y in kerma_lines(nuclide))
    return per_decay / (4.0 * math.pi * d_cm ** 2) * transport_mc.KEV_TO_J * 1e3


# ------------------------------------------------------------------ engine
class TransportEngine:
    """Same EngineResult interface as the other tiers, for walls, doors and windows."""

    name = ENGINE_NAME

    def __init__(self, design: RoomDesign):
        self.design = design
        self.analytical = AnalyticalEngine(design)

    def evaluate_all(self, layers_by_wall: Optional[Dict[str, list]] = None, seed: int = 1):
        """(EngineResults for every path, the KermaResult). Paths the tier does not build (ducts,
        mazes) come back unevaluated."""
        room = build_room(self.design, layers_by_wall)
        kerma = transport(room, self.design.source.isotope, seed)
        by_label = {p.label: (p, k, s) for p, k, s in zip(room.points, kerma.total_gy, kerma.se_gy)}
        walls = {w.id: w for w in self.design.walls}
        results = []
        for path in all_paths(self.design):
            if path.label in by_label:
                results.append(self._result(path, walls[path.wall_id], room, *by_label[path.label]))
            else:
                results.append(self._not_built(path))
        return results, kerma

    def _result(self, path, wall, room, point, kerma_gy, se_gy) -> EngineResult:
        distance = math.dist(room.source, point.xyz)
        ratio = kerma_gy / free_air_gy(self.design.source.isotope, distance)
        unshielded = self.analytical._source(_at_distance(path, distance)).total_unshielded()
        goal = self.analytical._goal(wall)
        goal_over_T = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly
        dose = unshielded * ratio
        return EngineResult(
            barrier_id=path.label, label=path.label, engine=self.name,
            B_required=min(1.0, goal_over_T / unshielded) if unshielded > 0 else 1.0,
            B_achieved=ratio, dose_mSv_wk=dose, goal_over_T=goal_over_T,
            passes=dose <= goal_over_T, margin=goal_over_T / dose if dose > 0 else float("inf"),
            note=f"at {distance:.2f} m, 0.3 m beyond the outer face; MC ±{100 * se_gy / kerma_gy:.0f}% (1σ)")

    def _not_built(self, path: BarrierPath) -> EngineResult:
        return EngineResult(
            barrier_id=path.label, label=path.label, engine=self.name, B_required=None,
            B_achieved=None, dose_mSv_wk=None, goal_over_T=None, passes=None, margin=None,
            note=f"{path.kind.capitalize()}s are not built in the transport room; see the surrogate tier.")


def _at_distance(path: BarrierPath, distance_m: float) -> BarrierPath:
    return replace(path, d_pop_m=distance_m)
