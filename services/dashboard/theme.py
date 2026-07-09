"""Eorzean Night theme: palette, Altair styling, and CSS polish.

See STYLING.md for the canonical palette and the rules for when to use each
color. Keep this module and STYLING.md in sync.
"""

import altair as alt
import streamlit as st

# Eorzean Night palette
BACKGROUND = "#0E1117"   # page background (near-black slate)
PANEL = "#1B2430"        # panels, sidebar, metric cards
GOLD = "#E5A73C"         # primary accent - KPI values, highlights, links
BLUE = "#4FA3D1"         # secondary accent - categorical bars
TEXT = "#E6E6E6"
MUTED = "#8A94A6"        # captions, axis labels, gridlines
GRID = "#2A3644"

# Sequential scheme for intensity heatmaps.
HEATMAP_SCHEME = "inferno"

# Current FFXIV savage tier (patch 7.4, Arcadion). The duty strings must match
# the `duty` values scraped from xivpf.com; verify against the live data before
# relying on them for filtering. If they don't match, the tier is used as a
# text label only.
CURRENT_SAVAGE_TIER = {
    "label": "AAC Heavyweight (M9S-M12S)",
    "duties": [
        "AAC Heavyweight M1 (Savage)",
        "AAC Heavyweight M2 (Savage)",
        "AAC Heavyweight M3 (Savage)",
        "AAC Heavyweight M4 (Savage)",
    ],
}


def style_chart(chart: alt.Chart) -> alt.Chart:
    """Apply the dark theme to an Altair chart: transparent background, muted
    axes/legend, readable text."""
    return (
        chart.configure_view(strokeWidth=0, fill="transparent")
        .configure(background="transparent")
        .configure_axis(
            labelColor=MUTED,
            titleColor=TEXT,
            gridColor=GRID,
            domainColor=GRID,
            tickColor=GRID,
        )
        .configure_legend(labelColor=TEXT, titleColor=TEXT)
    )


def inject_css() -> None:
    """Small CSS polish on top of config.toml: tighten metric cards and paint
    KPI values gold."""
    st.markdown(
        f"""
        <style>
        [data-testid="stMetric"] {{
            background: {PANEL};
            border: 1px solid {GRID};
            border-radius: 10px;
            padding: 14px 16px;
        }}
        [data-testid="stMetricValue"] {{
            color: {GOLD};
            font-weight: 700;
        }}
        [data-testid="stMetricLabel"] {{
            color: {MUTED};
        }}
        a {{ color: {GOLD}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
