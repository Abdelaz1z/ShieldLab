"""ShieldLab identity primitives shared by the Streamlit product shell."""

from __future__ import annotations


def sl_mark_svg(css_class: str = "sl-mark-svg", title: str = "ShieldLab") -> str:
    """Return the selected ShieldLab structural SL monogram as safe inline SVG."""
    return f'''<svg class="{css_class}" viewBox="0 0 128 128" role="img" aria-label="{title}">
  <g fill="#102A43">
    <path d="M17 37c0-9 4-16 12-21L64 0l48 24v18L64 18 38 32c-6 3-8 7-8 12 0 6 3 10 10 14l23 13v17L31 70c-10-6-14-17-14-33Z"/>
    <path d="M18 85v-17l44 25v19L34 99c-10-5-16-15-16-25 0-4 1-7 2-10-1 8 4 15 12 19l30 14v15L29 98c-7-4-11-9-11-13Z"/>
    <path d="M67 31 91 43v54h24v19H67Z"/>
  </g>
  <path fill="#0B7285" d="M57 74 66 79v32l-9-4Z"/>
  <path fill="#9BD8DE" d="M57 74 66 79v4l-9-5Z"/>
</svg>'''
