# 🛡️ ShieldLab

**Photon shielding design & verification for medical radiation facilities**
X-ray · CT · dental panoramic · fluoroscopy · mammography · angiography · LINAC (Co-60 / 4–24 MV) · I-131 therapy · Tc-99m & F-18 nuclear medicine

Built for **Abdelaziz Habib** — Radiation Safety Officer (KSA), M.Sc. Radiation Protection, Cairo University.

> Given a **modality** and its **maximum energy**, a **distance** to the wall, an **occupancy**, and a **barrier built from one or more material layers** (mix lead, concrete, gypsum, steel, glass, wood, brick…), ShieldLab computes the **transmitted primary and scattered (secondary) radiation**, tells you whether it is **acceptable** against the chosen regulatory goal, and recommends the **required and preferred thicknesses** — with a **reference for every number**.

---

## 1. Install (Windows, Python 3.11 already present)

```powershell
cd "D:\Projects\Master\Master-26\Control Claude Program"
py -3.11 -m pip install -r requirements.txt
```

## 2. Run the app

```powershell
py -3.11 -m streamlit run app.py
```

Your browser opens at `http://localhost:8501`. (The physics engine itself uses only the Python standard library; Streamlit/pandas/matplotlib are only for the interface and plots.)

## 3. Use it (the wizard)

1. **Sidebar → Modality & Energy** — pick the facility/modality and its maximum energy (kVp / MV / radionuclide).
2. **Sidebar → Regulatory basis** — choose **NCRP** (weekly air-kerma goals) or **IAEA/Saudi NRRC** (annual constraints), the **area type** (controlled/uncontrolled) and the **occupancy factor T** (NCRP Table 4.1 guide). The design goal `P` is shown and **editable**.
3. **Inputs** — enter workload (patients/week, DLP, Gy/week, or mCi — editable defaults from NCRP 147 / Saudi SFDA NDRLs) and the **distances** (source→barrier).
4. **Barrier (mix materials)** — add/remove layers, each a material + thickness in mm.
5. **Results** — verdict (✅/❌), transmitted **total** and **scattered+leakage** dose, per-component breakdown, **required & preferred thickness** for each single material, lead/concrete **equivalents**, and a **transmission-vs-thickness plot**. Download an **HTML report** (print to PDF) for your design file.

---

## 4. How it works (method & references)

ShieldLab uses the **standard analytical formalism** prescribed by the references — the same method real shielding reports use and regulators accept (no Monte Carlo):

| Modality | Transmission model | Source data |
|----------|--------------------|-------------|
| Diagnostic X-ray, fluoro, mammo, dental, angio | **Archer** broad-beam `B(x)=[(1+β/α)e^{αγx}−β/α]^{−1/γ}` | NCRP 147 Tables B.1 (primary) & C.1 (secondary) |
| CT | scatter ∝ DLP | NCRP 147 §5.5 / Table 5.2; Saudi SFDA NDRLs |
| LINAC / Co-60 | **TVL** `n=x₁/TVL₁+(x−x₁)/TVLₑ, B=10⁻ⁿ` | IAEA SRS 47 Tables 4, 5, 8, 11 |
| I-131, Tc-99m, F-18, Lu-177 | broad-beam **TVL/HVL** | Oumano et al. 2025; AAPM TG-108 (PET) |
| I-131 released-patient dose | RG 8.39 biokinetic integral (Eq. B-5) | NRC RG 8.39 |
| any other material | **μ/ρ + buildup** `T=B·e^{−(μ/ρ)ρx}` | NIST XCOM / Hubbell-Seltzer |

Dose limits: **Saudi NRRC-R-01** (occupational 20 mSv/y, public 1 mSv/y) and **IAEA GSR Part 3**. Full bibliography is in the app's **References** tab and in [`radshield/data/references.json`](radshield/data/references.json).

**Validation** — the engine reproduces published worked examples (see `tests/`):
- IAEA SRS 47 Co-60 primary barrier → **1034 mm concrete** (report: 1033 mm)
- NRC RG 8.39 I-131 Example 2 → **4.53 mSv** (report: 4.53 mSv)

Run the tests:
```powershell
py -3.11 tests\test_validation.py
```

---

## 5. Editing the model (everything is editable)

The whole model is data-driven. To change a number, edit the JSON in [`radshield/data/`](radshield/data/) — no code changes needed:

| File | Holds |
|------|-------|
| `references.json` | every citation (referenced by key from all other files) |
| `limits.json` | frameworks, design goals, occupancy factors |
| `archer_diagnostic.json` | NCRP 147 α/β/γ transmission parameters |
| `tvl_megavoltage.json` | SRS 47 TVLs, scatter fractions, patient transmission |
| `radionuclides.json` | nuclide TVL/HVL, Γ, I-131 biokinetics, PET method |
| `materials.json` | densities + NIST μ/ρ grids (add your own materials here) |
| `scatter.json` | secondary kerma, CT DLP defaults, ceiling scatter |
| `workloads.json` | patient numbers, primary kerma, Saudi NDRLs, LINAC defaults |

To add a **new material**: add an entry to `materials.json` with its `density_kg_m3` and (optionally) a `mu_rho` grid on the shared `energy_grid_MeV`. To add a **modality**: add an entry to `ui/modality_config.py`.

Project structure:
```
app.py                  Streamlit entry point
radshield/
  data_loader.py        cached JSON access + citation resolver
  data/*.json           PART 1 — all physics & regulatory data
  physics/              PART 2 — engine (transmission, beams, barriers, sources, solver)
  regulatory/limits.py  frameworks + pass/fail verdict
  report/report.py      PART 4 — HTML report export
ui/                     PART 3 — Streamlit screens
tests/                  PART 4 — validation tests
tools/                  data-extraction & check scripts (not needed at runtime)
PROGRESS.md             development log
```

---

## 6. Limitations (read the app's **Limitations** tab)

Photons only — **LINAC > 10 MV photoneutrons are not modelled** (warned, with guidance). Multi-layer transmission is the product of per-layer broad-beam factors (slightly conservative). CT κ and some workloads are editable representative defaults. Skyshine/ducts/maze are qualitative in v1.0. **A qualified expert must review any design used for construction.**
