"""tests/test_ui_theme.py — v6 light-theme palette verification."""

import re
from pathlib import Path

from modules.utils import ui_helpers


def test_light_theme_chart_grid_is_black_alpha():
    """Grid lines must use a black-alpha colour for contrast on white."""
    grid = ui_helpers.CHART_GRID
    assert grid.startswith("rgba(0,0,0,") or grid.startswith("rgba(0, 0, 0,"), (
        f"CHART_GRID should use black alpha on light theme, got {grid!r}"
    )


def test_light_theme_primary_colors():
    """Primary palette values must match the light-theme spec."""
    assert ui_helpers.COLOR_GAIN == "#0F9D58"
    assert ui_helpers.COLOR_LOSS == "#D93025"
    assert ui_helpers.COLOR_ACCENT == "#2563EB"


def test_severity_colors_deeper_for_light_bg():
    """Severity swatches are deeper than the legacy dark-theme palette."""
    assert ui_helpers.SEVERITY_COLORS["severe"] == "#C5221F"
    assert ui_helpers.SEVERITY_COLORS["moderate"] == "#E37400"


def test_no_white_alpha_colors_in_modules_source():
    """No user-facing module may reference rgba(255,255,255,*) — those were
    dark-theme artefacts incompatible with a white background."""
    modules_root = Path(__file__).resolve().parent.parent / "modules"
    pattern = re.compile(r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,")
    offenders: list[str] = []
    for path in modules_root.rglob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(modules_root)))
    assert not offenders, (
        "The following files still contain white-alpha rgba(255,255,255,*) — "
        "they must be migrated to light-theme black-alpha or #E5E7EB: "
        + ", ".join(offenders)
    )


def test_streamlit_config_is_light_theme():
    """.streamlit/config.toml must pin base = \"light\"."""
    cfg = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"
    content = cfg.read_text(encoding="utf-8")
    assert 'base = "light"' in content
    assert "#FFFFFF" in content
