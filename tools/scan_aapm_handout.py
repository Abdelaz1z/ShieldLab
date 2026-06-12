# scan_aapm_handout.py
# Extracts text from the downloaded AAPM 2025 DX-NM shielding review handout to
# find clean Archer transmission parameter tables for cross-referencing.
import pdfplumber

PATH = r"C:\Users\NOTEBOOK\.claude\projects\D--Projects-Master-Master-26-Control-Claude-Program\c54e2a20-9734-4d41-a293-a96f010b2c40\tool-results\webfetch-1781116910770-8qzmkr.pdf"

with pdfplumber.open(PATH) as pdf:
    print("PAGES:", len(pdf.pages))
    for i, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        low = txt.lower()
        # flag pages mentioning archer parameters / transmission tables
        if any(k in low for k in ["alpha", "α", "archer", "transmission", "tvl", "kerma", "scatter fraction"]):
            print("=" * 80)
            print(f"PAGE {i+1}")
            print(" ".join(txt.split())[:1800])
