"""
Oblique-incidence correction (shieldlab.room.oblique_correction) and its use in the field tier's
wall equivalence. The constant K is checked against its fit by the research repository's
`src/fit_oblique_correction.py`, which refuses to pass if the two differ.

    py -3 tests\\test_oblique_correction.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shieldlab.room import field_surrogate as fs
from shieldlab.room import oblique_correction as obc

CONCRETE = (13.0, 2.30)


def _equivalents(isotope, layers, k):
    """The wall's R-equivalents with the correction's constant set to `k`."""
    saved = obc.K
    obc.K = k
    fs._equivalent.cache_clear()
    fs._oblique_reference_curve.cache_clear()
    try:
        return fs._equivalent(isotope, "concrete", layers)[0]
    finally:
        obc.K = saved
        fs._equivalent.cache_clear()
        fs._oblique_reference_curve.cache_clear()


def test_klein_nishina_at_511_keV():
    # 0.2866 barn per electron at k = 1 (Evans, The Atomic Nucleus, table of sigma_KN).
    assert abs(obc.klein_nishina_cm2(511.0) / 2.866e-25 - 1.0) < 0.003


def test_compton_share_follows_z_and_energy():
    assert obc.compton_fraction(7.4, 511.0) > 0.98
    assert obc.compton_fraction(82.0, 140.5) < 0.1
    assert obc.compton_fraction(82.0, 140.5) < obc.compton_fraction(82.0, 364.0) \
        < obc.compton_fraction(82.0, 511.0)
    assert obc.compton_fraction(26.0, 364.0) < obc.compton_fraction(13.0, 364.0)


def test_zero_at_normal_incidence_and_held_beyond_the_fit():
    wall = ((*CONCRETE, 300.0),)                       # ~7 mfp at 364 keV already at s = 1
    assert obc.shape(wall, 364.0, 1.0) == 0.0
    assert obc.shape(wall, 364.0, 3.0) == obc.shape(wall, 364.0, obc.MAX_SLANT)
    assert obc.log10_factor(wall, 364.0, 3.0) < 0.5


def test_concrete_wall_in_a_concrete_room_is_unchanged():
    layers = fs._app_layers("concrete", 200.0)
    with_k = _equivalents("I-131", layers, obc.K)
    without = _equivalents("I-131", layers, 0.0)
    assert all(abs(a / b - 1.0) < 0.02 for a, b in zip(with_k, without)), (with_k, without)


def test_lead_wall_in_a_concrete_room_matches_more_concrete_at_a_slant():
    """Concrete transmits more at an angle than at its slant thickness; lead at 364 keV barely
    does. Matched at their transmission at the angle, the lead wall is worth more concrete."""
    layers = (("lead", 14.0),)
    with_k = _equivalents("I-131", layers, obc.K)
    without = _equivalents("I-131", layers, 0.0)
    assert abs(with_k[0] - without[0]) < 1e-9
    at_60_degrees = list(fs.SLANTS).index(2.0)
    assert with_k[at_60_degrees] > 1.05 * without[at_60_degrees], (with_k, without)


if __name__ == "__main__":
    test_klein_nishina_at_511_keV()
    test_compton_share_follows_z_and_energy()
    test_zero_at_normal_incidence_and_held_beyond_the_fit()
    test_concrete_wall_in_a_concrete_room_is_unchanged()
    test_lead_wall_in_a_concrete_room_matches_more_concrete_at_a_slant()
    print("OK")
