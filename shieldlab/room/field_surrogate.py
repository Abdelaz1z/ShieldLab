"""
field_surrogate.py
==================
The 3D dose-field tier: a Monte-Carlo-trained U-Net that predicts the WHOLE in-room
air-kerma field (not a single per-barrier transmission), for the Room Designer's
plan-view field map. This is the thesis field-map campaign's payload
(`thesis_mc/src/train_field_unet.py`, job fmunet 126789, occupied-shell val
RMSE 0.068 dex vs the slab surrogate's own 0.21 dex).

WHAT IT IS — and is NOT
-----------------------
The U-Net was trained on a fixed 96x80x48 @ 100 mm voxel domain over rooms that are a
SINGLE wall material with symmetric per-axis wall thicknesses (the campaign geometry).
So in the Room Designer it answers "what does the dose field look like across this
room?" as a **screening / visualisation tier** — it is deliberately NOT wired into the
per-barrier PASS/FAIL verdict. That verdict stays with the validated analytical tier
and the scalar MC surrogate. A real ShieldLab room (four walls, each its own build-up, any
of the app's materials) is mapped onto the U-Net's box through equal-transmission
equivalents of one trained material; see "design -> box mapping" below for how, and for
what that was measured against. The field is an approximation and is labelled as one.

Graceful degradation: everything here is import-guarded. The tier runs on ONNX Runtime when
`models/field_unet/field_unet.onnx` is present (the deployable path — no torch needed), and
falls back to PyTorch + the .pt checkpoint if that is what the environment has. If neither
runtime nor weights are available, `FieldModel().available()` is False and the page simply
omits the field map — exactly how the app already degrades when the surrogate bundle is
missing. `FieldModel().backend()` reports which runtime served the map.

The input-channel construction below is a byte-for-byte copy of
`thesis_mc/src/field_dataset.py::make_input` (same mu/rho table, same ginv2 and energy
channels) — it MUST stay in sync with the code the model was trained under, so the model
sees at inference exactly the channels it saw in training.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

import numpy as np

# ----------------------------------------------------------------- fixed U-Net domain
# (copied from thesis_mc/src/room_field.py — the trained domain; do not change here)
GRID = (96, 80, 48)          # (nx, ny, nz)  -> 9.6 x 8.0 x 4.8 m
VOXEL_MM = 100.0

# label id -> material key (thesis_mc/src/field_dataset.py::LABEL_MATERIAL)
LABEL_MATERIAL = {0: "air", 1: "concrete", 2: "lead", 3: "steel", 4: "gypsum",
                  5: "barite_concrete", 6: "lead_glass", 7: "brick"}
MATERIAL_LABEL = {v: k for k, v in LABEL_MATERIAL.items()}

# ShieldLab isotope -> the campaign gamma energy (keV). Matches the surrogate bundle basis.
ISOTOPE_ENERGY_KEV = {"Tc-99m": 140.5, "Lu-177": 208.0, "I-131": 364.0,
                      "F-18": 511.0, "Ga-68": 511.0}

# mu/rho [cm^2/g] at the campaign energies + density [g/cm^3] — the INPUT prior only.
# (Exact copy of thesis_mc/src/field_dataset.py so channels match training.)
_E = np.array([140.5, 208.0, 364.0, 511.0, 1077.3])
MU_RHO = {
    "air":             np.array([0.1500, 0.1230, 0.0994, 0.0870, 0.0636]),
    "concrete":        np.array([0.1430, 0.1220, 0.0999, 0.0872, 0.0618]),
    "barite_concrete": np.array([0.2220, 0.1400, 0.1020, 0.0885, 0.0625]),
    "brick":           np.array([0.1390, 0.1210, 0.0996, 0.0870, 0.0619]),
    "gypsum":          np.array([0.1500, 0.1230, 0.0995, 0.0866, 0.0615]),
    "steel":           np.array([0.1850, 0.1460, 0.1050, 0.0840, 0.0596]),
    "lead":            np.array([2.2000, 0.9000, 0.2550, 0.1580, 0.0695]),
    "lead_glass":      np.array([0.5500, 0.2800, 0.1300, 0.0980, 0.0660]),
}
DENSITY = {"air": 0.0012, "concrete": 2.30, "barite_concrete": 3.35, "brick": 1.80,
           "gypsum": 2.32, "steel": 7.87, "lead": 11.35, "lead_glass": 4.80}

# The only wall materials in the 600-room training set
# (thesis_mc/hpc_campaign/build_fieldmap_campaign.py::MATERIALS). The label table above names
# more, but the network never saw them.
TRAINED_MATERIALS = ("concrete", "barite_concrete", "brick")


def mu_per_mm(material: str, energy_keV: float) -> float:
    mr = float(np.exp(np.interp(np.log(energy_keV), np.log(_E), np.log(MU_RHO[material]))))
    return mr * DENSITY[material] * 0.1        # cm^2/g * g/cm^3 -> 1/cm; *0.1 -> 1/mm


def trained_mu_range(energy_keV: float) -> Tuple[float, float]:
    """(min, max) wall mu [1/mm] the U-Net was trained on at this energy.

    The wall enters the network only through this mu channel, so a wall whose mu lies inside
    the range is inside the training distribution whatever its name (gypsum sits on concrete).
    Outside it the in-room field is wrong, not merely approximate: measured 2026-09-26 on a
    6x5x3 m box at 364 keV, the same 100 mm walls read 1.0x the inverse-square primary at
    concrete's mu (0.023/mm), 0.6x at 0.10/mm and 0.05-0.25x at lead's 0.29/mm. Ratios below
    1 in air next to a bare source are physically impossible.
    """
    mus = [mu_per_mm(m, energy_keV) for m in TRAINED_MATERIALS]
    return min(mus), max(mus)


# Effective Z of each wall material, as model E's bundle records it (material_map "zeff").
ZEFF = {"concrete": 13.0, "brick": 12.0, "barite_concrete": 41.9, "gypsum": 13.6,
        "steel": 26.0, "lead": 82.0, "lead_glass": 73.1}


def proxy_material(material: str, energy_keV: float) -> str:
    """The material the U-Net is run with for a wall of `material`.

    Inside the trained mu range, the material itself. Outside it, the trained material with the
    nearest effective Z: what a wall sends back into the room is set by its albedo, which follows
    Z; the field beyond the walls comes from the reference box instead (see the mapping notes
    below). Checked against the MC pilot rooms (in-room air, median log10
    error): lead at 364 keV -0.66 dex run as lead, +0.04 as barite concrete; lead glass at
    140.5 keV -0.28 as itself, +0.03 as barite concrete (fieldmap_pilot rows 18 and 14).
    """
    lo, hi = trained_mu_range(energy_keV)
    if lo <= mu_per_mm(material, energy_keV) <= hi:
        return material
    return min(TRAINED_MATERIALS, key=lambda m: abs(ZEFF[m] - ZEFF[material]))


def _coord_axes():
    nx, ny, nz = GRID
    xc = (np.arange(nx) - nx / 2.0 + 0.5) * VOXEL_MM
    yc = (np.arange(ny) - ny / 2.0 + 0.5) * VOXEL_MM
    zc = (np.arange(nz) - nz / 2.0 + 0.5) * VOXEL_MM
    return xc, yc, zc


def _snap_to_voxel_center(pos_mm):
    nx, ny, nz = GRID
    out = []
    for p, n in zip(pos_mm, (nx, ny, nz)):
        idx = int(np.floor(p / VOXEL_MM + n / 2.0))
        idx = min(max(idx, 0), n - 1)
        out.append((idx + 0.5 - n / 2.0) * VOXEL_MM)
    return out


def _build_labels(room_m, wall_mm, material):
    """Single-material box centred in the fixed domain (thesis_mc room_field.build_labels)."""
    nx, ny, nz = GRID
    lab = np.zeros((nz, ny, nx), dtype=np.int16)
    wl = MATERIAL_LABEL[material]
    rv = [max(1, int(round(r * 1000.0 / VOXEL_MM))) for r in room_m]
    tv = [max(1, int(round(t / VOXEL_MM))) for t in wall_mm]
    cx, cy, cz = nx // 2, ny // 2, nz // 2

    def span(c, n_vox):
        lo = c - n_vox // 2
        return lo, lo + n_vox

    x0, x1 = span(cx, rv[0]); y0, y1 = span(cy, rv[1]); z0, z1 = span(cz, rv[2])
    sx0, sx1 = x0 - tv[0], x1 + tv[0]
    sy0, sy1 = y0 - tv[1], y1 + tv[1]
    sz0, sz1 = z0 - tv[2], z1 + tv[2]
    if sx0 < 0 or sy0 < 0 or sz0 < 0 or sx1 > nx or sy1 > ny or sz1 > nz:
        raise ValueError(
            f"room + walls exceed the field model's {GRID[0]*VOXEL_MM/1000:.1f}"
            f"x{GRID[1]*VOXEL_MM/1000:.1f}x{GRID[2]*VOXEL_MM/1000:.1f} m domain")
    lab[sz0:sz1, sy0:sy1, sx0:sx1] = wl
    lab[z0:z1, y0:y1, x0:x1] = 0
    return lab, dict(room=(x0, x1, y0, y1, z0, z1), shell=(sx0, sx1, sy0, sy1, sz0, sz1))


def _make_input(labels: np.ndarray, energy_keV: float, source_mm) -> np.ndarray:
    """(3, nz, ny, nx) channels [mu, ginv2, energy] — exact copy of field_dataset.make_input."""
    mu = np.zeros_like(labels, dtype=np.float32)
    for lab in np.unique(labels):
        m = mu_per_mm(LABEL_MATERIAL[int(lab)], energy_keV)
        if m:
            mu[labels == lab] = m
    xc, yc, zc = _coord_axes()
    sx, sy, sz = source_mm
    r2 = ((xc[None, None, :] - sx) ** 2 + (yc[None, :, None] - sy) ** 2
          + (zc[:, None, None] - sz) ** 2)
    r2 = np.maximum(r2, (0.5 * VOXEL_MM) ** 2)
    ginv2 = np.log10(1.0 / (4.0 * np.pi * (r2 / 1e6))).astype(np.float32)
    energy = np.full(labels.shape, np.log10(energy_keV / 511.0), dtype=np.float32)
    return np.stack([mu, ginv2, energy], axis=0)


def _occupied_shell(labels: np.ndarray, iters: int = 10) -> np.ndarray:
    """Air within ~1 m (10 voxels) of a barrier — where the points of protection live."""
    air = labels == 0
    walls = labels > 0
    out = walls.copy()
    for _ in range(iters):
        d = out.copy()
        d[1:, :, :] |= out[:-1, :, :]; d[:-1, :, :] |= out[1:, :, :]
        d[:, 1:, :] |= out[:, :-1, :]; d[:, :-1, :] |= out[:, 1:, :]
        d[:, :, 1:] |= out[:, :, :-1]; d[:, :, :-1] |= out[:, :, 1:]
        out = d
    return air & out


# ----------------------------------------------------------------- design -> box mapping
# How a ShieldLab room reaches the U-Net, and why it is done this way (measured 2026-09-26/28
# against the pilot and oblique MC rooms, thesis_mc/hpc_campaign/fieldmap_{pilot,oblique}):
#
#  * The box is one REFERENCE material R the network was trained on: the room's dominant wall
#    material if it is one of TRAINED_MATERIALS, else concrete.
#  * Every real wall is replaced by the thickness of R that transmits the same, from the
#    per-barrier tier (model E, else the analytical tables, else narrow-beam). Comparing two
#    walls at EQUAL transmission is where that tier is strong. Using it for the CHANGE of the
#    field with thickness is not: model E's attenuation per 100 mm of concrete is ~20% shallower
#    than the room field's (MC and U-Net agree), which biased a direct B-ratio by 0.12-0.19 dex.
#  * The box is built at the nearest whole voxel to that equivalent, and the rest (at most
#    +/-50 mm) is corrected with the slope the U-Net itself gives in this room: a second run with
#    the side walls one voxel thicker or thinner, toward the equivalent (`_slope_steps`).
#    Checked on MC rooms with the box forced 100 mm off the real wall: the corrected field
#    matches the MC as closely as the U-Net run on the true geometry (median within 0.01 dex).
#    Through a concrete reference, brick walls land at -0.04 dex and barite at +0.09 to +0.18.
#  * Inside the room the field is set by what the walls send back, which follows Z, not by what
#    they let through. For walls outside the trained range the in-room air comes from a run with
#    the nearest-Z trained material (`proxy_material`).
#  * ShieldLab has no floor or ceiling input; they are taken as the mean of the four walls, and
#    corrected the same way from a third run with only the slabs one voxel thicker or thinner.
#    Uncorrected, they stood at the nearest whole 100 mm: the MC (FieldLead-1, 2026-09-28) read
#    the field above and below a 2 mm lead room 2.1x higher than the map.

SLANTS = np.array([1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0])   # 1/cos along a ray; held beyond
FACE_WALL = {(0, 1): "E", (0, -1): "W", (1, 1): "N", (1, -1): "S",
             (2, 1): "ceiling", (2, -1): "floor"}
SIDE_WALLS = ("N", "E", "S", "W")
SLOPE_STEP_MM = 100.0


class BoxMapping(NamedTuple):
    labels: np.ndarray            # the reference-material box the U-Net is run on
    bb: dict
    energy_keV: float
    source_mm: tuple
    material: str                 # reference material R
    wall_mm: Tuple[float, float, float]      # box thicknesses as built
    equivalent_mm: dict           # wall id -> R-equivalent normal thickness at each of SLANTS
    tiers: dict                   # wall id -> tier that gave the equivalent
    inroom_material: str          # material of the run that serves the in-room air
    room_m: tuple
    warnings: list


def _dominant_material(design) -> str:
    from collections import Counter
    mats = [w.material1 for w in design.walls if w.material1 in MATERIAL_LABEL]
    if not mats:
        return "concrete"
    return Counter(mats).most_common(1)[0][0]


def _wall_layers(wall):
    layers = [(wall.material1, wall.thickness1_mm)]
    if wall.material2 and wall.thickness2_mm > 0:
        layers.append((wall.material2, wall.thickness2_mm))
    return tuple((m, float(t)) for m, t in layers if t > 0)


def _app_layers(material: str, simulated_mm: float):
    """A thickness of the simulated (Geant4) material, as the product thickness the per-barrier
    tier expects; it maps it back at equal mass per area (transport_materials)."""
    from .transport_materials import SIMULATED, product_density_gcm3
    product = product_density_gcm3(material) or SIMULATED[material][1]
    return ((material, simulated_mm * SIMULATED[material][1] / product),)


def _normal_path(layers):
    """A (BarrierPath, Wall) pair for a wall of `layers` met head-on, as the barrier table
    builds them."""
    from .geometry import BarrierPath
    from .model import Wall
    (m1, t1), (m2, t2) = layers[0], (layers[1] if len(layers) > 1 else (None, 0.0))
    wall = Wall(id="field", material1=m1, thickness1_mm=t1, material2=m2, thickness2_mm=t2)
    path = BarrierPath(wall_id="field", kind="wall", label="field", d_pop_m=1.0, perp_m=1.0,
                       offset_m=0.0, pop_xy=(0.0, 0.0))
    return path, wall


def _log_b(tier: str, isotope: str, layers) -> Optional[float]:
    """log10 B of a wall at normal incidence from one tier, or None where it has no answer.

    model E       : the MC-trained per-barrier model, only inside its trusted domain;
    analytical    : the NCRP/TG-108 broad-beam tables the barrier table falls back to;
    narrow-beam   : exp(-mu x) from this module's mu/rho table at the product's density, for
                    walls neither serves (a 30 mm board is below model E's trained thickness).
    """
    if not layers:
        return 0.0
    if tier == "narrow-beam":
        from .transport_materials import product_density_gcm3
        energy, total = ISOTOPE_ENERGY_KEV[isotope], 0.0
        for material, t_mm in layers:
            if material not in MU_RHO:
                return None
            rho = product_density_gcm3(material) or DENSITY[material]
            total += mu_per_mm(material, energy) / DENSITY[material] * rho * t_mm
        return -total / np.log(10.0)
    from .engines import AnalyticalEngine, SurrogateEngine
    from .model import RoomDesign, Source
    design = RoomDesign.default()
    design.source = Source(isotope=isotope)
    path, wall = _normal_path(layers)
    if tier == "model E":
        engine = SurrogateEngine(design)
        if not engine.available():
            return None
        served = engine.evaluate(path, wall, wall.thickness1_mm)
        b = None if (served is None or served.ood) else served.B_achieved
    else:
        b = AnalyticalEngine(design).evaluate(path, wall, "check").B_achieved
    return float(np.log10(b)) if b else None


TIERS = ("model E", "analytical", "narrow-beam")
_REFERENCE_MM = np.geomspace(5.0, 3000.0, 48)       # simulated thickness grid of R


@lru_cache(maxsize=64)
def _reference_curve(isotope: str, reference: str, tier: str):
    """(thickness mm, log10 B) of the reference material over _REFERENCE_MM, where the tier
    answers; None if it answers at fewer than two thicknesses."""
    pts = [(t, _log_b(tier, isotope, _app_layers(reference, t))) for t in _REFERENCE_MM]
    # Model E caps B at 1, so its thinnest walls read flat; only the falling part inverts.
    pts = [(t, b) for t, b in pts if b is not None and b < -1e-4]
    pts = [p for i, p in enumerate(pts) if all(p[1] < q[1] for q in pts[:i])]
    if len(pts) < 2:
        return None
    t, b = map(np.array, zip(*pts))
    return t, b


def _thickness_for(curve, log_b: float) -> Optional[float]:
    """Reference thickness with this log10 B, or None if it lies beyond the curve's deep end.
    Between the curve's first point and B = 1 it falls to zero linearly."""
    t, b = curve
    if log_b >= 0.0:
        return 0.0
    if log_b > b[0]:
        return float(t[0] * log_b / b[0])
    if log_b < b[-1]:
        return None
    return float(np.interp(-log_b, -b, t))


@lru_cache(maxsize=256)
def _equivalent(isotope: str, reference: str, layers):
    """(R-equivalent NORMAL thickness at each of SLANTS, tier at normal incidence).

    At a path factor s the wall is (layers x s); its equivalent is the R thickness with the same
    transmission, divided by s. At each s the wall and R come from the same tier: the first of
    TIERS that serves both (a steep ray can take a wall outside model E's domain).
    """
    out, tiers = [], []
    for s in SLANTS:
        wall = tuple((m, t * s) for m, t in layers)
        for tier in TIERS:
            curve = _reference_curve(isotope, reference, tier)
            log_b = None if curve is None else _log_b(tier, isotope, wall)
            t_eq = None if log_b is None else _thickness_for(curve, log_b)
            if t_eq is not None:
                out.append(t_eq / s)
                tiers.append(tier)
                break
        else:
            return None, "none"
    return tuple(out), tiers[0]


def _voxels(t_mm: float) -> float:
    return max(1, int(round(t_mm / VOXEL_MM))) * VOXEL_MM


def _design_to_box(design) -> BoxMapping:
    """Map a ShieldLab RoomDesign onto the U-Net's single-material box.

    N/S walls barrier the y-axis, E/W walls the x-axis. Floor and ceiling are not ShieldLab
    walls; they take the mean equivalent of the four. The source is placed at mid-height.
    """
    warnings = []
    r, s = design.room, design.source
    room_m = (r.width_m, r.length_m, r.height_m)
    energy = ISOTOPE_ENERGY_KEV.get(s.isotope)
    if energy is None:
        raise ValueError(f"no field-model energy for isotope '{s.isotope}'")
    dominant = _dominant_material(design)
    reference = dominant if dominant in TRAINED_MATERIALS else "concrete"
    inroom = proxy_material(dominant, energy)

    equivalent, tiers = {}, {}
    for wall in design.walls:
        eq, tier = _equivalent(s.isotope, reference, _wall_layers(wall))
        if eq is not None:
            equivalent[wall.id], tiers[wall.id] = eq, tier
    missing = sorted(w.id for w in design.walls if w.id not in equivalent)
    if missing:
        warnings.append(f"no transmission data for wall(s) {', '.join(missing)}; the field "
                        f"beyond them is the {reference} box's, uncorrected.")

    def axis_mm(ids):
        ts = [equivalent[i][0] for i in ids if i in equivalent]
        return _voxels(float(np.mean(ts))) if ts else SLOPE_STEP_MM

    built = (axis_mm(("E", "W")), axis_mm(("N", "S")), axis_mm(SIDE_WALLS))
    labels, bb = _build_labels(room_m, built, reference)          # may raise ValueError
    sides = [equivalent[i] for i in SIDE_WALLS if i in equivalent]
    if sides:
        slab = tuple(float(v) for v in np.mean(np.array(sides), axis=0))
        for slab_id in ("floor", "ceiling"):
            equivalent[slab_id], tiers[slab_id] = slab, "mean of the walls"

    if dominant != reference:
        inroom_note = (f", and the air inside the room is taken from a run with {inroom} walls "
                       f"(nearest in effective Z to {dominant})" if inroom != reference else "")
        warnings.append(f"the field model was trained on {', '.join(TRAINED_MATERIALS)} walls "
                        f"only. Each wall is drawn as the {reference} that transmits the "
                        f"same{inroom_note}.")
    far = sorted(wid for (ax, _), wid in FACE_WALL.items() if wid in equivalent
                 and abs(equivalent[wid][0] - built[ax]) > SLOPE_STEP_MM)
    if far:
        warnings.append(f"wall(s) {', '.join(far)} differ from the box by more than "
                        f"{SLOPE_STEP_MM:g} mm of {reference} (the box is symmetric, at least "
                        f"{VOXEL_MM:g} mm), so the field beyond them is extrapolated from the "
                        f"model's own thickness slope.")
    narrow = sorted(i for i, t in tiers.items() if t == "narrow-beam")
    if narrow:
        warnings.append(f"wall(s) {', '.join(narrow)} are served by neither model E nor the "
                        f"analytical tables; their {reference} equivalent uses narrow-beam "
                        f"attenuation (no buildup).")

    off_mm = ((s.x_m - r.width_m / 2.0) * 1000.0, (s.y_m - r.length_m / 2.0) * 1000.0, 0.0)
    return BoxMapping(labels, bb, energy, tuple(_snap_to_voxel_center(off_mm)), reference, built,
                      equivalent, tiers, inroom, room_m, warnings)


def _exit_faces(bb, source_mm):
    """For every voxel: the side of the room box its straight ray from the source leaves by, as
    (axis, direction), and the ray's path-length factor 1/cos through that side."""
    nx, ny, nz = GRID
    xc, yc, zc = _coord_axes()
    x0, x1, y0, y1, z0, z1 = bb["room"]
    lo = [(i - n / 2.0) * VOXEL_MM for i, n in ((x0, nx), (y0, ny), (z0, nz))]
    hi = [(i - n / 2.0) * VOXEL_MM for i, n in ((x1, nx), (y1, ny), (z1, nz))]
    d = [xc[None, None, :] - source_mm[0], yc[None, :, None] - source_mm[1],
         zc[:, None, None] - source_mm[2]]
    d = [np.broadcast_to(a, (nz, ny, nx)) for a in d]
    t = []
    for k in range(3):
        with np.errstate(divide="ignore", invalid="ignore"):
            t.append(np.where(d[k] > 0, (hi[k] - source_mm[k]) / d[k],
                              np.where(d[k] < 0, (lo[k] - source_mm[k]) / d[k], np.inf)))
    axis = np.argmin(np.stack(t), axis=0)
    comp = np.choose(axis, d)
    norm = np.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        slant = np.where(comp != 0, norm / np.abs(comp), np.inf)
    return axis, np.sign(comp).astype(int), slant


def _outside(labels, bb):
    x0, x1, y0, y1, z0, z1 = bb["room"]
    out = labels == 0
    out[z0:z1, y0:y1, x0:x1] = False
    return out


def _slope_steps(box: BoxMapping):
    """Candidate (x, y) side-wall steps for the slope run, preferred first: each axis steps
    TOWARD its walls' equivalent, so the correction interpolates between two runs rather than
    extrapolating. (Stepping outward from 300 to 400 mm under-read the 200-300 mm slope by half:
    beyond 400 mm the training labels are MC-noisy and the network flattens.)"""
    def toward(ax, ids):
        deltas = [box.equivalent_mm[i][0] - box.wall_mm[ax] for i in ids if i in box.equivalent_mm]
        inward = deltas and np.mean(deltas) < 0 and box.wall_mm[ax] - SLOPE_STEP_MM >= VOXEL_MM
        return -SLOPE_STEP_MM if inward else SLOPE_STEP_MM
    preferred = (toward(0, ("E", "W")), toward(1, ("N", "S")))
    return [preferred, (SLOPE_STEP_MM, SLOPE_STEP_MM), (-SLOPE_STEP_MM, -SLOPE_STEP_MM)]


def _slab_steps(box: BoxMapping):
    """Candidate floor/ceiling steps for the slab slope run, preferred first (toward the slabs'
    equivalent, as `_slope_steps` does for the side walls)."""
    eq = box.equivalent_mm.get("ceiling")
    inward = eq is not None and eq[0] < box.wall_mm[2] and box.wall_mm[2] - SLOPE_STEP_MM >= VOXEL_MM
    return [-SLOPE_STEP_MM, SLOPE_STEP_MM] if inward else [SLOPE_STEP_MM, -SLOPE_STEP_MM]


def _second_run(box: BoxMapping, run, d0, steps, first_axis: int):
    """(slope per mm, voxels air in both boxes) from the first box in `steps` that fits the domain,
    each step a (dx, dy, dz) wall change; the slope is taken along axis `first_axis` for dz-only
    steps and along the voxel's exit axis otherwise. None if none fits."""
    for step in steps:
        other = tuple(w + d for w, d in zip(box.wall_mm, step))
        if min(t for t, d in zip(other, step) if d) < VOXEL_MM:
            continue
        try:
            labels2, _ = _build_labels(box.room_m, other, box.material)
        except ValueError:
            continue
        axis, _, _ = _exit_faces(box.bb, box.source_mm)
        per_voxel = step[first_axis] if first_axis == 2 else np.where(axis == 0, step[0], step[1])
        slope = (run(labels2, box.material) - d0) / per_voxel
        return slope, _outside(box.labels, box.bb) & (labels2 == 0)
    return None


def _thickness_slope(box: BoxMapping, run, d0):
    """(d log10(dose) / d(wall thickness, mm) per voxel beyond the walls, whether the floor and
    ceiling got one). Side walls: a second U-Net run with the side walls one voxel thicker or thinner
    (`_slope_steps`); floor and ceiling: a third run with only the slabs changed (`_slab_steps`).
    Voxels that are wall in the changed box take the median of their face and slant bin. (None,
    False) if no side-wall run fits the domain; the slabs are then left uncorrected too."""
    sides = _second_run(box, run, d0, [(dx, dy, 0.0) for dx, dy in _slope_steps(box)], 0)
    if sides is None:
        return None, False
    slabs = _second_run(box, run, d0, [(0.0, 0.0, dz) for dz in _slab_steps(box)], 2)
    axis, sign, s = _exit_faces(box.bb, box.source_mm)
    slope, both = sides
    if slabs is not None:
        on_slab = axis == 2
        slope = np.where(on_slab, slabs[0], slope)
        both = np.where(on_slab, slabs[1], both)
    else:
        both = both & (axis != 2)
    s = np.clip(s, SLANTS[0], SLANTS[-1])
    out = np.full(slope.shape, np.nan)
    out[both] = slope[both]
    edges = np.concatenate([SLANTS, [np.inf]])
    outside = _outside(box.labels, box.bb)
    for (ax, direction) in FACE_WALL:
        if ax == 2 and slabs is None:
            continue
        face = outside & (axis == ax) & (sign == direction)
        for lo, hi in zip(edges[:-1], edges[1:]):
            cell = face & (s >= lo) & (s < hi)
            known = cell & both
            if cell.any() and known.any():
                out[cell & ~both] = np.median(slope[known])
    return out, slabs is not None


def _correct_beyond_walls(log_dose, box: BoxMapping, slope):
    """Move the field beyond each side wall from the built box to the wall's equivalent."""
    out = log_dose.copy()
    outside = _outside(box.labels, box.bb)
    axis, sign, s = _exit_faces(box.bb, box.source_mm)
    s = np.clip(s, SLANTS[0], SLANTS[-1])
    for (ax, direction), wid in FACE_WALL.items():
        if wid not in box.equivalent_mm:
            continue
        sel = outside & (axis == ax) & (sign == direction) & np.isfinite(slope)
        delta = np.interp(np.log(s[sel]), np.log(SLANTS), box.equivalent_mm[wid]) - box.wall_mm[ax]
        out[sel] = log_dose[sel] + slope[sel] * delta
    return out


# ----------------------------------------------------------------- torch model (lazy)
def _make_unet_cls(nn):
    """UNet3D identical to thesis_mc/src/train_field_unet.py (so the state_dict loads 1:1)."""
    def gn(ch):
        g = 8
        while ch % g:
            g //= 2
        return nn.GroupNorm(g, ch)

    class DoubleConv(nn.Module):
        def __init__(self, cin, cout):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv3d(cin, cout, 3, padding=1, bias=False), gn(cout), nn.ReLU(inplace=True),
                nn.Conv3d(cout, cout, 3, padding=1, bias=False), gn(cout), nn.ReLU(inplace=True))

        def forward(self, x):
            return self.net(x)

    class UNet3D(nn.Module):
        def __init__(self, cin=3, base=24):
            super().__init__()
            c1, c2, c3, c4 = base, base * 2, base * 4, base * 8
            self.e1, self.e2, self.e3 = DoubleConv(cin, c1), DoubleConv(c1, c2), DoubleConv(c2, c3)
            self.pool = nn.MaxPool3d(2)
            self.bott = DoubleConv(c3, c4)
            self.u3 = nn.ConvTranspose3d(c4, c3, 2, 2); self.d3 = DoubleConv(c3 * 2, c3)
            self.u2 = nn.ConvTranspose3d(c3, c2, 2, 2); self.d2 = DoubleConv(c2 * 2, c2)
            self.u1 = nn.ConvTranspose3d(c2, c1, 2, 2); self.d1 = DoubleConv(c1 * 2, c1)
            self.head = nn.Conv3d(c1, 1, 1)

        def forward(self, x):
            e1 = self.e1(x)
            e2 = self.e2(self.pool(e1))
            e3 = self.e3(self.pool(e2))
            b = self.bott(self.pool(e3))
            import torch
            d3 = self.d3(torch.cat([self.u3(b), e3], 1))
            d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
            d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
            return self.head(d1)

    return UNet3D


@dataclass
class FieldPrediction:
    log_dose: np.ndarray          # (nz, ny, nx) log10 air-kerma field; NaN outside air
    labels: np.ndarray            # (nz, ny, nx) material labels
    bb: dict                      # room / shell voxel bounding boxes
    source_vox: Tuple[int, int, int]   # (iz, iy, ix) snapped source voxel
    z_index: int                  # z slice at source mid-height (for the plan view)
    material: str                 # the single box material used
    wall_mm: Tuple[float, float, float]   # as built on the 100 mm grid
    shell_p95_log: Optional[float]     # 95th-pct log10 dose over the occupied shell
    warnings: list


class FieldModel:
    """Loads the field U-Net once and predicts the in-room dose field for a RoomDesign.

    TWO BACKENDS, ONNX PREFERRED
    ----------------------------
    The network is the same either way; only the runtime differs.

      onnx  : onnxruntime + field_unet.onnx (~12 MB model, ~15-40 MB runtime).
      torch : PyTorch + field_unet_best.pt  (~12 MB model, ~200 MB+ runtime).

    ONNX is tried first because torch does not fit a free Streamlit Cloud container, which
    is what kept the 3-D field map dark for every cloud user. The exported graph was verified
    against torch on real campaign rooms before shipping: worst occupied-shell deviation
    1.2e-04 dex, four orders below the model's own 0.068 dex accuracy and the 0.055 dex MC
    label noise, so the two backends are interchangeable for any screening decision
    (thesis_mc/src/export_unet_onnx.py).

    torch is kept as a fallback so a local dev box with torch installed still works if the
    .onnx is absent, and so the two can be compared. If neither is present the tier simply
    goes dark, exactly as before.
    """

    _MODEL = None          # torch module OR onnxruntime InferenceSession
    _NORM = None
    _BACKEND = None        # "onnx" | "torch" | None
    _TRIED = False

    def __init__(self, model_path: Optional[str] = None, norm_path: Optional[str] = None):
        self.model_path = model_path
        self.norm_path = norm_path
        self._load()

    @classmethod
    def _default_dir(cls) -> Path:
        return Path(__file__).resolve().parents[2] / "models" / "field_unet"

    def _load(self):
        if FieldModel._TRIED:
            return
        FieldModel._TRIED = True
        d = self._default_dir()
        npth = Path(self.norm_path) if self.norm_path else d / "norm.json"
        if not npth.exists():
            return
        norm = json.loads(npth.read_text())

        # ---- 1st choice: ONNX Runtime (no torch dependency) ----
        onnx_p = Path(self.model_path) if self.model_path else d / "field_unet.onnx"
        if onnx_p.suffix == ".onnx" and onnx_p.exists():
            try:
                import onnxruntime as ort
                sess = ort.InferenceSession(str(onnx_p), providers=["CPUExecutionProvider"])
                FieldModel._MODEL = sess
                FieldModel._NORM = norm
                FieldModel._BACKEND = "onnx"
                return
            except Exception:
                pass                      # fall through to torch

        # ---- fallback: PyTorch checkpoint ----
        try:
            import torch
            import torch.nn as nn
        except Exception:
            return
        mp = Path(self.model_path) if (self.model_path and Path(self.model_path).suffix == ".pt") \
            else d / "field_unet_best.pt"
        if not mp.exists():
            return
        try:
            try:
                ckpt = torch.load(mp, map_location="cpu", weights_only=True)
            except Exception:
                ckpt = torch.load(mp, map_location="cpu", weights_only=False)
            base = int(ckpt.get("base_ch", 24))
            UNet3D = _make_unet_cls(nn)
            model = UNet3D(cin=3, base=base)
            model.load_state_dict(ckpt["model"])
            model.eval()
            FieldModel._MODEL = model
            FieldModel._NORM = norm
            FieldModel._BACKEND = "torch"
        except Exception:
            FieldModel._MODEL = None
            FieldModel._NORM = None
            FieldModel._BACKEND = None

    def available(self) -> bool:
        return FieldModel._MODEL is not None and FieldModel._NORM is not None

    def backend(self) -> Optional[str]:
        """'onnx', 'torch' or None — for the UI to show which runtime served the map."""
        return FieldModel._BACKEND

    def _log_dose(self, labels: np.ndarray, energy_keV: float, source_mm) -> np.ndarray:
        """One network pass: log10 air kerma per 2e7 photons over the whole domain."""
        X = _make_input(labels, energy_keV, source_mm)
        nm = FieldModel._NORM
        ch_mean = np.asarray(nm["ch_mean"], np.float32)[:, None, None, None]
        ch_std = np.asarray(nm["ch_std"], np.float32)[:, None, None, None]
        Xb = np.ascontiguousarray(((X - ch_mean) / ch_std).astype(np.float32))[None]
        # Same graph, same channels, same de-normalisation either way — only the runtime
        # differs. Input/output names match the export in export_unet_onnx.py.
        if FieldModel._BACKEND == "onnx":
            yn = FieldModel._MODEL.run(["logdose"], {"input": Xb})[0][0, 0]
        else:
            import torch
            with torch.no_grad():
                yn = FieldModel._MODEL(torch.from_numpy(Xb)).numpy()[0, 0]
        return yn * float(nm["y_std"]) + float(nm["y_mean"])

    def predict(self, design) -> Optional[FieldPrediction]:
        """Predict the room's log10 dose field. Returns None if unavailable; raises
        ValueError (caught by the caller) if the design can't be mapped onto the box."""
        if not self.available():
            return None

        box = _design_to_box(design)
        labels, bb, source_mm, warns = box.labels, box.bb, box.source_mm, list(box.warnings)

        def run(run_labels, material):
            return self._log_dose(np.where(run_labels > 0, MATERIAL_LABEL[material], 0),
                                  box.energy_keV, source_mm)

        base = run(labels, box.material)
        slope, slabs_corrected = _thickness_slope(box, run, base)
        if slope is None:
            log_dose = base
            warns.append("the room fills the model's domain, so walls are drawn at whole "
                         f"{VOXEL_MM:g} mm steps without the finer correction.")
        else:
            log_dose = _correct_beyond_walls(base, box, slope)
            if not slabs_corrected:
                warns.append("the room fills the model's domain in height, so the floor and "
                             f"ceiling are drawn at a whole {VOXEL_MM:g} mm step without the finer "
                             "correction; the field above and below the room is approximate.")
        if box.inroom_material != box.material:
            x0, x1, y0, y1, z0, z1 = bb["room"]
            inroom = run(labels, box.inroom_material)
            log_dose[z0:z1, y0:y1, x0:x1] = inroom[z0:z1, y0:y1, x0:x1]
        material, wall_mm = box.material, box.wall_mm
        air = labels == 0
        log_dose = np.where(air, log_dose, np.nan)

        # 95th-percentile shell dose (a screening headline; not a verdict)
        shell = _occupied_shell(labels)
        vals = log_dose[shell & np.isfinite(log_dose)]
        shell_p95 = float(np.percentile(vals, 95)) if vals.size else None

        # snapped source voxel + the z-slice through the source height
        nx, ny, nz = GRID
        ix = int(np.floor(source_mm[0] / VOXEL_MM + nx / 2.0)); ix = min(max(ix, 0), nx - 1)
        iy = int(np.floor(source_mm[1] / VOXEL_MM + ny / 2.0)); iy = min(max(iy, 0), ny - 1)
        iz = int(np.floor(source_mm[2] / VOXEL_MM + nz / 2.0)); iz = min(max(iz, 0), nz - 1)

        return FieldPrediction(
            log_dose=log_dose, labels=labels, bb=bb, source_vox=(iz, iy, ix), z_index=iz,
            material=material, wall_mm=wall_mm, shell_p95_log=shell_p95, warnings=warns)


# ----------------------------------------------------------------- plan-view field render
def render_field_slice(pred: FieldPrediction, design) -> bytes:
    """Top-down heat map of the predicted dose field at the source height, walls outlined,
    source marked. Returns PNG bytes for st.image. Matplotlib only (already an app dep)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import colors
    import io

    iz = pred.z_index
    field = pred.log_dose[iz]                       # (ny, nx) log10 dose
    lab = pred.labels[iz]                            # (ny, nx) materials
    finite = field[np.isfinite(field)]
    if finite.size == 0:
        vmin, vmax = -14.0, -6.0
    else:
        vmin, vmax = np.percentile(finite, 2), np.percentile(finite, 98)
        if vmax - vmin < 0.5:
            vmax = vmin + 0.5

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    masked = np.ma.masked_invalid(field)
    cmap = plt.get_cmap("inferno").copy()
    cmap.set_bad("#e9ecef")                         # walls / no-air voxels
    im = ax.imshow(masked, origin="lower", cmap=cmap,
                   norm=colors.Normalize(vmin=vmin, vmax=vmax),
                   extent=[0, GRID[0], 0, GRID[1]], aspect="equal")
    # wall outline (any solid voxel in this slice)
    ax.contour((lab > 0).astype(float), levels=[0.5], colors="#0b3d91", linewidths=1.2,
               extent=[0, GRID[0], 0, GRID[1]])
    iz_, iy_, ix_ = pred.source_vox
    ax.plot(ix_ + 0.5, iy_ + 0.5, marker="*", color="#00e5ff", markersize=15,
            markeredgecolor="#003", markeredgewidth=0.6, label="source")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("log₁₀ air-kerma (relative field)")
    ax.set_title(f"3D dose-field U-Net — slice at source height\n"
                 f"walls drawn as their {pred.material} equivalent "
                 f"(box {pred.wall_mm[0]:.0f}/{pred.wall_mm[1]:.0f}/{pred.wall_mm[2]:.0f} mm, "
                 f"corrected to each wall)",
                 fontsize=10)
    ax.set_xlabel("x (× 100 mm, W→E)"); ax.set_ylabel("y (× 100 mm, S→N)")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()
