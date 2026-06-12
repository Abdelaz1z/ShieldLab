# identify_pdfs.py
# Helper script: extracts the first pages of each reference PDF so we can
# identify the documents and see their tables of contents.
import os
from pypdf import PdfReader

REF_DIR = r"D:\Projects\Master\Master-26\Control Claude Program\References"

for fname in sorted(os.listdir(REF_DIR)):
    if not fname.lower().endswith(".pdf"):
        continue
    path = os.path.join(REF_DIR, fname)
    print("=" * 100)
    print("FILE:", fname)
    try:
        reader = PdfReader(path)
        print("PAGES:", len(reader.pages))
        # extract first 3 pages of text, truncated per page
        for i in range(min(3, len(reader.pages))):
            txt = reader.pages[i].extract_text() or "(no extractable text - probably scanned image)"
            txt = " ".join(txt.split())  # collapse whitespace
            print(f"--- page {i+1} ---")
            print(txt[:1200])
    except Exception as e:
        print("ERROR:", e)
    print()
