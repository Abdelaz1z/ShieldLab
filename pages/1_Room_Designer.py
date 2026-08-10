"""ShieldLab Room Designer page entry point."""

import streamlit as st

from ui import commercial_room
from ui import i18n


st.set_page_config(
    page_title=f"{i18n.t('room_designer')} | ShieldLab",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="auto",
)

commercial_room.render()
