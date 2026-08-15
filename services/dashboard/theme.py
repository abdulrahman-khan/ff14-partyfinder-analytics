"""Eorzean Night theme: palette, Altair styling, and CSS polish.

Professional analytics dashboard theme for FFXIV Party Finder data.
Dark mode optimized for data density and readability.
"""

import altair as alt
import streamlit as st

# ------------------------------------------------------------------ Palette
# Professional dark analytics palette - high contrast, accessible
BG_PRIMARY = "#0B0F14"       # page background
BG_SECONDARY = "#151B24"     # panels, sidebar, cards
BG_TERTIARY = "#1C2533"      # hover states, active elements
BORDER = "#2A3644"           # borders, gridlines
TEXT_PRIMARY = "#E8EDF4"     # headings, values
TEXT_SECONDARY = "#8B95A8"   # captions, axis labels, muted text
TEXT_MUTED = "#5C6678"       # placeholders, disabled

# Accent colors - gold for primary metrics, blue for secondary
ACCENT_GOLD = "#D4A843"      # KPI values, highlights, active states
ACCENT_BLUE = "#5BA4E6"      # categorical bars, secondary elements
ACCENT_GREEN = "#4ADE80"     # positive indicators, filled outcomes
ACCENT_RED = "#F87171"       # negative indicators, expired outcomes
ACCENT_PURPLE = "#A78BFA"    # tertiary accents

# Sequential scheme for intensity heatmaps - viridis is perceptually uniform
HEATMAP_SCHEME = "viridis"

# Semantic role palette
ROLE_COLORS = {"Tank": ACCENT_BLUE, "Healer": ACCENT_GREEN, "DPS": ACCENT_RED}

# Semantic outcome palette
OUTCOME_COLORS = {
    "Filled": ACCENT_GREEN,
    "Expired (partial)": ACCENT_RED,
    "Flash": ACCENT_GOLD,
    "Live": ACCENT_BLUE,
    "Multiparty": TEXT_SECONDARY,
}

# Current FFXIV savage tier
CURRENT_SAVAGE_TIER = {
    "label": "AAC Heavyweight (M9S-M12S)",
    "duties": [
        "AAC Heavyweight M1 (Savage)",
        "AAC Heavyweight M2 (Savage)",
        "AAC Heavyweight M3 (Savage)",
        "AAC Heavyweight M4 (Savage)",
    ],
}


# --------------------------------------------------------------- Chart styling


def style_chart(chart: alt.Chart) -> alt.Chart:
    """Apply dark theme to an Altair chart."""
    return (
        chart
        .configure_view(strokeWidth=0, fill="transparent")
        .configure(background="transparent")
        .configure_axis(
            labelColor=TEXT_SECONDARY,
            titleColor=TEXT_PRIMARY,
            gridColor=BORDER,
            domainColor=BORDER,
            tickColor=BORDER,
            labelFontSize=11,
            titleFontSize=12,
        )
        .configure_legend(
            labelColor=TEXT_PRIMARY,
            titleColor=TEXT_PRIMARY,
            labelFontSize=11,
            titleFontSize=12,
            symbolSize=80,
        )
        .configure_title(
            color=TEXT_PRIMARY,
            fontSize=14,
            font="Inter, -apple-system, sans-serif",
            anchor="middle",
        )
        .configure_mark(color=ACCENT_BLUE)
    )


def style_line_chart(chart: alt.Chart, color: str = ACCENT_BLUE) -> alt.Chart:
    """Style a line chart with specific color."""
    return style_chart(
        chart.mark_line(point=True, color=color, strokeWidth=2).encode(
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
            ]
        )
    )


# ------------------------------------------------------------------- CSS


def inject_css() -> None:
    """Inject professional dashboard CSS."""
    st.markdown(
        f"""
        <style>
        /* === Global typography === */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
        
        h1, h2, h3, h4 {{
            letter-spacing: -0.02em;
            font-weight: 700;
            color: {TEXT_PRIMARY};
        }}
        h1 {{ font-size: 1.8rem; }}
        h2 {{ font-size: 1.35rem; }}
        h3 {{ font-size: 1.15rem; }}
        
        /* === Captions === */
        [data-testid="stCaptionContainer"] {{
            color: {TEXT_SECONDARY};
            font-size: 0.85rem;
        }}
        
        /* === KPI Cards === */
        [data-testid="stMetric"] {{
            background: {BG_SECONDARY};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 16px 20px;
            transition: border-color 0.2s;
        }}
        [data-testid="stMetric"]:hover {{
            border-color: {ACCENT_GOLD};
        }}
        [data-testid="stMetricValue"] {{
            color: {ACCENT_GOLD};
            font-weight: 700;
            font-size: 1.5rem;
        }}
        [data-testid="stMetricLabel"] {{
            color: {TEXT_SECONDARY};
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
        }}
        
        /* === Tabbed Navigation === */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 2px;
            border-bottom: 2px solid {BORDER};
            padding-left: 0;
        }}
        .stTabs [data-baseweb="tab"] {{
            padding: 10px 20px;
            color: {TEXT_SECONDARY};
            font-weight: 500;
            font-size: 0.9rem;
            background: transparent;
            border-radius: 8px 8px 0 0;
            transition: all 0.2s;
            height: auto;
            white-space: nowrap;
        }}
        .stTabs [data-baseweb="tab"]:hover {{
            color: {TEXT_PRIMARY};
            background: {BG_TERTIARY};
        }}
        .stTabs [aria-selected="true"] {{
            color: {ACCENT_GOLD} !important;
            background: {BG_SECONDARY};
            border-bottom: 2px solid {ACCENT_GOLD};
            font-weight: 600;
        }}
        
        /* === Sidebar === */
        [data-testid="stSidebar"] {{
            border-right: 1px solid {BORDER};
            background: {BG_SECONDARY};
        }}
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {{
            font-size: 1rem;
            color: {TEXT_PRIMARY};
        }}
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stRadio,
        [data-testid="stSidebar"] .stSlider {{
            padding: 4px 0;
        }}
        [data-testid="stSidebar"] label {{
            color: {TEXT_SECONDARY};
            font-size: 0.85rem;
            font-weight: 500;
        }}
        
        /* === Dividers === */
        hr {{
            border: none;
            border-top: 1px solid {BORDER};
            margin: 1.5rem 0;
        }}
        
        /* === Info/Warning boxes === */
        .stAlert {{
            border-radius: 8px;
        }}
        
        /* === Selectbox / Dropdowns === */
        .stSelectbox > div {{
            border-color: {BORDER} !important;
            border-radius: 6px !important;
        }}
        .stSelectbox > div:hover {{
            border-color: {ACCENT_BLUE} !important;
        }}
        
        /* === Buttons === */
        .stButton > button {{
            border-radius: 6px;
            border: 1px solid {BORDER};
            background: {BG_TERTIARY};
            color: {TEXT_PRIMARY};
            font-weight: 500;
            padding: 8px 16px;
            transition: all 0.2s;
        }}
        .stButton > button:hover {{
            border-color: {ACCENT_BLUE};
            background: {BG_SECONDARY};
            color: {ACCENT_BLUE};
        }}
        
        /* === Links === */
        a {{ color: {ACCENT_BLUE}; }}
        
        /* === Scrollbar === */
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: {BG_PRIMARY}; }}
        ::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: {TEXT_SECONDARY}; }}
        
        /* === Remove top margin on first element in tab === */
        section[data-testid="stTab"] > div:first-child {{
            margin-top: 0.5rem !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
