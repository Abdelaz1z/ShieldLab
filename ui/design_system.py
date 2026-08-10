"""Shared ShieldLab visual system and presentation components.

The physics and regulatory engines deliberately stay outside this module.  It
contains only the app shell, design tokens, and small accessible HTML helpers
used by both Streamlit workspaces.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

import streamlit as st

from . import i18n


_STYLES = r"""
<style>
:root {
  --sl-canvas: #f4f7f9;
  --sl-surface: #ffffff;
  --sl-surface-muted: #edf2f4;
  --sl-ink: #102a36;
  --sl-ink-soft: #4d636e;
  --sl-border: #d7e1e5;
  --sl-border-strong: #bdccd2;
  --sl-navy: #102b3f;
  --sl-navy-deep: #0b1c2b;
  --sl-teal: #0b6673;
  --sl-teal-hover: #07515b;
  --sl-blue: #145b8c;
  --sl-pass: #145a3d;
  --sl-pass-border: #21875b;
  --sl-pass-bg: #e8f5ee;
  --sl-review: #714500;
  --sl-review-border: #c27b00;
  --sl-review-bg: #fff6dc;
  --sl-fail: #7a1f27;
  --sl-fail-border: #c23b44;
  --sl-fail-bg: #fdecec;
  --sl-info: #174f78;
  --sl-info-border: #4f8db8;
  --sl-info-bg: #eaf3f9;
  --sl-font-sans: "Segoe UI Variable", "Segoe UI", Tahoma, Arial, sans-serif;
  --sl-font-arabic: "Segoe UI", Tahoma, Arial, sans-serif;
  --sl-text-xs: 12px;
  --sl-text-sm: 14px;
  --sl-text-base: 16px;
  --sl-text-md: 17px;
  --sl-text-lg: 20px;
  --sl-text-xl: 24px;
  --sl-text-display: clamp(34px, 3.4vw, 44px);
  --sl-leading-body: 1.6;
  --sl-content-max: 1360px;
  --sl-shadow: 0 1px 2px rgba(16, 42, 54, 0.06), 0 12px 32px rgba(16, 42, 54, 0.07);
  --sl-shadow-soft: 0 1px 2px rgba(16, 42, 54, 0.05), 0 6px 18px rgba(16, 42, 54, 0.04);
  --sl-radius: 16px;
  --sl-radius-large: 20px;
  --sl-control-radius: 10px;
}

html {
  color-scheme: light;
  scroll-behavior: smooth;
}

body,
.stApp {
  background: var(--sl-canvas);
  color: var(--sl-ink);
  font-family: var(--sl-font-sans);
  font-size: var(--sl-text-base);
  line-height: var(--sl-leading-body);
  -webkit-font-smoothing: antialiased;
}

.stApp {
  overflow-x: hidden;
}

.sl-locale-marker {
  display: none;
}

body:has(.sl-locale-marker[dir="rtl"]) .stApp,
body:has(.sl-locale-marker[dir="rtl"]) [data-testid="stSidebarContent"] {
  direction: rtl;
  font-family: var(--sl-font-arabic);
  text-align: start;
}

body:has(.sl-locale-marker[dir="rtl"]) .sl-brand-copy span,
body:has(.sl-locale-marker[dir="rtl"]) .sl-sidebar-label,
body:has(.sl-locale-marker[dir="rtl"]) .sl-sidebar-context span,
body:has(.sl-locale-marker[dir="rtl"]) .sl-eyebrow,
body:has(.sl-locale-marker[dir="rtl"]) .sl-context-item span,
body:has(.sl-locale-marker[dir="rtl"]) .sl-table-status,
body:has(.sl-locale-marker[dir="rtl"]) .sl-page-header h1,
body:has(.sl-locale-marker[dir="rtl"]) .sl-status-title,
body:has(.sl-locale-marker[dir="rtl"]) [data-testid="stMetricLabel"] p {
  letter-spacing: 0;
  text-transform: none;
}

bdi,
.sl-value-isolate {
  unicode-bidi: isolate;
}

.num,
[data-testid="stMetricValue"],
input[type="number"],
input[inputmode="decimal"],
code,
kbd,
samp {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: start;
}

.sl-skip-link {
  position: fixed;
  inset-block-start: 8px;
  inset-inline-start: 12px;
  z-index: 1000000;
  padding: 10px 14px;
  border-radius: var(--sl-control-radius);
  background: var(--sl-navy-deep);
  color: #fff !important;
  font-size: var(--sl-text-sm);
  font-weight: 700;
  transform: translateY(-150%);
}

.sl-skip-link:focus-visible {
  transform: translateY(0);
}

[data-testid="stHeader"] {
  height: 3.25rem;
  background: rgba(244, 247, 249, 0.92);
  border-bottom: 1px solid rgba(189, 204, 210, 0.65);
  backdrop-filter: blur(12px);
}

[data-testid="stDecoration"],
[data-testid="stAppDeployButton"] {
  display: none;
}

[data-testid="stMainBlockContainer"],
.block-container {
  width: min(100%, var(--sl-content-max));
  max-width: var(--sl-content-max);
  padding-block-start: 2.25rem;
  padding-block-end: calc(5rem + env(safe-area-inset-bottom));
  padding-inline: clamp(1.25rem, 3vw, 2.75rem);
}

/* Sidebar: product navigation first, assessment setup second. */
[data-testid="stSidebar"] {
  background: var(--sl-navy-deep);
  border-inline-end: 1px solid #20394b;
}

[data-testid="stSidebarNav"] {
  display: none;
}

[data-testid="stSidebarContent"] {
  padding-top: calc(1rem + env(safe-area-inset-top));
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
  color: #f6fafb;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] small {
  color: #aebfca;
}

[data-testid="stSidebar"] hr {
  border-color: #294253;
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  min-height: 48px;
  margin-block: 4px;
  padding: 0.75rem 0.875rem;
  color: #dce7ec;
  border: 1px solid transparent;
  border-radius: 11px;
  font-size: var(--sl-text-sm);
  font-weight: 650;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease;
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
  background: #173246;
  border-color: #315267;
  color: #ffffff;
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {
  background: #124654;
  border-color: #2c7b84;
  color: #ffffff;
}

.sl-brand {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 6px 2px 16px;
}

.sl-brand-mark {
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  flex: 0 0 46px;
  color: #e9fbfc;
  background: linear-gradient(145deg, #117786, #0a5663);
  border: 1px solid #3f919b;
  border-radius: 13px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
}

.sl-brand-copy strong {
  display: block;
  color: #ffffff;
  font-size: var(--sl-text-lg);
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.sl-brand-copy span {
  display: block;
  margin-block-start: 4px;
  color: #b7c8d1;
  font-size: var(--sl-text-xs);
  line-height: 1.4;
  letter-spacing: 0.055em;
  text-transform: uppercase;
}

[data-testid="stSidebar"] .stButtonGroup {
  margin-block: 0 18px;
}

[data-testid="stSidebar"] .stButtonGroup [data-baseweb="button-group"] {
  width: 100%;
  padding: 3px;
  background: #112a3c;
  border: 1px solid #29485b;
  border-radius: 11px;
}

[data-testid="stSidebar"] .stButtonGroup button {
  min-height: 44px;
  color: #dce7ec;
  border-radius: 8px;
  font-size: var(--sl-text-sm);
  touch-action: manipulation;
}

[data-testid="stSidebar"] .stButtonGroup button[aria-checked="true"] {
  color: #ffffff;
  background: #176474;
}

.sl-sidebar-label {
  margin: 14px 2px 7px;
  color: #a9bec9;
  font-size: var(--sl-text-xs);
  font-weight: 700;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}

.sl-sidebar-context {
  margin: 12px 0 4px;
  padding: 14px;
  background: #112a3c;
  border: 1px solid #29485b;
  border-radius: 10px;
}

.sl-sidebar-context span,
.sl-sidebar-context strong {
  display: block;
}

.sl-sidebar-context span {
  color: #a9bec9;
  font-size: var(--sl-text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.sl-sidebar-context strong {
  margin-block-start: 5px;
  color: #f7fbfc;
  font-size: 15px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.sl-sidebar-foot {
  margin-block-start: 24px;
  padding-block-start: 16px;
  color: #a9bec9;
  border-block-start: 1px solid #294253;
  font-size: 13px;
  line-height: 1.6;
}

/* Page and section hierarchy. */
.sl-page-header {
  overflow: hidden;
  margin: 2px 0 28px;
  padding: clamp(24px, 3vw, 34px);
  background: linear-gradient(135deg, #ffffff 0%, #f3fbfb 68%, #edf4f7 100%);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius-large);
  box-shadow: var(--sl-shadow);
}

.sl-eyebrow {
  margin-block-end: 8px;
  color: var(--sl-teal);
  font-size: var(--sl-text-xs);
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.sl-page-header h1 {
  max-width: 900px;
  margin: 0;
  color: var(--sl-ink);
  font-size: var(--sl-text-display);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.15;
  text-wrap: balance;
}

.sl-page-header p {
  max-width: 850px;
  margin: 12px 0 0;
  color: var(--sl-ink-soft);
  font-size: var(--sl-text-md);
  line-height: 1.6;
  text-wrap: pretty;
}

.sl-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-block-start: 18px;
}

.sl-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 5px 11px;
  color: #3e5662;
  background: #ffffff;
  border: 1px solid var(--sl-border);
  border-radius: 999px;
  font-size: var(--sl-text-xs);
  font-weight: 650;
  line-height: 1.2;
}

.sl-badge::before {
  width: 6px;
  height: 6px;
  margin-inline-end: 7px;
  background: var(--sl-teal);
  border-radius: 50%;
  content: "";
}

.sl-step-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-block-end: 18px;
}

.sl-step-number {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  flex: 0 0 36px;
  color: #ffffff;
  background: var(--sl-navy);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.sl-step-copy h2 {
  display: block;
  margin: 0;
  color: var(--sl-ink);
  font-size: var(--sl-text-lg);
  line-height: 1.3;
}

.sl-step-copy span {
  display: block;
  margin-block-start: 4px;
  color: var(--sl-ink-soft);
  font-size: var(--sl-text-sm);
  line-height: 1.55;
}

.sl-live-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 20px;
  color: #3d5965;
  font-size: var(--sl-text-sm);
}

.sl-live-note::before {
  width: 8px;
  height: 8px;
  background: var(--pass-color, var(--pass, #21875b));
  border: 2px solid #cbe8d8;
  border-radius: 50%;
  content: "";
}

.sl-context-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1px;
  overflow: hidden;
  margin: 0 0 24px;
  background: var(--sl-border);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius);
}

.sl-context-item {
  min-width: 0;
  padding: 15px 16px;
  background: var(--sl-surface);
}

.sl-context-item span,
.sl-context-item strong {
  display: block;
}

.sl-context-item span {
  color: var(--sl-ink-soft);
  font-size: var(--sl-text-xs);
  font-weight: 700;
  letter-spacing: 0.055em;
  text-transform: uppercase;
}

.sl-context-item strong {
  margin-block-start: 5px;
  color: var(--sl-ink);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

/* Decision and assurance components. */
.sl-status-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 18px;
  margin: 8px 0 20px;
  padding: 22px 24px;
  border: 1px solid;
  border-inline-start-width: 6px;
  border-radius: var(--sl-radius);
}

.sl-status-card.pass {
  color: var(--sl-pass);
  background: var(--sl-pass-bg);
  border-color: var(--sl-pass-border);
}

.sl-status-card.review {
  color: var(--sl-review);
  background: var(--sl-review-bg);
  border-color: var(--sl-review-border);
}

.sl-status-card.fail {
  color: var(--sl-fail);
  background: var(--sl-fail-bg);
  border-color: var(--sl-fail-border);
}

.sl-status-symbol {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 2px solid currentColor;
  border-radius: 50%;
  font-size: var(--sl-text-lg);
  font-weight: 800;
  line-height: 1;
}

.sl-status-content {
  min-width: 0;
}

.sl-status-title {
  color: currentColor;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.sl-status-message {
  margin-block-start: 6px;
  color: var(--sl-ink);
  font-size: var(--sl-text-base);
  line-height: 1.6;
}

.sl-status-meta {
  margin-block-start: 9px;
  color: #465e68;
  font-size: var(--sl-text-sm);
  font-variant-numeric: tabular-nums;
  line-height: 1.55;
}

.sl-assurance-note {
  margin: 10px 0 18px;
  padding: 14px 16px;
  color: var(--sl-info);
  background: var(--sl-info-bg);
  border: 1px solid var(--sl-info-border);
  border-radius: 9px;
  font-size: var(--sl-text-sm);
  line-height: 1.6;
}

.sl-empty-state {
  padding: 18px;
  color: var(--sl-ink-soft);
  background: var(--sl-surface-muted);
  border: 1px dashed var(--sl-border-strong);
  border-radius: 10px;
  font-size: var(--sl-text-sm);
  line-height: 1.6;
  text-align: center;
}

/* Semantic results table. */
.sl-table-scroll {
  overflow-x: auto;
  margin: 8px 0 16px;
  background: var(--sl-surface);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius);
  overscroll-behavior: contain;
}

.sl-results-table {
  width: 100%;
  min-width: 1120px;
  border-collapse: separate;
  border-spacing: 0;
  color: var(--sl-ink);
  font-size: var(--sl-text-sm);
  line-height: 1.5;
}

.sl-results-table caption {
  padding: 14px 16px;
  color: var(--sl-ink-soft);
  background: #f8fafb;
  border-block-end: 1px solid var(--sl-border);
  font-size: 13px;
  text-align: start;
}

.sl-results-table th {
  padding: 12px 14px;
  color: #eaf2f5;
  background: var(--sl-navy);
  border-block-end: 1px solid #26465b;
  font-size: var(--sl-text-xs);
  font-weight: 800;
  letter-spacing: 0.045em;
  text-align: start;
  text-transform: uppercase;
  white-space: nowrap;
}

.sl-results-table thead th {
  position: sticky;
  inset-block-start: 0;
  z-index: 2;
}

.sl-results-table td {
  padding: 13px 14px;
  background: #ffffff;
  border-block-end: 1px solid #e1e8eb;
  vertical-align: top;
}

.sl-results-table tbody tr:last-child td {
  border-block-end: 0;
}

.sl-results-table tbody tr:hover td {
  background: #f7fafb;
}

.sl-results-table th:first-child {
  position: sticky;
  inset-inline-start: 0;
  z-index: 3;
}

.sl-results-table .num {
  font-family: var(--sl-font-sans);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.sl-results-table .subtle {
  display: block;
  margin-block-start: 3px;
  color: var(--sl-ink-soft);
  font-size: var(--sl-text-xs);
  line-height: 1.45;
}

.sl-table-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-size: var(--sl-text-xs);
  font-weight: 800;
  letter-spacing: 0.035em;
  text-transform: uppercase;
  white-space: nowrap;
}

.sl-table-status.pass {
  color: var(--sl-pass);
  background: var(--sl-pass-bg);
  border-color: var(--sl-pass-border);
}

.sl-table-status.review {
  color: var(--sl-review);
  background: var(--sl-review-bg);
  border-color: var(--sl-review-border);
}

.sl-table-status.fail {
  color: var(--sl-fail);
  background: var(--sl-fail-bg);
  border-color: var(--sl-fail-border);
}

/* Streamlit primitives. */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--sl-surface);
  border-color: var(--sl-border);
  border-radius: var(--sl-radius);
  box-shadow: var(--sl-shadow);
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: #f8fafb;
  box-shadow: none;
}

[data-testid="stMetric"] {
  min-height: 120px;
  padding: 18px;
  background: var(--sl-surface);
  border: 1px solid var(--sl-border);
  border-radius: var(--sl-radius);
  box-shadow: var(--sl-shadow-soft);
}

[data-testid="stMetricLabel"] p {
  color: var(--sl-ink-soft);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.035em;
  text-transform: uppercase;
}

[data-testid="stMetricValue"] {
  color: var(--sl-ink);
  font-family: var(--sl-font-sans);
  font-size: clamp(26px, 2.2vw, 32px);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.04em;
}

[data-testid="stMetricDelta"] {
  font-size: var(--sl-text-xs);
}

[data-testid="stWidgetLabel"] p {
  color: var(--sl-ink);
  font-size: var(--sl-text-sm);
  font-weight: 650;
  line-height: 1.4;
}

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="base-input"],
textarea,
[data-testid="stFileUploaderDropzone"] {
  min-height: 46px;
  border-color: var(--sl-border-strong);
  border-radius: var(--sl-control-radius);
}

div[data-baseweb="input"] input,
div[data-baseweb="base-input"] input,
div[data-baseweb="select"] [role="combobox"],
textarea {
  font-size: var(--sl-text-base);
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div,
div[data-baseweb="base-input"]:focus-within,
textarea:focus-visible,
[data-testid="stFileUploaderDropzone"]:focus-within {
  border-color: var(--sl-teal);
  box-shadow: 0 0 0 3px rgba(11, 102, 115, 0.16);
}

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
  min-height: 46px;
  border-color: var(--sl-border-strong);
  border-radius: var(--sl-control-radius);
  font-size: 15px;
  font-weight: 700;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease;
  touch-action: manipulation;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {
  color: var(--sl-teal);
  background: #eef7f7;
  border-color: var(--sl-teal);
}

.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
[data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stPageLink-NavLink"]:focus-visible,
summary:focus-visible {
  outline: 3px solid rgba(11, 102, 115, 0.34);
  outline-offset: 2px;
}

button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
  color: #ffffff;
  background: var(--sl-teal);
  border-color: var(--sl-teal);
}

button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover {
  color: #ffffff;
  background: var(--sl-teal-hover);
  border-color: var(--sl-teal-hover);
}

[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 6px;
  overflow-x: auto;
  padding: 4px;
  background: #e8eef1;
  border-radius: 12px;
  overscroll-behavior-inline: contain;
  scrollbar-width: none;
}

[data-testid="stTabs"] button[data-baseweb="tab"] {
  min-height: 46px;
  flex: 0 0 auto;
  padding: 9px 16px;
  border-radius: 9px;
  font-size: 15px;
  font-weight: 700;
  touch-action: manipulation;
}

[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--sl-ink);
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(16, 42, 54, 0.11);
}

[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
  display: none;
}

[data-testid="stExpander"] {
  overflow: hidden;
  background: #ffffff;
  border: 1px solid var(--sl-border);
  border-radius: 14px;
}

[data-testid="stExpander"] summary {
  min-height: 48px;
  font-size: 15px;
  font-weight: 700;
}

[data-testid="stAlert"] {
  border-radius: 14px;
}

[data-testid="stDataFrame"],
[data-testid="stTable"] {
  overflow: hidden;
  background: #ffffff;
  border: 1px solid var(--sl-border);
  border-radius: 14px;
}

hr {
  border-color: var(--sl-border);
}

h1, h2, h3 {
  color: var(--sl-ink);
  letter-spacing: -0.02em;
  scroll-margin-top: 5rem;
  text-wrap: balance;
}

h2 {
  font-size: 27px;
}

h3 {
  font-size: var(--sl-text-lg);
}

code, kbd, samp, .stDataFrame {
  font-variant-numeric: tabular-nums;
}

.st-key-sl_room_preview {
  position: sticky;
  top: 4.5rem;
}

.st-key-sl_wall_selector [data-testid="stRadio"] [role="radiogroup"] {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.st-key-sl_wall_selector [data-testid="stRadio"] label {
  min-height: 48px;
  justify-content: center;
  margin: 0;
  padding: 10px 12px;
  background: #f5f8f9;
  border: 1px solid var(--sl-border);
  border-radius: 10px;
}

.st-key-sl_wall_selector [data-testid="stRadio"] label:has(input:checked) {
  color: var(--sl-teal);
  background: #eaf5f5;
  border-color: var(--sl-teal);
}

@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"],
  .block-container {
    padding-block-start: 1.5rem;
  }

  .st-key-sl_room_preview {
    position: static;
  }

  .sl-page-header {
    margin-block-end: 18px;
  }
}

@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"],
  .block-container {
    padding-inline: max(1rem, env(safe-area-inset-left), env(safe-area-inset-right));
  }

  .sl-page-header {
    padding: 20px;
  }

  .sl-page-header h1 {
    font-size: 32px;
  }

  .sl-page-header p {
    font-size: var(--sl-text-base);
  }

  .sl-context-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sl-status-card {
    grid-template-columns: 1fr;
  }

  .sl-status-symbol {
    width: 36px;
    height: 36px;
  }

  .stButton > button,
  .stDownloadButton > button,
  [data-testid="stFormSubmitButton"] > button {
    min-height: 48px;
  }

  .st-key-sl_wall_selector [data-testid="stRadio"] [role="radiogroup"] {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  html {
    scroll-behavior: auto;
  }

  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

@media print {
  [data-testid="stSidebar"],
  [data-testid="stHeader"],
  .stButton,
  .stDownloadButton,
  [data-testid="stFileUploader"] {
    display: none !important;
  }

  .stApp,
  body {
    background: #ffffff;
  }

  [data-testid="stMainBlockContainer"],
  .block-container {
    max-width: none;
    padding: 0;
  }

  .sl-table-scroll {
    overflow: visible;
  }
}
</style>
"""


def inject_styles() -> None:
    """Apply the visual system, locale direction, and keyboard skip navigation."""
    st.markdown(_STYLES, unsafe_allow_html=True)
    st.markdown(i18n.locale_marker_html(), unsafe_allow_html=True)
    st.markdown(
        f'<a class="sl-skip-link" href="#shieldlab-main" {i18n.html_attributes()}>'
        f'{escape(i18n.t("skip_to_assessment"))}</a>',
        unsafe_allow_html=True,
    )


def render_sidebar_footer() -> None:
    """Close the sidebar after page-specific controls have been rendered."""
    with st.sidebar:
        st.markdown(
            f"""
            <div class="sl-sidebar-foot" {i18n.html_attributes()}>
              {escape(i18n.t("decision_support"))}<br>
              {escape(i18n.t("qualified_review_required"))}
            </div>
            """,
            unsafe_allow_html=True,
        )


def page_header(
    eyebrow: str, title: str, description: str, badges: Sequence[str] = ()
) -> None:
    """Render a compact product header without marketing-style decoration."""
    badge_html = "".join(f'<span class="sl-badge">{escape(badge)}</span>' for badge in badges)
    badge_row = f'<div class="sl-badge-row">{badge_html}</div>' if badge_html else ""
    st.markdown(
        f"""
        <header class="sl-page-header" id="shieldlab-main" tabindex="-1"
                {i18n.html_attributes()}>
          <div class="sl-eyebrow">{escape(eyebrow)}</div>
          <h1>{escape(title)}</h1>
          <p>{escape(description)}</p>
          {badge_row}
        </header>
        """,
        unsafe_allow_html=True,
    )


def section_header(step: str, title: str, description: str = "") -> None:
    """Render a numbered workflow heading inside a bordered container."""
    detail = f"<span>{escape(description)}</span>" if description else ""
    st.markdown(
        f"""
        <div class="sl-step-header" {i18n.html_attributes()}>
          <div class="sl-step-number" aria-hidden="true">{escape(str(step))}</div>
          <div class="sl-step-copy"><h2>{escape(title)}</h2>{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def live_note(message: str) -> None:
    st.markdown(
        f'<div class="sl-live-note" {i18n.html_attributes()}>{escape(message)}</div>',
        unsafe_allow_html=True,
    )


def assurance_note(message: str) -> None:
    st.markdown(
        f'<div class="sl-assurance-note" {i18n.html_attributes()}>{escape(message)}</div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    st.markdown(
        f'<div class="sl-empty-state" {i18n.html_attributes()}>{escape(message)}</div>',
        unsafe_allow_html=True,
    )
