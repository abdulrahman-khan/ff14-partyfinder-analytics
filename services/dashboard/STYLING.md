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

- Sequential intensity (heatmaps): use `theme.HEATMAP_SCHEME` (`inferno`). `magma` is an acceptable alternative in the same family. For a "lower is better" metric (e.g. time-to-fill) reverse the scale (`alt.Scale(scheme=HEATMAP_SCHEME, reverse=True)`) so short waits read as hot.
- Categorical bars: default to `BLUE`. Use `GOLD` to highlight a called-out subset (e.g. current-tier savage duties).
- Roles (tank / healer / DPS): use `theme.ROLE_COLORS` (blue / green / red) - a documented semantic exception to the blue/gold rule. Fill outcomes: use `theme.OUTCOME_COLORS`.
- Never use Altair/Vega default colors directly - they clash with the dark theme.
- Prefer `width="stretch"` on `st.altair_chart` (the replacement for the deprecated `use_container_width=True`).

## Layout conventions

- Wide layout (`layout="wide"`) on every page.
- **Sidebar = global filters only**, in a fixed order: brand -> Region -> Data center -> trend date-range -> freshness/FAQ note. Filters are `st.selectbox`es driven off the actual mart data (not `reference/worlds.csv`) and default to **NA / Aether** via `data.DEFAULT_REGION` / `DEFAULT_DATACENTER`. Every interactive widget carries a unique `key=` (tabs render all widgets each run, so duplicate labels collide).
- **Main page = tabs** (`st.tabs`), one analytical question each: Overview -> When to Post -> Duty Trends -> Roles -> Fill Outcomes. Tabs are styled via `inject_css` (gold active underline).
- KPIs use `st.metric` rows; values render gold via the injected CSS.
- Use `st.subheader` + a one-line `st.caption(...)` scope note at the top of each tab section; `st.divider()` between sub-sections within a tab.
- Guard every chart against empty filtered frames with an `st.info(...)` fallback.
- Pattern marts (`mart_time_to_fill`, `mart_role_demand`, `mart_activity_heatmap`) cover only a recent window - label them with their `window_start_date` / `window_end_date`.

## Files

- `.streamlit/config.toml` - Streamlit theme (background, primary, text, font).
- `theme.py` - palette constants, `ROLE_COLORS`, `OUTCOME_COLORS`, `style_chart`, `inject_css` (Inter font + tab/sidebar CSS), `CURRENT_SAVAGE_TIER`.
- `data.py` - shared BigQuery loading, `WEEKDAY_ORDER`, filter defaults.
- `streamlit_app.py` - main page: sidebar filters + five tabs, one render function per tab.
