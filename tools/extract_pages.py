# extract_pages.py
# Dumps the located table pages from each reference PDF into plain-text files
# (tools/extracted/) so the data-encoding step can read exact values.
# Uses pdfplumber 'layout' mode to preserve column structure where possible.
import os
import pdfplumber

REF = r"D:\Projects\Master\Master-26\Control Claude Program\References"
OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\extracted"
os.makedirs(OUT, exist_ok=True)

# file -> list of 1-based page numbers to dump
jobs = {
    "NRRC-R-01.PDF": [4, 18, 44, 45, 46, 47, 48, 58, 61, 65, 76, 91, 96, 98, 122],
    "NCRP Report No. 147.pdf": (
        [40, 41]            # Table 4.1 occupancy factors
        + [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]  # workload discussion, T4.2, T4.3, T4.4
        + [52, 53, 54, 55, 56, 57, 58]              # T4.5 primary kerma, T4.6 scatter, T4.7 secondary kerma
        + [79, 80, 81]                              # Table 5.1 area
        + [104, 105, 106, 107, 108, 109, 110, 111]  # CT section + Table 5.2
        + list(range(136, 160))                     # Appendices B (workload distributions) & C (Archer params)
    ),
    "IAEA_SRS_47_Radiotherapy_Facilities.pdf": list(range(60, 92)) + [9, 38, 47, 48, 49, 50],
    "RG 8.39.pdf": [4, 5, 6, 7, 8, 9, 17, 18, 19, 20, 21, 22, 23],
    "shielding height shb.pdf": [1, 2, 3, 4],
}

for fname, pages in jobs.items():
    path = os.path.join(REF, fname)
    base = os.path.splitext(fname)[0].replace(" ", "_").replace(".", "_")
    with pdfplumber.open(path) as pdf:
        for p in sorted(set(pages)):
            if p > len(pdf.pages):
                continue
            page = pdf.pages[p - 1]
            try:
                txt = page.extract_text(layout=True) or ""
            except Exception:
                txt = page.extract_text() or ""
            out_path = os.path.join(OUT, f"{base}_p{p:03d}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(txt)
    print(f"done: {fname} -> {len(set(pages))} pages")
print("ALL DONE ->", OUT)
