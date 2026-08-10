"""
ShieldLab - commercial Streamlit application shell.

All calculations remain in ``shieldlab``; this entry point only assembles the
shared product navigation and the single-barrier assessment workspace.
"""

import os
import sys

# Make the shieldlab package importable when Streamlit runs this file directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from ui import commercial_views as views
from ui import i18n
from ui import product_shell as ds


st.set_page_config(
    page_title=f"{i18n.t('barrier_assessment')} | ShieldLab",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="auto",
)


def main() -> None:
    ds.inject_styles()
    ds.render_sidebar("calculator")
    ds.page_header(
        i18n.t("calculator_eyebrow"),
        i18n.t("calculator_title"),
        i18n.t("calculator_description"),
        badges=(
            i18n.t("badge_traceable"),
            i18n.t("badge_live"),
            i18n.t("badge_rso"),
        ),
    )

    with st.container(key="sl_primary_tabs"):
        tabs = st.tabs(
            [
                i18n.t("tab_assessment"),
                i18n.t("tab_methods"),
                i18n.t("tab_safety"),
            ]
        )

    with tabs[0]:
        views.calculator_tab()
    with tabs[1]:
        views.references_tab()
    with tabs[2]:
        views.limitations_tab()
    ds.render_sidebar_footer()


if __name__ == "__main__":
    main()
