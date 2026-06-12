# apptest_modalities.py
# Drives the app through several modality groups via Streamlit AppTest to confirm
# each render path (diagnostic, CT, LINAC>10MV neutron warning, I-131 release).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def run_group(group_label):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    # sidebar selectbox[0] is the modality group
    at.sidebar.selectbox[0].select(group_label).run()
    n_exc = len(at.exception)
    ok = n_exc == 0
    msg = "" if ok else str(at.exception[0].value)
    print(f"{'OK ' if ok else 'EXC'}  group='{group_label}'  exceptions={n_exc}  {msg}")
    return ok


groups = ["Diagnostic X-ray", "Computed Tomography",
          "Radiotherapy (LINAC / Co-60)", "Nuclear Medicine", "Iodine-131 Therapy"]
results = [run_group(g) for g in groups]
print("ALL GROUPS OK" if all(results) else "SOME GROUPS FAILED")
sys.exit(0 if all(results) else 1)
