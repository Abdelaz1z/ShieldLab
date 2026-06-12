"""
ShieldLab - Streamlit application (Part 3: User Interface)
==================================================================
Run from this folder with:

    py -3.11 -m streamlit run app.py

The UI is a wizard:
    1. choose a MODALITY and its MAXIMUM ENERGY
    2. enter WORKLOAD (editable defaults from NCRP 147 / Saudi SFDA)
    3. enter GEOMETRY (distance device->barrier, occupancy of the area)
    4. choose the REGULATORY FRAMEWORK and design goal
    5. build the BARRIER from one or more material layers (mix any materials)
    6. read RESULTS: transmitted primary & scattered (secondary) dose, the
       pass/fail verdict and margin, the required & preferred thicknesses,
       lead/concrete equivalents, and a transmission plot.

All physics lives in the radshield package; this file only collects inputs and
shows results, so it is easy to read and edit.
"""

import os
import sys

# make the radshield package importable when Streamlit runs this file directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from radshield import data_loader as dl
from radshield.physics import beams as bm, barriers as ba, sources as src, solver
from radshield.regulatory import limits as reg
from ui import modality_config as mc
from ui import views


st.set_page_config(page_title="ShieldLab", page_icon="🛡️", layout="wide")


def main():
    st.title("🛡️ ShieldLab")
    st.caption(
        "Photon shielding design & verification for medical radiation facilities — "
        "X-ray, CT, dental panoramic, LINAC, I-131 therapy and nuclear medicine. "
        "Prepared for Abdelaziz Habib (RSO, KSA)."
    )

    tabs = st.tabs(["🧮 Shielding Calculator", "📚 References & Method", "⚠️ Limitations"])

    with tabs[0]:
        views.calculator_tab()
    with tabs[1]:
        views.references_tab()
    with tabs[2]:
        views.limitations_tab()


if __name__ == "__main__":
    main()
