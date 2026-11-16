"""One colour system for every figure of the project.

Colours are assigned by the *job* they do, never at random:

* **identity** (categorical): fixed slots, always in the same order, so an entity keeps its colour
  in every notebook. The two hotels take slots 1-2; the third slot marks *our system* in
  comparisons; personas take the slots in a fixed order. The order comes from a palette validated
  for colour-vision deficiency (adjacent slots stay distinguishable).
* **magnitude** (sequential): one hue, light to dark. Blue for value / volume, orange for risk.
* **polarity** (diverging): blue <-> red around a neutral grey (e.g. deviation from a mean).
* **state** (status): reserved for decision outcomes and losses (accepted, rejected, walked), never
  reused for a series, and always labelled.

Reference points (baselines, oracle, "other") are drawn in neutral greys so the eye goes to the
coloured series.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from cycler import cycler
from matplotlib.colors import LinearSegmentedColormap

FIGURES = Path(__file__).resolve().parent.parent / "docs" / "figures"

# ---- categorical slots (fixed order) -------------------------------------------------------------
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
CATEGORICAL = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]

# ---- ink and chrome ------------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"          # secondary text
MUTED = "#898781"          # axis labels, reference series
LIGHT = "#c3c2b7"          # baselines, light reference series
GRID = "#e1e0d9"
NEUTRAL = "#f0efec"        # diverging midpoint

# ---- roles ---------------------------------------------------------------------------------------
HOTEL_COLORS = {"Downtown Hotel": BLUE, "Seaside Hotel": ORANGE}
OURS = AQUA                # our system in every comparison
REFERENCE = MUTED          # baselines
REFERENCE_LIGHT = LIGHT    # weaker baselines / "before"
ACCENT = OURS              # single-series highlight
GREY = MUTED

# Personas: fixed slot order, identical in both hotels and in every notebook.
PERSONA_COLORS = {
    "Online leisure couples": BLUE, "Families": ORANGE, "Tour-operator holidays": AQUA,
    "Contracts / allotments": YELLOW, "Last-minute direct guests": MAGENTA,
    "Business / corporate": VIOLET, "Groups and agency blocks": RED,
}

# Status: decision outcomes (always shown with a label, never colour alone).
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
OUTCOME_COLORS = {"accepted": GOOD, "price": SERIOUS, "full": CRITICAL, "capacity": WARNING, "invalid": LIGHT}
OUTCOME_LABELS = {"accepted": "accepted", "price": "rejected: rate below bid price",
                  "full": "rejected: nights already full", "capacity": "rejected: would exceed capacity",
                  "invalid": "rejected: zero rate"}

# ---- continuous scales ---------------------------------------------------------------------------
BLUES = LinearSegmentedColormap.from_list(
    "project_blues", ["#f3f7fd", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"])
ORANGES = LinearSegmentedColormap.from_list(
    "project_oranges", ["#fdf6f2", "#f8d3c1", "#f2a27f", "#eb6834", "#c24e1f", "#8f3715"])
DIVERGING = LinearSegmentedColormap.from_list(
    "project_diverging", ["#104281", "#3987e5", "#9ec5f4", NEUTRAL, "#f2a9a8", "#e34948", "#9e2323"])

PCT = mtick.PercentFormatter(1)


def setup() -> None:
    """Apply the project style to matplotlib."""
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
        "figure.facecolor": "white", "axes.facecolor": SURFACE, "savefig.facecolor": "white",
        "axes.prop_cycle": cycler(color=CATEGORICAL),
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": LIGHT, "axes.linewidth": .8,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": .6, "axes.axisbelow": True,
        "axes.titleweight": "bold", "axes.titlesize": 11, "axes.titlecolor": INK, "axes.titlelocation": "left",
        "axes.labelsize": 9, "axes.labelcolor": INK_2,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "xtick.color": INK_2, "ytick.color": INK_2,
        "text.color": INK, "legend.fontsize": 8, "legend.frameon": False,
        "lines.linewidth": 2, "lines.markersize": 5, "patch.linewidth": 0,
        "image.cmap": "project_blues",
        "font.family": "DejaVu Sans",
    })
    for cmap in (BLUES, ORANGES, DIVERGING):
        try:
            plt.colormaps.register(cmap)
        except ValueError:          # already registered in this session
            pass


def save(fig, name: str) -> None:
    """Save a figure used by the README / docs (docs/figures/<name>.png)."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png")
