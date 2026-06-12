# check_app_imports.py
# Imports the UI modules and exercises the non-Streamlit logic paths to catch
# syntax/import errors before launching the server.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui.modality_config as mc
from radshield.physics import sources as src, barriers as ba, solver
from radshield.regulatory import limits as reg

# exercise one modality of each builder type through the engine
goal = reg.design_goal("NCRP", "uncontrolled", 1.0)

s1 = src.diagnostic_source("chest_room", 200, 2.0, 1.5, kvp=125)
s2 = src.ct_source(550, 100, 3.0)
s3 = src.linac_source(450, "6 MV", 4.0, 4.0)
s4 = src.radionuclide_point_source("F-18", 15, 3.0)
for s in (s1, s2, s3, s4):
    b = ba.Barrier().add("concrete", 100).add("lead", 2)
    ev = solver.evaluate(s, b, goal)
    print(f"{s.modality:24s} total={ev.transmitted_total:.3g} {s.unit}  "
          f"acceptable={ev.verdict.acceptable}")

print("groups:", mc.groups())
print("IMPORTS + ENGINE PATHS OK")
