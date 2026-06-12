"""
data_loader.py
==============
Loads the JSON datasets in radshield/data/ and caches them. Every other module
gets its numbers from here, so there is ONE place that reads the data files.

Why a loader (and not just `import json` everywhere):
    * one cached read per file (fast),
    * a single helper to resolve a reference key -> full citation, used by the
      UI and the report so every number can show where it came from,
    * a clear error if a data file is missing or malformed.

All datasets are plain JSON and meant to be edited by the user; nothing here
hard-codes physics values.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

# Directory that holds the JSON datasets (sits next to this file).
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@lru_cache(maxsize=None)
def load(name: str) -> Dict[str, Any]:
    """Load one dataset by file stem, e.g. load('materials').

    The result is cached, so repeated calls are cheap. Raises a clear error if
    the file is missing or not valid JSON.
    """
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset '{name}.json' not found in {DATA_DIR}. "
            f"Available: {', '.join(sorted(list_datasets()))}"
        )
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Dataset '{name}.json' is not valid JSON: {exc}") from exc


def list_datasets() -> list[str]:
    """Return the available dataset names (file stems)."""
    return [
        os.path.splitext(f)[0]
        for f in os.listdir(DATA_DIR)
        if f.lower().endswith(".json")
    ]


# --- convenience accessors (named, so callers read clearly) -----------------

def materials() -> Dict[str, Any]:
    return load("materials")


def archer_diagnostic() -> Dict[str, Any]:
    return load("archer_diagnostic")


def tvl_megavoltage() -> Dict[str, Any]:
    return load("tvl_megavoltage")


def radionuclides() -> Dict[str, Any]:
    return load("radionuclides")


def scatter() -> Dict[str, Any]:
    return load("scatter")


def workloads() -> Dict[str, Any]:
    return load("workloads")


def limits() -> Dict[str, Any]:
    return load("limits")


def references() -> Dict[str, Any]:
    return load("references")


# --- reference resolution ----------------------------------------------------

def citation(ref_key: str) -> str:
    """Return the full citation string for a reference key (e.g. 'NCRP147').

    Used by the UI/report so every displayed number can be traced to a source.
    Unknown keys are returned as-is (so a typo is visible rather than hidden).
    """
    refs = references()
    entry = refs.get(ref_key)
    if isinstance(entry, dict):
        return entry.get("citation", ref_key)
    return ref_key


def citations(ref_keys) -> list[str]:
    """Resolve a single key or a list of keys to a list of citation strings."""
    if isinstance(ref_keys, str):
        ref_keys = [ref_keys]
    return [citation(k) for k in (ref_keys or [])]
