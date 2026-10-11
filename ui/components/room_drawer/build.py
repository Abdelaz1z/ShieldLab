"""
Builds the Draw & Survey page's drawing component from Room Designer's one-file handout.

Room Designer is developed in its own folder; its `node build.js` writes `dist/Room-Designer.html`,
the whole app in one file. This script copies that file here as `index.html` and inlines
`bridge.js` before `</body>`, so Streamlit can serve it as a component. Re-run it after Room
Designer changes:

    py -3 ui\\components\\room_drawer\\build.py "D:\\Projects\\Claude\\Room Designer\\dist\\Room-Designer.html"
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build(handout: Path) -> Path:
    html = handout.read_text(encoding="utf-8")
    if html.count("</body>") != 1:
        raise ValueError(f"{handout} does not look like Room Designer's one-file build.")
    bridge = (HERE / "bridge.js").read_text(encoding="utf-8")
    out = HERE / "index.html"
    out.write_text(html.replace("</body>", f"<script>\n{bridge}\n</script>\n</body>"),
                   encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print("wrote", build(Path(sys.argv[1])))
