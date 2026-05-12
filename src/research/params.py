"""
Shared loader for src/research/params.yaml.
All research modules import from here — never read the YAML directly.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from functools import lru_cache

import yaml

PARAMS_PATH = Path(__file__).parent / "params.yaml"


@lru_cache(maxsize=1)
def load_params() -> dict:
    """Parse and return the full params.yaml dict. Result is cached."""
    with open(PARAMS_PATH, "r") as f:
        return yaml.safe_load(f)


def reload_params() -> dict:
    """Force reload params.yaml (clears cache). Use when params change at runtime."""
    load_params.cache_clear()
    return load_params()


def get(section: str, key: str):
    """
    Convenience accessor. Returns the 'value' field from params[section][key].
    Raises KeyError with a clear message if the path doesn't exist.
    """
    p = load_params()
    try:
        entry = p[section][key]
    except KeyError:
        raise KeyError(f"params.yaml: no key '{section}.{key}'")
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry
