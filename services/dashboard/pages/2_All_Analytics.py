"""General, non-fight-specific Party Finder analytics: activity, fill outcomes, cross-DC
travel, and listing description tags across all content categories.

This is the broader companion to the fight-scoped main page (streamlit_app.py), which
narrows everything to one Savage/Ultimate fight a raider is progging. Data is loaded once
per cold start (see data.py) and shaped in pandas. Styling lives in theme.py, documented
in STYLING.md.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import altair as alt
import pandas as pd
import streamlit as st
from data import DEFAULT_DATACENTER, DEFAULT_REGION, WEEKDAY_ORDER, load
from theme import (
    ACCENT_BLUE as BLUE,
)
from theme import (
    ACCENT_GREEN,
    ACCENT_PURPLE,
    HEATMAP_SCHEME,
    OUTCOME_COLORS,
    inject_css,
    style_chart,
)

st.set_page_config(page_title="All Analytics - FFXIV Party Finder", page_icon="📊", layout="wide")
inject_css()

MART_NAMES = [
    "mart_fill_funnel",
    "mart_activity_heatmap",
    "mart_duty_trends",
    "mart_travel_demand",
    "mart_listing_tags",
]
with ThreadPoolExecutor(max_workers=len(MART_NAMES)) as pool:
    marts = dict(zip(MART_NAMES, pool.map(load, MART_NAMES), strict=True))

funnel = marts["mart_fill_funnel"]
heatmap = marts["mart_activity_heatmap"]
duty_trends = marts["mart_duty_trends"]
travel = marts["mart_travel_demand"]
tags = marts["mart_listing_tags"]

duty_trends["reset_week"] = pd.to_datetime(duty_trends["reset_week"])
travel["reset_week"] = pd.to_datetime(travel["reset_week"])
tags["reset_week"] = pd.to_datetime(tags["reset_week"])


def _pick(options: list, preferred: str) -> int:
    return options.index(preferred) if preferred in options else 0


def _window_caption(df: pd.DataFrame) -> str:
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

    last_listings, last_delta, last_label = 0, None, "Listings last week"
    if not duty_dc.empty:
        by_week = duty_dc.groupby("reset_week")["listings"].sum().sort_index()
        today = pd.Timestamp(dt.datetime.now(dt.UTC).date())
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
    c2.metric(
        last_label, f"{last_listings:,}", delta=None if last_delta is None else f"{last_delta:+,}"
    )
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
                color=alt.Color(
                    "listings_posted:Q", title="Listings", scale=alt.Scale(scheme=HEATMAP_SCHEME)
                ),
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
        labels = (
            alt.Chart(by_cat)
            .mark_text(align="left", baseline="middle", dx=5, fontSize=11, color="#E6E6E6")
            .encode(text=alt.Text("sessions:Q", format=","))
        )
        st.altair_chart(style_chart(bars + labels), width="stretch")


# ------------------------------------------------------------- Tab: Fill Outcomes


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
    long = agg.melt(
        id_vars=["content_category", "sessions"],
        value_vars=cols,
        var_name="outcome",
        value_name="count",
    )
    long["pct"] = (long["count"] / long["sessions"] * 100).round(1)
    long["outcome"] = long["outcome"].map(label_map)

    order = list(OUTCOME_COLORS)
    long["outcome_order"] = long["outcome"].map({o: i for i, o in enumerate(order)})
    chart = (
        alt.Chart(long)
        .mark_bar()
        .encode(
            x=alt.X(
                "count:Q", title="Share of listings", stack="normalize", axis=alt.Axis(format="%")
            ),
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


# ------------------------------------------------------------------- Tab: Travel


def render_travel(travel_dc, datacenter):
    st.subheader("Cross-DC / cross-region travel demand")
    st.caption("Share of listings posted by someone from a different DC or region.")
    if travel_dc.empty:
        st.info("No travel data for this data center yet.")
        return

    total_travel = int(travel_dc["sessions"].sum())
    imported = int(travel_dc["traveller"].sum() + travel_dc["voyager"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Total sessions", f"{total_travel:,}")
    c2.metric(
        "Imported",
        f"{imported:,}",
        f"{imported / total_travel * 100:.0f}%" if total_travel else "-",
    )
    c3.metric(
        "Local",
        f"{total_travel - imported:,}",
        f"{(total_travel - imported) / total_travel * 100:.0f}%" if total_travel else "-",
    )

    st.divider()
    st.markdown("**Travel share over time**")
    travel_wide = travel_dc.groupby("reset_week", as_index=False).agg(
        local=("local", "sum"), traveller=("traveller", "sum"), voyager=("voyager", "sum")
    )
    travel_wide = travel_wide.sort_values("reset_week")
    travel_long = travel_wide.melt(
        id_vars=["reset_week"],
        value_vars=["local", "traveller", "voyager"],
        var_name="type",
        value_name="count",
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
                    range=[ACCENT_GREEN, BLUE, ACCENT_PURPLE],
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


# --------------------------------------------------------------------- Tab: Tags


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

    tag_cols = [
        "loot_pct",
        "clear_pct",
        "one_per_job_pct",
        "weekly_unclaimed_pct",
        "duty_completion_pct",
        "duty_incomplete_pct",
    ]
    tag_labels = ["Loot", "Clear", "1/job", "Weekly", "Completion", "Incomplete"]
    tag_vals = [cat_df[c].mean() for c in tag_cols]

    cols = st.columns(6)
    for col, label, val in zip(cols, tag_labels, tag_vals, strict=True):
        col.metric(f"{label}%", f"{val:.0f}%")

    st.divider()
    st.markdown("**Tag prevalence by duty** (average %, top 20 duties by avg tag %)")
    duty_tags = (
        cat_df.groupby("duty", as_index=False)[tag_cols]
        .mean()
        .melt(id_vars=["duty"], value_vars=tag_cols, var_name="tag", value_name="pct")
        .sort_values("pct", ascending=False)
    )
    duty_tags["tag_label"] = duty_tags["tag"].map(dict(zip(tag_cols, tag_labels, strict=True)))
    tag_order = tag_labels

    duty_avg = duty_tags.groupby("duty")["pct"].mean().sort_values(ascending=False)
    top_duties = duty_avg.head(20).index.tolist()
    duty_tags = duty_tags[duty_tags["duty"].isin(top_duties)].sort_values("pct", ascending=False)

    chart = (
        alt.Chart(duty_tags)
        .mark_bar()
        .encode(
            x=alt.X("pct:Q", title="Avg prevalence (%)"),
            y=alt.Y("duty:N", title="Duty", sort="-x"),
            color=alt.Color(
                "tag_label:N",
                title="Tag",
                scale=alt.Scale(domain=tag_order, scheme="tableau10"),
            ),
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
        cat_df.groupby("reset_week", as_index=False)[tag_cols]
        .mean()
        .melt(id_vars=["reset_week"], value_vars=tag_cols, var_name="tag", value_name="pct")
    )
    time_tags["tag_label"] = time_tags["tag"].map(dict(zip(tag_cols, tag_labels, strict=True)))
    chart = (
        alt.Chart(time_tags)
        .mark_line(point=True, strokeWidth=2)
        .encode(
            x=alt.X("reset_week:T", title="Reset week"),
            y=alt.Y("pct:Q", title="Avg prevalence (%)"),
            color=alt.Color(
                "tag_label:N",
                title="Tag",
                scale=alt.Scale(domain=tag_order, scheme="tableau10"),
            ),
            tooltip=[
                alt.Tooltip("reset_week:T", title="Week"),
                alt.Tooltip("tag_label:N", title="Tag"),
                alt.Tooltip("pct:Q", title="Prevalence", format=".1f"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(style_chart(chart), width="stretch")


# ------------------------------------------------------------------------- Main

st.title("📊 All Analytics")
st.caption(
    "General Party Finder activity across every content type - looking for one specific "
    "raid fight instead? See the **Raid Finder** main page."
)

with st.sidebar:
    st.markdown("### 📊 All Analytics")
    st.divider()
    regions = sorted(funnel["pf_region"].dropna().unique().tolist())
    region = st.selectbox("Region", regions, index=_pick(regions, DEFAULT_REGION), key="flt_region")
    datacenters = sorted(
        funnel.loc[funnel["pf_region"] == region, "pf_datacenter"].dropna().unique().tolist()
    )
    datacenter = st.selectbox(
        "Data center", datacenters, index=_pick(datacenters, DEFAULT_DATACENTER), key="flt_dc"
    )
    st.divider()
    st.caption("Data is refreshed periodically, not live. See the **FAQ** page for methodology.")


def dc_mask(df):
    return df[(df["pf_region"] == region) & (df["pf_datacenter"] == datacenter)]


funnel_dc = dc_mask(funnel)
heatmap_dc = dc_mask(heatmap)
duty_dc = dc_mask(duty_trends)
travel_dc = dc_mask(travel)
tags_dc = dc_mask(tags)

tab_overview, tab_outcomes, tab_travel, tab_tags = st.tabs(
    ["📊 Overview", "✅ Fill Outcomes", "🎯 Travel", "🏷️ Tags"]
)
with tab_overview:
    render_overview(funnel_dc, heatmap_dc, duty_dc, datacenter)
with tab_outcomes:
    render_outcomes(funnel_dc, datacenter)
with tab_travel:
    render_travel(travel_dc, datacenter)
with tab_tags:
    render_listing_tags(tags_dc, datacenter)
