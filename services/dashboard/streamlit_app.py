"""Public analytics dashboard for the FFXIV Party Finder gold marts.

A tabbed exploration tool for a general audience: pick a Region + Data Center in
the sidebar, then browse Overview / When to Post / Duty Trends / Roles / Fill
Outcomes. Data is loaded once per cold start (see data.py) and shaped in pandas;
there are no per-interaction BigQuery queries. Styling lives in theme.py and is
documented in STYLING.md.

Datacenter is the primary scope because a Party Finder listing is exclusive to
the data center it is hosted on; region is only a rollup.
"""

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

from data import DEFAULT_DATACENTER, DEFAULT_REGION, WEEKDAY_ORDER, load
from theme import (
    BLUE,
    CURRENT_SAVAGE_TIER,
    GOLD,
    HEATMAP_SCHEME,
    OUTCOME_COLORS,
    ROLE_COLORS,
    inject_css,
    style_chart,
)

st.set_page_config(page_title="FFXIV Party Finder Analytics", page_icon="⚔️", layout="wide")
inject_css()

MIN_SAMPLE = 3  # a weekday x hour bucket needs this many filled sessions to be "advisable"

funnel = load("mart_fill_funnel")
heatmap = load("mart_activity_heatmap")
time_to_fill = load("mart_time_to_fill")
role_demand = load("mart_role_demand")
duty_trends = load("mart_duty_trends")
role_trends = load("mart_role_trends")

# reset_week arrives as a DATE; normalize to Timestamp for filtering and sorting
for _df in (duty_trends, role_trends):
    _df["reset_week"] = pd.to_datetime(_df["reset_week"])


def _pick(options: list, preferred: str) -> int:
    """Index of the preferred option, or 0 if it isn't present."""
    return options.index(preferred) if preferred in options else 0


def _window_caption(df: pd.DataFrame) -> str:
    """Label for the recent-window pattern marts (mart_time_to_fill / role_demand /
    activity_heatmap), which cover only the last few reset weeks."""
    if df.empty or "window_start_date" not in df:
        return ""
    ws = pd.to_datetime(df["window_start_date"].iloc[0])
    we = pd.to_datetime(df["window_end_date"].iloc[0])
    return f"Recent window: {ws:%b %d} - {we:%b %d}."


# ------------------------------------------------------------------ Tab: Overview


def render_overview(funnel_dc, heatmap_dc, duty_dc, datacenter):
    total_sessions = int(funnel_dc["sessions"].sum())
    fill_pct = (
        funnel_dc["filled"].sum() / funnel_dc["sessions"].sum() * 100 if total_sessions else 0.0
    )

    # "Last week" = the most recent fully completed reset week (7 days past its
    # Tuesday 08:00 UTC start). The latest mart row is usually the in-progress
    # week, which we skip so the KPI isn't a misleading partial count.
    last_listings, last_delta, last_label = 0, None, "Listings last week"
    if not duty_dc.empty:
        by_week = duty_dc.groupby("reset_week")["listings"].sum().sort_index()
        today = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
        complete = by_week[by_week.index + pd.Timedelta(days=7) <= today]
        ref = complete if not complete.empty else by_week
        latest = ref.index[-1]
        last_listings = int(ref.loc[latest])
        pos = by_week.index.get_loc(latest)
        if pos >= 1:
            last_delta = last_listings - int(by_week.iloc[pos - 1])
        last_label = f"Listings, week of {latest:%b %d}"

    busiest = "-"
    if not heatmap_dc.empty:
        by_hour = heatmap_dc.groupby("post_hour")["listings_posted"].sum()
        if not by_hour.empty:
            busiest = f"{int(by_hour.idxmax()):02d}:00 UTC"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total listings", f"{total_sessions:,}")
    c2.metric(last_label, f"{last_listings:,}", delta=None if last_delta is None else f"{last_delta:+,}")
    c3.metric("Fill rate", f"{fill_pct:.1f}%")
    c4.metric("Busiest hour", busiest)

    st.divider()

    st.subheader(f"When is Party Finder busiest on {datacenter}?")
    st.caption(f"Listings posted by day of week and hour (UTC). {_window_caption(heatmap_dc)}")
    if heatmap_dc.empty:
        st.info("No activity data for this data center yet.")
    else:
        hm = heatmap_dc.groupby(["day_name", "post_hour"], as_index=False)["listings_posted"].sum()
        chart = (
            alt.Chart(hm)
            .mark_rect()
            .encode(
                x=alt.X("post_hour:O", title="Hour of day (UTC)"),
                y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
                color=alt.Color("listings_posted:Q", title="Listings", scale=alt.Scale(scheme=HEATMAP_SCHEME)),
                tooltip=[
                    alt.Tooltip("day_name:N", title="Day"),
                    alt.Tooltip("post_hour:O", title="Hour"),
                    alt.Tooltip("listings_posted:Q", title="Listings", format=","),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.subheader("Listings by content type")
    st.caption("All-time share of listing sessions on this data center, by content category.")
    by_cat = (
        funnel_dc.groupby("content_category", as_index=False)["sessions"]
        .sum()
        .sort_values("sessions", ascending=False)
    )
    if by_cat.empty:
        st.info("No listings for this data center yet.")
    else:
        chart = (
            alt.Chart(by_cat)
            .mark_bar(color=BLUE)
            .encode(
                x=alt.X("sessions:Q", title="Listing sessions"),
                y=alt.Y("content_category:N", title=None, sort="-x"),
                tooltip=[
                    alt.Tooltip("content_category:N", title="Category"),
                    alt.Tooltip("sessions:Q", title="Sessions", format=","),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------------- Tab: When to Post


def render_timing(ttf_dc, datacenter):
    st.subheader("When should I post to fill fastest?")
    st.caption(
        "Fill rate and average time-to-fill by weekday and hour (UTC), from when listings were "
        f"posted. {_window_caption(ttf_dc)}"
    )
    if ttf_dc.empty:
        st.info("No time-to-fill data for this data center yet.")
        return

    cats = sorted(ttf_dc["content_category"].dropna().unique().tolist())
    f1, f2, f3 = st.columns([1, 1.4, 1.2])
    cat = f1.selectbox("Content type", cats, index=_pick(cats, "savage"), key="timing_cat")
    cat_df = ttf_dc[ttf_dc["content_category"] == cat]
    duty_opts = ["All duties"] + (
        cat_df.groupby("duty")["sessions"].sum().sort_values(ascending=False).index.tolist()
    )
    duty = f2.selectbox("Duty", duty_opts, key="timing_duty")
    metric = f3.radio("Colour by", ["Fill rate", "Avg time to fill"], horizontal=True, key="timing_metric")

    df = cat_df if duty == "All duties" else cat_df[cat_df["duty"] == duty]
    if df.empty:
        st.info("No data for this selection.")
        return

    # Aggregate to weekday x hour. Fill rate pools exactly; time-to-fill uses a
    # session-weighted mean of per-bucket means (median-of-medians would be wrong).
    df = df.assign(ttf_weight=df["avg_time_to_fill_min"].fillna(0) * df["sessions_filled"])
    g = (
        df.groupby(["post_weekday", "day_name", "post_hour"], as_index=False)
        .agg(
            sessions=("sessions", "sum"),
            filled=("sessions_filled", "sum"),
            resolved=("sessions_resolved", "sum"),
            ttf_weight=("ttf_weight", "sum"),
        )
    )
    g["fill_rate_pct"] = (g["filled"] / g["resolved"].replace(0, pd.NA) * 100).round(1)
    g["avg_ttf_min"] = (g["ttf_weight"] / g["filled"].replace(0, pd.NA)).round(0)

    # Headline metrics + best time to post
    tot_filled, tot_resolved = int(g["filled"].sum()), int(g["resolved"].sum())
    overall_fill = tot_filled / tot_resolved * 100 if tot_resolved else 0.0
    overall_ttf = g["ttf_weight"].sum() / tot_filled if tot_filled else None
    advisable = g[g["filled"] >= MIN_SAMPLE]
    if metric == "Fill rate":
        best = advisable.loc[advisable["fill_rate_pct"].idxmax()] if not advisable.empty else None
    else:
        best = advisable.loc[advisable["avg_ttf_min"].idxmin()] if not advisable.empty else None

    k1, k2, k3 = st.columns(3)
    k1.metric("Overall fill rate", f"{overall_fill:.0f}%")
    k2.metric("Avg time to fill", "-" if overall_ttf is None else f"{overall_ttf:.0f} min")
    if best is not None:
        detail = f"{best['fill_rate_pct']:.0f}% fill" if metric == "Fill rate" else f"{best['avg_ttf_min']:.0f} min"
        k3.metric("Best time to post", f"{best['day_name'][:3]} {int(best['post_hour']):02d}:00", detail)
    else:
        k3.metric("Best time to post", "-", f"needs {MIN_SAMPLE}+ filled")

    if metric == "Fill rate":
        color = alt.Color("fill_rate_pct:Q", title="Fill %", scale=alt.Scale(scheme=HEATMAP_SCHEME))
        value_tip = alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".0f")
    else:
        # lower time is better -> reverse so short waits read as "hot"
        color = alt.Color("avg_ttf_min:Q", title="Min", scale=alt.Scale(scheme=HEATMAP_SCHEME, reverse=True))
        value_tip = alt.Tooltip("avg_ttf_min:Q", title="Avg time to fill", format=".0f")

    chart = (
        alt.Chart(g)
        .mark_rect()
        .encode(
            x=alt.X("post_hour:O", title="Hour of day (UTC)"),
            y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
            color=color,
            tooltip=[
                alt.Tooltip("day_name:N", title="Day"),
                alt.Tooltip("post_hour:O", title="Hour"),
                value_tip,
                alt.Tooltip("sessions:Q", title="Listings", format=","),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(style_chart(chart), width="stretch")
    st.caption(
        "Time-to-fill is a session-weighted mean; fill/expiry are inferred from delisting - see the "
        "FAQ. Empty cells had no listings in the recent window."
    )


# -------------------------------------------------------------- Tab: Duty Trends


def render_duty_trends(duty_range, datacenter, has_range):
    st.subheader("Popularity, fill rate & speed over patch history")
    if not has_range:
        st.info("Not enough weekly history for this data center yet.")
        return
    st.caption("Scoped to the reset-week range in the sidebar. Reset weeks open Tuesday 08:00 UTC.")
    if duty_range.empty:
        st.info("No duty listings in the selected range.")
        return

    left, right = st.columns(2)
    with left:
        st.markdown("**Most listed duties**")
        top = (
            duty_range.groupby("duty", as_index=False)["listings"]
            .sum()
            .sort_values("listings", ascending=False)
            .head(15)
        )
        top["current_tier"] = top["duty"].isin(CURRENT_SAVAGE_TIER["duties"])
        chart = (
            alt.Chart(top)
            .mark_bar()
            .encode(
                x=alt.X("listings:Q", title="Listings"),
                y=alt.Y("duty:N", title=None, sort="-x"),
                color=alt.Color(
                    "current_tier:N",
                    scale=alt.Scale(domain=[True, False], range=[GOLD, BLUE]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("duty:N", title="Duty"),
                    alt.Tooltip("listings:Q", title="Listings", format=","),
                ],
            )
            .properties(height=360)
        )
        st.altair_chart(style_chart(chart), width="stretch")
        st.caption("Gold = current savage tier.")

    with right:
        st.markdown("**Fill rate by reset week**")
        wk = duty_range.groupby("reset_week", as_index=False).agg(
            filled=("sessions_filled", "sum"), resolved=("sessions_resolved", "sum")
        )
        wk = wk[wk["resolved"] > 0]
        if wk.empty:
            st.info("No resolved sessions in this range.")
        else:
            wk["fill_rate_pct"] = (wk["filled"] / wk["resolved"] * 100).round(1)
            chart = (
                alt.Chart(wk)
                .mark_line(point=True, color=GOLD)
                .encode(
                    x=alt.X("reset_week:T", title="Reset week"),
                    y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
                    tooltip=[
                        alt.Tooltip("reset_week:T", title="Week"),
                        alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                    ],
                )
                .properties(height=360)
            )
            st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.markdown("**Duty detail: time-to-fill and fill rate over time**")
    duty_opts = duty_range.groupby("duty")["listings"].sum().sort_values(ascending=False).index.tolist()
    sel = st.selectbox("Duty", duty_opts, key="dt_duty")
    series = duty_range[duty_range["duty"] == sel].sort_values("reset_week")
    d1, d2 = st.columns(2)
    with d1:
        chart = (
            alt.Chart(series)
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
            .properties(height=280)
        )
        st.altair_chart(style_chart(chart), width="stretch")
    with d2:
        fill = series[series["fill_rate_pct"].notna()]
        if fill.empty:
            st.info("No resolved sessions for this duty in range.")
        else:
            chart = (
                alt.Chart(fill)
                .mark_line(point=True, color=GOLD)
                .encode(
                    x=alt.X("reset_week:T", title="Reset week"),
                    y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
                    tooltip=[
                        alt.Tooltip("reset_week:T", title="Week"),
                        alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(style_chart(chart), width="stretch")


# -------------------------------------------------------------------- Tab: Roles


def _role_share_long(df):
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


def render_roles(rd_dc, rt_range, datacenter, has_range):
    st.subheader("Which role is the bottleneck?")
    st.caption(
        "Open-slot share is unmet role demand: the role with the largest share is hardest to "
        "recruit. Roles, not jobs (the source only exposes tank / healer / DPS)."
    )
    if rd_dc.empty:
        st.info("No role data for this data center yet.")
        return

    cats = sorted(rd_dc["content_category"].dropna().unique().tolist())
    cat = st.selectbox("Content type", cats, index=_pick(cats, "savage"), key="roles_cat")

    # bottleneck callout from pooled open slots across the recent window
    cat_dc = rd_dc[rd_dc["content_category"] == cat]
    pooled = {
        "Tank": cat_dc["avg_open_tank"].mul(cat_dc["sessions"]).sum(),
        "Healer": cat_dc["avg_open_healer"].mul(cat_dc["sessions"]).sum(),
        "DPS": cat_dc["avg_open_dps"].mul(cat_dc["sessions"]).sum(),
    }
    total_open = sum(pooled.values()) or 1
    k1, k2, k3 = st.columns(3)
    for col, role in zip((k1, k2, k3), ("Tank", "Healer", "DPS")):
        col.metric(f"{role} open share", f"{pooled[role] / total_open * 100:.0f}%")

    st.markdown("**By hour of day** (recent window)")
    st.caption(_window_caption(rd_dc))
    hourly = _role_share_long(cat_dc.sort_values("post_hour"))
    if hourly["share_pct"].dropna().empty:
        st.info("No open-slot data for this content type.")
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
            .properties(height=300)
        )
        st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.markdown("**Over patch history**")
    if not has_range:
        st.info("Not enough weekly history for the trend view yet.")
        return
    cat_rt = rt_range[rt_range["content_category"] == cat].sort_values("reset_week")
    weekly = _role_share_long(cat_rt)
    if weekly["share_pct"].dropna().empty:
        st.info("No role trend data for this content type in the selected range.")
    else:
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
            .properties(height=300)
        )
        st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------------ Tab: Fill Outcomes


def render_outcomes(funnel_dc, datacenter):
    st.subheader("What happens to a listing?")
    st.caption(
        "Every listing session resolves to one outcome. 'Filled' and 'expired' are inferred from "
        "delisting; 'flash' is a single-snapshot ambiguity band; 'multiparty' (alliance/PvP) can't "
        "be tracked for fill. See the FAQ."
    )
    if funnel_dc.empty:
        st.info("No outcome data for this data center yet.")
        return

    cols = ["filled", "expired_partial", "flash", "live", "multiparty"]
    agg = funnel_dc.groupby("content_category", as_index=False)[cols + ["sessions"]].sum()

    resolved = int(agg["filled"].sum() + agg["expired_partial"].sum())
    filled = int(agg["filled"].sum())
    k1, k2 = st.columns(2)
    k1.metric("Resolved fill rate", f"{filled / resolved * 100:.0f}%" if resolved else "-")
    k2.metric("Listings analysed", f"{int(agg['sessions'].sum()):,}")

    label_map = {
        "filled": "Filled",
        "expired_partial": "Expired (partial)",
        "flash": "Flash",
        "live": "Live",
        "multiparty": "Multiparty",
    }
    long = agg.melt(id_vars=["content_category", "sessions"], value_vars=cols, var_name="outcome", value_name="count")
    long["pct"] = (long["count"] / long["sessions"] * 100).round(1)
    long["outcome"] = long["outcome"].map(label_map)

    order = list(OUTCOME_COLORS)
    long["outcome_order"] = long["outcome"].map({o: i for i, o in enumerate(order)})
    chart = (
        alt.Chart(long)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Share of listings", stack="normalize", axis=alt.Axis(format="%")),
            y=alt.Y("content_category:N", title=None),
            color=alt.Color(
                "outcome:N",
                title="Outcome",
                scale=alt.Scale(domain=order, range=[OUTCOME_COLORS[o] for o in order]),
                sort=order,
            ),
            order=alt.Order("outcome_order:Q"),
            tooltip=[
                alt.Tooltip("content_category:N", title="Category"),
                alt.Tooltip("outcome:N", title="Outcome"),
                alt.Tooltip("pct:Q", title="Share", format=".1f"),
                alt.Tooltip("count:Q", title="Sessions", format=","),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------------------------- Main

st.title("⚔️ FFXIV Party Finder Analytics")
st.caption(
    "Explore Party Finder trends - scraped from xivpf.com and modelled through a BigQuery pipeline. "
    "Data is refreshed periodically, not live."
)

# --- Sidebar: consistent global filters ---
with st.sidebar:
    st.markdown("### ⚔️ PF Analytics")
    st.caption("Final Fantasy XIV Party Finder insights")
    st.divider()

    regions = sorted(funnel["pf_region"].dropna().unique().tolist())
    region = st.selectbox("Region", regions, index=_pick(regions, DEFAULT_REGION), key="flt_region")
    datacenters = sorted(
        funnel.loc[funnel["pf_region"] == region, "pf_datacenter"].dropna().unique().tolist()
    )
    datacenter = st.selectbox(
        "Data center", datacenters, index=_pick(datacenters, DEFAULT_DATACENTER), key="flt_dc"
    )
    st.caption("A listing only shows on the data center it was made on.")

    st.divider()
    st.markdown("**Trend date range**")
    st.caption("Applies to the Duty Trends & Roles-over-time charts.")


dc_mask = lambda df: df[(df["pf_region"] == region) & (df["pf_datacenter"] == datacenter)]
funnel_dc = dc_mask(funnel)
heatmap_dc = dc_mask(heatmap)
ttf_dc = dc_mask(time_to_fill)
rd_dc = dc_mask(role_demand)
duty_dc = dc_mask(duty_trends)
role_dc = dc_mask(role_trends)

# Reset-week range slider lives in the sidebar; drives the trend tabs.
weeks = sorted(duty_dc["reset_week"].dropna().unique())
has_range = len(weeks) >= 2
if has_range:
    week_dates = [pd.Timestamp(w) for w in weeks]
    default_start = week_dates[-8] if len(week_dates) > 8 else week_dates[0]
    start, end = st.sidebar.select_slider(
        "Reset-week range",
        options=week_dates,
        value=(default_start, week_dates[-1]),
        format_func=lambda d: d.strftime("%b %d, %Y"),
        label_visibility="collapsed",
        key="flt_weeks",
    )
    in_range = lambda df: df[(df["reset_week"] >= start) & (df["reset_week"] <= end)]
    duty_range, role_range = in_range(duty_dc), in_range(role_dc)
else:
    st.sidebar.caption("Not enough weekly history yet.")
    duty_range, role_range = duty_dc, role_dc

with st.sidebar:
    st.divider()
    st.caption("Data is refreshed periodically, not live. See the **FAQ** page for methodology and privacy.")

tab_overview, tab_timing, tab_duties, tab_roles, tab_outcomes = st.tabs(
    ["📊 Overview", "⏰ When to Post", "📈 Duty Trends", "🛡️ Roles", "✅ Fill Outcomes"]
)
with tab_overview:
    render_overview(funnel_dc, heatmap_dc, duty_dc, datacenter)
with tab_timing:
    render_timing(ttf_dc, datacenter)
with tab_duties:
    render_duty_trends(duty_range, datacenter, has_range)
with tab_roles:
    render_roles(rd_dc, role_range, datacenter, has_range)
with tab_outcomes:
    render_outcomes(funnel_dc, datacenter)
