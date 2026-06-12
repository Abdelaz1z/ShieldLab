# extract_chars_ordered.py
# Some NCRP 147 table pages store text right-to-left (mirror reversed), which
# breaks normal extraction. This rebuilds true reading order by sorting the raw
# characters by their (y, x) positions on the page, so values come out correctly.
import os
import sys
import pdfplumber

REF = r"D:\Projects\Master\Master-26\Control Claude Program\References"
OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\extracted"
PATH = os.path.join(REF, "NCRP Report No. 147.pdf")

# pages to rebuild (passed on command line, else default set)
pages = [int(a) for a in sys.argv[1:]] or [151, 152, 157, 158]

Y_TOL = 3.0  # chars whose 'top' differ by < this are treated as the same line

with pdfplumber.open(PATH) as pdf:
    for p in pages:
        page = pdf.pages[p - 1]
        chars = page.chars
        # group chars into lines by their vertical position
        chars_sorted = sorted(chars, key=lambda c: round(c["top"] / Y_TOL))
        lines = {}
        for c in chars:
            key = round(c["top"] / Y_TOL)
            lines.setdefault(key, []).append(c)
        out_path = os.path.join(OUT, f"NCRP147_ORDERED_p{p:03d}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for key in sorted(lines):
                row = sorted(lines[key], key=lambda c: c["x0"])  # left-to-right
                text = "".join(c["text"] for c in row)
                if text.strip():
                    f.write(text + "\n")
        print(f"page {p} -> {out_path}")
print("DONE")
