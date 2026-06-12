# dump_srs47.py
# Full text dump of IAEA SRS 47 to one file so we can grep for the TVL data
# tables (printed Tables 3-9) without rendering every page.
import pdfplumber

PATH = r"D:\Projects\Master\Master-26\Control Claude Program\References\IAEA_SRS_47_Radiotherapy_Facilities.pdf"
OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\extracted\SRS47_ALL.txt"

with pdfplumber.open(PATH) as pdf, open(OUT, "w", encoding="utf-8") as f:
    for i, page in enumerate(pdf.pages):
        f.write(f"\n===== PDF PAGE {i+1} =====\n")
        f.write(page.extract_text() or "")
print("DONE ->", OUT)
