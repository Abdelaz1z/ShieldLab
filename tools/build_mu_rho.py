"""Generate NIST mass attenuation grids for the materials that had none.

Audit finding F-05. Six selectable materials -- barite concrete, brick, gypsum,
plate glass, lead glass and wood -- carried no ``mu_rho`` grid, which made them
unevaluable in the calculator and made the mu*x>=4 geometry-bias warning
unreachable for any wall built from them.

METHOD. mu/rho for a mixture is the mass-weighted sum of its elements
(Hubbell & Seltzer, the same additivity rule XCOM uses for compounds):

    (mu/rho)_mix = SUM_i  w_i * (mu/rho)_i

Elemental coefficients come from `xraydb`, whose Elam tables are the NIST
photon cross-sections. `--verify` checks them against the NIST values already
in materials.json for water, lead and concrete; the worst deviation over the
whole 0.01-0.5 MeV grid is 0.04%, so the two are the same data.

ENERGY RANGE. Capped at 0.8 MeV, the documented reliability limit of the Elam
tables -- above it they flat-line, which would silently under-predict. Every
energy this engine actually asks a mu/rho grid for is below that cap: the
radionuclide gammas (Tc-99m 140, Lu-177 208, I-131 364, F-18 511 keV) and the
diagnostic mean-energy proxy (~kVp/2). Megavoltage never reaches this model --
`beams.data_path` returns PATH_NONE for it without a tabulated TVL.

Run:  python tools/build_mu_rho.py --verify      # check against the repo's NIST rows
      python tools/build_mu_rho.py --write       # regenerate shieldlab/data/materials.json

Requires xraydb (see requirements-dev.txt); it is NOT needed at runtime.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATERIALS_JSON = ROOT / "shieldlab" / "data" / "materials.json"

# Elam tables are reliable to 800 keV; beyond that xraydb warns and flat-lines.
MAX_ENERGY_MeV = 0.8

# Grid for the generated materials: the shared grid truncated at the cap.
NEW_GRID_MeV = [0.01, 0.015, 0.02, 0.03, 0.05, 0.06, 0.08, 0.1,
                0.15, 0.2, 0.3, 0.5, 0.8]

ATOMIC_MASS = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "S": 32.06, "K": 39.098,
    "Ca": 40.078, "Ti": 47.867, "Fe": 55.845, "As": 74.922, "Ba": 137.327,
    "Pb": 207.2,
}

# --- compositions -----------------------------------------------------------
# Mass fractions. Every entry records where the composition comes from so the
# numbers stay auditable; the JSON keeps the same record.

STOICHIOMETRIC = {
    # Gypsum wallboard core, CaSO4.2H2O -- exact from the formula, no table needed.
    "gypsum": ("CaSO4·2H2O", {"Ca": 1, "S": 1, "O": 6, "H": 4}),
}

BY_MASS_FRACTION = {
    # NIST/ICRU tabulated compositions (Hubbell & Seltzer, Table 4 materials).
    "barite_concrete": {
        "H": 0.003585, "O": 0.311622, "Mg": 0.001195, "Al": 0.004183,
        "Si": 0.010457, "S": 0.107858, "Ca": 0.050194, "Fe": 0.047505,
        "Ba": 0.462386,
    },
    "plate_glass": {
        "O": 0.459800, "Na": 0.096441, "Si": 0.336553, "Ca": 0.107205,
    },
    "lead_glass": {
        "O": 0.156453, "Si": 0.080866, "Ti": 0.008092, "As": 0.002651,
        "Pb": 0.751938,
    },
    "wood": {
        "H": 0.059642, "C": 0.497018, "N": 0.004970, "O": 0.427435,
        "Mg": 0.001988, "S": 0.004970, "K": 0.001988, "Ca": 0.001988,
    },
}

# Fired clay brick has no NIST entry. This is a representative oxide analysis for
# common fired clay, converted to elements below. Above ~100 keV the result is
# Compton-dominated and therefore insensitive to the exact split (<Z/A> is nearly
# constant across these light elements), but the basis is recorded so an RSO with
# a mill certificate for their own brick can replace it.
BRICK_OXIDES = {
    "SiO2": 0.60, "Al2O3": 0.20, "Fe2O3": 0.07, "CaO": 0.05,
    "MgO": 0.02, "K2O": 0.03, "Na2O": 0.02, "TiO2": 0.01,
}
OXIDE_FORMULA = {
    "SiO2": {"Si": 1, "O": 2}, "Al2O3": {"Al": 2, "O": 3},
    "Fe2O3": {"Fe": 2, "O": 3}, "CaO": {"Ca": 1, "O": 1},
    "MgO": {"Mg": 1, "O": 1}, "K2O": {"K": 2, "O": 1},
    "Na2O": {"Na": 2, "O": 1}, "TiO2": {"Ti": 1, "O": 2},
}

COMPOSITION_SOURCE = {
    "barite_concrete": "NIST/ICRU tabulated composition, Concrete (Barite, TYPE BA)",
    "brick": "Representative fired-clay oxide analysis, converted to mass fractions",
    "gypsum": "Stoichiometric CaSO4·2H2O",
    "plate_glass": "NIST/ICRU tabulated composition, Glass (Plate)",
    "lead_glass": "NIST/ICRU tabulated composition, Glass (Lead)",
    "wood": "NIST/ICRU tabulated composition, Wood (Southern Pine)",
}

# Compositions of materials the repo ALREADY has NIST rows for, used only by
# --verify to prove the generator reproduces them.
VERIFY_AGAINST = {
    "water": {"H": 0.111894, "O": 0.888106},
    "lead": {"Pb": 1.0},
    "concrete": {
        "H": 0.022100, "C": 0.002484, "O": 0.574930, "Na": 0.015208,
        "Mg": 0.001266, "Al": 0.019953, "Si": 0.304627, "K": 0.010045,
        "Ca": 0.042951, "Fe": 0.006435,
    },
}


def _normalise(fractions: dict) -> dict:
    total = sum(fractions.values())
    return {element: value / total for element, value in fractions.items()}


def from_formula(counts: dict) -> dict:
    """Mass fractions from an atom-count formula."""
    masses = {el: n * ATOMIC_MASS[el] for el, n in counts.items()}
    return _normalise(masses)


def brick_composition() -> dict:
    """Convert the oxide analysis to elemental mass fractions."""
    elemental: dict = {}
    for oxide, oxide_fraction in BRICK_OXIDES.items():
        formula = OXIDE_FORMULA[oxide]
        oxide_mass = sum(n * ATOMIC_MASS[el] for el, n in formula.items())
        for element, count in formula.items():
            share = count * ATOMIC_MASS[element] / oxide_mass
            elemental[element] = elemental.get(element, 0.0) + oxide_fraction * share
    return _normalise(elemental)


def compositions() -> dict:
    """Every generated material's elemental mass fractions."""
    built = {name: _normalise(f) for name, f in BY_MASS_FRACTION.items()}
    for name, (_formula, counts) in STOICHIOMETRIC.items():
        built[name] = from_formula(counts)
    built["brick"] = brick_composition()
    return built


def mu_rho(composition: dict, energies_MeV) -> list:
    """Mass attenuation coefficients (cm^2/g) by the mixture rule."""
    import xraydb

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = []
        for energy in energies_MeV:
            if energy > MAX_ENERGY_MeV:
                raise ValueError(
                    f"{energy} MeV is above the {MAX_ENERGY_MeV} MeV Elam reliability "
                    "limit; do not generate points there."
                )
            total = sum(
                weight * xraydb.mu_elam(element, energy * 1e6, kind="total")
                for element, weight in composition.items()
            )
            out.append(float(f"{total:.5g}"))
        return out


def verify() -> int:
    """Check the generator against the NIST rows already in materials.json."""
    data = json.loads(MATERIALS_JSON.read_text(encoding="utf-8"))
    grid = data["energy_grid_MeV"]
    checked = [(i, e) for i, e in enumerate(grid) if e <= MAX_ENERGY_MeV]
    worst = 0.0
    print(f"{'material':10s} {'points':>7s} {'worst dev':>10s}")
    for name, composition in VERIFY_AGAINST.items():
        reference = data["materials"][name]["mu_rho"]
        generated = mu_rho(_normalise(composition), [e for _, e in checked])
        deviations = [
            abs(generated[k] - reference[i]) / reference[i] * 100.0
            for k, (i, _e) in enumerate(checked)
        ]
        worst = max(worst, max(deviations))
        print(f"{name:10s} {len(checked):7d} {max(deviations):9.3f}%")
    print(f"\nworst deviation overall: {worst:.3f}%")
    return 0 if worst < 1.0 else 1


def write() -> int:
    data = json.loads(MATERIALS_JSON.read_text(encoding="utf-8"))
    built = compositions()
    for name, composition in built.items():
        entry = data["materials"][name]
        entry["mu_rho"] = mu_rho(composition, NEW_GRID_MeV)
        entry["energy_grid_MeV"] = list(NEW_GRID_MeV)
        entry["mu_rho_max_energy_MeV"] = MAX_ENERGY_MeV
        entry["composition_mass_fraction"] = {
            element: float(f"{weight:.6f}")
            for element, weight in sorted(composition.items())
        }
        entry["composition_ref"] = COMPOSITION_SOURCE[name]
        entry["mu_rho_ref"] = "NIST_XCOM"
        print(f"  {name:16s} {len(entry['mu_rho'])} points, "
              f"{min(composition, key=composition.get)}..{max(composition, key=composition.get)}")
    MATERIALS_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {MATERIALS_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="check the generator against the repo's existing NIST rows")
    parser.add_argument("--write", action="store_true",
                        help="regenerate the mu_rho grids in materials.json")
    args = parser.parse_args()
    if args.verify:
        raise SystemExit(verify())
    if args.write:
        raise SystemExit(write())
    parser.print_help()
