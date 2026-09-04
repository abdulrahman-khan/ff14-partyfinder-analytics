"""Raider-focused Party Finder analytics for one Savage or Ultimate fight at a time.

Sidebar picks Region -> Datacenter -> My Fight -> My Role, and everything on the page
scopes to that selection: prime hours to post vs. to find an open party, the role
bottleneck, popularity across the patch, gear-gate trend, and prog/farm intent split.

General, non-fight-specific analytics (Overview, Fill Outcomes, Travel, Tags) live on
the "All Analytics" page instead - this page is deliberately narrow. Data is loaded
once per cold start (see data.py) and shaped in pandas; there are no per-interaction
BigQuery queries. Styling lives in theme.py and is documented in STYLING.md.
"""

from concurrent.futures import ThreadPoolExecutor

import altair as alt
import pandas as pd
import streamlit as st
from data import DEFAULT_DATACENTER, DEFAULT_REGION, WEEKDAY_ORDER, load
from theme import (
    ACCENT_BLUE as BLUE,
)
from theme import (
    ACCENT_GOLD as GOLD,
)
from theme import (
    ACCENT_GREEN,
    ACCENT_PURPLE,
    CURRENT_SAVAGE_TIER,
    HEATMAP_SCHEME,
    ROLE_COLORS,
    inject_css,
    style_chart,
)

st.set_page_config(page_title="FFXIV Raid Finder", page_icon="⚔️", layout="wide")
inject_css()

RAID_CATEGORIES = ["savage", "ultimate"]
RAID_FILTER = "content_category IN ({})".format(", ".join(f"'{c}'" for c in RAID_CATEGORIES))
MIN_SAMPLE = 3  # a weekday x hour (or intent) bucket needs this many sessions to be "advisable"

# Filter to Savage/Ultimate in SQL (not pandas) so BigQuery never sends the rows this
# page doesn't use, and run the 7 queries concurrently instead of one after another -
# both matter more since these marts are duty-grained now (far more rows than before).
MART_NAMES = [
    "mart_time_to_fill",
    "mart_market_saturation",
    "mart_role_demand",
    "mart_role_trends",
    "mart_duty_trends",
    "mart_ilvl_gating",
    "mart_listing_intent",
]


def _load_raid(name: str) -> pd.DataFrame:
    return load(name, where=RAID_FILTER)


with ThreadPoolExecutor(max_workers=len(MART_NAMES)) as pool:
    marts = dict(zip(MART_NAMES, pool.map(_load_raid, MART_NAMES), strict=True))

time_to_fill = marts["mart_time_to_fill"]
saturation = marts["mart_market_saturation"]
role_demand = marts["mart_role_demand"]
role_trends = marts["mart_role_trends"]
duty_trends = marts["mart_duty_trends"]
ilvl_gating = marts["mart_ilvl_gating"]
intent = marts["mart_listing_intent"]

for _df in (duty_trends, role_trends, ilvl_gating, intent):
    _df["reset_week"] = pd.to_datetime(_df["reset_week"])


def _pick(options: list, preferred: str) -> int:
    """Index of the preferred option, or 0 if it isn't present."""
    return options.index(preferred) if preferred in options else 0


def _window_caption(df: pd.DataFrame) -> str:
    """Label for pattern-family marts, which cover only the last few reset weeks."""
    if df.empty or "window_start_date" not in df:
        return ""
    ws = pd.to_datetime(df["window_start_date"].iloc[0])
    we = pd.to_datetime(df["window_end_date"].iloc[0])
    return f"Recent window: {ws:%b %d} - {we:%b %d}."


def _role_share_long(df: pd.DataFrame) -> pd.DataFrame:
    """Melt the three open-slot share columns into a tidy role/share frame."""
    long = df.melt(
        id_vars=[c for c in ("post_hour", "reset_week") if c in df.columns],
        value_vars=["open_tank_share_pct", "open_healer_share_pct", "open_dps_share_pct"],
        var_name="role",
        value_name="share_pct",
    )
    long["role"] = long["role"].map(
        {
            "open_tank_share_pct": "Tank",
            "open_healer_share_pct": "Healer",
            "open_dps_share_pct": "DPS",
        }
    )
    return long


def _default_fight(cat_df: pd.DataFrame, category: str) -> str | None:
    """Most-listed duty in the window; for savage, prefer the current tier if present.

    Ultimate never rotates (all 7 stay permanently relevant), so it gets no curated
    list - just the most-listed one. Savage rotates every tier and has no
    release-date field anywhere in the schema, so "current tier" can't be derived
    and needs the maintained CURRENT_SAVAGE_TIER list instead.
    """
    if cat_df.empty:
        return None
    pool = cat_df
    if category == "savage":
        current = cat_df[cat_df["duty"].isin(CURRENT_SAVAGE_TIER["duties"])]
        if not current.empty:
            pool = current
    return pool.groupby("duty")["sessions"].sum().idxmax()


# --------------------------------------------------------------------------- Sidebar

st.title("⚔️ FFXIV Raid Finder")
st.caption(
    "Prime hours, role bottlenecks, popularity, and gear-gate trends for the "
    "Savage/Ultimate fight you're progging."
)

with st.sidebar:
    st.markdown("### ⚔️ Raid Finder")
    st.caption("Pick your fight - everything below scopes to it.")
    st.divider()

    regions = sorted(time_to_fill["pf_region"].dropna().unique().tolist())
    region = st.selectbox("Region", regions, index=_pick(regions, DEFAULT_REGION), key="flt_region")
    datacenters = sorted(
        time_to_fill.loc[time_to_fill["pf_region"] == region, "pf_datacenter"]
        .dropna()
        .unique()
        .tolist()
    )
    datacenter = st.selectbox(
        "Data center", datacenters, index=_pick(datacenters, DEFAULT_DATACENTER), key="flt_dc"
    )
    dc_ttf = time_to_fill[
        (time_to_fill["pf_region"] == region) & (time_to_fill["pf_datacenter"] == datacenter)
    ]

    st.divider()
    category_label = st.selectbox(
        "Content", [c.capitalize() for c in RAID_CATEGORIES], key="flt_category"
    )
    category = category_label.lower()
    cat_ttf = dc_ttf[dc_ttf["content_category"] == category]
    duty_opts = sorted(cat_ttf["duty"].dropna().unique().tolist())
    default_fight = _default_fight(cat_ttf, category)
    if duty_opts:
        fight = st.selectbox(
            "My Fight",
            duty_opts,
            index=_pick(duty_opts, default_fight) if default_fight else 0,
            key="flt_fight",
        )
    else:
        fight = None
        st.info("No data for this content type on this data center yet.")

    st.divider()
    role = st.selectbox("My Role", ["Any", "Tank", "Healer", "DPS"], key="flt_role")

    st.divider()
    st.caption("Data is refreshed periodically, not live. See the **FAQ** page for methodology.")
    st.caption("General, non-fight-specific analytics live on the **All Analytics** page.")

if fight is None:
    st.stop()


def scope(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["pf_region"] == region) & (df["pf_datacenter"] == datacenter) & (df["duty"] == fight)
    ]


ttf = scope(time_to_fill)
sat = scope(saturation)
rd = scope(role_demand)
rt = scope(role_trends).sort_values("reset_week")
trend = scope(duty_trends).sort_values("reset_week")
ilv = scope(ilvl_gating).sort_values("reset_week")
itt = scope(intent).sort_values("reset_week")

st.header(fight)
st.caption(f"{category_label} · {datacenter} ({region})")

# --------------------------------------------------------------------------- KPI header

resolved = int(ttf["sessions_resolved"].sum())
filled = int(ttf["sessions_filled"].sum())
fill_pct = filled / resolved * 100 if resolved else 0.0
ttf_weight = (ttf["avg_time_to_fill_min"].fillna(0) * ttf["sessions_filled"]).sum()
avg_ttf = ttf_weight / filled if filled else None
avg_conc = sat["avg_concurrent"].mean() if not sat.empty else None
total_listings = int(trend["listings"].sum()) if not trend.empty else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total listings (all-time)", f"{total_listings:,}")
k2.metric("Fill rate (recent)", f"{fill_pct:.0f}%")
k3.metric("Avg time to fill", "-" if avg_ttf is None else f"{avg_ttf:.0f} min")
k4.metric("Avg competing listings", "-" if avg_conc is None else f"{avg_conc:.1f}")

st.divider()

# --------------------------------------------------------------------------- Prime Hours

st.subheader("Prime hours")
st.caption(
    "Post: when to list your own party to fill fastest. "
    "Join: when the most open parties are competing for the same slot pool, so fewer "
    f"competing listings means better odds of finding one to join. {_window_caption(ttf)}"
)

left, right = st.columns(2)
with left:
    st.markdown("**Post now**")
    if ttf.empty:
        st.info("No time-to-fill data for this fight yet.")
    else:
        chart = (
            alt.Chart(ttf)
            .mark_rect()
            .encode(
                x=alt.X("post_hour:O", title="Hour of day (UTC)"),
                y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
                color=alt.Color(
                    "fill_rate_pct:Q", title="Fill %", scale=alt.Scale(scheme=HEATMAP_SCHEME)
                ),
                tooltip=[
                    alt.Tooltip("day_name:N", title="Day"),
                    alt.Tooltip("post_hour:O", title="Hour"),
                    alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".0f"),
                    alt.Tooltip("sessions:Q", title="Listings", format=","),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(style_chart(chart), width="stretch")
        advisable = ttf[ttf["sessions_filled"] >= MIN_SAMPLE]
        if not advisable.empty:
            best = advisable.loc[advisable["fill_rate_pct"].idxmax()]
            st.caption(
                f"Best: {best['day_name'][:3]} {int(best['post_hour']):02d}:00 UTC - "
                f"{best['fill_rate_pct']:.0f}% fill rate"
            )

with right:
    st.markdown("**Find an open party**")
    if sat.empty:
        st.info("No saturation data for this fight yet.")
    else:
        chart = (
            alt.Chart(sat)
            .mark_rect()
            .encode(
                x=alt.X("post_hour:O", title="Hour of day (UTC)"),
                y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
                color=alt.Color(
                    "avg_concurrent:Q",
                    title="Competing",
                    scale=alt.Scale(scheme=HEATMAP_SCHEME, reverse=True),
                ),
                tooltip=[
                    alt.Tooltip("day_name:N", title="Day"),
                    alt.Tooltip("post_hour:O", title="Hour"),
                    alt.Tooltip("avg_concurrent:Q", title="Avg competing", format=".1f"),
                    alt.Tooltip("zero_competition:Q", title="Zero-comp %", format=".0f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(style_chart(chart), width="stretch")
        advisable_sat = sat[sat["sessions"] >= MIN_SAMPLE]
        if not advisable_sat.empty:
            best_sat = advisable_sat.loc[advisable_sat["avg_concurrent"].idxmin()]
            st.caption(
                f"Best: {best_sat['day_name'][:3]} {int(best_sat['post_hour']):02d}:00 UTC - "
                f"{best_sat['avg_concurrent']:.1f} avg competing listings"
            )

st.divider()

# --------------------------------------------------------------------------- Roles

st.subheader("Which role is the bottleneck?")
st.caption(
    "Open-slot share is unmet role demand: the role with the largest share is hardest "
    "to recruit for this fight. Roles, not jobs (the source only exposes tank / healer / DPS)."
)

if rd.empty:
    st.info("No role data for this fight yet.")
else:
    pooled = {
        "Tank": rd["avg_open_tank"].mul(rd["sessions"]).sum(),
        "Healer": rd["avg_open_healer"].mul(rd["sessions"]).sum(),
        "DPS": rd["avg_open_dps"].mul(rd["sessions"]).sum(),
    }
    total_open = sum(pooled.values()) or 1
    bottleneck_role = max(pooled, key=pooled.get)
    bottleneck_pct = pooled[bottleneck_role] / total_open * 100
    st.info(f"**{bottleneck_role}** is the bottleneck for **{bottleneck_pct:.0f}%** of open slots.")
    if role != "Any":
        my_pct = pooled[role] / total_open * 100
        st.caption(
            f"As a **{role}**, that's {my_pct:.0f}% of the open-slot pool you're competing for."
        )

    k1, k2, k3 = st.columns(3)
    for col, r in zip((k1, k2, k3), ("Tank", "Healer", "DPS"), strict=True):
        col.metric(f"{r} open share", f"{pooled[r] / total_open * 100:.0f}%")

    st.markdown(f"**By hour of day** {_window_caption(rd)}")
    hourly = _role_share_long(rd.sort_values("post_hour"))
    if hourly["share_pct"].dropna().empty:
        st.info("No open-slot data for this fight.")
    else:
        chart = (
            alt.Chart(hourly)
            .mark_line(point=True)
            .encode(
                x=alt.X("post_hour:O", title="Hour of day (UTC)"),
                y=alt.Y("share_pct:Q", title="Open-slot share (%)"),
                color=alt.Color(
                    "role:N",
                    title="Role",
                    scale=alt.Scale(domain=list(ROLE_COLORS), range=list(ROLE_COLORS.values())),
                ),
                tooltip=[
                    alt.Tooltip("post_hour:O", title="Hour"),
                    alt.Tooltip("role:N", title="Role"),
                    alt.Tooltip("share_pct:Q", title="Share", format=".1f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(style_chart(chart), width="stretch")

    if not rt.empty:
        st.markdown("**Over patch history**")
        weekly = _role_share_long(rt)
        if not weekly["share_pct"].dropna().empty:
            chart = (
                alt.Chart(weekly)
                .mark_line(point=True)
                .encode(
                    x=alt.X("reset_week:T", title="Reset week"),
                    y=alt.Y("share_pct:Q", title="Open-slot share (%)"),
                    color=alt.Color(
                        "role:N",
                        title="Role",
                        scale=alt.Scale(domain=list(ROLE_COLORS), range=list(ROLE_COLORS.values())),
                    ),
                    tooltip=[
                        alt.Tooltip("reset_week:T", title="Week"),
                        alt.Tooltip("role:N", title="Role"),
                        alt.Tooltip("share_pct:Q", title="Share", format=".1f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(style_chart(chart), width="stretch")

st.divider()

# --------------------------------------------------------------------------- Popularity

st.subheader(f"How popular is {category_label.lower()} content on {datacenter}?")
cat_trend = duty_trends[
    (duty_trends["pf_region"] == region)
    & (duty_trends["pf_datacenter"] == datacenter)
    & (duty_trends["content_category"] == category)
]
weeks = sorted(cat_trend["reset_week"].dropna().unique())
has_range = len(weeks) >= 2

if not has_range:
    st.info("Not enough weekly history for this data center yet.")
else:
    week_dates = [pd.Timestamp(w) for w in weeks]
    default_start = week_dates[-8] if len(week_dates) > 8 else week_dates[0]
    start, end = st.select_slider(
        "Reset-week range",
        options=week_dates,
        value=(default_start, week_dates[-1]),
        format_func=lambda d: d.strftime("%b %d, %Y"),
        key="flt_weeks",
    )
    cat_range = cat_trend[(cat_trend["reset_week"] >= start) & (cat_trend["reset_week"] <= end)]
    trend_range = trend[(trend["reset_week"] >= start) & (trend["reset_week"] <= end)]

    if cat_range.empty:
        st.info("No listings in the selected range.")
    else:
        cat_range = cat_range.copy()
        cat_range["is_selected"] = cat_range["duty"] == fight
        chart = (
            alt.Chart(cat_range)
            .mark_line()
            .encode(
                x=alt.X("reset_week:T", title="Reset week"),
                y=alt.Y("listings:Q", title="Listings"),
                detail="duty:N",
                color=alt.condition("datum.is_selected", alt.value(GOLD), alt.value(BLUE)),
                size=alt.condition("datum.is_selected", alt.value(3), alt.value(1)),
                opacity=alt.condition("datum.is_selected", alt.value(1.0), alt.value(0.35)),
                tooltip=[
                    alt.Tooltip("duty:N", title="Duty"),
                    alt.Tooltip("reset_week:T", title="Week"),
                    alt.Tooltip("listings:Q", title="Listings", format=","),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(style_chart(chart), width="stretch")
        st.caption(
            f"Gold = {fight} (your fight). "
            f"Blue = other {category_label.lower()} fights on {datacenter}."
        )

    if trend_range.empty:
        st.info("No history for this fight in the selected range.")
    else:
        d1, d2 = st.columns(2)
        with d1:
            chart = (
                alt.Chart(trend_range)
                .mark_line(point=True, color=BLUE)
                .encode(
                    x=alt.X("reset_week:T", title="Reset week"),
                    y=alt.Y("median_time_to_fill_min:Q", title="Median time to fill (min)"),
                    tooltip=[
                        alt.Tooltip("reset_week:T", title="Week"),
                        alt.Tooltip("median_time_to_fill_min:Q", title="Median min", format=".0f"),
                        alt.Tooltip("p90_time_to_fill_min:Q", title="p90 min", format=".0f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(style_chart(chart), width="stretch")
        with d2:
            fill_series = trend_range[trend_range["fill_rate_pct"].notna()]
            if fill_series.empty:
                st.info("No resolved sessions for this fight in range.")
            else:
                chart = (
                    alt.Chart(fill_series)
                    .mark_line(point=True, color=GOLD)
                    .encode(
                        x=alt.X("reset_week:T", title="Reset week"),
                        y=alt.Y(
                            "fill_rate_pct:Q",
                            title="Fill rate (%)",
                            scale=alt.Scale(domain=[0, 100]),
                        ),
                        tooltip=[
                            alt.Tooltip("reset_week:T", title="Week"),
                            alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                        ],
                    )
                    .properties(height=260)
                )
                st.altair_chart(style_chart(chart), width="stretch")

st.divider()

# --------------------------------------------------------------------------- ILvl Gating

st.subheader("Gear-gate trend")
st.caption("Minimum item-level requirement over time, alongside fill rate for the same weeks.")
if ilv.empty:
    st.info("No ilvl gating data for this fight yet.")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg min ilvl", f"{ilv['avg_ilvl'].mean():.0f}")
    c2.metric("Avg fill rate", f"{ilv['fill_rate_pct'].mean():.0f}%")
    c3.metric("Avg median TTF", f"{ilv['median_time_to_fill_min'].mean():.0f} min")

    ilvl_line = (
        alt.Chart(ilv)
        .mark_line(point=True, color=ACCENT_PURPLE)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("avg_ilvl:Q", title="Avg min ilvl"),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("avg_ilvl:Q", title="Avg min ilvl", format=".0f"),
                alt.Tooltip("sessions:Q", title="Sessions", format=","),
            ],
        )
    )
    fill_line = (
        alt.Chart(ilv)
        .mark_line(point=True, color=ACCENT_GREEN)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
            ],
        )
    )
    st.altair_chart(style_chart(ilvl_line + fill_line), width="stretch")
    st.caption("Purple = avg min ilvl. Green = fill rate, same weeks.")

st.divider()

# --------------------------------------------------------------------------- Intent

st.subheader("Who's this fight for right now?")
st.caption("Splits listings into practice, reclear-farm, and blind-prog buckets.")
if itt.empty:
    st.info("No intent data for this fight yet.")
else:
    total = int(itt["sessions"].sum())
    practice = int(itt["practice"].sum())
    reclear = int(itt["reclear_farm"].sum())
    blind = int(itt["blind_prog"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Practice", f"{practice:,}", f"{practice / total * 100:.0f}%" if total else "-")
    c2.metric("Reclear-farm", f"{reclear:,}", f"{reclear / total * 100:.0f}%" if total else "-")
    c3.metric("Blind-prog", f"{blind:,}", f"{blind / total * 100:.0f}%" if total else "-")

    by_intent = (
        itt.groupby("intent", as_index=False)
        .agg(sessions=("sessions", "sum"), sessions_filled=("sessions_filled", "sum"))
        .assign(fill_rate_pct=lambda d: (d["sessions_filled"] / d["sessions"] * 100).round(1))
    )
    if by_intent.empty:
        st.info("No fill data for this fight.")
    else:
        chart = (
            alt.Chart(by_intent)
            .mark_bar()
            .encode(
                x=alt.X("intent:N", title="Intent"),
                y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color(
                    "intent:N",
                    scale=alt.Scale(
                        domain=["practice", "reclear_farm", "blind_prog"],
                        range=[ACCENT_PURPLE, ACCENT_GREEN, BLUE],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("intent:N", title="Intent"),
                    alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                    alt.Tooltip("sessions:Q", title="Sessions", format=","),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(style_chart(chart), width="stretch")
