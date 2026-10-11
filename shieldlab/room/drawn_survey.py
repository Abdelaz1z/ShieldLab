"""
drawn_survey.py
===============
The predicted survey of a drawn room: the weekly dose at each numbered survey point, from the
source at the radiation symbol, through every barrier on the straight line between them.

For each point:

1. A point drawn against a wall (within half its thickness plus SNAP_REACH_M of the centre line)
   is moved to the NCRP point of protection: 0.3 m beyond the wall's outer face, on the side away
   from the source. A point drawn in open space is used where it is.
2. The line from the source to that point is intersected with every wall side. Where it crosses a
   side inside a door or window, the opening's build-up is used instead of the wall's. A door with
   a lead-glass panel is served as the weaker of its leaf and its panel, the conservative choice,
   because the drawing does not say which of the two the line passes through.
3. Each crossed barrier is served by the room engines exactly as a wall of the rectangular Room
   Designer is, at its slant thickness (each layer times 1/cos of the angle to the wall's normal).
   Where model E serves it, the oblique-incidence correction the field tier applies is added
   (`oblique_correction`, fitted to 60 degrees and held at that edge beyond it).
4. The transmissions of the crossed barriers are multiplied. That treats each barrier as seeing
   a broad beam of its own and so counts buildup once per barrier, which over-states the
   transmission of a line through two walls; the interval's edges are multiplied the same way and
   are not a calibrated interval for the product.

The dose is the unshielded weekly dose at the point's distance (`AnalyticalEngine`, inverse
square, the source's workload) times that product, judged against the point's design goal P/T.
Scatter that goes over or around a barrier (ceiling, floor, room return) is not in this
calculation: it is the subject of the room-scale tiers, and the reason a line-of-sight survey can
read low behind a thick wall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from . import field_surrogate as fs
from . import oblique_correction as obc
from .drawn_plan import DrawnPlan, PlanOpening, Point, Segment, SurveyPoint, nearest_segment
from .engines import AnalyticalEngine, EngineResult, SurrogateEngine
from .geometry import POP_STANDOFF_M, BarrierPath
from .model import AdjacentArea, RoomDesign, Source, Wall

Layers = Tuple[Tuple[str, float], ...]          # (material, mm at normal incidence), inner face first

SNAP_REACH_M = 0.6          # how far from a wall's face a drawn point still counts as "at the wall"
MAX_SLANT = 20.0            # a near-grazing line is held at 87 degrees
SURROGATE = "surrogate"     # SurrogateEngine's name when model E served the barrier in its domain


@dataclass
class SurveySetup:
    """Everything the drawing does not carry: the source, the build-up of every barrier and how
    each survey point is occupied."""
    isotope: str = "F-18"
    activity_MBq: float = 370.0
    patients_per_week: float = 40.0
    residence_min: float = 60.0
    framework: str = "NCRP"
    walls: Dict[str, Layers] = field(default_factory=dict)       # segment key -> layers
    openings: Dict[str, Layers] = field(default_factory=dict)    # opening key -> door leaf / window
    panels: Dict[str, Layers] = field(default_factory=dict)      # opening key -> glass panel
    occupancy: Dict[int, float] = field(default_factory=dict)    # point number -> T
    controlled: Dict[int, bool] = field(default_factory=dict)    # point number -> controlled area

    def design(self) -> RoomDesign:
        """The room-engine design carrying this setup's source and framework."""
        return RoomDesign(source=Source(isotope=self.isotope, activity_MBq=self.activity_MBq,
                                        patients_per_week=self.patients_per_week,
                                        residence_min=self.residence_min, x_m=0.0, y_m=0.0),
                          framework=self.framework)

    def area(self, n: int) -> AdjacentArea:
        return AdjacentArea(name=f"Point {n}", occupancy_T=self.occupancy.get(n, 1.0),
                            kind="controlled" if self.controlled.get(n, False) else "public")


@dataclass
class Crossing:
    """One barrier on the line from the source to a point."""
    barrier: str
    layers: Layers
    angle_deg: float
    result: Optional[EngineResult]          # None for an open gap
    analytical: Optional[EngineResult]
    oblique_log10: float = 0.0


@dataclass
class PointResult:
    point: SurveyPoint
    calc_xy: Point
    moved_beyond: Optional[str]             # the wall the point was moved beyond, if any
    distance_m: float
    crossings: List[Crossing]
    B: Optional[float]
    B_low: Optional[float]
    B_high: Optional[float]
    B_analytical: Optional[float]
    dose_mSv_wk: Optional[float]
    dose_upper_mSv_wk: Optional[float]
    goal_over_T: float
    passes: Optional[bool]
    notes: List[str]


# ------------------------------------------------------------------------------- geometry

def _unit_normal(segment: Segment) -> Point:
    (ax, ay), (bx, by) = segment.a, segment.b
    length = segment.length_m
    return (-(by - ay) / length, (bx - ax) / length)


def calculation_point(plan: DrawnPlan, source: Point, point: SurveyPoint
                      ) -> Tuple[Point, Optional[Segment]]:
    """Where the dose is calculated for a drawn point, and the wall it was moved beyond (if any)."""
    near = nearest_segment(plan, point.xy)
    if near is None:
        return point.xy, None
    segment, foot, gap = near
    if gap > segment.thickness_m / 2.0 + SNAP_REACH_M:
        return point.xy, None
    nx, ny = _unit_normal(segment)
    source_side = (source[0] - foot[0]) * nx + (source[1] - foot[1]) * ny
    if abs(source_side) < 1e-9:
        return point.xy, None                    # the source stands on the wall's own line
    away = -1.0 if source_side > 0 else 1.0
    reach = segment.thickness_m / 2.0 + POP_STANDOFF_M
    return (foot[0] + away * nx * reach, foot[1] + away * ny * reach), segment


def _intersection(p: Point, q: Point, segment: Segment) -> Optional[Tuple[float, float]]:
    """(fraction along p->q, fraction along the side) where the line crosses the side, or None."""
    rx, ry = q[0] - p[0], q[1] - p[1]
    sx, sy = segment.b[0] - segment.a[0], segment.b[1] - segment.a[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-12:
        return None                              # parallel: the line runs along the wall
    wx, wy = segment.a[0] - p[0], segment.a[1] - p[1]
    u = (wx * sy - wy * sx) / denominator
    v = (wx * ry - wy * rx) / denominator
    if 1e-9 < u < 1.0 - 1e-9 and -1e-9 <= v <= 1.0 + 1e-9:
        return u, v
    return None


def crossed_sides(plan: DrawnPlan, source: Point, target: Point
                  ) -> List[Tuple[Segment, float, Optional[PlanOpening]]]:
    """The sides the line crosses, nearest the source first, with the angle of incidence in degrees
    and the opening it passes through. A line through a corner shared by two sides of one wall is
    counted once."""
    length = math.dist(source, target)
    dx, dy = (target[0] - source[0]) / length, (target[1] - source[1]) / length
    hits, seen = [], set()
    for segment in plan.segments:
        crossing = _intersection(source, target, segment)
        if crossing is None:
            continue
        u, v = crossing
        where = (segment.wall_id, round(u * length, 3))
        if where in seen:
            continue
        seen.add(where)
        nx, ny = _unit_normal(segment)
        angle = math.degrees(math.acos(min(1.0, abs(dx * nx + dy * ny))))
        opening = next((o for o in plan.openings if o.segment_key == segment.key
                        and abs(v - o.t) * segment.length_m <= o.width_m / 2.0), None)
        hits.append((u, segment, angle, opening))
    return [(segment, angle, opening) for _, segment, angle, opening in sorted(hits, key=lambda h: h[0])]


# ------------------------------------------------------------------------------- physics

def _wall(key: str, layers: Layers, area: AdjacentArea) -> Wall:
    padded = list(layers) + [(None, 0.0)] * (3 - len(layers))
    (m1, t1), (m2, t2), (m3, t3) = padded[:3]
    return Wall(id=key, material1=m1, thickness1_mm=t1, material2=m2, thickness2_mm=t2,
                material3=m3, thickness3_mm=t3, adjacent=area)


def _oblique_log10(isotope: str, layers: Layers, slant: float) -> float:
    energy = fs.ISOTOPE_ENERGY_KEV.get(isotope)
    if energy is None or slant <= 1.0:
        return 0.0
    return obc.log10_factor(fs._simulated_layers(layers), energy, slant)


def _raised(result: EngineResult, log10_factor: float) -> EngineResult:
    """The result with its transmission, interval and dose raised by 10**log10_factor."""
    k = 10.0 ** log10_factor
    scale = lambda value: None if value is None else value * k
    return replace(result, B_achieved=scale(result.B_achieved),
                   ci_low=scale(result.ci_low), ci_high=scale(result.ci_high),
                   dose_mSv_wk=scale(result.dose_mSv_wk))


def serve_barrier(setup: SurveySetup, path: BarrierPath, layers: Layers, angle_deg: float,
                  area: AdjacentArea) -> Tuple[Optional[EngineResult], Optional[EngineResult], float]:
    """(model answer, analytical answer, oblique log10 factor) for one barrier crossed at
    `angle_deg`; (None, None, 0) for a barrier with no layers."""
    layers = tuple((m, float(t)) for m, t in layers if m and t and t > 0)
    if not layers:
        return None, None, 0.0
    slant = min(1.0 / max(math.cos(math.radians(angle_deg)), 1e-9), MAX_SLANT)
    wall = _wall(path.wall_id, tuple((m, t * slant) for m, t in layers), area)
    design = setup.design()
    analytical = AnalyticalEngine(design).evaluate(path, wall, "check")
    served = SurrogateEngine(design).evaluate(path, wall, wall.thickness1_mm, analytical=analytical)
    if served is None:                                   # no model bundle deployed
        return analytical, analytical, 0.0
    if served.engine != SURROGATE:
        return served, analytical, 0.0
    factor = _oblique_log10(setup.isotope, layers, slant)
    return _raised(served, factor), analytical, factor


def _opening_layers(setup: SurveySetup, opening: PlanOpening, path: BarrierPath, angle: float,
                    area: AdjacentArea) -> Layers:
    """The build-up a line through this opening meets: the weaker of leaf and panel for a door
    with a lead-glass panel."""
    if opening.kind == "gap":
        return ()
    leaf = setup.openings.get(opening.key, ())
    panel = setup.panels.get(opening.key, ()) if opening.vision_panel else ()
    if not panel:
        return leaf
    if not leaf:
        return ()
    b_leaf = serve_barrier(setup, path, leaf, angle, area)[0]
    b_panel = serve_barrier(setup, path, panel, angle, area)[0]
    if b_leaf is None or b_panel is None or b_leaf.B_achieved is None or b_panel.B_achieved is None:
        return leaf
    return panel if b_panel.B_achieved > b_leaf.B_achieved else leaf


def _product(values: List[Optional[float]]) -> Optional[float]:
    if any(v is None for v in values):
        return None
    return math.prod(values)


def survey_point(plan: DrawnPlan, setup: SurveySetup, source: Point, point: SurveyPoint
                 ) -> PointResult:
    """The predicted weekly dose at one survey point."""
    calc, moved = calculation_point(plan, source, point)
    distance = max(math.dist(source, calc), 1e-3)
    area = setup.area(point.n)
    crossings, notes = [], []
    for segment, angle, opening in crossed_sides(plan, source, calc):
        label = opening.label if opening else segment.label
        path = BarrierPath(wall_id=opening.key if opening else segment.key, kind="wall",
                           label=label, d_pop_m=distance, perp_m=distance, offset_m=0.0,
                           pop_xy=calc)
        layers = (_opening_layers(setup, opening, path, angle, area) if opening
                  else setup.walls.get(segment.key, ()))
        served, analytical, factor = serve_barrier(setup, path, layers, angle, area)
        crossings.append(Crossing(label, tuple(layers), angle, served, analytical, factor))

    design = setup.design()
    engine = AnalyticalEngine(design)
    probe = BarrierPath(wall_id="point", kind="wall", label=f"Point {point.n}", d_pop_m=distance,
                        perp_m=distance, offset_m=0.0, pop_xy=calc)
    unshielded = engine._source(probe).total_unshielded()
    goal = engine._goal(_wall("point", (), area))
    goal_over_T = goal.P_weekly / goal.occupancy_T if goal.occupancy_T > 0 else goal.P_weekly

    served = [c.result for c in crossings if c.result is not None]
    B = _product([r.B_achieved for r in served]) if served else 1.0
    B_low = _product([r.ci_low for r in served]) if served else 1.0
    B_high = _product([r.ci_high for r in served]) if served else 1.0
    B_analytical = _product([c.analytical.B_achieved for c in crossings if c.analytical]) \
        if served else 1.0
    dose = None if B is None else unshielded * B
    upper = None if B_high is None else unshielded * B_high

    if moved is not None:
        notes.append(f"Calculated {POP_STANDOFF_M:.1f} m beyond {moved.label}.")
    if not crossings:
        notes.append("No wall lies between the source and this point.")
    elif not served:
        notes.append("The line passes only through open gaps.")
    if len(served) > 1:
        notes.append("Several barriers: their transmissions are multiplied, which over-states the "
                     "dose, and the interval is not calibrated for the product.")
    if B is None:
        notes.append("At least one barrier is outside every tier; a Monte Carlo run is needed.")
    notes += [f"{c.barrier}: {c.result.note}" for c in crossings
              if c.result is not None and c.result.engine != SURROGATE and c.result.note]
    return PointResult(point=point, calc_xy=calc, moved_beyond=moved.label if moved else None,
                       distance_m=distance, crossings=crossings, B=B, B_low=B_low, B_high=B_high,
                       B_analytical=B_analytical, dose_mSv_wk=dose, dose_upper_mSv_wk=upper,
                       goal_over_T=goal_over_T, passes=None if dose is None else dose <= goal_over_T,
                       notes=notes)


def survey(plan: DrawnPlan, setup: SurveySetup) -> List[PointResult]:
    """Every survey point, from the first radiation symbol in the plan."""
    if plan.problems():
        raise ValueError(" ".join(plan.problems()))
    source = plan.sources[0]
    return [survey_point(plan, setup, source, point) for point in plan.points]


def barrier_transmission(setup: SurveySetup, key: str, layers: Layers
                         ) -> Tuple[Optional[EngineResult], Optional[EngineResult]]:
    """(model, analytical) transmission of one barrier at normal incidence, for the barrier table."""
    path = BarrierPath(wall_id=key, kind="wall", label=key, d_pop_m=1.0, perp_m=1.0,
                       offset_m=0.0, pop_xy=(0.0, 0.0))
    served, analytical, _ = serve_barrier(setup, path, layers, 0.0, AdjacentArea())
    return served, analytical
