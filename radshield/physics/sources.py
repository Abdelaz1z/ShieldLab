"""
sources.py
==========
SOURCE TERMS: the UNSHIELDED radiation level at the occupied point, before any
barrier. This is where modality + maximum energy + workload + distance combine.

Each function returns a `SourceTerm` giving the unshielded primary and secondary
(scatter + leakage) dose at the point of interest, in the natural unit for that
modality, together with the matching `Beam` objects the barrier engine needs.

The geometry convention follows NCRP 147 / SRS 47:
    * distances are measured from the radiation source (tube focus, isocentre,
      or patient) to the point of interest, in METRES;
    * the point of protection is taken 0.3 m beyond the barrier surface;
    * inverse-square (1/d^2) reduces the per-source-strength dose with distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from .. import data_loader as dl
from . import beams as bm


@dataclass
class Component:
    """One unshielded dose contribution at the point, with the beam to attenuate it."""
    name: str               # 'primary', 'scatter', 'leakage'
    unshielded: float       # unshielded dose at the point (in `unit`)
    beam: bm.Beam           # beam used to compute this component's transmission
    detail: str = ""        # short human note (how it was computed)


@dataclass
class SourceTerm:
    """All unshielded contributions at one point for one modality."""
    modality: str
    unit: str               # e.g. 'mGy/week' (air kerma) or 'mSv/week'
    period: str             # e.g. 'week'
    components: List[Component] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    refs: List[str] = field(default_factory=list)

    def total_unshielded(self) -> float:
        return sum(c.unshielded for c in self.components)


# ---------------------------------------------------------------------------
# DIAGNOSTIC X-RAY (radiography, fluoroscopy, R&F, chest, dental, mammography)
# ---------------------------------------------------------------------------

def diagnostic_source(distribution: str, patients_per_week: float,
                      d_primary_m: float, d_secondary_m: float,
                      kvp: Optional[int] = None,
                      include_primary: bool = True,
                      secondary_geometry: str = "leak_forward_back") -> SourceTerm:
    """Unshielded air kerma (mGy/week) at a point for a diagnostic X-ray room.

    Method (NCRP 147):
        primary   :  K_pri = K1_P  * N / d_primary^2
        secondary :  K_sec = K1_sec * N / d_secondary^2
    where K1_P (Table 4.5) and K1_sec (Table 4.7) are the unshielded air kerma
    per patient at 1 m for the chosen workload distribution, and N is the number
    of patients per week.

    Parameters
    ----------
    distribution      : NCRP 147 workload distribution key (e.g. 'chest_room').
    patients_per_week : number of patients N.
    d_primary_m       : tube-to-point distance for the primary beam.
    d_secondary_m     : patient-to-point distance for scatter/leakage.
    secondary_geometry: which Table 4.7 column ('leak_side_scatter',
                        'forward_back', or 'leak_forward_back' = conservative).
    """
    wl = dl.workloads()["diagnostic"]
    sc = dl.scatter()["diagnostic_secondary_kerma"]
    st = SourceTerm(modality="diagnostic", unit="mGy/week (air kerma)",
                    period="week", refs=["NCRP147"])

    # PRIMARY (only distributions whose primary beam strikes a barrier) ----
    prim = wl["primary_kerma_per_patient"].get(distribution)
    if include_primary and prim:
        K1_P = prim["K1_P_mGy_per_patient"]
        K_pri = K1_P * patients_per_week / (d_primary_m ** 2)
        st.components.append(Component(
            "primary", K_pri,
            bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="primary",
                    distribution=distribution, kvp=kvp),
            detail=f"K1_P={K1_P} mGy/patient @1m x {patients_per_week} pt / {d_primary_m} m^2",
        ))

    # SECONDARY (scatter + leakage) ----------------------------------------
    order = sc["_order"]
    if distribution in order:
        i = order.index(distribution)
        K1_sec = sc[secondary_geometry][i]
        if K1_sec is not None:
            K_sec = K1_sec * patients_per_week / (d_secondary_m ** 2)
            st.components.append(Component(
                "secondary", K_sec,
                bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary",
                        distribution=distribution, kvp=kvp),
                detail=f"K1_sec({secondary_geometry})={K1_sec} mGy/patient @1m "
                       f"x {patients_per_week} pt / {d_secondary_m} m^2",
            ))
    st.notes.append("Air kerma at the reference point (0.3 m beyond barrier per NCRP 147).")
    return st


# ---------------------------------------------------------------------------
# COMPUTED TOMOGRAPHY (secondary/scatter only)
# ---------------------------------------------------------------------------

def ct_source(dlp_per_exam_mGy_cm: float, exams_per_week: float,
              d_secondary_m: float) -> SourceTerm:
    """Unshielded scattered air kerma (mGy/week) from a CT scanner.

    CT is treated as a pure scatter source. NCRP 147 Section 5.5:
        K_sec(d) = kappa * (DLP_total per week) / d^2
    with kappa the scatter air kerma at 1 m per unit DLP (editable in scatter.json).
    """
    ct = dl.scatter()["ct"]
    kappa = ct["scatter_air_kerma_per_DLP"]["value"]
    dlp_total = dlp_per_exam_mGy_cm * exams_per_week
    K_sec = kappa * dlp_total / (d_secondary_m ** 2)
    st = SourceTerm(modality="ct", unit="mGy/week (air kerma)", period="week",
                    refs=["NCRP147", "BIR2012"])
    st.components.append(Component(
        "scatter", K_sec,
        bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.07),  # CT scatter ~70 keV effective
        detail=f"kappa={kappa} mGy/(mGy*cm)@1m x DLP_total {dlp_total:g} mGy*cm / {d_secondary_m} m^2",
    ))
    st.notes.append("CT scatter scales with total DLP per week; kappa is scanner-dependent (verify).")
    return st


# ---------------------------------------------------------------------------
# MEGAVOLTAGE (LINAC / Co-60)
# ---------------------------------------------------------------------------

def linac_source(W_Gy_per_week: float, mv_energy: str,
                 d_primary_m: float, d_secondary_m: float,
                 U_primary: float = 0.25, imrt_factor: float = 1.0,
                 field_cm2: float = 400.0, scatter_angle_deg: float = 90.0,
                 use_patient_attenuation: bool = False) -> SourceTerm:
    """Unshielded dose (mSv/week ~ mGy/week) at a point for a megavoltage vault.

    Method (IAEA SRS 47 / NCRP 151), three components at the point:
        primary  :  H_pri = W * U / d_pri^2            (optionally x patient transmission f)
        leakage  :  H_leak = W * 0.001 * C_I / d_sec^2 (0.1% head leakage; IMRT factor on MU)
        scatter  :  H_sca = W * a * (field/400) / d_sec^2
    'a' is the patient scatter fraction at the chosen angle (SRS 47 Table 5).
    """
    mv = dl.tvl_megavoltage()
    st = SourceTerm(modality="megavoltage", unit="mSv/week", period="week",
                    refs=["SRS47", "NCRP151"])

    # PRIMARY --------------------------------------------------------------
    f = 1.0
    if use_patient_attenuation:
        pt = mv["patient_transmission_f"]
        if mv_energy in pt["energies"]:
            f = pt["f"][pt["energies"].index(mv_energy)]
    H_pri = W_Gy_per_week * 1000.0 * U_primary * f / (d_primary_m ** 2)  # Gy->mGy(~mSv)
    st.components.append(Component(
        "primary", H_pri,
        bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="primary", mv_energy=mv_energy),
        detail=f"W={W_Gy_per_week} Gy/wk x U={U_primary} x f={f} / {d_primary_m} m^2",
    ))

    # LEAKAGE --------------------------------------------------------------
    leak_frac = mv["leakage_fraction"]["value"]
    H_leak = W_Gy_per_week * 1000.0 * leak_frac * imrt_factor / (d_secondary_m ** 2)
    st.components.append(Component(
        "leakage", H_leak,
        bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="secondary", mv_energy=mv_energy),
        detail=f"W x {leak_frac} (0.1% leakage) x C_I={imrt_factor} / {d_secondary_m} m^2",
    ))

    # SCATTER (off patient) ------------------------------------------------
    sf = mv["scatter_fraction_a"]
    a = None
    if mv_energy in sf["energies"]:
        col = sf["energies"].index(mv_energy)
        ang = str(int(scatter_angle_deg))
        if ang in sf["values"]:
            a = sf["values"][ang][col]
    if a is not None:
        H_sca = W_Gy_per_week * 1000.0 * a * (field_cm2 / sf["reference_field_cm2"]) / (d_secondary_m ** 2)
        st.components.append(Component(
            "scatter", H_sca,
            bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="scatter",
                    mv_energy=mv_energy, scatter_angle_deg=scatter_angle_deg),
            detail=f"W x a({int(scatter_angle_deg)}deg)={a} x field/{sf['reference_field_cm2']} / {d_secondary_m} m^2",
        ))

    if mv_energy not in ("Co-60", "4 MV", "6 MV", "10 MV"):
        st.notes.append("PHOTONEUTRONS: energy > 10 MV produces neutrons not modelled here "
                        "(photons only). Maze/door neutron design needs a qualified expert.")
    return st


# ---------------------------------------------------------------------------
# RADIONUCLIDE point source (rooms: Tc-99m, F-18, generic)
# ---------------------------------------------------------------------------

# 1 R ~ 10 mSv (conservative ambient-dose approximation, see radionuclides.json).
R_TO_MSV = 10.0


def radionuclide_point_source(nuclide: str, activity_mCi: float, d_m: float,
                              hours_per_week: float = 40.0,
                              occupancy: float = 1.0) -> SourceTerm:
    """Unshielded dose (mSv/week) at a point from a radionuclide point source.

    Dose rate at distance d (m) for activity A (mCi):
        dose_rate = Gamma * A / d^2     (Gamma in R*cm^2/mCi*h, d in cm)
    Converted to mSv and integrated over the occupied hours per week.

    Used for imaging rooms (Tc-99m, F-18 stored/decaying sources) and as the
    base for therapy-room wall design. For the I-131 RELEASED PATIENT integrated
    dose, use i131_released_patient_dose() instead.
    """
    data = dl.radionuclides()["radionuclides"]
    nuc = data.get(nuclide)
    if not nuc:
        raise ValueError(f"Unknown radionuclide '{nuclide}'.")
    gamma = nuc["dose_rate_constant"]                # R*cm^2/(mCi*h)
    d_cm = d_m * 100.0
    dose_rate_R_per_h = gamma * activity_mCi / (d_cm ** 2)
    dose_rate_mSv_per_h = dose_rate_R_per_h * R_TO_MSV
    weekly = dose_rate_mSv_per_h * hours_per_week * occupancy

    st = SourceTerm(modality=f"radionuclide_{nuclide}", unit="mSv/week", period="week",
                    refs=["OUMANO2025", "RG839"])
    e_keV = nuc.get("main_gamma_keV", 364)
    st.components.append(Component(
        "primary", weekly,
        bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide=nuclide),
        detail=f"Gamma={gamma} R*cm^2/mCi*h x {activity_mCi} mCi / ({d_cm} cm)^2 "
               f"x {R_TO_MSV} mSv/R x {hours_per_week} h/wk x T={occupancy}",
    ))
    st.notes.append(f"Point-source dose at {e_keV} keV; broad-beam TVL shielding. "
                    f"1 R ~ {R_TO_MSV} mSv approximation (editable).")
    return st


def i131_released_patient_dose(activity_mCi: float, condition: str,
                               distance_m: float = 1.0) -> Dict[str, float]:
    """Integrated dose (mSv) to a nearby person from a released I-131 patient.

    Implements RG 8.39 Eq. B-5 (three-component biokinetic model):
        D(inf) = 34.6 * Gamma * Q0 * E / r^2 *
                 { 0.8*(1 - e^{-0.693*0.33/Tp})
                   + e^{-0.693*0.33/Tp} * [F1*T1eff + F2*T2eff] }
    Returns the dose and whether release criteria are met. This is the
    patient-as-source therapy calculation (not a barrier transmission).
    """
    bk = dl.radionuclides()["i131_biokinetics"]
    cond = bk["medical_conditions"].get(condition)
    if not cond:
        raise ValueError(f"Unknown I-131 condition '{condition}'. "
                         f"Options: {list(bk['medical_conditions'])}")
    gamma = dl.radionuclides()["radionuclides"]["I-131"]["dose_rate_constant"]  # 2.2
    Tp = bk["physical_half_life_days"]
    E1 = bk["occupancy_factor_first_8h"]
    E2 = bk["occupancy_factor_after_8h"]
    F1, T1 = cond["F1_extrathyroidal"], cond["T1eff_days"]
    F2, T2 = cond["F2_thyroidal"], cond["T2eff_days"]
    r_cm = distance_m * 100.0

    decay_8h = math.exp(-0.693 * 0.33 / Tp)
    # first 8 h (physical half-life, 80% of activity), then the two biokinetic comps
    term1 = E1 * 0.8 * (1 - decay_8h) * Tp
    term2 = E2 * decay_8h * (F1 * T1 + F2 * T2)
    # The constant 34.6 with Gamma in R*cm^2/mCi*h yields the integrated exposure
    # in roentgen (~rem); 1 rem = 10 mSv. (Validated vs RG 8.39 Example 2: 200 mCi
    # thyroid-cancer -> 4.53 mSv.)
    dose_rem = 34.6 * gamma * activity_mCi * (term1 + term2) / (r_cm ** 2)
    dose_mSv = dose_rem * 10.0

    limits = bk["release_dose_limits"]
    return {
        "dose_mSv": dose_mSv,
        "may_release": dose_mSv <= limits["total_effective_dose_to_others_mSv"],
        "instructions_required": dose_mSv > limits["instructions_required_above_mSv"],
        "release_limit_mSv": limits["total_effective_dose_to_others_mSv"],
        "condition": condition,
        "activity_mCi": activity_mCi,
    }
