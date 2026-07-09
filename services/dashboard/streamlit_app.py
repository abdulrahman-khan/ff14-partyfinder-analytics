"""Public summary dashboard for the FFXIV Party Finder gold marts.

Main page: region / data center filters, DC-scoped KPIs, and an activity
heatmap. Data is loaded once per cold start (see data.py) and shaped in pandas;
there are no per-interaction BigQuery queries. Styling lives in theme.py and is
documented in STYLING.md.
"""

import datetime as dt

import altair as alt
import pandas as pd
import streamlit as st

from data import DEFAULT_DATACENTER, DEFAULT_REGION, WEEKDAY_ORDER, load
from theme import BLUE, CURRENT_SAVAGE_TIER, GOLD, HEATMAP_SCHEME, inject_css, style_chart

st.set_page_config(page_title="FFXIV Party Finder Analytics", page_icon="⚔️", layout="wide")
inject_css()

funnel = load("mart_fill_funnel")
heatmap = load("mart_activity_heatmap")
trends = load("mart_content_trends")
weekly = load("mart_weekly_datacenter")

st.title("⚔️ FFXIV Party Finder Analytics")
st.markdown(
    "A look at **Final Fantasy XIV** Party Finder activity, scraped from "
    "[xivpf.com](https://xivpf.com) and modelled through a BigQuery data pipeline. "
    "Data is refreshed periodically, not live - see the **FAQ** in the sidebar."
)


def _pick(options: list[str], preferred: str) -> int:
    """Index of the preferred option, or 0 if it isn't present."""
    return options.index(preferred) if preferred in options else 0


# --- Global filters ---
regions = sorted(funnel["pf_region"].dropna().unique().tolist())
fcol1, fcol2, _ = st.columns([1, 1, 2])
region = fcol1.selectbox("Region", regions, index=_pick(regions, DEFAULT_REGION))

datacenters = sorted(
    funnel.loc[funnel["pf_region"] == region, "pf_datacenter"].dropna().unique().tolist()
)
datacenter = fcol2.selectbox(
    "Data center", datacenters, index=_pick(datacenters, DEFAULT_DATACENTER)
)

dc_mask = lambda df: df[(df["pf_region"] == region) & (df["pf_datacenter"] == datacenter)]
funnel_dc = dc_mask(funnel)
heatmap_dc = dc_mask(heatmap)
weekly_dc = dc_mask(weekly)

st.divider()

# --- KPI row (scoped to the selected data center) ---
total_sessions = int(funnel_dc["sessions"].sum())
fill_pct = (
    funnel_dc["filled"].sum() / funnel_dc["sessions"].sum() * 100 if total_sessions else 0.0
)

# "Last week" = the most recent fully completed reset week (a week is complete
# once we're 7 days past its Tuesday 08:00 UTC start). The latest row in the mart
# is usually the current, in-progress week, which we skip so the KPI isn't a
# misleading partial count.
last_week_listings, last_week_delta, last_week_label = 0, None, "Listings last week"
if not weekly_dc.empty:
    by_week = (
        weekly_dc.assign(reset_week=pd.to_datetime(weekly_dc["reset_week"]))
        .groupby("reset_week")["listings"]
        .sum()
        .sort_index()
    )
    today = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
    complete = by_week[by_week.index + pd.Timedelta(days=7) <= today]
    ref = complete if not complete.empty else by_week
    latest = ref.index[-1]
    last_week_listings = int(ref.loc[latest])
    pos = by_week.index.get_loc(latest)
    if pos >= 1:
        last_week_delta = last_week_listings - int(by_week.iloc[pos - 1])
    last_week_label = f"Listings, week of {latest:%b %d}"

busiest = "-"
if not heatmap_dc.empty:
    by_hour = heatmap_dc.groupby("post_hour")["listings_posted"].sum()
    if not by_hour.empty:
        busiest = f"{int(by_hour.idxmax()):02d}:00 UTC"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total listings", f"{total_sessions:,}")
c2.metric(
    last_week_label,
    f"{last_week_listings:,}",
    delta=None if last_week_delta is None else f"{last_week_delta:+,}",
)
c3.metric("Fill rate", f"{fill_pct:.1f}%")
c4.metric("Busiest hour", busiest)

st.divider()

# --- Activity heatmap (this data center) ---
st.subheader(f"When is Party Finder busiest on {datacenter}?")
st.caption("Listings posted by day of week and hour (UTC).")

if heatmap_dc.empty:
    st.info("No activity data for this data center yet.")
else:
    hm = heatmap_dc.groupby(["day_name", "post_hour"], as_index=False)["listings_posted"].sum()
    heatmap_chart = (
        alt.Chart(hm)
        .mark_rect()
        .encode(
            x=alt.X("post_hour:O", title="Hour of day (UTC)"),
            y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
            color=alt.Color(
                "listings_posted:Q",
                title="Listings",
                scale=alt.Scale(scheme=HEATMAP_SCHEME),
            ),
            tooltip=[
                alt.Tooltip("day_name:N", title="Day"),
                alt.Tooltip("post_hour:O", title="Hour"),
                alt.Tooltip("listings_posted:Q", title="Listings", format=","),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(style_chart(heatmap_chart), use_container_width=True)

st.divider()

col_left, col_right = st.columns(2)

# --- Listings by content type (this data center) ---
with col_left:
    st.subheader("Listings by content type")
    by_category = (
        funnel_dc.groupby("content_category", as_index=False)["sessions"]
        .sum()
        .sort_values("sessions", ascending=False)
    )
    if by_category.empty:
        st.info("No listings for this data center yet.")
    else:
        category_chart = (
            alt.Chart(by_category)
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
        st.altair_chart(style_chart(category_chart), use_container_width=True)

# --- Most listed duties in the latest reset week (region-wide) ---
with col_right:
    st.subheader("Most listed duties")
    region_trends = trends[trends["pf_region"] == region]
    if region_trends.empty:
        st.info("No duty trends for this region yet.")
    else:
        latest_week = region_trends["reset_week"].max()
        st.caption(
            f"Reset week of {latest_week:%Y-%m-%d}, {region} region-wide. "
            f"Current tier: {CURRENT_SAVAGE_TIER['label']} (gold)."
        )
        top_duties = (
            region_trends[region_trends["reset_week"] == latest_week]
            .groupby("duty", as_index=False)["listings"]
            .sum()
            .sort_values("listings", ascending=False)
            .head(15)
        )
        top_duties["current_tier"] = top_duties["duty"].isin(CURRENT_SAVAGE_TIER["duties"])
        duties_chart = (
            alt.Chart(top_duties)
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
            .properties(height=320)
        )
        st.altair_chart(style_chart(duties_chart), use_container_width=True)
