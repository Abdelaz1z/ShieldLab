# apptest.py
# Uses Streamlit's official headless test harness to run app.py and report any
# exception raised while rendering (catches UI runtime errors without a browser).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")

at = AppTest.from_file(APP, default_timeout=60)
at.run()

print("Render exceptions:", len(at.exception))
for e in at.exception:
    print("  EXC:", e.value)

# the default modality is the first diagnostic one; check a verdict rendered
print("success boxes:", len(at.success))
print("error boxes:", len(at.error))
print("APPTEST OK" if not at.exception else "APPTEST FOUND EXCEPTIONS")
