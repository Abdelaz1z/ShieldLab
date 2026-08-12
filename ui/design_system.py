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
from .brand import sl_mark_svg


_STYLES = r"""
<style>
:root {
  --sl-canvas: #F6F8FB;
  --sl-surface: #FFFFFF;
  --sl-surface-muted: #EAF0F5;
  --sl-ink: #102A43;
  --sl-ink-soft: #3E566B;
  --sl-border: #C4D1DC;
  --sl-border-strong: #879CAB;
  --sl-navy: #102A43;
  --sl-navy-deep: #0B2438;
  --sl-teal: #0B7285;
  --sl-teal-hover: #075D6A;
  --sl-cyan: #2B9CAC;
  --sl-cyan-soft: #9BD8DE;
  --sl-violet: #52697D;
  --sl-amber: #e59b26;
  --sl-blue: #0f527f;
  --sl-pass: #0a472e;
  --sl-pass-border: #147347;
  --sl-pass-bg: #d7ecdf;
  --sl-review: #563200;
  --sl-review-border: #a25e00;
  --sl-review-bg: #ffedb8;
  --sl-fail: #671620;
  --sl-fail-border: #a82432;
  --sl-fail-bg: #f8dadd;
  --sl-info: #0b3f60;
  --sl-info-border: #2c7099;
  --sl-info-bg: #dcebf4;
  --sl-sidebar-ink: #f7fbfc;
  --sl-sidebar-soft: #c5d3d9;
  --sl-sidebar-accent: #91cbd1;
  --sl-sidebar-panel: #0d2a3b;
  --sl-sidebar-border: #456273;
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
  --sl-shadow: 0 2px 5px rgba(7, 28, 39, 0.10), 0 20px 48px rgba(7, 28, 39, 0.12);
  --sl-shadow-soft: 0 1px 2px rgba(7, 28, 39, 0.08), 0 10px 24px rgba(7, 28, 39, 0.08);
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
  background: rgba(232, 238, 242, 0.82);
  border-bottom: 1px solid rgba(96, 125, 138, 0.58);
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
  border-inline-end: 1px solid #345365;
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
  color: var(--sl-sidebar-ink);
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] small {
  color: var(--sl-sidebar-soft);
}

[data-testid="stSidebar"] hr {
  border-color: var(--sl-sidebar-border);
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  min-height: 48px;
  margin-block: 4px;
  padding: 0.75rem 0.875rem;
  color: #edf4f7;
  border: 1px solid transparent;
  border-radius: 11px;
  font-size: var(--sl-text-sm);
  font-weight: 650;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, transform 150ms ease;
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
  background: linear-gradient(90deg, #12384e, #0d3043);
  border-color: #6c91a3;
  color: #ffffff;
  transform: translateX(3px);
}

[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {
  background: linear-gradient(110deg, #0d6875, #10445e);
  border-color: #83d1d6;
  color: #ffffff;
  box-shadow: inset 3px 0 0 var(--sl-cyan-soft), 0 8px 20px rgba(0, 0, 0, 0.16);
}

.sl-brand {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 6px 2px 16px;
}

.sl-brand-mark {
  display: grid;
  width: 48px;
  height: 48px;
  padding: 5px;
  place-items: center;
  flex: 0 0 48px;
  background: #ffffff;
  border: 1px solid #6D899A;
  border-radius: 10px;
  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.18);
}

.sl-brand-logo {
  display: block;
  width: 100%;
  height: 100%;
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
  color: var(--sl-sidebar-soft);
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
  background: var(--sl-sidebar-panel);
  border: 1px solid var(--sl-sidebar-border);
  border-radius: 11px;
}

[data-testid="stSidebar"] .stButtonGroup button {
  min-height: 44px;
  color: #edf4f7;
  border-radius: 8px;
  font-size: var(--sl-text-sm);
  touch-action: manipulation;
}

[data-testid="stSidebar"] .stButtonGroup button[aria-checked="true"] {
  color: #ffffff;
  background: #0f6874;
}

.sl-sidebar-label {
  margin: 14px 2px 7px;
  color: var(--sl-sidebar-soft);
  font-size: var(--sl-text-xs);
  font-weight: 700;
  letter-spacing: 0.075em;
  text-transform: uppercase;
}

.sl-sidebar-context {
  margin: 12px 0 4px;
  padding: 14px;
  background: var(--sl-sidebar-panel);
  border: 1px solid var(--sl-sidebar-border);
  border-radius: 10px;
}

.sl-sidebar-context span,
.sl-sidebar-context strong {
  display: block;
}

.sl-sidebar-context span {
  color: var(--sl-sidebar-soft);
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
  color: var(--sl-sidebar-soft);
  border-block-start: 1px solid var(--sl-sidebar-border);
  font-size: 13px;
  line-height: 1.6;
}

/* Page and section hierarchy. */
.sl-page-header {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(190px, 250px);
  align-items: center;
  gap: clamp(22px, 4vw, 54px);
  min-height: 310px;
  overflow: hidden;
  margin: 2px 0 28px;
  padding: clamp(28px, 4vw, 48px);
  color: #ffffff;
  background: var(--sl-navy);
  border: 1px solid #416277;
  border-radius: 20px;
  box-shadow: 0 16px 40px rgba(16, 42, 67, 0.18);
}

.sl-page-header::before {
  position: absolute;
  inset: 0;
  z-index: -1;
  background-image:
    linear-gradient(rgba(141, 231, 236, 0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(141, 231, 236, 0.07) 1px, transparent 1px);
  background-size: 32px 32px;
  content: "";
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 58%, #000);
  mask-image: linear-gradient(90deg, transparent, #000 58%, #000);
}

.sl-page-header::after {
  display: none;
}

.sl-hero-copy {
  min-width: 0;
}

.sl-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  margin-block-end: 12px;
  color: var(--sl-cyan-soft);
  font-size: var(--sl-text-xs);
  font-weight: 800;
  letter-spacing: 0.13em;
  text-transform: uppercase;
}

.sl-eyebrow::before {
  width: 26px;
  height: 2px;
  background: currentColor;
  content: "";
}

.sl-page-header h1 {
  max-width: 860px;
  margin: 0;
  color: #ffffff;
  font-size: clamp(38px, 4.2vw, 58px);
  font-weight: 760;
  letter-spacing: -0.045em;
  line-height: 1.06;
  text-wrap: balance;
}

.sl-page-header p {
  max-width: 760px;
  margin: 16px 0 0;
  color: #d2e2e8;
  font-size: var(--sl-text-md);
  line-height: 1.65;
  text-wrap: pretty;
}

.sl-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-block-start: 22px;
}

.sl-badge {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 6px 12px;
  color: #f4fbfc;
  background: rgba(8, 29, 42, 0.48);
  border: 1px solid rgba(141, 231, 236, 0.42);
  border-radius: 999px;
  backdrop-filter: blur(10px);
  font-size: var(--sl-text-xs);
  font-weight: 700;
  line-height: 1.2;
}

.sl-badge::before {
  width: 7px;
  height: 7px;
  margin-inline-end: 8px;
  background: var(--sl-cyan-soft);
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(141, 231, 236, 0.10);
  content: "";
}

.sl-hero-visual {
  position: relative;
  display: grid;
  width: min(100%, 240px);
  aspect-ratio: 1;
  place-items: center;
  justify-self: center;
}

.sl-orbit-ring {
  position: absolute;
  border: 1px solid rgba(141, 231, 236, 0.34);
  border-radius: 50%;
}

.sl-orbit-ring.one {
  inset: 7%;
  border-style: dashed;
  animation: sl-orbit-spin 22s linear infinite;
}

.sl-orbit-ring.two {
  inset: 22%;
  border-color: rgba(255, 255, 255, 0.32);
}

.sl-orbit-ring.three {
  inset: 35%;
  border-color: rgba(32, 184, 198, 0.64);
  box-shadow: 0 0 32px rgba(32, 184, 198, 0.24);
}

.sl-orbit-ring.one::before,
.sl-orbit-ring.two::after {
  position: absolute;
  width: 10px;
  height: 10px;
  background: var(--sl-cyan-soft);
  border: 3px solid #0b4051;
  border-radius: 50%;
  content: "";
  box-shadow: 0 0 16px rgba(141, 231, 236, 0.75);
}

.sl-orbit-ring.one::before {
  inset-block-start: 12%;
  inset-inline-end: 12%;
}

.sl-orbit-ring.two::after {
  inset-block-end: -5px;
  inset-inline-start: 46%;
  background: #b9adff;
}

.sl-orbit-core {
  display: grid;
  width: 76px;
  height: 76px;
  place-items: center;
  color: #ffffff;
  background: linear-gradient(145deg, rgba(32, 184, 198, 0.95), rgba(0, 79, 92, 0.96));
  border: 1px solid #a9f5f7;
  border-radius: 23px;
  box-shadow: 0 0 0 10px rgba(141, 231, 236, 0.08), 0 20px 42px rgba(0, 0, 0, 0.30);
  transform: rotate(4deg);
}

.sl-orbit-core svg {
  transform: rotate(-4deg);
}

/* Selected ShieldLab structural SL monogram. */
.sl-hero-mark-panel {
  display: grid;
  width: 164px;
  height: 164px;
  padding: 21px;
  place-items: center;
  background: #ffffff;
  border: 1px solid rgba(155, 216, 222, 0.82);
  border-radius: 18px;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22);
}

.sl-hero-mark {
  display: block;
  width: 100%;
  height: 100%;
}

@keyframes sl-orbit-spin {
  to { transform: rotate(360deg); }
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
  background: linear-gradient(145deg, var(--sl-cyan), var(--sl-teal) 58%, var(--sl-blue));
  border: 1px solid #6fd0d7;
  border-radius: 11px;
  box-shadow: 0 8px 18px rgba(0, 101, 116, 0.20);
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
  display: inline-flex;
  align-items: center;
  gap: 9px;
  margin: 8px 0 22px;
  padding: 8px 12px;
  color: #1e4654;
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid #9cb8c3;
  border-radius: 999px;
  font-size: var(--sl-text-sm);
  font-weight: 650;
  box-shadow: 0 5px 14px rgba(7, 28, 39, 0.06);
}

.sl-live-note::before {
  width: 8px;
  height: 8px;
  background: var(--sl-pass-border);
  border: 2px solid #a4d2b7;
  border-radius: 50%;
  content: "";
  box-shadow: 0 0 0 4px rgba(20, 115, 71, 0.11);
  animation: sl-live-pulse 2.2s ease-in-out infinite;
}

.sl-context-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
  margin: 0 0 26px;
}

.sl-context-item {
  position: relative;
  min-width: 0;
  overflow: hidden;
  padding: 16px 17px;
  background: linear-gradient(145deg, #ffffff, #f1f7f8);
  border: 1px solid var(--sl-border);
  border-radius: 13px;
  box-shadow: var(--sl-shadow-soft);
}

.sl-context-item::after {
  position: absolute;
  width: 42px;
  height: 3px;
  inset-block-end: 0;
  inset-inline-start: 17px;
  background: linear-gradient(90deg, var(--sl-cyan), var(--sl-violet));
  border-radius: 4px 4px 0 0;
  content: "";
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
  overflow: hidden;
  padding: 24px 26px;
  border: 1px solid;
  border-inline-start-width: 7px;
  border-radius: 18px;
  box-shadow: var(--sl-shadow-soft);
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
  color: #304b58;
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
  background: var(--sl-surface-muted);
  border-block-end: 1px solid var(--sl-border);
  font-size: 13px;
  text-align: start;
}

.sl-results-table th {
  padding: 12px 14px;
  color: #ffffff;
  background: var(--sl-navy);
  border-block-end: 1px solid #496879;
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
  border-block-end: 1px solid #c4d1d7;
  vertical-align: top;
}

.sl-results-table tbody tr:last-child td {
  border-block-end: 0;
}

.sl-results-table tbody tr:hover td {
  background: #e7f0f3;
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
  background: linear-gradient(160deg, #ffffff 0%, #f8fbfc 100%);
  border-color: var(--sl-border);
  border-radius: 18px;
  box-shadow: var(--sl-shadow);
}

.st-key-sl_source_inputs > [data-testid="stVerticalBlockBorderWrapper"],
.st-key-sl_barrier_builder > [data-testid="stVerticalBlockBorderWrapper"] {
  position: relative;
  overflow: hidden;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.st-key-sl_source_inputs > [data-testid="stVerticalBlockBorderWrapper"]::before,
.st-key-sl_barrier_builder > [data-testid="stVerticalBlockBorderWrapper"]::before {
  position: absolute;
  inset: 0 0 auto;
  height: 4px;
  background: linear-gradient(90deg, var(--sl-cyan), var(--sl-violet));
  content: "";
}

@media (hover: hover) and (pointer: fine) {
  .st-key-sl_source_inputs > [data-testid="stVerticalBlockBorderWrapper"]:hover,
  .st-key-sl_barrier_builder > [data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: #3a8391;
    box-shadow: 0 24px 55px rgba(7, 28, 39, 0.16);
    transform: translateY(-3px);
  }
}

[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--sl-surface-muted);
  box-shadow: none;
}

[data-testid="stMetric"] {
  position: relative;
  min-height: 126px;
  overflow: hidden;
  padding: 20px;
  background:
    radial-gradient(circle at 100% 0%, rgba(32, 184, 198, 0.15), transparent 8rem),
    var(--sl-surface);
  border: 1px solid var(--sl-border);
  border-radius: 16px;
  box-shadow: var(--sl-shadow-soft);
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

[data-testid="stMetric"]::before {
  position: absolute;
  width: 54px;
  height: 4px;
  inset-block-start: 0;
  inset-inline-start: 20px;
  background: linear-gradient(90deg, var(--sl-cyan), var(--sl-violet));
  border-radius: 0 0 5px 5px;
  content: "";
}

@media (hover: hover) and (pointer: fine) {
  [data-testid="stMetric"]:hover {
    border-color: #3a8391;
    box-shadow: 0 16px 34px rgba(7, 28, 39, 0.13);
    transform: translateY(-2px);
  }
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

/* BaseWeb applies child-level theme colors, so sidebar form descendants need
   explicit foregrounds instead of relying on inherited sidebar text color. */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] label p,
[data-testid="stSidebar"] [data-testid="stRadio"] label p {
  color: var(--sl-sidebar-ink) !important;
  opacity: 1;
}

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] svg,
[data-testid="stSidebar"] div[data-baseweb="select"] svg {
  color: var(--sl-sidebar-soft) !important;
  fill: currentColor;
  opacity: 1;
}

[data-testid="stSidebar"] input,
[data-testid="stSidebar"] input:disabled,
[data-testid="stSidebar"] input[aria-disabled="true"] {
  color: var(--sl-sidebar-ink) !important;
  -webkit-text-fill-color: var(--sl-sidebar-ink) !important;
  opacity: 1 !important;
}

[data-testid="stSidebar"] div[data-baseweb="input"] button {
  color: #173846 !important;
  opacity: 1;
}

[data-testid="stSidebar"] div[data-baseweb="input"] button:disabled {
  color: #536d78 !important;
  opacity: 1;
}

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="base-input"],
textarea,
[data-testid="stFileUploaderDropzone"] {
  min-height: 46px;
  color: var(--sl-ink);
  background: var(--sl-surface);
  border: 1px solid var(--sl-border-strong);
  border-radius: var(--sl-control-radius);
}

div[data-baseweb="input"] input,
div[data-baseweb="base-input"] input,
div[data-baseweb="select"] [role="combobox"],
textarea {
  color: var(--sl-ink);
  caret-color: var(--sl-teal);
  font-size: var(--sl-text-base);
}

input::placeholder,
textarea::placeholder {
  color: #536d79;
  opacity: 1;
}

div[data-baseweb="select"] svg {
  fill: var(--sl-ink-soft);
}

[data-testid="stSidebar"] div[data-baseweb="input"] > div,
[data-testid="stSidebar"] div[data-baseweb="select"] > div,
[data-testid="stSidebar"] div[data-baseweb="base-input"],
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
  color: var(--sl-sidebar-ink);
  background: var(--sl-sidebar-panel);
  border-color: var(--sl-sidebar-border);
}

[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] div[data-baseweb="select"] [role="combobox"] {
  color: var(--sl-sidebar-ink);
}

[data-testid="stSidebar"] input::placeholder,
[data-testid="stSidebar"] textarea::placeholder {
  color: var(--sl-sidebar-soft);
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div,
div[data-baseweb="base-input"]:focus-within,
textarea:focus-visible,
[data-testid="stFileUploaderDropzone"]:focus-within {
  border-color: var(--sl-teal);
  box-shadow: 0 0 0 3px rgba(0, 101, 116, 0.22);
}

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
  min-height: 46px;
  color: var(--sl-navy);
  background: var(--sl-surface);
  border: 1px solid var(--sl-border-strong);
  border-radius: var(--sl-control-radius);
  font-size: 15px;
  font-weight: 700;
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
  touch-action: manipulation;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {
  color: var(--sl-teal);
  background: #dff0f1;
  border-color: var(--sl-teal);
  box-shadow: 0 8px 18px rgba(7, 28, 39, 0.12);
  transform: translateY(-1px);
}

.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
[data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stPageLink-NavLink"]:focus-visible,
summary:focus-visible {
  outline: 3px solid rgba(0, 101, 116, 0.42);
  outline-offset: 2px;
}

button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
  color: #ffffff;
  background: linear-gradient(110deg, #087989, var(--sl-teal) 58%, #154d79);
  border-color: #005360;
  box-shadow: 0 9px 20px rgba(0, 101, 116, 0.22);
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
  padding: 5px;
  background: linear-gradient(115deg, #b9ccd4, #d3dde2);
  border: 1px solid #8fa7b2;
  border-radius: 14px;
  box-shadow: inset 0 1px 2px rgba(7, 28, 39, 0.12);
  overscroll-behavior-inline: contain;
  scrollbar-width: none;
}

[data-testid="stTabs"] button[data-baseweb="tab"] {
  min-height: 46px;
  flex: 0 0 auto;
  padding: 9px 16px;
  color: var(--sl-ink-soft);
  border: 1px solid transparent;
  border-radius: 9px;
  font-size: 15px;
  font-weight: 700;
  touch-action: manipulation;
}

[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--sl-ink);
  background: linear-gradient(135deg, #ffffff, #edf8f8);
  border-color: #4b8996;
  box-shadow: 0 7px 18px rgba(7, 28, 39, 0.15);
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
  background: #dfe7eb;
  border: 1px solid var(--sl-border);
  border-radius: 10px;
}

.st-key-sl_wall_selector [data-testid="stRadio"] label:has(input:checked) {
  color: var(--sl-teal);
  background: #d5ecee;
  border-color: var(--sl-teal);
}

@keyframes sl-live-pulse {
  0%, 100% { opacity: 0.72; transform: scale(0.88); }
  50% { opacity: 1; transform: scale(1.16); }
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
    grid-template-columns: minmax(0, 1fr) 180px;
    min-height: 280px;
    margin-block-end: 18px;
  }
}

@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"],
  .block-container {
    padding-inline: max(1rem, env(safe-area-inset-left), env(safe-area-inset-right));
  }

  .sl-page-header {
    grid-template-columns: 1fr;
    min-height: 0;
    padding: 25px 22px;
    border-radius: 20px;
  }

  .sl-page-header h1 {
    font-size: 36px;
  }

  .sl-hero-visual {
    display: none;
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

/* ShieldLab Command Suite — operational, decision-first product layer. */
:root {
  --sl-canvas: #eef3f6;
  --sl-surface: #ffffff;
  --sl-surface-alt: #f7fafb;
  --sl-ink: #102a43;
  --sl-ink-soft: #526d7e;
  --sl-border: #d5e1e7;
  --sl-border-strong: #a9c0cb;
  --sl-navy: #102a43;
  --sl-navy-deep: #081d2d;
  --sl-teal: #087a86;
  --sl-cyan: #24b4bd;
  --sl-cyan-soft: #b9edf0;
  --sl-radius: 14px;
  --sl-radius-large: 20px;
  --sl-shadow: 0 18px 44px rgba(11, 36, 56, 0.10);
  --sl-shadow-soft: 0 8px 24px rgba(11, 36, 56, 0.07);
}

.stApp {
  background: radial-gradient(circle at 100% -10%, rgba(36,180,189,.13), transparent 26rem), linear-gradient(180deg, #f9fbfc 0, var(--sl-canvas) 38rem);
}

[data-testid="stHeader"] { height: 3.4rem; background: rgba(248,251,252,.88); border-bottom-color: rgba(169,192,203,.65); }
[data-testid="stMainBlockContainer"], .block-container { max-width: 1480px; padding-block: 1.6rem 5.5rem; }

/* Product rail */
[data-testid="stSidebar"] { background: radial-gradient(circle at 0 0, rgba(22,130,143,.42), transparent 19rem), linear-gradient(180deg, #0a273a, var(--sl-navy-deep) 74%); border-inline-end-color: #264b5e; }
[data-testid="stSidebarContent"] { padding-inline: .92rem; }
.sl-brand { gap: 11px; margin: .2rem 0 .7rem; padding: .52rem .18rem .7rem; }
.st-key-sl_language_top { display: flex; justify-content: flex-end; padding-top: .54rem; }
.st-key-sl_language_top .stButtonGroup { width: auto; margin: 0; }
.st-key-sl_language_top .stButtonGroup [data-baseweb="button-group"] { width: auto; min-width: 72px; gap: 3px; padding: 3px; background: rgba(4, 23, 36, .82); border-color: rgba(177, 237, 240, .62); border-radius: 10px; box-shadow: inset 0 0 0 1px rgba(5, 53, 69, .7), 0 4px 12px rgba(0,0,0,.18); }
.st-key-sl_language_top .stButtonGroup button { min-width: 31px; min-height: 29px; padding: 2px 7px; color: #e7fbfc !important; background: rgba(102, 190, 197, .14); border: 1px solid rgba(173, 235, 238, .30); border-radius: 7px; font-size: 11px; font-weight: 800; line-height: 1; }
.st-key-sl_language_top .stButtonGroup button * { color: #e7fbfc !important; }
.st-key-sl_language_top .stButtonGroup button[aria-checked="true"] { color: #062f3a !important; background: #f4ffff; border-color: #ffffff; box-shadow: 0 2px 7px rgba(0,0,0,.26); }
.st-key-sl_language_top .stButtonGroup button[aria-checked="true"] * { color: #062f3a !important; }
.st-key-sl_language_top .stButtonGroup button:focus-visible { outline: 2px solid #8ff0f2; outline-offset: 2px; }
.sl-brand-mark { width: 46px; height: 46px; flex-basis: 46px; padding: 5px; background: linear-gradient(145deg,#f8ffff,#d6f2f4); border-color: rgba(186,245,247,.92); border-radius: 13px; box-shadow: 0 10px 24px rgba(0,0,0,.24), inset 0 0 0 1px rgba(8,122,134,.08); }
.sl-brand-copy strong { font-size: 19px; letter-spacing: -.035em; }
.sl-brand-copy span { color: #a7d3d8; font-size: 10px; letter-spacing: .095em; }
.sl-sidebar-label { margin: 1.15rem .2rem .45rem; color: #8abdc4; font-size: 10px; letter-spacing: .14em; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { min-height: 46px; margin-block: 5px; padding: .7rem .76rem; border-radius: 11px; font-size: 13px; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background: linear-gradient(115deg,#096f7b,#10425d); border-color: rgba(152,236,239,.65); box-shadow: inset 3px 0 0 #bcf5f6, 0 8px 20px rgba(0,0,0,.18); }
.sl-sidebar-context { margin-top: 1rem; padding: 13px 14px; background: linear-gradient(145deg,rgba(16,60,78,.94),rgba(10,43,61,.82)); border-color: rgba(127,196,203,.38); border-radius: 13px; box-shadow: inset 0 1px 0 rgba(216,255,255,.08); }
.sl-sidebar-context::before { display: inline-block; width: 7px; height: 7px; margin-inline-end: 7px; background: #75e1e3; border-radius: 50%; box-shadow: 0 0 0 4px rgba(117,225,227,.12); content: ""; }
.sl-sidebar-context span { display: inline; color: #9ecbd0; font-size: 10px; }
.sl-sidebar-context strong { margin-top: 7px; font-size: 14px; line-height: 1.35; }
.sl-sidebar-status { display: block; margin-top: 7px; color: #9bd8de; font-size: 10px; font-weight: 700; letter-spacing: .055em; text-transform: uppercase; }
.sl-sidebar-step { position: relative; margin: 1rem 0 .7rem; padding: .1rem 0 .1rem .75rem; border-inline-start: 2px solid rgba(131, 211, 216, .36); }
.sl-sidebar-step-index { color: #9ee4e7; font-size: 10px; font-weight: 800; letter-spacing: .15em; text-transform: uppercase; }
.sl-sidebar-step-title { margin-top: 3px; color: #f8fcfd; font-size: 15px; font-weight: 760; line-height: 1.3; }
.sl-sidebar-step-copy { margin-top: 3px; color: #aacbd1; font-size: 12px; line-height: 1.45; }

/* Compact operational masthead */
.sl-page-header { grid-template-columns: minmax(0,1fr) 164px; min-height: 220px; gap: clamp(20px,3vw,38px); margin: 0 0 22px; padding: clamp(25px,3vw,34px); background: linear-gradient(112deg,rgba(8,31,48,.99),rgba(15,58,75,.96)),var(--sl-navy); border-color: #315c6e; border-radius: var(--sl-radius-large); box-shadow: 0 20px 42px rgba(8,29,45,.18); }
.sl-page-header::before { background-size: 28px 28px; opacity: .86; }
.sl-eyebrow { margin-bottom: 8px; color: #a9f0f2; font-size: 10px; letter-spacing: .16em; }
.sl-eyebrow::before { width: 22px; }
.sl-page-header h1 { max-width: 720px; font-size: clamp(32px,3.7vw,48px); }
.sl-page-header p { max-width: 680px; margin-top: 12px; color: #c8dde4; font-size: 15px; line-height: 1.62; }
.sl-badge-row { gap: 7px; margin-top: 17px; }
.sl-badge { min-height: 29px; padding: 5px 10px; font-size: 10px; }
.sl-badge::before { width: 6px; height: 6px; margin-inline-end: 7px; }
.sl-hero-visual { width: 154px; }
.sl-orbit-ring.one { inset: 3%; }
.sl-orbit-ring.two { inset: 20%; }
.sl-orbit-ring.three { inset: 36%; }
.sl-hero-mark-panel { width: 118px; height: 118px; padding: 14px; border-radius: 17px; box-shadow: 0 18px 34px rgba(0,0,0,.25), 0 0 0 8px rgba(128,239,241,.055); }

/* Linked input / result workspaces */
.sl-context-strip { grid-template-columns: repeat(5,minmax(0,1fr)); gap: 9px; margin-bottom: 20px; }
.sl-context-item { min-height: 96px; padding: 14px 15px; background: linear-gradient(145deg,#fff,#f3f8f9); border-color: #d7e4e9; border-radius: 13px; box-shadow: 0 7px 18px rgba(11,36,56,.055); }
.sl-context-item::after { width: 30px; height: 3px; inset-inline-start: 15px; background: linear-gradient(90deg,var(--sl-teal),var(--sl-cyan)); }
.sl-context-item span { color: #607988; font-size: 10px; letter-spacing: .075em; }
.sl-context-item strong { margin-top: 7px; color: #18384b; font-size: 13px; line-height: 1.3; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: #d8e4e8; border-radius: 17px; box-shadow: var(--sl-shadow-soft); }
.st-key-sl_source_inputs > [data-testid="stVerticalBlockBorderWrapper"], .st-key-sl_barrier_builder > [data-testid="stVerticalBlockBorderWrapper"], .st-key-sl_room_source > [data-testid="stVerticalBlockBorderWrapper"], .st-key-sl_wall_editor > [data-testid="stVerticalBlockBorderWrapper"] { background: linear-gradient(150deg,#fff,#f9fcfc); border-color: #cedfe5; }
.st-key-sl_source_inputs > [data-testid="stVerticalBlockBorderWrapper"]::before, .st-key-sl_barrier_builder > [data-testid="stVerticalBlockBorderWrapper"]::before, .st-key-sl_room_source > [data-testid="stVerticalBlockBorderWrapper"]::before, .st-key-sl_wall_editor > [data-testid="stVerticalBlockBorderWrapper"]::before { height: 5px; background: linear-gradient(90deg,#0a7784,#35c4c9 52%,#b7eef0); }
.sl-step-header { gap: 12px; margin-bottom: 16px; }
.sl-step-number { width: 34px; height: 34px; flex-basis: 34px; border-radius: 10px; font-size: 11px; }
.sl-step-copy h2 { color: #163b50; font-size: 18px; }
.sl-step-copy span { color: #607987; font-size: 13px; }

/* Calibrated control language */
[data-testid="stWidgetLabel"] p { color: #426071; font-size: 11px; font-weight: 760; letter-spacing: .035em; text-transform: uppercase; }
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="base-input"], textarea { min-height: 45px; background: #fbfdfd; border-color: #c6d7de; border-radius: 10px; }
div[data-baseweb="input"]:focus-within > div, div[data-baseweb="select"]:focus-within > div, div[data-baseweb="base-input"]:focus-within { border-color: #168b96; box-shadow: 0 0 0 3px rgba(22,139,150,.14); }
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button { min-height: 43px; border-radius: 10px; font-size: 13px; }
button[kind="primary"], .stDownloadButton > button[kind="primary"] { background: linear-gradient(110deg,#087784,#0b7180 58%,#145b81); border-color: #075967; }

/* Decision stack */
.sl-status-card { gap: 16px; margin: 12px 0 18px; padding: 21px 23px; border-inline-start-width: 8px; border-radius: 16px; box-shadow: 0 11px 28px rgba(11,36,56,.10); }
.sl-status-symbol { width: 40px; height: 40px; font-size: 18px; }
.sl-status-title { font-size: 20px; }
.sl-status-message { margin-top: 4px; font-size: 14px; }
.sl-status-meta { font-size: 12px; }
[data-testid="stMetric"] { min-height: 112px; padding: 16px; background: linear-gradient(145deg,#fff,#f4f8fa); border-color: #d4e1e6; border-radius: 14px; box-shadow: 0 7px 17px rgba(11,36,56,.06); }
[data-testid="stMetric"]::before { width: 34px; height: 3px; inset-inline-start: 16px; }
[data-testid="stMetricLabel"] p { font-size: 10px; }
[data-testid="stMetricValue"] { color: #173e51; font-size: clamp(23px,2vw,29px); }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 4px; padding: 4px; background: #e7eff2; border-color: #c7d6dc; border-radius: 12px; }
[data-testid="stTabs"] button[data-baseweb="tab"] { min-height: 41px; padding: 8px 13px; font-size: 13px; }
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] { background: #fff; border-color: #99b7c2; box-shadow: 0 5px 12px rgba(11,36,56,.10); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-color: #d1e0e5; border-radius: 13px; box-shadow: 0 6px 16px rgba(11,36,56,.045); }
[data-testid="stExpander"] { border-color: #d3e1e6; border-radius: 13px; }

/* Room design command center */
.st-key-sl_command_bar > [data-testid="stVerticalBlockBorderWrapper"] { padding: 8px 12px; background: linear-gradient(100deg,#0d2d42,#135068); border-color: #326b7e; box-shadow: 0 12px 28px rgba(8,29,45,.13); }
.st-key-sl_command_bar [data-testid="stWidgetLabel"] p { color: #b9dce1; }
.st-key-sl_command_bar div[data-baseweb="input"] > div, .st-key-sl_command_bar div[data-baseweb="select"] > div { background: rgba(255,255,255,.95); }
.st-key-sl_command_bar .stDownloadButton > button { color: #eaffff; background: transparent; border-color: #78b6c1; }
.st-key-sl_room_preview > [data-testid="stVerticalBlockBorderWrapper"] { background: linear-gradient(150deg,#fafdfe,#eaf4f6); border-color: #bcd2da; box-shadow: 0 15px 34px rgba(11,36,56,.09); }

.st-key-sl_decision_panel > [data-testid="stVerticalBlockBorderWrapper"] { position: relative; overflow: hidden; padding: 4px; background: linear-gradient(135deg,#fff,#f3f9fa); border-color: #bcd7df; box-shadow: 0 16px 34px rgba(11,36,56,.10); }
.st-key-sl_decision_panel > [data-testid="stVerticalBlockBorderWrapper"]::before { position: absolute; inset: 0 auto 0 0; width: 5px; background: linear-gradient(180deg,#32c5cb,#087a86 60%,#153f61); content: ""; }
.st-key-sl_decision_panel h2 { margin-top: .3rem; color: #163c50; font-size: 22px; }
.st-key-sl_result_tabs { margin-top: 1.1rem; }
.st-key-sl_wall_selector [data-testid="stRadio"] [role="radiogroup"] { gap: 8px; padding: 7px; background: #e9f1f3; border: 1px solid #c6d8df; border-radius: 14px; }
.st-key-sl_wall_selector [data-testid="stRadio"] label { min-height: 44px; background: #f9fcfc; border-color: #c7d9df; box-shadow: 0 3px 9px rgba(11,36,56,.04); }
.st-key-sl_wall_selector [data-testid="stRadio"] label:has(input:checked) { color: #075f6b; background: linear-gradient(145deg,#e8fbfb,#d0f0f1); border-color: #2197a0; box-shadow: 0 6px 14px rgba(8,122,134,.13); }

[data-testid="stSidebar"] .stButtonGroup [data-baseweb="button-group"] { background: rgba(8,31,45,.65); border-color: rgba(134,202,208,.34); box-shadow: inset 0 1px 0 rgba(219,255,255,.06); }
[data-testid="stSidebar"] .stButtonGroup button[aria-checked="true"] { background: linear-gradient(120deg,#0d8490,#17607c); }

.st-key-sl_export_identity > [data-testid="stVerticalBlockBorderWrapper"], .st-key-sl_export_delivery > [data-testid="stVerticalBlockBorderWrapper"] { padding: 8px; background: linear-gradient(145deg,#ffffff,#f5fafb); border-color: #cbdde3; box-shadow: 0 10px 24px rgba(11,36,56,.065); }
.st-key-sl_export_delivery > [data-testid="stVerticalBlockBorderWrapper"] { background: linear-gradient(145deg,#eefafa,#ffffff); border-color: #9ecbd1; }
.st-key-sl_export_identity h3, .st-key-sl_export_delivery h3 { color: #184256; font-size: 18px; }

@media (max-width: 1080px) { .sl-context-strip { grid-template-columns: repeat(3,minmax(0,1fr)); } .sl-page-header { grid-template-columns: minmax(0,1fr) 140px; } .sl-hero-visual { width: 134px; } .sl-hero-mark-panel { width: 103px; height: 103px; } }
@media (max-width: 720px) { [data-testid="stMainBlockContainer"], .block-container { padding-block-start: 1rem; } .sl-page-header { grid-template-columns: 1fr; padding: 25px 21px; } .sl-hero-visual { display: none; } .sl-context-strip { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 7px; } .sl-context-item { min-height: 84px; padding: 12px; } .sl-context-item strong { font-size: 12px; } [data-testid="stMetric"] { min-height: 96px; padding: 13px; } }
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
    """Render the product command-center header and its trust signals."""
    badge_html = "".join(f'<span class="sl-badge">{escape(badge)}</span>' for badge in badges)
    badge_row = f'<div class="sl-badge-row">{badge_html}</div>' if badge_html else ""
    st.markdown(
        f"""
        <header class="sl-page-header" id="shieldlab-main" tabindex="-1"
                {i18n.html_attributes()}>
          <div class="sl-hero-copy">
            <div class="sl-eyebrow">{escape(eyebrow)}</div>
            <h1>{escape(title)}</h1>
            <p>{escape(description)}</p>
            {badge_row}
          </div>
          <div class="sl-hero-visual" aria-hidden="true">
            <div class="sl-hero-mark-panel">{sl_mark_svg("sl-hero-mark", "ShieldLab")}</div>
          </div>
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
