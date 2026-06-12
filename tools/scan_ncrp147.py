# scan_ncrp147.py
# Locates the key data tables inside NCRP 147 (transmission fitting parameters,
# workload distributions, scatter fractions, CT factors) so the build phase
# knows which pages to extract.
import re
from pypdf import PdfReader

PATH = r"D:\Projects\Master\Master-26\Control Claude Program\References\NCRP Report No. 147.pdf"
reader = PdfReader(PATH)

# patterns that mark the tables we will need
patterns = {
    "archer_fit": re.compile(r"fitting parameters|alpha.*beta.*gamma|Archer", re.I),
    "workload": re.compile(r"workload distribution|total workload per patient", re.I),
    "scatter": re.compile(r"scatter fraction|scattered.*primary", re.I),
    "ct": re.compile(r"DLP|dose.length product|CT scanner", re.I),
    "leakage": re.compile(r"leakage technique factor", re.I),
    "design_goal": re.compile(r"shielding design goal", re.I),
}

hits = {k: [] for k in patterns}
for i, page in enumerate(reader.pages):
    try:
        txt = page.extract_text() or ""
    except Exception:
        continue
    for key, pat in patterns.items():
        if pat.search(txt):
            hits[key].append(i + 1)  # 1-based PDF page

for key, pages in hits.items():
    # compress page lists into ranges for readability
    print(f"{key}: {pages[:40]}")
