"""Photon transport through a shielded room: the dose that goes around a barrier as well as through it.

Geometry: non-overlapping axis-aligned boxes in an air world (metres in, centimetres inside).
Physics: incoherent scattering (Klein-Nishina with the incoherent scattering function; Compton
energy, no Doppler), coherent scattering (form factor), photoelectric absorption by implicit
capture; no fluorescence, no electrons, no pair production (every line served is below 1.022 MeV).
Estimator: the uncollided air kerma is computed deterministically; every collision adds its
next-event (point-detector) contribution to each tally sphere. Uncertainty from independent batches.

Cross sections are tables per unit density (`shieldlab/data/transport_tables.npz`, built from
xraylib in the research repository by `room_transport_dev/build_app_tables.py`) for the Geant4/PNNL
compositions the Monte Carlo campaigns used; a product is transported at its own density. The
air kerma uses the NIST (Hubbell & Seltzer) dry-air mu_en/rho table.

Validated in the research repository against GATE 10 (Geant4 11.4) in a pre-registered room it was
not built on (Room-2, 2026-09-28): within x2 of GATE at every one of 212 behind-barrier pairs,
four nuclides, median deviation 0.5%.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

try:
    import numba as nb
except ImportError:          # the tier reports itself unavailable; nothing else in the app needs numba
    nb = None

TABLES = Path(__file__).resolve().parent.parent / "data" / "transport_tables.npz"
KEV_TO_J = 1.602176634e-16
E_MIN, E_MAX, N_E = 10.0, 1600.0, 320
N_THETA = 721
N_F = 4096
LOG_E_MIN, LOG_E_MAX = math.log(E_MIN), math.log(E_MAX)
E_GRID = np.exp(np.linspace(LOG_E_MIN, LOG_E_MAX, N_E))
THETA = np.linspace(0.0, math.pi, N_THETA)
TAU_CUT = 40.0
AIR_ID = 0
HC_KEV_ANGSTROM = 12.39842


def available() -> bool:
    return nb is not None and TABLES.exists()


def _njit(**options):
    return nb.njit(cache=True, **options) if nb is not None else (lambda fn: fn)


_prange = nb.prange if nb is not None else range


def _normalise(dcs, sin):
    """pdf per steradian and its CDF in theta, normalised over the sphere."""
    w = dcs * sin[None, None, :] * 2 * math.pi
    dth = THETA[1] - THETA[0]
    cum = np.concatenate([np.zeros(w.shape[:2] + (1,)), np.cumsum(0.5 * (w[..., 1:] + w[..., :-1]) * dth, -1)], -1)
    total = cum[..., -1:]
    return dcs / total, cum / total


def _angular_tables(s, f2, x):
    """Klein-Nishina x S(x) and Thomson x F(x)^2 on (E_GRID, THETA), normalised per material."""
    e = E_GRID[None, :, None]
    th = THETA[None, None, :]
    k = 1.0 / (1.0 + e / 511.0 * (1.0 - np.cos(th)))
    kn = 0.5 * k ** 2 * (k + 1.0 / k - np.sin(th) ** 2)
    thomson = 0.5 * (1.0 + np.cos(th) ** 2)
    xm = (np.sin(th / 2.0) * e / HC_KEV_ANGSTROM)[0]
    dcs_inc = kn * np.stack([np.interp(xm, x, row) for row in s])
    dcs_coh = thomson * np.stack([np.interp(xm, x, row) for row in f2])
    sin = np.sin(THETA)
    return _normalise(dcs_inc, sin), _normalise(dcs_coh, sin)


def kerma_factor(e_kev: float) -> float:
    """E * mu_en/rho of dry air (keV cm2/g), from the same table the transport tallies with."""
    l_kf = np.load(TABLES)["l_kf"]
    x = (math.log(e_kev) - LOG_E_MIN) / (LOG_E_MAX - LOG_E_MIN) * (N_F - 1)
    return math.exp(np.interp(x, np.arange(N_F), l_kf))


def load_tables(densities: dict) -> dict:
    """Linear coefficients (1/cm, as logarithms) and angular tables for {material: density g/cm3};
    air must come first."""
    raw = np.load(TABLES)
    names = list(raw["names"])
    if tuple(raw["grid"]) != (E_MIN, E_MAX, N_E, N_THETA, N_F):
        raise ValueError(f"{TABLES.name} was built on another energy/angle grid")
    unknown = set(densities) - set(names)
    if unknown:
        raise ValueError(f"no transport data for {sorted(unknown)}")
    rows = [names.index(m) for m in densities]
    log_rho = np.log(np.array(list(densities.values()), float))[:, None]
    (pdf_inc, cdf_inc), (pdf_coh, cdf_coh) = _angular_tables(raw["s"][rows], raw["f2"][rows], raw["x"])
    return dict(l_inc=raw["l_inc"][rows] + log_rho, l_coh=raw["l_coh"][rows] + log_rho,
                l_pe=raw["l_pe"][rows] + log_rho, l_tot=raw["l_tot"][rows] + log_rho, l_kf=raw["l_kf"],
                pdf_inc=pdf_inc, cdf_inc=cdf_inc, pdf_coh=pdf_coh, cdf_coh=cdf_coh)


# ------------------------------------------------------------------ numba kernels
@_njit()
def _rand(state):
    state[0] = (state[0] + np.uint64(0x9E3779B97F4A7C15))
    z = state[0]
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    z = z ^ (z >> np.uint64(31))
    return (z >> np.uint64(11)) * (1.0 / 9007199254740992.0)


@_njit()
def _eidx(e):
    x = (math.log(e) - math.log(E_MIN)) / (math.log(E_MAX) - math.log(E_MIN)) * (N_E - 1)
    if x < 0.0:
        return 0, 0.0
    if x >= N_E - 1:
        return N_E - 2, 1.0
    i = int(x)
    return i, x - i


@_njit()
def _lerp(ltab, m, i, f):
    """Log-log interpolation in a table of logarithms."""
    return math.exp(ltab[m, i] + f * (ltab[m, i + 1] - ltab[m, i]))


@_njit()
def _fidx(e):
    x = (math.log(e) - LOG_E_MIN) / (LOG_E_MAX - LOG_E_MIN) * (N_F - 1)
    if x < 0.0:
        return 0, 0.0
    if x >= N_F - 1:
        return N_F - 2, 1.0
    i = int(x)
    return i, x - i


@_njit()
def _mu_all(l_tot, e, out):
    i, f = _fidx(e)
    for m in range(out.shape[0]):
        out[m] = math.exp(l_tot[m, i] + f * (l_tot[m, i + 1] - l_tot[m, i]))


@_njit()
def _kf(l_kf, e):
    """Kerma factor E * mu_en/rho(air) in keV cm2/g."""
    i, f = _fidx(e)
    return math.exp(l_kf[i] + f * (l_kf[i + 1] - l_kf[i]))


@_njit()
def _box_interval(lo, hi, b, p, u):
    t0, t1 = 0.0, 1e30
    for k in range(3):
        if abs(u[k]) < 1e-15:
            if p[k] < lo[b, k] or p[k] > hi[b, k]:
                return 1.0, 0.0
        else:
            a = (lo[b, k] - p[k]) / u[k]
            c = (hi[b, k] - p[k]) / u[k]
            if a > c:
                a, c = c, a
            if a > t0:
                t0 = a
            if c < t1:
                t1 = c
    return t0, t1


@_njit()
def _world_exit(wlo, whi, p, u):
    t = 1e30
    for k in range(3):
        if u[k] > 1e-15:
            t = min(t, (whi[k] - p[k]) / u[k])
        elif u[k] < -1e-15:
            t = min(t, (wlo[k] - p[k]) / u[k])
    return max(t, 0.0)


@_njit()
def _optical(lo, hi, bmat, mu, p, u, dist):
    """Optical depth from p along u over dist (cm); mu[m] is precomputed at the photon energy."""
    tau, inside = 0.0, 0.0
    for b in range(lo.shape[0]):
        t0, t1 = _box_interval(lo, hi, b, p, u)
        if t1 > dist:
            t1 = dist
        if t1 > t0:
            tau += (t1 - t0) * mu[bmat[b]]
            inside += t1 - t0
    return tau + (dist - inside) * mu[AIR_ID]


@_njit()
def _chords(lo, hi, bmat, p, u, dist, acc):
    """Path length (cm) per medium from p along u over dist, into acc (air included). Slab test
    with the inverse direction computed once per ray."""
    acc[:] = 0.0
    inside = 0.0
    ix = 1.0 / u[0] if abs(u[0]) > 1e-15 else 1e300
    iy = 1.0 / u[1] if abs(u[1]) > 1e-15 else 1e300
    iz = 1.0 / u[2] if abs(u[2]) > 1e-15 else 1e300
    for b in range(lo.shape[0]):
        a, c = (lo[b, 0] - p[0]) * ix, (hi[b, 0] - p[0]) * ix
        t0, t1 = min(a, c), max(a, c)
        a, c = (lo[b, 1] - p[1]) * iy, (hi[b, 1] - p[1]) * iy
        t0, t1 = max(t0, min(a, c)), min(t1, max(a, c))
        a, c = (lo[b, 2] - p[2]) * iz, (hi[b, 2] - p[2]) * iz
        t0, t1 = max(t0, min(a, c), 0.0), min(t1, max(a, c), dist)
        if t1 > t0:
            acc[bmat[b]] += t1 - t0
            inside += t1 - t0
    acc[AIR_ID] += dist - inside


@_njit()
def _collide(lo, hi, bmat, wlo, whi, mu, p, u, target, ts, te, tm):
    """Distance to the collision where the optical depth reaches target; -1 if the photon escapes.
    Also returns the medium there."""
    tw = _world_exit(wlo, whi, p, u)
    n = 0
    for b in range(lo.shape[0]):
        t0, t1 = _box_interval(lo, hi, b, p, u)
        if t1 > tw:
            t1 = tw
        if t1 > t0:
            j = n
            while j > 0 and ts[j - 1] > t0:
                ts[j], te[j], tm[j] = ts[j - 1], te[j - 1], tm[j - 1]
                j -= 1
            ts[j], te[j], tm[j] = t0, t1, bmat[b]
            n += 1
    tau, pos = 0.0, 0.0
    for k in range(n + 1):
        a_end = ts[k] if k < n else tw
        if a_end > pos:
            d = (a_end - pos) * mu[AIR_ID]
            if tau + d >= target:
                return pos + (target - tau) / mu[AIR_ID], AIR_ID
            tau += d
            pos = a_end
        if k < n:
            d = (te[k] - ts[k]) * mu[tm[k]]
            if tau + d >= target:
                return ts[k] + (target - tau) / mu[tm[k]], tm[k]
            tau += d
            pos = te[k]
    return -1.0, -1


@_njit()
def _pdf_at(pdf, m, i, f, theta):
    x = theta / math.pi * (N_THETA - 1)
    j = min(int(x), N_THETA - 2)
    g = x - j
    a = (1 - g) * pdf[m, i, j] + g * pdf[m, i, j + 1]
    b = (1 - g) * pdf[m, i + 1, j] + g * pdf[m, i + 1, j + 1]
    return (1 - f) * a + f * b


@_njit()
def _sample_theta(cdf, m, i, f, r):
    row = i if f < 0.5 else i + 1
    lo_j, hi_j = 0, N_THETA - 1
    while hi_j - lo_j > 1:
        mid = (lo_j + hi_j) // 2
        if cdf[m, row, mid] < r:
            lo_j = mid
        else:
            hi_j = mid
    c0, c1 = cdf[m, row, lo_j], cdf[m, row, hi_j]
    g = (r - c0) / (c1 - c0) if c1 > c0 else 0.5
    return (lo_j + g) * math.pi / (N_THETA - 1)


@_njit()
def _rotate(u, cos_t, phi, out):
    sin_t = math.sqrt(max(0.0, 1 - cos_t * cos_t))
    ux, uy, uz = u[0], u[1], u[2]
    w = math.sqrt(max(0.0, 1 - uz * uz))
    if w < 1e-8:
        out[0], out[1], out[2] = sin_t * math.cos(phi), sin_t * math.sin(phi), cos_t * (1.0 if uz > 0 else -1.0)
    else:
        out[0] = ux * cos_t + sin_t * (ux * uz * math.cos(phi) - uy * math.sin(phi)) / w
        out[1] = uy * cos_t + sin_t * (uy * uz * math.cos(phi) + ux * math.sin(phi)) / w
        out[2] = uz * cos_t - sin_t * math.cos(phi) * w
    nrm = math.sqrt(out[0] ** 2 + out[1] ** 2 + out[2] ** 2)
    out[0] /= nrm
    out[1] /= nrm
    out[2] /= nrm


@_njit()
def _in_sphere(state, pts, rad, q, out):
    while True:
        a, b, g = 2 * _rand(state) - 1, 2 * _rand(state) - 1, 2 * _rand(state) - 1
        if a * a + b * b + g * g <= 1.0:
            break
    out[0], out[1], out[2] = pts[q, 0] + a * rad[q], pts[q, 1] + b * rad[q], pts[q, 2] + g * rad[q]


@_njit(parallel=True)
def _run(lo, hi, bmat, wlo, whi, l_inc, l_coh, l_pe, l_tot, mu_min, l_kf, pdf_inc, cdf_inc, pdf_coh, cdf_coh,
         src, line_e, line_cdf, ysum, pts, rad, rmin, n_batches, per_batch, seed, w_min):
    nm = l_tot.shape[0]
    npnt = pts.shape[0]
    out = np.zeros((n_batches, npnt))
    for bt in _prange(n_batches):
        state = np.array([np.uint64(seed) * np.uint64(1000003) + np.uint64(bt) * np.uint64(0x632BE59BD9B4E019)],
                         dtype=np.uint64)
        mu = np.empty(nm)
        mu2 = np.empty(nm)
        ts, te = np.empty(lo.shape[0] + 1), np.empty(lo.shape[0] + 1)
        tm = np.empty(lo.shape[0] + 1, dtype=np.int64)
        p, u, u2, v = np.empty(3), np.empty(3), np.empty(3), np.empty(3)
        tally = np.zeros(npnt)
        acc = np.empty(nm)
        tgt = np.empty(3)
        for _ in range(per_batch):
            r = _rand(state)
            k = 0
            while line_cdf[k] < r:
                k += 1
            e = line_e[k]
            w = ysum
            cz = 2 * _rand(state) - 1
            ph = 2 * math.pi * _rand(state)
            sz = math.sqrt(1 - cz * cz)
            u[0], u[1], u[2] = sz * math.cos(ph), sz * math.sin(ph), cz
            p[0], p[1], p[2] = src[0], src[1], src[2]
            while True:
                _mu_all(l_tot, e, mu)
                target = -math.log(1.0 - _rand(state))
                d, m = _collide(lo, hi, bmat, wlo, whi, mu, p, u, target, ts, te, tm)
                if d < 0:
                    break
                for c in range(3):
                    p[c] += d * u[c]
                i, f = _eidx(e)
                s_inc = _lerp(l_inc, m, i, f)
                s_coh = _lerp(l_coh, m, i, f)
                s_tot = s_inc + s_coh + _lerp(l_pe, m, i, f)
                w *= (s_inc + s_coh) / s_tot
                f_inc = s_inc / (s_inc + s_coh)
                kf0 = _kf(l_kf, e)
                # next-event estimate to a uniform point inside every tally sphere
                for q in range(npnt):
                    _in_sphere(state, pts, rad, q, tgt)
                    dist = 0.0
                    for c in range(3):
                        v[c] = tgt[c] - p[c]
                        dist += v[c] * v[c]
                    dist = math.sqrt(dist)
                    for c in range(3):
                        v[c] /= dist
                    _chords(lo, hi, bmat, p, v, dist, acc)
                    # mu_min[m] bounds every energy's coefficient from below, so a path whose
                    # optical depth exceeds TAU_CUT even at mu_min contributes < exp(-TAU_CUT)
                    tau_lb = 0.0
                    for mm in range(nm):
                        tau_lb += acc[mm] * mu_min[mm]
                    if tau_lb > TAU_CUT:
                        continue
                    tau0 = 0.0
                    for mm in range(nm):
                        tau0 += acc[mm] * mu[mm]
                    cos_t = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
                    e1 = e / (1 + e / 511.0 * (1 - cos_t))
                    theta = math.acos(max(-1.0, min(1.0, cos_t)))
                    fi, ff = _fidx(e1)
                    tau1 = 0.0
                    for mm in range(nm):
                        if acc[mm] > 0.0:
                            tau1 += acc[mm] * math.exp(l_tot[mm, fi] + ff * (l_tot[mm, fi + 1] - l_tot[mm, fi]))
                    k_inc = f_inc * _pdf_at(pdf_inc, m, i, f, theta) * math.exp(-tau1) * _kf(l_kf, e1)
                    k_coh = (1 - f_inc) * _pdf_at(pdf_coh, m, i, f, theta) * math.exp(-tau0) * kf0
                    tally[q] += w * (k_inc + k_coh) / max(dist, rmin) ** 2
                # scatter
                if _rand(state) < f_inc:
                    theta = _sample_theta(cdf_inc, m, i, f, _rand(state))
                    cos_t = math.cos(theta)
                    e = e / (1 + e / 511.0 * (1 - cos_t))
                else:
                    theta = _sample_theta(cdf_coh, m, i, f, _rand(state))
                    cos_t = math.cos(theta)
                _rotate(u, cos_t, 2 * math.pi * _rand(state), u2)
                u[0], u[1], u[2] = u2[0], u2[1], u2[2]
                if e < E_MIN:
                    break
                if w < w_min * ysum:
                    if _rand(state) < 0.1:
                        w *= 10.0
                    else:
                        break
        for q in range(npnt):
            out[bt, q] = tally[q] * KEV_TO_J * 1e3 / per_batch   # Gy per decay (J/g -> J/kg)
    return out


# ------------------------------------------------------------------ public
class Room:
    def __init__(self, boxes, world_lo_m, world_hi_m, densities):
        """boxes: objects with .lo, .hi (m) and .material; densities: {material: g/cm3} for every
        material the boxes use (air is added at 0.00120479 g/cm3 if absent)."""
        used = sorted({b.material for b in boxes} - {"air"})
        self.names = ["air", *used]
        rho = {"air": 0.00120479} | dict(densities)
        self.lo = np.array([b.lo for b in boxes], float).reshape(-1, 3) * 100.0
        self.hi = np.array([b.hi for b in boxes], float).reshape(-1, 3) * 100.0
        self.bmat = np.array([self.names.index(b.material) for b in boxes], np.int64)
        self.wlo = np.array(world_lo_m, float) * 100.0
        self.whi = np.array(world_hi_m, float) * 100.0
        self.t = load_tables({name: rho[name] for name in self.names})

    def uncollided(self, src_m, lines, pts_m, radii_m, n_sample=512, seed=7):
        """Deterministic uncollided air kerma per decay (Gy), averaged over each tally sphere."""
        t = self.t
        s = np.array(src_m, float) * 100.0
        rng = np.random.default_rng(seed)
        offsets = rng.normal(size=(n_sample, 3))
        offsets *= (rng.random(n_sample) ** (1 / 3) / np.linalg.norm(offsets, axis=1))[:, None]
        mu = np.empty(len(self.names))
        out = np.zeros(len(pts_m))
        for j, (pt, rad) in enumerate(zip(np.array(pts_m, float) * 100.0, np.array(radii_m, float) * 100.0)):
            for off in offsets:
                d = pt + off * rad - s
                r = float(np.linalg.norm(d))
                for e, y in lines:
                    _mu_all(t["l_tot"], e, mu)
                    tau = _optical(self.lo, self.hi, self.bmat, mu, s, d / r, r)
                    out[j] += y / (4 * math.pi * r * r) * math.exp(-tau) * _kf(t["l_kf"], e)
        return out * KEV_TO_J * 1e3 / n_sample

    def scattered(self, src_m, lines, pts_m, radii_m, n, seed=1, n_batches=64, rmin_cm=10.0, w_min=1e-4):
        """Collided air kerma per decay (Gy), averaged over each tally sphere: mean and standard error."""
        t = self.t
        e = np.array([l[0] for l in lines], float)
        y = np.array([l[1] for l in lines], float)
        cdf = np.cumsum(y) / y.sum()
        cdf[-1] = 1.0
        per = max(1, int(n // n_batches))
        res = _run(self.lo, self.hi, self.bmat, self.wlo, self.whi, t["l_inc"], t["l_coh"], t["l_pe"], t["l_tot"],
                   np.exp(t["l_tot"].min(1)), t["l_kf"], t["pdf_inc"], t["cdf_inc"], t["pdf_coh"], t["cdf_coh"],
                   np.array(src_m, float) * 100.0, e, cdf, float(y.sum()), np.array(pts_m, float) * 100.0,
                   np.array(radii_m, float) * 100.0, rmin_cm, n_batches, per, seed, w_min)
        return res.mean(0), res.std(0, ddof=1) / math.sqrt(n_batches)
