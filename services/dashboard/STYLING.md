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
| Background | `#0B0F14` | `BG_PRIMARY` | Page background (near-black slate). |
| Panel | `#151B24` | `BG_SECONDARY` | Sidebar, metric cards, panels. |
| Panel hover | `#1C2533` | `BG_TERTIARY` | Hover/active panel state. |
| Primary / gold | `#D4A843` | `ACCENT_GOLD` | KPI values, links, highlights, current-tier/selected-fight lines, active widgets. |
| Accent / blue | `#5BA4E6` | `ACCENT_BLUE` | Default categorical bars and lines. |
| Text | `#E8EDF4` | `TEXT_PRIMARY` | Body text, chart titles, headings. |
| Muted | `#8B95A8` | `TEXT_SECONDARY` | Captions, axis labels, metric labels. |
| Disabled | `#5C6678` | `TEXT_MUTED` | Placeholders, disabled text. |
| Grid / border | `#2A3644` | `BORDER` | Chart gridlines, axis domains, card borders. |
| Green accent | `#4ADE80` | `ACCENT_GREEN` | Positive indicators, filled outcomes, Healer role. |
| Red accent | `#F87171` | `ACCENT_RED` | Negative indicators, expired outcomes, DPS role. |
| Purple accent | `#A78BFA` | `ACCENT_PURPLE` | Tertiary accent (e.g. ilvl trend line, practice intent). |

These values are the source of truth (they're what actually renders); `theme.py` and `.streamlit/config.toml` must both match this table exactly.

The Streamlit chrome (background, primary, text, corner radius) is set in `.streamlit/config.toml`.
The finer polish (metric cards, gold KPI values, tab underline, link color) is injected via `theme.inject_css()`, which every page calls right after `st.set_page_config`.

## Charts (Altair)

Always wrap a chart in `theme.style_chart(chart)` before `st.altair_chart(...)`.
It applies a transparent background and muted axes/legend so charts sit cleanly on the dark page.

- Sequential intensity (heatmaps): use `theme.HEATMAP_SCHEME` (`viridis`). Viridis is perceptually uniform and colorblind-safe, which matters most where two heatmaps are read side by side (the main page's Post/Join prime-hours pair) - a shared, uniform ramp keeps that comparison legible. For a "lower is better" metric (e.g. time-to-fill, competing listings) reverse the scale (`alt.Scale(scheme=HEATMAP_SCHEME, reverse=True)`) so the good outcome reads hot.
- Categorical bars/lines: default to `BLUE`. Use `GOLD` to highlight a called-out subset (e.g. the selected fight among its category's popularity trend lines, or current-tier savage duties).
- Roles (tank / healer / DPS): use `theme.ROLE_COLORS` (blue / green / red) - a documented semantic exception to the blue/gold rule. Fill outcomes: use `theme.OUTCOME_COLORS`.
- Never use Altair/Vega default colors directly - they clash with the dark theme.
- Prefer `width="stretch"` on `st.altair_chart` (the replacement for the deprecated `use_container_width=True`).

## Layout conventions

- Wide layout (`layout="wide"`) on every page.
- **Two pages**, each with its own sidebar filter chain:
  - `streamlit_app.py` ("Raid Finder", the main/default page) - scopes everything to one fight: Region -> Datacenter -> Content (Savage/Ultimate) -> My Fight -> My Role. No tabs; the page is one scrolldown of sections (KPI header, Prime Hours, Roles, Popularity, ILvl Gating, Intent), each scoped to the sidebar's current selection.
  - `pages/2_All_Analytics.py` ("All Analytics") - general, non-fight-specific signals: Region -> Datacenter only, then `st.tabs` (Overview, Fill Outcomes, Travel, Tags), one analytical question each.
  - `pages/1_FAQ.py` - static, no filters.
- Filters are `st.selectbox`es driven off the actual mart data (not `reference/worlds.csv`) and default to **NA / Aether** via `data.DEFAULT_REGION` / `DEFAULT_DATACENTER`. Every interactive widget carries a unique `key=` (widgets can render more than once per run, so duplicate labels/keys collide) - and the same `key` (e.g. `flt_region`, `flt_dc`) is intentionally reused across both pages so the selection carries over when a viewer switches pages.
- KPIs use `st.metric` rows; values render gold via the injected CSS.
- Use `st.subheader` + a one-line `st.caption(...)` scope note at the top of each section; `st.divider()` between sections.
- Guard every chart against empty filtered frames with an `st.info(...)` fallback.
- Pattern marts (`mart_time_to_fill`, `mart_role_demand`, `mart_market_saturation`, `mart_activity_heatmap`) cover only a recent window - label them with their `window_start_date` / `window_end_date`.

## Files

- `.streamlit/config.toml` - Streamlit theme (background, primary, text, font, corner radius).
- `theme.py` - palette constants, `ROLE_COLORS`, `OUTCOME_COLORS`, `style_chart`, `inject_css` (Inter font + tab/sidebar CSS), `CURRENT_SAVAGE_TIER`.
- `data.py` - shared BigQuery loading, `WEEKDAY_ORDER`, filter defaults.
- `streamlit_app.py` - main page: one fight-scoped view, sidebar filters drive every section.
- `pages/2_All_Analytics.py` - general analytics: sidebar Region/DC filters + four tabs.
- `pages/1_FAQ.py` - static FAQ/About page.
