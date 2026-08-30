"""Which materials each beam may be shielded with, and how well that is known.

Covers the audit findings F-03, F-04, F-05 and F-08. The rule these tests pin down
is that a material is only offered when a transmission dataset actually reaches it,
and that anything served by the generic narrow-beam model is labelled as such rather
than presented like a tabulated broad-beam value.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from shieldlab import data_loader as dl
from shieldlab.physics import beams as bm
from shieldlab.room import engines as room_engines

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"

ALL_MATERIALS = list(dl.materials()["materials"])
RADIONUCLIDES = list(dl.radionuclides()["radionuclides"])


# --- F-08: the offered order must not move between runs ---------------------

def test_available_materials_follows_materials_json_order():
    """Set operations lose order; a UI built on that would reshuffle every restart."""
    beam = bm.Beam(kind=bm.KIND_MEGAVOLTAGE, mv_energy="6 MV")
    offered = bm.available_materials(beam)
    assert offered == [m for m in ALL_MATERIALS if m in offered]


def test_available_materials_is_stable_across_interpreters():
    """String hashing is randomised per process, so this needs separate interpreters."""
    script = (
        "import sys; sys.path.insert(0, %r);"
        "from shieldlab.physics import beams as bm;"
        "print(bm.available_materials(bm.Beam(kind=bm.KIND_MEGAVOLTAGE, mv_energy='6 MV')))"
        % str(ROOT)
    )
    runs = {
        subprocess.run([sys.executable, "-c", script], capture_output=True,
                       text=True, check=True).stdout.strip()
        for _ in range(3)
    }
    assert len(runs) == 1, f"material order changed between runs: {runs}"


# --- F-04: everything offered must actually evaluate ------------------------

@pytest.mark.parametrize("kvp", [70, 100, 120, 140])
def test_every_offered_diagnostic_material_evaluates(kvp):
    beam = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=kvp)
    for material in bm.available_materials(beam):
        transmission = bm.transmission_of_layer(beam, material, 100.0)
        assert 0.0 <= transmission <= 1.0


@pytest.mark.parametrize("nuclide", RADIONUCLIDES)
def test_every_offered_radionuclide_material_evaluates(nuclide):
    beam = bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide=nuclide)
    for material in bm.available_materials(beam):
        transmission = bm.transmission_of_layer(beam, material, 100.0)
        assert 0.0 <= transmission <= 1.0


def test_materials_without_any_data_are_not_offered():
    """A material with no dataset must be withheld, not offered and then raised on."""
    beam = bm.Beam(kind=bm.KIND_MEGAVOLTAGE, mv_energy="6 MV")
    withheld = set(ALL_MATERIALS) - set(bm.available_materials(beam))
    assert withheld, "expected at least one material with no megavoltage TVL"
    for material in withheld:
        with pytest.raises(ValueError):
            bm.transmission_of_layer(beam, material, 100.0)


def test_calculator_dropdown_offers_only_evaluable_materials():
    """The regression behind F-04: three materials used to crash the page on one click.

    Every material the layer selector accepts must survive a full recalculation.
    Materials the beam has no data for are expected to be absent from the options,
    which AppTest signals by refusing the selection.
    """
    app = AppTest.from_file(str(APP_PATH), default_timeout=90).run()
    assert not app.exception
    offered_labels = next(
        element for element in app.selectbox if element.label == "Layer 1 Material"
    ).options

    # These three used to crash the page. They now carry mu/rho grids, so they are
    # offered -- but only through the generic model, which the label must declare.
    beam = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=100)
    for material in ("barite_concrete", "lead_glass", "brick"):
        assert bm.data_path(beam, material) == bm.PATH_NARROW
        label = next(l for l in offered_labels if l.startswith(material))
        assert "narrow-beam" in label, (
            f"{material} is served by the narrow-beam model and must say so"
        )

    # Every material the selector will accept must survive a full recalculation.
    # AppTest refuses a value outside the options with ValueError, which is how a
    # withheld material shows up here.
    accepted = []
    for material in ALL_MATERIALS:
        fresh = AppTest.from_file(str(APP_PATH), default_timeout=90).run()
        selector = next(
            element for element in fresh.selectbox if element.label == "Layer 1 Material"
        )
        try:
            selector.select(material)
            fresh.run()
        except ValueError:
            continue                     # withheld on purpose: no data for this beam
        assert not fresh.exception, f"selecting {material!r} broke the assessment page"
        accepted.append(material)

    # Every material in materials.json now evaluates for a diagnostic beam: the
    # tabulated ones broad-beam, the rest through the labelled generic model.
    assert set(accepted) == set(ALL_MATERIALS)


# --- F-03 / F-05: narrow-beam results must be declared ----------------------

def test_narrow_beam_materials_are_a_subset_of_available():
    beam = bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=100)
    assert set(bm.narrow_beam_materials(beam)) <= set(bm.available_materials(beam))


def test_data_path_agrees_with_transmission_of_layer():
    """data_path is the single source of truth; it must not disagree with the engine."""
    probes = [
        bm.Beam(kind=bm.KIND_DIAGNOSTIC, component="secondary", kvp=100),
        bm.Beam(kind=bm.KIND_MEGAVOLTAGE, component="primary", mv_energy="6 MV"),
        bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide="I-131"),
        bm.Beam(kind=bm.KIND_MONO, mono_energy_MeV=0.07),
    ]
    for beam in probes:
        for material in ALL_MATERIALS:
            path = bm.data_path(beam, material)
            if path is bm.PATH_NONE:
                with pytest.raises(ValueError):
                    bm.transmission_of_layer(beam, material, 50.0)
            else:
                assert 0.0 <= bm.transmission_of_layer(beam, material, 50.0) <= 1.0


@pytest.mark.parametrize("nuclide", RADIONUCLIDES)
def test_room_wall_materials_all_have_broad_beam_data(nuclide):
    """F-03: steel had no radionuclide TVL and silently took the narrow-beam path."""
    beam = bm.Beam(kind=bm.KIND_RADIONUCLIDE, nuclide=nuclide)
    for material in room_engines.usable_wall_materials(nuclide):
        assert bm.data_path(beam, material) == bm.PATH_BROAD, (
            f"{material} is offered as a {nuclide} wall material but has no "
            "broad-beam dataset; its transmission would be optimistic"
        )


# --- F-05: optical depth must reach every offered wall material -------------

@pytest.mark.parametrize("nuclide", RADIONUCLIDES)
def test_geometry_bias_warning_can_fire_for_every_wall_material(nuclide):
    """The mu*x>=4 warning is silently unreachable if optical_depth returns None."""
    energy_keV = dl.radionuclides()["radionuclides"][nuclide]["main_gamma_keV"]
    for material in room_engines.usable_wall_materials(nuclide):
        depth = room_engines.optical_depth(energy_keV, [(material, 300.0)])
        assert depth is not None, (
            f"optical_depth is unknown for {material}: the finite-field geometry-bias "
            "warning could never reach a wall built from it"
        )
        assert depth > 0.0
