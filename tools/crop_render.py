# crop_render.py
# Renders a sub-region (crop) of a PDF page at very high zoom so small
# scientific-notation exponents in dense tables can be read exactly.
# Usage: py crop_render.py "<pdf>" <page> <x0frac> <y0frac> <x1frac> <y1frac> <zoom> <tag>
import os
import sys
import fitz

OUT = r"D:\Projects\Master\Master-26\Control Claude Program\tools\rendered"
os.makedirs(OUT, exist_ok=True)

pdf_path = sys.argv[1]
page_no = int(sys.argv[2])
x0f, y0f, x1f, y1f = [float(a) for a in sys.argv[3:7]]
zoom = float(sys.argv[7])
tag = sys.argv[8]

doc = fitz.open(pdf_path)
page = doc[page_no - 1]
r = page.rect
clip = fitz.Rect(r.x0 + x0f * r.width, r.y0 + y0f * r.height,
                 r.x0 + x1f * r.width, r.y0 + y1f * r.height)
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
out = os.path.join(OUT, f"crop_{tag}.png")
pix.save(out)
print(out)
