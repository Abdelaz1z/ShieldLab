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
and the scalar MC surrogate. A real ShieldLab room with four different wall materials is
mapped onto the U-Net's single-material box by picking the dominant wall material and the
per-axis wall thicknesses; the field is therefore an approximation and is labelled as one.

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
from pathlib import Path
from typing import Optional, Tuple

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


def mu_per_mm(material: str, energy_keV: float) -> float:
    mr = float(np.exp(np.interp(np.log(energy_keV), np.log(_E), np.log(MU_RHO[material]))))
    return mr * DENSITY[material] * 0.1        # cm^2/g * g/cm^3 -> 1/cm; *0.1 -> 1/mm


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
def _dominant_material(design) -> str:
    from collections import Counter
    mats = [w.material1 for w in design.walls if w.material1 in MATERIAL_LABEL]
    if not mats:
        return "concrete"
    return Counter(mats).most_common(1)[0][0]


def _axis_thickness(design, wall_ids) -> float:
    """Representative solid thickness (mm) for a pair of walls; >=100 mm (grid floor)."""
    ts = []
    for wid in wall_ids:
        try:
            w = design.wall(wid)
        except KeyError:
            continue
        t = (w.thickness1_mm or 0.0) + (w.thickness2_mm or 0.0 if w.material2 else 0.0)
        if t > 0:
            ts.append(t)
    return max(100.0, float(np.mean(ts))) if ts else 150.0


def _design_to_box(design):
    """Map a ShieldLab RoomDesign onto the U-Net's single-material box.

    Returns (labels, bb, energy_keV, source_mm_snapped, material, wall_mm, warnings).
    N/S walls barrier the y-axis; E/W walls barrier the x-axis; floor/ceiling (no ShieldLab
    wall) takes the room-mean thickness. The source is placed at mid-height.
    """
    warnings = []
    r = design.room
    room_m = (r.width_m, r.length_m, r.height_m)
    material = _dominant_material(design)
    distinct = {w.material1 for w in design.walls if w.material1}
    if len(distinct) > 1:
        warnings.append(f"walls use {len(distinct)} materials "
                        f"({', '.join(sorted(distinct))}); the field model is a single-material "
                        f"box, mapped to the dominant material '{material}'.")

    tx = _axis_thickness(design, ("E", "W"))
    ty = _axis_thickness(design, ("N", "S"))
    tz = _axis_thickness(design, ("N", "E", "S", "W"))     # floor/ceiling proxy
    wall_mm = (tx, ty, tz)

    labels, bb = _build_labels(room_m, wall_mm, material)   # may raise ValueError

    energy = ISOTOPE_ENERGY_KEV.get(design.source.isotope)
    if energy is None:
        raise ValueError(f"no field-model energy for isotope '{design.source.isotope}'")

    # source: room coords (SW origin) -> domain-centred mm, mid-height, snapped to a voxel centre
    s = design.source
    off_mm = ((s.x_m - r.width_m / 2.0) * 1000.0,
              (s.y_m - r.length_m / 2.0) * 1000.0,
              0.0)
    source_mm = _snap_to_voxel_center(off_mm)
    return labels, bb, energy, source_mm, material, wall_mm, warnings


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
    wall_mm: Tuple[float, float, float]
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

    def predict(self, design) -> Optional[FieldPrediction]:
        """Predict the room's log10 dose field. Returns None if unavailable; raises
        ValueError (caught by the caller) if the design can't be mapped onto the box."""
        if not self.available():
            return None

        labels, bb, energy, source_mm, material, wall_mm, warns = _design_to_box(design)
        X = _make_input(labels, energy, source_mm)
        nm = FieldModel._NORM
        ch_mean = np.asarray(nm["ch_mean"], np.float32)[:, None, None, None]
        ch_std = np.asarray(nm["ch_std"], np.float32)[:, None, None, None]
        Xn = ((X - ch_mean) / ch_std).astype(np.float32)
        Xb = np.ascontiguousarray(Xn)[None]                            # (1,3,nz,ny,nx)

        # Same graph, same channels, same de-normalisation either way — only the runtime
        # differs. Input/output names match the export in export_unet_onnx.py.
        if FieldModel._BACKEND == "onnx":
            yn = FieldModel._MODEL.run(["logdose"], {"input": Xb})[0][0, 0]
        else:
            import torch
            with torch.no_grad():
                yn = FieldModel._MODEL(torch.from_numpy(Xb)).numpy()[0, 0]
        log_dose = yn * float(nm["y_std"]) + float(nm["y_mean"])       # un-normalise -> log10 dose
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
                 f"single-material box: {pred.material}, walls "
                 f"{pred.wall_mm[0]:.0f}/{pred.wall_mm[1]:.0f}/{pred.wall_mm[2]:.0f} mm",
                 fontsize=10)
    ax.set_xlabel("x (× 100 mm, W→E)"); ax.set_ylabel("y (× 100 mm, S→N)")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.85)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()
