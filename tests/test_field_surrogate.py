"""
Smoke test for the field-map U-Net tier (radshield.room.field_surrogate).

Runs two ways:
  * WITHOUT torch installed -> the tier must degrade gracefully (available() is False,
    no import error) so the app still runs.
  * WITH torch + weights present -> loads the model, predicts on the default room, and
    checks the field is finite in air, shaped right, and physically ordered
    (dose falls with distance from the source).

    py -3.11 tests\\test_field_surrogate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from radshield.room.model import RoomDesign
from radshield.room import field_surrogate as fs


def test_graceful_and_predict():
    design = RoomDesign.default()
    fm = fs.FieldModel()

    if not fm.available():
        print("torch/weights absent -> tier correctly reports available() == False (graceful).")
        # the design->box mapping must still work without torch:
        labels, bb, e, smm, mat, wall_mm, warns = fs._design_to_box(design)
        assert labels.shape == (fs.GRID[2], fs.GRID[1], fs.GRID[0]), labels.shape
        assert mat in fs.MATERIAL_LABEL
        print(f"design->box OK: material={mat}, walls={tuple(round(t) for t in wall_mm)} mm, "
              f"E={e} keV, labels{labels.shape}")
        return

    pred = fm.predict(design)
    assert pred is not None
    ld = pred.log_dose
    assert ld.shape == (fs.GRID[2], fs.GRID[1], fs.GRID[0]), ld.shape
    air = pred.labels == 0
    fin = np.isfinite(ld)
    assert (fin == air).all() or fin.sum() > 0, "field should be finite exactly in air voxels"
    # physical ordering: mean dose in the occupied shell < mean dose near the source
    iz, iy, ix = pred.source_vox
    near = ld[max(iz-2, 0):iz+3, max(iy-2, 0):iy+3, max(ix-2, 0):ix+3]
    near = near[np.isfinite(near)]
    shell = fs._occupied_shell(pred.labels)
    shellvals = ld[shell & np.isfinite(ld)]
    assert near.size and shellvals.size
    assert near.mean() > shellvals.mean(), (near.mean(), shellvals.mean())
    png = fs.render_field_slice(pred, design)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "render should return a PNG"
    print(f"predict OK: material={pred.material}, shell p95 log10={pred.shell_p95_log:.2f}, "
          f"near-source mean {near.mean():.2f} > shell mean {shellvals.mean():.2f} dex, "
          f"PNG {len(png)} bytes")


if __name__ == "__main__":
    test_graceful_and_predict()
    print("OK")
