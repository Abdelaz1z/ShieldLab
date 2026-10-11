"""ShieldLab Draw & Survey page entry point."""

import streamlit as st

from ui import draw_survey
from ui import i18n


st.set_page_config(
    page_title=f"{i18n.t('draw_survey')} | ShieldLab",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="auto",
)

draw_survey.render()
