# Dashboard Styling Reference - Eorzean Night

Read this file before restyling the dashboard.
It is the single source of truth for the dashboard's look, and it must stay in sync with `theme.py` and `.streamlit/config.toml`.
When you change a color or convention, update all three.

## Theme name

Eorzean Night - a dark slate UI with FFXIV-inspired gold and aether-blue accents.
The mood is a premium, on-theme analytics console: near-black background, warm gold highlights, cool blue data.

## Palette

| Role | Hex | Constant (`theme.py`) | Used for |
| --- | --- | --- | --- |
| Background | `#0E1117` | `BACKGROUND` | Page background (near-black slate). |
| Panel | `#1B2430` | `PANEL` | Sidebar, metric cards, panels. |
| Primary / gold | `#E5A73C` | `GOLD` | KPI values, links, highlights, current-tier bars, active widgets. |
| Accent / blue | `#4FA3D1` | `BLUE` | Default categorical bars. |
| Text | `#E6E6E6` | `TEXT` | Body text, chart titles. |
| Muted | `#8A94A6` | `MUTED` | Captions, axis labels, metric labels. |
| Grid | `#2A3644` | `GRID` | Chart gridlines, axis domains, card borders. |

The Streamlit chrome (background, primary, text) is set in `.streamlit/config.toml`.
The finer polish (metric cards, gold KPI values, link color) is injected via `theme.inject_css()`, which every page calls right after `st.set_page_config`.

## Charts (Altair)

Always wrap a chart in `theme.style_chart(chart)` before `st.altair_chart(...)`.
It applies a transparent background and muted axes/legend so charts sit cleanly on the dark page.

- Sequential intensity (heatmaps): use `theme.HEATMAP_SCHEME` (`inferno`). `magma` is an acceptable alternative in the same family.
- Categorical bars: default to `BLUE`. Use `GOLD` to highlight a called-out subset (e.g. current-tier savage duties).
- Never use Altair/Vega default colors directly - they clash with the dark theme.

## Layout conventions

- Wide layout (`layout="wide"`) on every page.
- Order on the main page: title + intro -> filter row -> KPI row -> heatmap -> paired charts.
- Filters are `st.selectbox`es driven off the actual mart data (not `reference/worlds.csv`), and default to **NA / Aether** via `data.DEFAULT_REGION` / `DEFAULT_DATACENTER`.
- KPIs use `st.metric` in a 4-column row; values render gold via the injected CSS.
- Use `st.divider()` between major sections and `st.caption(...)` for scope notes under each chart.
- Guard every chart against empty filtered frames with an `st.info(...)` fallback.

## Files

- `.streamlit/config.toml` - Streamlit theme (background, primary, text, font).
- `theme.py` - palette constants, `style_chart`, `inject_css`, `CURRENT_SAVAGE_TIER`.
- `data.py` - shared BigQuery loading, `WEEKDAY_ORDER`, filter defaults.
