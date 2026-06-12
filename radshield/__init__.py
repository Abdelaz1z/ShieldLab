"""
ShieldLab
=================
Photon shielding design & verification for medical radiation facilities.

A teaching/planning tool that, given a modality, a maximum energy and a barrier
made of one or more material layers, computes the transmitted primary and
secondary (scatter + leakage) radiation behind the barrier, compares it with the
selected regulatory design goal, and recommends the required/preferred
thicknesses.

Author : built for Abdelaziz Habib (RSO, KSA; M.Sc. Radiation Protection, Cairo University)
Method : standard analytical formalism (Archer broad-beam transmission, TVL,
         inverse-square, scatter fractions, buildup) per NCRP 147 / NCRP 151 /
         IAEA SRS 47 / AAPM TG-108. See radshield/data/references.json.

Package layout
--------------
    radshield/
        data/         <- Part 1: all physics & regulatory datasets (editable JSON)
        physics/      <- Part 2: the calculation engine (this part)
        regulatory/   <- regulatory frameworks & pass/fail verdict
        report/       <- Part 4: audit-trail report export
"""

__version__ = "1.0.0"
__author__ = "Abdelaziz Habib (with Claude)"
