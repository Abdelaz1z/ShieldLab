# dump_ndrl.py - extract the Saudi SFDA NDRL tables (Annex 2) text.
import pdfplumber
PATH = r"D:\Projects\Master\Master-26\Control Claude Program\References\NDRL-En.pdf"
with pdfplumber.open(PATH) as pdf:
    for i in (6, 7):
        if i < len(pdf.pages):
            print(f"===== PAGE {i+1} =====")
            print(pdf.pages[i].extract_text() or "(none)")
