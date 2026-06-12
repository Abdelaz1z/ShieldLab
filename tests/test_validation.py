"""
test_validation.py
==================
Regression + validation tests for the ShieldLab engine. These reproduce
published worked examples so that any future edit to the data files or the
engine that breaks accuracy is caught immediately.

Run:  py -3.11 -m pytest tests/ -v        (if pytest installed)
or:   py -3.11 tests/test_validation.py   (runs a built-in fallback runner)

References for each anchor are given in the test docstrings.
"""

import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radshield.physics import transmission as tx, beams as bm, barriers as ba, sources as src, solver
from radshield.regulatory import limits as reg


# --- transmission model unit tests ------------------------------------------

def test_archer_zero_thickness():
    """Transmission through zero thickness must be exactly 1."""
    assert tx.archer_transmission(0.0, 2.5, 15.0, 0.5) == 1.0


def test_tvl_decades():
    """One TVL -> 0.1, two TVL -> 0.01 (definition of tenth-value layer)."""
    assert abs(tx.tvl_transmission(218, 218) - 0.1) < 1e-9
    assert abs(tx.tvl_transmission(436, 218) - 0.01) < 1e-9


def test_archer_inverse_roundtrip():
    """archer_thickness_for_B must invert archer_transmission."""
    a, b, g = 2.346, 15.9, 0.4982          # NCRP 147 Rad Room lead, primary
    x = 3.0
    B = tx.archer_transmission(x, a, b, g)
    x_back = tx.archer_thickness_for_B(B, a, b, g)
    assert abs(x_back - x) < 1e-3


def test_tvl_inverse_roundtrip():
    B = tx.tvl_transmission(123.0, 218.0)
    x_back = tx.tvl_thickness_for_B(B, 218.0)
    assert abs(x_back - 123.0) < 1e-6


# --- published worked-example validation ------------------------------------

def test_srs47_co60_primary_barrier():
    """IAEA SRS 47 Section 6.1.4 worked example.

    P=0.12 mSv/wk (controlled), d=3.0 m, SAD=0.8 m, W=384 Gy/wk, U=0.25, T=1.
    Required attenuation B=1.81e-5 -> 4.74 TVL -> 4.74*218 = 1033 mm concrete.
    Accept within +/- 1.5 % (engineering tolerance).
    """
    goal = reg.design_goal("NCRP", "controlled", occupancy_T=1.0, override_P_weekly=0.12)
    st = src.linac_source(384.0, "Co-60", d_primary_m=3.8, d_secondary_m=3.8, U_primary=0.25)
    st.components = [c for c in st.components if c.name == "primary"]
    req = solver.required_thickness(st, "concrete", goal)
    assert abs(req - 1033.0) / 1033.0 < 0.015, f"got {req:.1f} mm, expected ~1033 mm"


def test_rg839_i131_thyroid_cancer_example():
    """NRC RG 8.39 Appendix B, Example 2.

    200 mCi I-131 (post-thyroidectomy thyroid cancer), Eq. B-5 -> 4.53 mSv.
    """
    res = src.i131_released_patient_dose(200, "thyroid_cancer_postthyroidectomy", 1.0)
    assert abs(res["dose_mSv"] - 4.53) < 0.1, f"got {res['dose_mSv']:.2f} mSv, expected 4.53"
    assert res["may_release"] is True


def test_rg839_i131_hyperthyroid_simple():
    """RG 8.39 Eq. B-1 simple example: 60 mCi, E=0.125, physical half-life only.

    34.6 * 2.2 * 60 * 8.04 * 0.125 / 100^2 = 0.459 rem = 4.59 mSv.
    We check the closed-form Eq. B-1 directly here.
    """
    gamma, Q0, Tp, E, r_cm = 2.2, 60.0, 8.04, 0.125, 100.0
    dose_rem = 34.6 * gamma * Q0 * Tp * E / (r_cm ** 2)
    dose_mSv = dose_rem * 10.0
    assert abs(dose_mSv - 4.59) < 0.05, f"got {dose_mSv:.2f} mSv, expected 4.59"


def test_pet_511kev_lead_tvl():
    """F-18 (511 keV) lead TVL ~15.4 mm (Oumano 2025): 15.4 mm -> B~0.1."""
    beam = bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide="F-18")
    B = bm.transmission_of_layer(beam, "lead", 15.4)
    assert abs(B - 0.1) < 0.02, f"got B={B:.3f}, expected ~0.1"


def test_multilayer_is_product():
    """A two-layer barrier transmission must equal the product of the layers."""
    beam = bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="primary", mv_energy="6 MV")
    barrier = ba.Barrier().add("concrete", 343.0).add("lead", 55.0)  # ~1 TVL each at 6 MV
    B_total = barrier.transmission(beam)
    B1 = bm.transmission_of_layer(beam, "concrete", 343.0)
    B2 = bm.transmission_of_layer(beam, "lead", 55.0)
    assert abs(B_total - B1 * B2) < 1e-9


def test_verdict_pass_and_fail():
    """Verdict logic: acceptable iff transmitted <= P/T."""
    goal = reg.design_goal("NCRP", "uncontrolled", occupancy_T=1.0)  # 0.02 mGy/wk
    assert reg.verdict(0.01, goal).acceptable is True
    assert reg.verdict(0.05, goal).acceptable is False


def test_preferred_thickness_rounds_up():
    assert solver.preferred_thickness(2.336, "lead") == 2.5
    assert solver.preferred_thickness(1034.0, "concrete") == 1040.0


def test_report_builds():
    """The HTML report builder runs and includes the verdict and a reference."""
    from radshield.report import report as rpt
    st = src.diagnostic_source("chest_room", 200, 2.0, 1.5, kvp=125)
    goal = reg.design_goal("NCRP", "uncontrolled", 1.0)
    barrier = ba.Barrier().add("lead", 2.0).add("concrete", 100.0)
    ev = solver.evaluate(st, barrier, goal)
    html = rpt.build_html(source=st, barrier=barrier, goal=goal, evaluation=ev,
                          inputs={"Modality": "chest"}, prepared_by="Abdelaziz Habib")
    assert "ShieldLab" in html and ("ACCEPTABLE" in html or "NOT ACCEPTABLE" in html)
    assert "NCRP" in html


def test_all_data_files_load():
    """Every dataset parses and the citation resolver works."""
    from radshield import data_loader as dl
    for name in ["references", "limits", "archer_diagnostic", "tvl_megavoltage",
                 "radionuclides", "materials", "scatter", "workloads"]:
        assert dl.load(name)
    assert "NCRP" in dl.citation("NCRP147")


# --- fallback runner (no pytest needed) -------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
