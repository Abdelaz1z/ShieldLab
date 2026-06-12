# extract_param_tables.py
# The Archer transmission-parameter tables and kerma tables have ruled-grid
# layouts that pdfplumber can parse as real tables. This dumps them as CSV-like
# rows for accurate transcription. Targets NCRP 147 appendix + body tables.
import os
import pdfplumber

REF = r"D:\Projects\Master\Master-26\Control Claude Program\References"
OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\extracted"

PATH = os.path.join(REF, "NCRP Report No. 147.pdf")

# pages believed to hold the Archer alpha/beta/gamma tables (Table C.1) and the
# primary/secondary unshielded kerma tables (4.5, 4.7) and scatter (4.6)
pages = [54, 55, 56, 57, 151, 152, 153, 154, 155, 156, 157, 158]

with pdfplumber.open(PATH) as pdf:
    for p in pages:
        if p > len(pdf.pages):
            continue
        page = pdf.pages[p - 1]
        tables = page.extract_tables()
        out_path = os.path.join(OUT, f"NCRP147_TABLES_p{p:03d}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"=== PAGE {p}: {len(tables)} table(s) found ===\n")
            for ti, table in enumerate(tables):
                f.write(f"\n--- table {ti} ---\n")
                for row in table:
                    cells = ["" if c is None else " ".join(str(c).split()) for c in row]
                    f.write(" | ".join(cells) + "\n")
        print(f"page {p}: {len(tables)} tables -> {out_path}")
print("DONE")
