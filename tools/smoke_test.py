# smoke_test.py
# Quick end-to-end check of the engine: transmission models, a diagnostic room,
# a LINAC vault (validated vs SRS 47 Co-60 example), an I-131 release calc, and
# the required-thickness solver. Run: py smoke_test.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radshield.physics import transmission as tx, beams as bm, barriers as ba, sources as src, solver
from radshield.regulatory import limits as reg

print("=== transmission model sanity ===")
# Archer at x=0 must be 1.0
print("Archer B(0):", tx.archer_transmission(0, 2.5, 15, 0.5))
# TVL: one TVL -> 0.1
print("TVL B(1 TVL):", tx.tvl_transmission(218, 218))   # expect 0.1
print("TVL B(2 TVL):", tx.tvl_transmission(436, 218))   # expect 0.01

print("\n=== SRS 47 Co-60 primary barrier validation ===")
# SRS 47 example: P=0.12 mSv/wk controlled, d=3.0 m, SAD 0.8, W=384e3 mGy/wk,
# U=0.25, T=1. Required B = 1.81e-5 -> 4.74 TVL -> 4.74*218 = 1033 mm concrete.
W_Gy_wk = 384.0  # 384e3 mGy/wk = 384 Gy/wk
goal = reg.design_goal("NCRP", "controlled", occupancy_T=1.0, override_P_weekly=0.12)
# unshielded primary at 3 m (use SAD-corrected distance handled by example as d+SAD)
st = src.linac_source(W_Gy_wk, "Co-60", d_primary_m=3.0+0.8, d_secondary_m=3.0+0.8,
                      U_primary=0.25)
# keep only the primary component for this primary-barrier check
st.components = [c for c in st.components if c.name == "primary"]
req = solver.required_thickness(st, "concrete", goal)
print(f"unshielded primary = {st.total_unshielded():.4g} mSv/wk")
print(f"required concrete = {req:.0f} mm   (SRS 47 expected ~1033 mm)")

print("\n=== I-131 released patient (RG 8.39 Example 2) ===")
res = src.i131_released_patient_dose(200, "thyroid_cancer_postthyroidectomy", 1.0)
print(f"200 mCi thyroid cancer -> {res['dose_mSv']:.2f} mSv  (RG 8.39 expected 4.53)")
print(f"may release: {res['may_release']}")

print("\n=== Diagnostic chest room example ===")
st2 = src.diagnostic_source("chest_room", patients_per_week=200,
                            d_primary_m=2.0, d_secondary_m=1.5, kvp=125)
goal2 = reg.design_goal("NCRP", "uncontrolled", occupancy_T=1.0)
barrier = ba.Barrier().add("lead", 1.0).add("gypsum", 15.0)
ev = solver.evaluate(st2, barrier, goal2)
print("barrier:", ev.barrier_description)
for cr in ev.components:
    print(f"  {cr.name}: unshielded={cr.unshielded:.3g}, B={cr.transmission:.3g}, transmitted={cr.transmitted:.3g}")
print("verdict:", ev.verdict.message)
print("scattered (secondary) transmitted:", f"{ev.transmitted_secondary:.3g} {ev.unit}")
print("equivalents:", {k: round(v,3) for k,v in ev.equivalents.items()})
req_pb = solver.required_thickness(st2, "lead", goal2)
print(f"required lead alone: {req_pb:.3f} mm -> preferred {solver.preferred_thickness(req_pb,'lead')} mm")

print("\nSMOKE TEST DONE")
