"""ShieldLab product shell with stable workspace navigation."""

from html import escape

import streamlit as st

from . import i18n
from .brand import sl_mark_svg
from .design_system import (
    assurance_note,
    empty_state,
    inject_styles,
    live_note,
    page_header,
    render_sidebar_footer,
    section_header,
)


__all__ = [
    "assurance_note",
    "context_strip",
    "empty_state",
    "inject_styles",
    "live_note",
    "page_header",
    "render_sidebar",
    "render_sidebar_footer",
    "section_header",
    "status_card",
]


def _render_html(content: str) -> None:
    """Use Streamlit's HTML element to avoid Markdown parsing of nested cards."""
    if hasattr(st, "html"):
        st.html(content)
    else:  # Compatibility for older supported Streamlit releases.
        st.markdown(content, unsafe_allow_html=True)


def _context_cell(label: object, value: object) -> str:
    label_text = escape(str(label))
    value_text = escape(str(value))
    return (
        '<div class="sl-context-item">'
        f"<span>{label_text}</span>"
        f'<strong title="{value_text}"><bdi class="sl-value-isolate" '
        f'dir="auto">{value_text}</bdi></strong>'
        "</div>"
    )


def context_strip(items) -> None:
    cells = "".join(_context_cell(label, value) for label, value in items)
    _render_html(
        f'<section class="sl-context-strip" {i18n.html_attributes()} '
        f'aria-label="{escape(i18n.t("assessment_basis"))}">{cells}</section>'
    )


def _status_presentation(status: str) -> tuple[str, str, str]:
    normalized_status = status.upper()
    if normalized_status == "PASS":
        return "pass", "✓", i18n.t("pass")
    if normalized_status == "FAIL":
        return "fail", "×", i18n.t("fail")
    return "review", "!", i18n.t("review_required")


def _status_copy(css_class: str, copy: str) -> str:
    if not copy:
        return ""
    return (
        f'<div class="{css_class}"><bdi class="sl-value-isolate" '
        f'dir="auto">{escape(copy)}</bdi></div>'
    )


def status_card(status: str, message: str, detail: str = "", meta: str = "") -> None:
    css_class, symbol, status_label = _status_presentation(status)
    detail_html = _status_copy("sl-status-message", detail)
    meta_html = _status_copy("sl-status-meta", meta)
    _render_html(
        f'<section class="sl-status-card {css_class}" {i18n.html_attributes()} '
        'role="status" aria-live="polite">'
        f'<div class="sl-status-symbol" aria-hidden="true">{symbol}</div>'
        '<div class="sl-status-content">'
        f'<div class="sl-status-title">{escape(status_label)} · '
        f'<bdi dir="auto">{escape(message)}</bdi></div>'
        f"{detail_html}{meta_html}</div></section>"
    )


def _workspace_fallback_html() -> str:
    return (
        f'<div class="sl-sidebar-context" {i18n.html_attributes()}>'
        f'<span>{escape(i18n.t("workspace_navigation"))}</span>'
        f'<strong>{escape(i18n.t("barrier_assessment"))}<br>'
        f'{escape(i18n.t("room_designer"))}</strong></div>'
    )


def _workspace_links() -> None:
    """Render multipage links, with a safe fallback for direct-page test runs."""
    try:
        st.page_link(
            "app.py",
            label=i18n.t("barrier_assessment"),
            icon=":material/calculate:",
        )
        st.page_link(
            "pages/1_Room_Designer.py",
            label=i18n.t("room_designer"),
            icon=":material/architecture:",
        )
    except KeyError:
        st.markdown(_workspace_fallback_html(), unsafe_allow_html=True)


def _brand_html() -> str:
    return f"""
    <div class="sl-brand" {i18n.html_attributes()}>
      <div class="sl-brand-mark">{sl_mark_svg("sl-brand-logo", "ShieldLab")}</div>
      <div class="sl-brand-copy">
        <strong translate="no">ShieldLab</strong>
        <span>{escape(i18n.t("brand_subtitle"))}</span>
      </div>
    </div>
    """


def _active_workspace_html(active_label: str) -> str:
    return (
        f'<div class="sl-sidebar-context" {i18n.html_attributes()}>'
        f'<span>{escape(i18n.t("active_workspace"))}</span>'
        f'<strong>{escape(active_label)}</strong></div>'
    )


def render_sidebar(active_workspace: str) -> None:
    workspace_keys = {
        "calculator": "barrier_assessment",
        "room": "room_designer",
    }
    active_message_key = workspace_keys.get(active_workspace)
    active_label = i18n.t(active_message_key) if active_message_key else str(active_workspace)
    with st.sidebar:
        st.markdown(_brand_html(), unsafe_allow_html=True)
        i18n.render_language_switcher()
        st.markdown(
            f'<div class="sl-sidebar-label" {i18n.html_attributes()}>'
            f'{escape(i18n.t("workspaces"))}</div>',
            unsafe_allow_html=True,
        )
        _workspace_links()
        st.markdown(_active_workspace_html(active_label), unsafe_allow_html=True)
