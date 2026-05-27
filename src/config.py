"""
Loads config.yaml from the repo root and exposes it as `cfg`.

Edit config.yaml (not this file) to tune geometry, SD settings, or DXF canvas size.
All src/ modules import constants from here instead of hardcoding them.

Usage:
    from src.config import cfg
    width = cfg["plate"]["width_mm"]
"""
import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg: dict = _load()
