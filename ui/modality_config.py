"""
modality_config.py
===================
Maps the user's MODALITY choice (what they see in the UI) onto the engine's
source-term builders and the right energy options. Keeping this mapping in one
small module means the UI code stays about layout, and the engine stays about
physics.

Each modality entry describes:
    group        : the high-level group shown in the sidebar
    label        : UI label
    builder      : which source-term function to call ('diagnostic','ct',
                   'linac','radionuclide','i131')
    distribution : NCRP 147 workload distribution key (diagnostic)
    energies     : selectable maximum-energy options
    default_*    : sensible editable defaults
"""

# Diagnostic kVp options
KVP_OPTIONS = [50, 60, 70, 80, 90, 100, 110, 120, 125, 140, 150]
# Megavoltage options (must match keys in tvl_megavoltage.json 'energies')
MV_OPTIONS = ["Co-60", "4 MV", "6 MV", "10 MV", "15 MV", "18 MV", "20 MV", "24 MV"]

MODALITIES = {
    # ---- Diagnostic X-ray group -------------------------------------------
    "radiography": {
        "group": "Diagnostic X-ray",
        "label": "General Radiography Room (all barriers)",
        "builder": "diagnostic", "distribution": "rad_room_all",
        "default_kvp": 100, "default_patients": 112, "default_d_primary": 2.0,
        "default_d_secondary": 1.5,
    },
    "radiography_chest_bucky": {
        "group": "Diagnostic X-ray",
        "label": "Radiography - Chest Bucky (wall)",
        "builder": "diagnostic", "distribution": "rad_room_chest_bucky",
        "default_kvp": 120, "default_patients": 112, "default_d_primary": 2.0,
        "default_d_secondary": 1.5,
    },
    "radiography_floor": {
        "group": "Diagnostic X-ray",
        "label": "Radiography - Floor / Table (other barriers)",
        "builder": "diagnostic", "distribution": "rad_room_floor_other",
        "default_kvp": 80, "default_patients": 112, "default_d_primary": 1.5,
        "default_d_secondary": 1.5,
    },
    "chest": {
        "group": "Diagnostic X-ray",
        "label": "Dedicated Chest Room",
        "builder": "diagnostic", "distribution": "chest_room",
        "default_kvp": 125, "default_patients": 200, "default_d_primary": 2.5,
        "default_d_secondary": 2.0,
    },
    "fluoroscopy": {
        "group": "Diagnostic X-ray",
        "label": "Fluoroscopy / R&F (fluoro tube)",
        "builder": "diagnostic", "distribution": "fluoro_tube_rf",
        "default_kvp": 100, "default_patients": 30, "default_d_primary": 1.5,
        "default_d_secondary": 1.5,
    },
    "rf_rad_tube": {
        "group": "Diagnostic X-ray",
        "label": "R&F Room - Radiographic tube",
        "builder": "diagnostic", "distribution": "rad_tube_rf",
        "default_kvp": 100, "default_patients": 30, "default_d_primary": 2.0,
        "default_d_secondary": 1.5,
    },
    "mammography": {
        "group": "Diagnostic X-ray",
        "label": "Mammography Room",
        "builder": "diagnostic", "distribution": "mammography",
        "default_kvp": 30, "default_patients": 80, "default_d_primary": 1.5,
        "default_d_secondary": 1.0,
    },
    "cardiac_angiography": {
        "group": "Diagnostic X-ray",
        "label": "Cardiac Angiography / Cath Lab",
        "builder": "diagnostic", "distribution": "cardiac_angio",
        "default_kvp": 90, "default_patients": 20, "default_d_primary": 1.5,
        "default_d_secondary": 1.5,
    },
    "peripheral_angiography": {
        "group": "Diagnostic X-ray",
        "label": "Peripheral / Neuro Angiography",
        "builder": "diagnostic", "distribution": "peripheral_angio",
        "default_kvp": 90, "default_patients": 20, "default_d_primary": 1.5,
        "default_d_secondary": 1.5,
    },
    "dental_pan": {
        "group": "Diagnostic X-ray",
        "label": "Dental Panoramic (OPG) / Cephalometric",
        "builder": "diagnostic", "distribution": "rad_room_all",
        "default_kvp": 90, "default_patients": 40, "default_d_primary": 1.5,
        "default_d_secondary": 1.0,
        "note": "Panoramic/intraoral dental beams are low workload; modelled here "
                "with the general-radiography distribution as a conservative proxy. "
                "Intraoral dental rooms are usually self-shielding at typical workloads.",
    },

    # ---- CT group ----------------------------------------------------------
    "ct": {
        "group": "Computed Tomography",
        "label": "CT Scanner (scatter source)",
        "builder": "ct",
        "default_dlp": 550, "default_exams": 100, "default_d_secondary": 3.0,
        "ct_exam_options": ["head", "chest", "abdomen", "pelvis", "body_average"],
    },

    # ---- LINAC group -------------------------------------------------------
    "linac": {
        "group": "Radiotherapy (LINAC / Co-60)",
        "label": "Megavoltage Vault (LINAC or Co-60)",
        "builder": "linac",
        "default_mv": "6 MV", "default_W": 450, "default_d_primary": 4.0,
        "default_d_secondary": 4.0, "default_U": 0.25,
    },

    # ---- Nuclear medicine imaging -----------------------------------------
    "tc99m": {
        "group": "Nuclear Medicine",
        "label": "Tc-99m Gamma Camera / SPECT Room",
        "builder": "radionuclide", "nuclide": "Tc-99m",
        "default_activity": 30, "default_d": 3.0, "default_hours": 40,
    },
    "pet_f18": {
        "group": "Nuclear Medicine",
        "label": "F-18 PET / PET-CT Room",
        "builder": "radionuclide", "nuclide": "F-18",
        "default_activity": 15, "default_d": 3.0, "default_hours": 40,
    },
    "lu177": {
        "group": "Nuclear Medicine",
        "label": "Lu-177 Therapy Room",
        "builder": "radionuclide", "nuclide": "Lu-177",
        "default_activity": 200, "default_d": 2.0, "default_hours": 40,
    },

    # ---- Iodine therapy ----------------------------------------------------
    "i131": {
        "group": "Iodine-131 Therapy",
        "label": "I-131 Therapy Room / Isolation Ward",
        "builder": "i131", "nuclide": "I-131",
        "default_activity": 200, "default_d": 2.0, "default_hours": 40,
    },
}


def groups():
    """Ordered list of unique modality groups for the sidebar."""
    seen = []
    for m in MODALITIES.values():
        if m["group"] not in seen:
            seen.append(m["group"])
    return seen


def modalities_in_group(group):
    """(key, label) pairs for modalities in a group."""
    return [(k, v["label"]) for k, v in MODALITIES.items() if v["group"] == group]
