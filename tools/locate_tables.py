# locate_tables.py
# Finds the PDF page numbers of every data table the model needs, across all
# reference PDFs, so extraction scripts can target exact pages.
import os
import re
from pypdf import PdfReader

REF = r"D:\Projects\Master\Master-26\Control Claude Program\References"

# file -> list of regex patterns to locate (table captions / key phrases)
targets = {
    "NCRP Report No. 147.pdf": [
        r"TABLE 4\.1",   # occupancy factors
        r"TABLE 4\.2",   # workload survey summary
        r"TABLE 4\.3",   # workload distributions per room type
        r"TABLE 4\.4",   # use factors
        r"TABLE 4\.5",   # unshielded primary air kerma per patient
        r"TABLE 4\.6",   # scatter fractions
        r"TABLE 4\.7",   # unshielded secondary air kerma per patient
        r"TABLE 5\.1",   # CT (?)
        r"TABLE 5\.2",
        r"TABLE B\.1",   # workload distribution appendix
        r"TABLE B\.2",
        r"TABLE C\.1",   # Archer parameters (broad beams)
        r"TABLE C\.2",   # Archer parameters per workload distribution
        r"dose.length product|DLP",
    ],
    "IAEA_SRS_47_Radiotherapy_Facilities.pdf": [
        r"TVL",                      # all TVL mentions
        r"TABLE 1[0-9]",             # numbered tables 10-19
        r"TABLE [1-9][^0-9]",        # tables 1-9
        r"scatter fraction",
        r"leakage",
        r"CONTENTS",
    ],
    "RG 8.39.pdf": [
        r"TABLE 1",
        r"TABLE 2",
        r"TABLE 3",
        r"TABLE B-1|Table B-1",
        r"occupancy factor",
        r"effective half-li",
        r"uptake fraction",
    ],
    "NRRC-R-01.pdf": [  # name guess; will resolve actual filename below
        r"dose limit",
        r"20 mSv",
        r"1 mSv",
        r"shielding",
        r"design",
        r"constraint",
    ],
    "shielding height shb.pdf": [
        r"Table 2\.5",
        r"tertiary",
    ],
}

# resolve actual NRRC filename (user added it manually, name unknown)
actual_files = os.listdir(REF)
print("FILES IN References/:")
for f in actual_files:
    print("  ", f)
print()

nrrc_name = None
for f in actual_files:
    if "nrrc" in f.lower() or "r-01" in f.lower() or "r01" in f.lower():
        nrrc_name = f
if nrrc_name:
    targets[nrrc_name] = targets.pop("NRRC-R-01.pdf")
else:
    targets.pop("NRRC-R-01.pdf")
    print("!! NRRC file not found by name pattern - check listing above")

for fname, pats in targets.items():
    path = os.path.join(REF, fname)
    if not os.path.exists(path):
        print(f"MISSING: {fname}")
        continue
    print("=" * 80)
    print("FILE:", fname)
    reader = PdfReader(path)
    compiled = [(p, re.compile(p, re.I)) for p in pats]
    found = {p: [] for p, _ in compiled}
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            continue
        for p, rx in compiled:
            if rx.search(txt):
                found[p].append(i + 1)
    for p, pages in found.items():
        print(f"  {p}: {pages[:25]}")
