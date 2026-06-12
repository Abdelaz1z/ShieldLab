# render_pages.py
# Renders specified PDF pages to high-resolution PNG images so table data that
# cannot be reliably extracted as text (rotated/mirrored layouts) can be read
# visually. Usage: py render_pages.py "<pdf path>" <page> <page> ...
import os
import sys
import fitz  # PyMuPDF

OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\rendered"
os.makedirs(OUT, exist_ok=True)

pdf_path = sys.argv[1]
pages = [int(a) for a in sys.argv[2:]]
base = os.path.splitext(os.path.basename(pdf_path))[0].replace(" ", "_")

doc = fitz.open(pdf_path)
zoom = 2.2  # ~158 dpi -> crisp enough to read small table digits
mat = fitz.Matrix(zoom, zoom)
for p in pages:
    page = doc[p - 1]
    pix = page.get_pixmap(matrix=mat)
    out = os.path.join(OUT, f"{base}_p{p:03d}.png")
    pix.save(out)
    print(out)
print("DONE")
