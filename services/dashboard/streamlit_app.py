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
from streamlit_echarts import st_echarts

from data import DEFAULT_DATACENTER, DEFAULT_REGION, WEEKDAY_ORDER, load
from theme import (
    ACCENT_BLUE as BLUE,
    ACCENT_GOLD as GOLD,
    CURRENT_SAVAGE_TIER,
    HEATMAP_SCHEME,
    OUTCOME_COLORS,
    ROLE_COLORS,
    ACCENT_GREEN,
    ACCENT_PURPLE,
    ACCENT_RED,
    ACCENT_BLUE,
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
intent = load("mart_listing_intent")
travel = load("mart_travel_demand")
ilvl = load("mart_ilvl_gating")
tags = load("mart_listing_tags")
saturation = load("mart_market_saturation")

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

    # KPI row — styled cards via injected CSS (gold values, panel bg, border)
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
        bars = (
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
        )
        labels = alt.Chart(by_cat).mark_text(
            align="left",
            baseline="middle",
            dx=5,
            fontSize=11,
            color="#E6E6E6",
        ).encode(text=alt.Text("sessions:Q", format=","))
        chart_with_labels = bars + labels
        st.altair_chart(style_chart(chart_with_labels), width="stretch")


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

    # Altair heatmap (single metric, colour-coded)
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

    st.divider()
    st.markdown("**Time-to-fill distribution**")
    st.caption("Histogram buckets of fill speed for the selected duty/content type.")
    # Build TTF distribution from the aggregated data
    ttf_df = cat_df if duty == "All duties" else cat_df[cat_df["duty"] == duty]
    if ttf_df.empty:
        st.info("No data for this selection.")
    else:
        ttf_dist = {
            "lt_15": int(ttf_df["ttf_lt_15"].sum()),
            "t_15_30": int(ttf_df["ttf_15_30"].sum()),
            "t_30_60": int(ttf_df["ttf_30_60"].sum()),
            "t_60_120": int(ttf_df["ttf_60_120"].sum()),
            "gt_120": int(ttf_df["ttf_gt_120"].sum()),
            "censored": float(ttf_df["censored_pct"].iloc[0]),
        }
        total_filled = int(ttf_dist["lt_15"] + ttf_dist["t_15_30"] + ttf_dist["t_30_60"] + ttf_dist["t_60_120"] + ttf_dist["gt_120"])
        if total_filled == 0:
            st.info("No filled sessions in this selection.")
        else:
            dist_long = pd.DataFrame({
                "bucket": ["<15m", "15-30m", "30-60m", "60-120m", ">120m"],
                "count": [ttf_dist["lt_15"], ttf_dist["t_15_30"], ttf_dist["t_30_60"], ttf_dist["t_60_120"], ttf_dist["gt_120"]],
            })
            dist_long["pct"] = (dist_long["count"] / total_filled * 100).round(1)
            bucket_colors = [ACCENT_GREEN, ACCENT_GREEN, ACCENT_BLUE, ACCENT_RED, ACCENT_RED]
            chart = (
                alt.Chart(dist_long)
                .mark_bar()
                .encode(
                    x=alt.X("bucket:N", title="Time-to-fill"),
                    y=alt.Y("count:Q", title="Filled sessions"),
                    color=alt.Color(
                        "bucket:N",
                        scale=alt.Scale(domain=dist_long["bucket"].tolist(), range=bucket_colors),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("bucket:N", title="Bucket"),
                        alt.Tooltip("count:Q", title="Count", format=","),
                        alt.Tooltip("pct:Q", title="Share", format=".1f"),
                    ],
                )
                .properties(height=220)
            )
            st.altair_chart(style_chart(chart), width="stretch")
            st.caption(f"Censored (live/flash) share: {ttf_dist['censored']:.0f}%")


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
    st.markdown("**Volume trend with anomaly detection**")
    st.caption(
        "Trailing 4-week rolling average smooths week-to-week noise. "
        "Anomaly flag (red dots) when volume deviates ≥2σ from the rolling average."
    )
    vol = duty_range[duty_range["listings"] > 0].copy()
    if vol.empty:
        st.info("No volume data in this range.")
    else:
        vol["anomaly"] = vol["is_volume_anomaly"].fillna(False)
        # Base line chart (all weeks)
        base_line = (
            alt.Chart(vol)
            .mark_line(point=True, color=BLUE, strokeWidth=2)
            .encode(
                x=alt.X("reset_week:T", title="Reset week"),
                y=alt.Y("listings:Q", title="Listings"),
                tooltip=[
                    alt.Tooltip("reset_week:T", title="Week"),
                    alt.Tooltip("listings:Q", title="Listings", format=","),
                    alt.Tooltip("rolling_avg_listings_4wk:Q", title="4wk avg", format=".0f"),
                    alt.Tooltip("listings_zscore:Q", title="Z-score", format=".2f"),
                ],
            )
        )
        # Rolling average line
        roll_line = (
            alt.Chart(vol)
            .mark_line(point=True, color=ACCENT_PURPLE, strokeWidth=2, strokeDash=[6, 4])
            .encode(
                x=alt.X("reset_week:T", title="Reset week"),
                y=alt.Y("rolling_avg_listings_4wk:Q", title="Listings"),
                tooltip=[
                    alt.Tooltip("reset_week:T", title="Week"),
                    alt.Tooltip("rolling_avg_listings_4wk:Q", title="4wk rolling avg", format=".0f"),
                ],
            )
        )
        # Anomaly markers
        anomaly_pts = (
            alt.Chart(vol[vol["anomaly"]])
            .mark_circle(color=ACCENT_RED, size=120)
            .encode(
                x=alt.X("reset_week:T", title="Reset week"),
                y=alt.Y("listings:Q", title="Listings"),
                tooltip=[
                    alt.Tooltip("reset_week:T", title="Week"),
                    alt.Tooltip("listings:Q", title="Listings", format=","),
                    alt.Tooltip("listings_zscore:Q", title="Z-score", format=".2f"),
                ],
            )
        )
        st.altair_chart(style_chart(base_line + roll_line + anomaly_pts), width="stretch")

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

    # Bottleneck summary text
    bottleneck_role = max(pooled, key=pooled.get)
    bottleneck_pct = pooled[bottleneck_role] / total_open * 100
    st.info(
        f"**{bottleneck_role}** is the bottleneck for **{bottleneck_pct:.0f}%** of open slots "
        f"in {cat} on {datacenter}."
    )

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

    # --- ECharts Sankey diagram ---
    st.markdown("**Outcome flow**")
    source_cats = long["content_category"].dropna().unique().tolist()
    categories = [{"name": s} for s in source_cats] + [{"name": o} for o in order]
    links = []
    for _, row in long.iterrows():
        links.append({
            "source": row["content_category"],
            "target": row["outcome"],
            "value": int(row["count"]),
        })

    sankey_chart = {
        "tooltip": {"trigger": "item", "formatter": "{b} → {c}: {d}%"},
        "series": [{
            "type": "sankey",
            "layout": "none",
            "emphasis": {"focus": "adjacency"},
            "lineStyle": {"color": "source", "curveness": 0.5},
            "itemStyle": {"borderWidth": 0},
            "label": {"color": "#E6E6E6"},
            "nodeAlign": "left",
            "layoutIterations": 32,
            "data": categories,
            "links": links,
        }],
    }
    st_echarts(sankey_chart, height=340)

    st.divider()

    # --- Stacked bar fallback (precise values) ---
    st.markdown("**Precise breakdown**")
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


# ------------------------------------------------------- Tab: Intent & Travel


def render_intent_travel(intent_dc, travel_dc, datacenter):
    st.subheader("High-end listing intent")
    st.caption(
        "Splits high-end listings into practice, reclear-farm, and blind-prog buckets. "
        f"{_window_caption(intent_dc)}"
    )
    if intent_dc.empty:
        st.info("No high-end intent data for this data center yet.")
        return

    cats = sorted(intent_dc["content_category"].dropna().unique().tolist())
    cat = st.selectbox("Content type", cats, index=_pick(cats, "savage"), key="intent_cat")
    cat_df = intent_dc[intent_dc["content_category"] == cat]

    # KPI cards
    total = int(cat_df["sessions"].sum())
    practice = int(cat_df["practice"].sum())
    reclear = int(cat_df["reclear_farm"].sum())
    blind = int(cat_df["blind_prog"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Practice", f"{practice:,}", f"{practice/total*100:.0f}%" if total else "-")
    c2.metric("Reclear-farm", f"{reclear:,}", f"{reclear/total*100:.0f}%" if total else "-")
    c3.metric("Blind-prog", f"{blind:,}", f"{blind/total*100:.0f}%" if total else "-")

    st.divider()
    st.markdown("**Fill rate by intent**")
    fill_by_intent = cat_df[cat_df["fill_rate_pct"].notna()].sort_values("sessions", ascending=False)
    if fill_by_intent.empty:
        st.info("No fill data for this content type.")
    else:
        chart = (
            alt.Chart(fill_by_intent)
            .mark_bar()
            .encode(
                x=alt.X("intent:N", title="Intent"),
                y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color(
                    "intent:N",
                    scale=alt.Scale(
                        domain=["practice", "reclear_farm", "blind_prog"],
                        range=[ACCENT_PURPLE, ACCENT_GREEN, ACCENT_BLUE],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("intent:N", title="Intent"),
                    alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                    alt.Tooltip("sessions:Q", title="Sessions", format=","),
                    alt.Tooltip("median_time_to_fill_min:Q", title="Median TTF (min)", format=".0f"),
                ],
            )
            .properties(height=260)
        )
        st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.markdown("**Intent split by duty** (top 10)")
    duty_intent = (
        cat_df.groupby("duty", as_index=False)[["practice", "reclear_farm", "blind_prog", "sessions"]]
        .sum()
        .sort_values("sessions", ascending=False)
        .head(10)
    )
    duty_intent_long = duty_intent.melt(
        id_vars=["duty", "sessions"],
        value_vars=["practice", "reclear_farm", "blind_prog"],
        var_name="intent", value_name="count",
    )
    chart = (
        alt.Chart(duty_intent_long)
        .mark_bar()
        .encode(
            x=alt.X("duty:N", title="Duty", sort="-y"),
            y=alt.Y("count:Q", title="Sessions", stack="normalize", axis=alt.Axis(format="%")),
            color=alt.Color(
                "intent:N",
                scale=alt.Scale(
                    domain=["practice", "reclear_farm", "blind_prog"],
                    range=[ACCENT_PURPLE, ACCENT_GREEN, ACCENT_BLUE],
                ),
            ),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("intent:N", title="Intent"),
                alt.Tooltip("count:Q", title="Count", format=","),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(style_chart(chart), width="stretch")

    # --- Travel demand ---
    st.divider()
    st.markdown("**Cross-DC / cross-region travel demand")
    st.caption("Share of listings posted by someone from a different DC or region.")
    if travel_dc.empty:
        st.info("No travel data for this data center yet.")
        return

    # KPI cards for travel
    total_travel = int(travel_dc["sessions"].sum())
    imported = int(travel_dc["traveller"].sum() + travel_dc["voyager"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Total sessions", f"{total_travel:,}")
    c2.metric("Imported", f"{imported:,}", f"{imported/total_travel*100:.0f}%" if total_travel else "-")
    c3.metric("Local", f"{total_travel - imported:,}", f"{(total_travel-imported)/total_travel*100:.0f}%" if total_travel else "-")

    st.divider()
    st.markdown("**Travel share over time**")
    travel_wide = travel_dc.groupby("reset_week", as_index=False).agg(
        local=("local", "sum"),
        traveller=("traveller", "sum"),
        voyager=("voyager", "sum"),
    )
    travel_wide = travel_wide.sort_values("reset_week")
    travel_long = travel_wide.melt(
        id_vars=["reset_week"],
        value_vars=["local", "traveller", "voyager"],
        var_name="type", value_name="count",
    )
    chart = (
        alt.Chart(travel_long)
        .mark_area(interpolate="monotone")
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("count:Q", title="Sessions", stack="normalize", axis=alt.Axis(format="%")),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(
                    domain=["local", "traveller", "voyager"],
                    range=[ACCENT_GREEN, ACCENT_BLUE, ACCENT_PURPLE],
                ),
            ),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("type:N", title="Type"),
                alt.Tooltip("count:Q", title="Count", format=","),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------- Tab: ILvl Gating


def render_ilvl_gating(ilvl_dc, datacenter):
    st.subheader("Item-level gating trends")
    st.caption(
        "Tracks how minimum item-level gates evolve over time and correlates with fill speed. "
        f"{_window_caption(ilvl_dc)}"
    )
    if ilvl_dc.empty:
        st.info("No ilvl gating data for this data center yet.")
        return

    cats = sorted(ilvl_dc["content_category"].dropna().unique().tolist())
    cat = st.selectbox("Content type", cats, index=_pick(cats, "savage"), key="ilvl_cat")
    cat_df = ilvl_dc[ilvl_dc["content_category"] == cat].sort_values("reset_week")

    if cat_df.empty:
        st.info("No data for this content type.")
        return

    # KPI cards
    avg_ilvl = cat_df["avg_ilvl"].mean()
    fill_rate = cat_df["fill_rate_pct"].mean()
    ttf = cat_df["median_time_to_fill_min"].mean()
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg min ilvl", f"{avg_ilvl:.0f}")
    c2.metric("Avg fill rate", f"{fill_rate:.0f}%")
    c3.metric("Avg median TTF", f"{ttf:.0f} min")

    st.divider()
    st.markdown("**ILvl gate & fill rate over time**")
    duty_opts = ["All duties"] + cat_df["duty"].dropna().unique().tolist()
    duty = st.selectbox("Duty", duty_opts, key="ilvl_duty")
    duty_df = cat_df if duty == "All duties" else cat_df[cat_df["duty"] == duty]

    if duty_df.empty:
        st.info("No data for this selection.")
        return

    # Dual-axis chart: ilvl line + fill rate line
    ilvl_line = (
        alt.Chart(duty_df)
        .mark_line(point=True, color=ACCENT_PURPLE)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("avg_ilvl:Q", title="Avg min ilvl"),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("avg_ilvl:Q", title="Avg min ilvl", format=".0f"),
                alt.Tooltip("p50_ilvl:Q", title="Median ilvl", format=".0f"),
                alt.Tooltip("sessions:Q", title="Sessions", format=","),
            ],
        )
    )
    fill_line = (
        alt.Chart(duty_df)
        .mark_line(point=True, color=ACCENT_GREEN)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("fill_rate_pct:Q", title="Fill rate (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("fill_rate_pct:Q", title="Fill rate", format=".1f"),
                alt.Tooltip("median_time_to_fill_min:Q", title="Median TTF (min)", format=".0f"),
            ],
        )
    )
    chart = style_chart(ilvl_line + fill_line)
    st.altair_chart(chart, width="stretch")

    st.divider()
    st.markdown("**ILvl distribution by duty**")
    duty_ilvl = (
        duty_df.groupby("duty", as_index=False).agg(
            avg=("avg_ilvl", "mean"),
            p50=("p50_ilvl", "first"),
            p90=("p90_ilvl", "first"),
            fill=("fill_rate_pct", "mean"),
            sessions=("sessions", "sum"),
        )
        .sort_values("avg", ascending=False)
        .head(15)
    )
    chart = (
        alt.Chart(duty_ilvl)
        .mark_bar()
        .encode(
            x=alt.X("avg:Q", title="Avg min ilvl"),
            y=alt.Y("duty:N", title="Duty", sort="-x"),
            color=alt.Color("fill:Q", title="Fill rate (%)", scale=alt.Scale(scheme="greens")),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("avg:Q", title="Avg min ilvl", format=".0f"),
                alt.Tooltip("p50:Q", title="Median ilvl", format=".0f"),
                alt.Tooltip("p90:Q", title="p90 ilvl", format=".0f"),
                alt.Tooltip("fill:Q", title="Fill rate", format=".1f"),
                alt.Tooltip("sessions:Q", title="Sessions", format=","),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------- Tab: Listing Tags


def render_listing_tags(tags_dc, datacenter):
    st.subheader("Listing description tags")
    st.caption(
        "Share of sessions carrying each tag: loot rules, one-per-job, duty completion variants. "
        f"{_window_caption(tags_dc)}"
    )
    if tags_dc.empty:
        st.info("No tag data for this data center yet.")
        return

    cats = sorted(tags_dc["content_category"].dropna().unique().tolist())
    cat = st.selectbox("Content type", cats, index=_pick(cats, "savage"), key="tags_cat")
    cat_df = tags_dc[tags_dc["content_category"] == cat]

    if cat_df.empty:
        st.info("No data for this content type.")
        return

    # KPI cards - overall tag prevalence
    tag_cols = ["loot_pct", "clear_pct", "one_per_job_pct", "weekly_unclaimed_pct", "duty_completion_pct", "duty_incomplete_pct"]
    tag_labels = ["Loot", "Clear", "1/job", "Weekly", "Completion", "Incomplete"]
    tag_vals = [cat_df[c].mean() for c in tag_cols]

    cols = st.columns(6)
    for col, label, val in zip(cols, tag_labels, tag_vals):
        col.metric(f"{label}%", f"{val:.0f}%")

    st.divider()
    st.markdown("**Tag prevalence by duty** (average %, top 20 duties by avg tag %)")
    duty_tags = (
        cat_df.groupby("duty", as_index=False)[tag_cols].mean()
        .melt(id_vars=["duty"], value_vars=tag_cols, var_name="tag", value_name="pct")
        .sort_values("pct", ascending=False)
    )
    duty_tags["tag_label"] = duty_tags["tag"].map(dict(zip(tag_cols, tag_labels)))
    tag_order = tag_labels

    # Limit to top 20 duties by average tag percentage to avoid overcrowding
    duty_avg = duty_tags.groupby("duty")["pct"].mean().sort_values(ascending=False)
    top_duties = duty_avg.head(20).index.tolist()
    duty_tags = duty_tags[duty_tags["duty"].isin(top_duties)].sort_values("pct", ascending=False)

    chart = (
        alt.Chart(duty_tags)
        .mark_bar()
        .encode(
            x=alt.X("pct:Q", title="Avg prevalence (%)"),
            y=alt.Y("duty:N", title="Duty", sort="-x"),
            color=alt.Color("tag_label:N", title="Tag", scale=alt.Scale(domain=tag_order, range=list(HEATMAP_SCHEME))),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("tag_label:N", title="Tag"),
                alt.Tooltip("pct:Q", title="Avg prevalence", format=".1f"),
            ],
        )
        .properties(height=400)
    )
    st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.markdown("**Tag trends over time**")
    time_tags = (
        cat_df.groupby("reset_week", as_index=False)[tag_cols].mean()
        .melt(id_vars=["reset_week"], value_vars=tag_cols, var_name="tag", value_name="pct")
    )
    time_tags["tag_label"] = time_tags["tag"].map(dict(zip(tag_cols, tag_labels)))

    chart = (
        alt.Chart(time_tags)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("pct:Q", title="Avg prevalence (%)"),
            color=alt.Color("tag_label:N", title="Tag", scale=alt.Scale(domain=tag_order, range=list(HEATMAP_SCHEME))),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("tag_label:N", title="Tag"),
                alt.Tooltip("pct:Q", title="Prevalence", format=".1f"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------- Tab: Market Saturation


def render_market_saturation(sat_dc, datacenter):
    st.subheader("Market saturation / concurrency")
    st.caption(
        "Estimates how many other groups are recruiting for the same duty at the same time. "
        f"{_window_caption(sat_dc)}"
    )
    if sat_dc.empty:
        st.info("No saturation data for this data center yet.")
        return

    cats = sorted(sat_dc["content_category"].dropna().unique().tolist())
    cat = st.selectbox("Content type", cats, index=_pick(cats, "savage"), key="sat_cat")
    cat_df = sat_dc[sat_dc["content_category"] == cat]

    if cat_df.empty:
        st.info("No data for this content type.")
        return

    # KPI cards
    avg_conc = cat_df["avg_concurrent"].mean()
    max_conc = cat_df["max_concurrent"].max()
    zero_comp = cat_df["zero_competition"].mean()
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg concurrency", f"{avg_conc:.1f}")
    c2.metric("Peak concurrency", f"{max_conc:.0f}")
    c3.metric("Avg zero-comp %", f"{zero_comp:.0f}%")

    st.divider()
    st.markdown("**Concurrency by duty × hour**")
    sat_heatmap = cat_df.groupby(["duty", "post_hour"], as_index=False)["avg_concurrent"].mean()
    sat_heatmap = sat_heatmap.sort_values("avg_concurrent", ascending=False).head(20)

    chart = (
        alt.Chart(sat_heatmap)
        .mark_rect()
        .encode(
            x=alt.X("post_hour:O", title="Hour (UTC)"),
            y=alt.Y("duty:N", title="Duty", sort="-x"),
            color=alt.Color("avg_concurrent:Q", title="Avg concurrency", scale=alt.Scale(scheme="viridis")),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("post_hour:O", title="Hour"),
                alt.Tooltip("avg_concurrent:Q", title="Avg concurrency", format=".1f"),
                alt.Tooltip("max_concurrent:Q", title="Max concurrency", format=".0f"),
                alt.Tooltip("zero_competition:Q", title="Zero-comp %", format=".1f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(style_chart(chart), width="stretch")

    st.divider()
    st.markdown("**Zero-competition chance by duty**")
    duty_zero = (
        cat_df.groupby("duty", as_index=False)["zero_competition"]
        .mean()
        .sort_values("zero_competition", ascending=False)
        .head(15)
    )
    chart = (
        alt.Chart(duty_zero)
        .mark_bar()
        .encode(
            x=alt.X("zero_competition:Q", title="Zero-comp %", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("duty:N", title="Duty", sort="-x"),
            color=alt.Color("zero_competition:Q", title="Zero-comp %", scale=alt.Scale(scheme="greens")),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("zero_competition:Q", title="Zero-comp %", format=".1f"),
                alt.Tooltip("avg_concurrent:Q", title="Avg concurrency", format=".1f"),
            ],
        )
        .properties(height=320)
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
intent_dc = dc_mask(intent)
travel_dc = dc_mask(travel)
ilvl_dc = dc_mask(ilvl)
tags_dc = dc_mask(tags)
sat_dc = dc_mask(saturation)

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

    # Quick-select buttons for common ranges
    q1, q2, q3 = st.sidebar.columns(3)
    if q1.button("8w", key="qbtn_8w", use_container_width=True):
        st.session_state.flt_weeks = (week_dates[-8], week_dates[-1])
    if q2.button("16w", key="qbtn_16w", use_container_width=True):
        st.session_state.flt_weeks = (week_dates[-16], week_dates[-1])
    if q3.button("All", key="qbtn_all", use_container_width=True):
        st.session_state.flt_weeks = (week_dates[0], week_dates[-1])
else:
    st.sidebar.caption("Not enough weekly history yet.")
    duty_range, role_range = duty_dc, role_dc

with st.sidebar:
    st.divider()
    st.caption("Data is refreshed periodically, not live. See the **FAQ** page for methodology and privacy.")

tab_overview, tab_timing, tab_duties, tab_roles, tab_outcomes, tab_intent, tab_ilvl, tab_tags, tab_sat = st.tabs(
    ["📊 Overview", "⏰ When to Post", "📈 Duty Trends", "🛡️ Roles", "✅ Fill Outcomes", "🎯 Intent & Travel", "⚔️ ILvl Gating", "🏷️ Tags", "📊 Saturation"]
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
with tab_intent:
    render_intent_travel(intent_dc, travel_dc, datacenter)
with tab_ilvl:
    render_ilvl_gating(ilvl_dc, datacenter)
with tab_tags:
    render_listing_tags(tags_dc, datacenter)
with tab_sat:
    render_market_saturation(sat_dc, datacenter)
