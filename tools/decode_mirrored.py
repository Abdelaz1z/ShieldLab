# decode_mirrored.py
# NCRP 147 stores some table pages as mirror-reversed text (each word's
# characters are reversed and words run right-to-left). pdfplumber's
# extract_words() still gives correct word bounding boxes, so we:
#   1) reverse the characters within each word,
#   2) sort words top-to-bottom then left-to-right,
# to reconstruct the true table contents for accurate transcription.
import os
import sys
import pdfplumber

REF = r"D:\Projects\Master\Master-26\Control Claude Program\References"
OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\extracted"
PATH = os.path.join(REF, "NCRP Report No. 147.pdf")

pages = [int(a) for a in sys.argv[1:]] or [157, 158]
Y_TOL = 4.0

with pdfplumber.open(PATH) as pdf:
    for p in pages:
        page = pdf.pages[p - 1]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        # bucket words into rows by vertical position
        rows = {}
        for w in words:
            key = round(w["top"] / Y_TOL)
            rows.setdefault(key, []).append(w)
        out_path = os.path.join(OUT, f"NCRP147_DECODED_p{p:03d}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for key in sorted(rows):
                row = sorted(rows[key], key=lambda w: w["x0"])
                # reverse characters in each word to undo the mirroring
                cells = [w["text"][::-1] for w in row]
                f.write(" | ".join(cells) + "\n")
        print(f"page {p} -> {out_path}")
print("DONE")
