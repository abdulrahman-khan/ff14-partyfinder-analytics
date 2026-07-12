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

# Semantic role palette (tank/healer/dps) - the FFXIV-intuitive blue/green/red,
# muted to sit on the dark theme. A documented exception to the blue/gold rule.
ROLE_COLORS = {"Tank": "#4FA3D1", "Healer": "#6FBF73", "DPS": "#D9645B"}

# Semantic outcome palette for the fill funnel.
OUTCOME_COLORS = {
    "Filled": "#6FBF73",          # good - reached full
    "Expired (partial)": "#D9645B",  # never filled
    "Flash": "#E5A73C",           # ambiguity band (single-snapshot)
    "Live": "#4FA3D1",            # unresolved at frontier
    "Multiparty": "#8A94A6",      # fill-untrackable
}

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
    """CSS polish on top of config.toml: modern Inter type, tabbed-nav styling,
    tightened metric cards with gold KPI values, and a clean sidebar. Called on
    every page right after st.set_page_config."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}

        /* Headings: tighter, calmer */
        h1, h2, h3 {{ letter-spacing: -0.01em; font-weight: 700; }}
        [data-testid="stCaptionContainer"] {{ color: {MUTED}; }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background: {PANEL};
            border: 1px solid {GRID};
            border-radius: 12px;
            padding: 14px 16px;
        }}
        [data-testid="stMetricValue"] {{ color: {GOLD}; font-weight: 700; }}
        [data-testid="stMetricLabel"] {{ color: {MUTED}; }}

        /* Tabbed navigation */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px;
            border-bottom: 1px solid {GRID};
        }}
        .stTabs [data-baseweb="tab"] {{
            padding: 10px 18px;
            color: {MUTED};
            font-weight: 600;
            background: transparent;
        }}
        .stTabs [data-baseweb="tab"]:hover {{ color: {TEXT}; }}
        .stTabs [aria-selected="true"] {{
            color: {GOLD} !important;
            border-bottom: 2px solid {GOLD};
        }}

        /* Sidebar */
        [data-testid="stSidebar"] {{ border-right: 1px solid {GRID}; }}
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2 {{ font-size: 1.05rem; }}

        a {{ color: {GOLD}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
