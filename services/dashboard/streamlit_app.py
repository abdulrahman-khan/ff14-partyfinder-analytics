"""Public summary dashboard for the FFXIV Party Finder gold marts.

Pulls the small pre-aggregated gold tables once per cold start, caches them in
memory, and does all shaping in pandas. No per-interaction BigQuery queries.
"""

import os

import altair as alt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

BQ_PROJECT = os.environ.get("BQ_PROJECT", "ff14-pf-data")
BQ_DATASET = os.environ.get("BQ_DATASET", "gold")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "3600"))  # data is refreshed manually; stale is fine

# 1=Sunday .. 7=Saturday, matching mart_activity_heatmap.post_weekday
WEEKDAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@st.cache_resource
def get_client() -> bigquery.Client:
    """BigQuery client from the Streamlit secret key, or ADC for local dev."""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        return bigquery.Client(credentials=creds, project=BQ_PROJECT)
    return bigquery.Client(project=BQ_PROJECT)


@st.cache_data(ttl=CACHE_TTL)
def load(table: str) -> pd.DataFrame:
    """One query per mart per cold start; everything downstream is in-memory pandas."""
    return get_client().query(
        f"SELECT * FROM `{BQ_PROJECT}.{BQ_DATASET}.{table}`"
    ).to_dataframe()


st.set_page_config(page_title="FFXIV Party Finder Analytics", page_icon="⚔️", layout="wide")

st.title("⚔️ FFXIV Party Finder Analytics")
st.markdown(
    "A look at **Final Fantasy XIV** Party Finder activity, scraped from "
    "[xivpf.com](https://xivpf.com) and modelled through a BigQuery data pipeline. "
    "Data is refreshed periodically - this is a showcase, not live analytics."
)

funnel = load("mart_fill_funnel")
heatmap = load("mart_activity_heatmap")
trends = load("mart_content_trends")

# --- KPI row ---
total_sessions = int(funnel["sessions"].sum())
overall_fill_pct = (
    funnel["filled"].sum() / funnel["sessions"].sum() * 100 if total_sessions else 0.0
)
distinct_duties = int(trends["duty"].nunique())
regions = funnel["pf_region"].nunique()
datacenters = funnel["pf_datacenter"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Listing sessions", f"{total_sessions:,}")
c2.metric("Overall fill rate", f"{overall_fill_pct:.1f}%")
c3.metric("Duties tracked", f"{distinct_duties:,}")
c4.metric("Regions / datacenters", f"{regions} / {datacenters}")

st.divider()

# --- Activity heatmap (weekday x hour) ---
st.subheader("When is Party Finder busiest?")
st.caption("Total listings posted by day of week and hour (UTC), across all regions.")

hm = (
    heatmap.groupby(["day_name", "post_hour"], as_index=False)["listings_posted"].sum()
)
heatmap_chart = (
    alt.Chart(hm)
    .mark_rect()
    .encode(
        x=alt.X("post_hour:O", title="Hour of day (UTC)"),
        y=alt.Y("day_name:O", title=None, sort=WEEKDAY_ORDER),
        color=alt.Color("listings_posted:Q", title="Listings", scale=alt.Scale(scheme="magma")),
        tooltip=[
            alt.Tooltip("day_name:N", title="Day"),
            alt.Tooltip("post_hour:O", title="Hour"),
            alt.Tooltip("listings_posted:Q", title="Listings", format=","),
        ],
    )
    .properties(height=280)
)
st.altair_chart(heatmap_chart, use_container_width=True)

st.divider()

col_left, col_right = st.columns(2)

# --- Sessions by content category ---
with col_left:
    st.subheader("Listings by content type")
    by_category = (
        funnel.groupby("content_category", as_index=False)["sessions"]
        .sum()
        .sort_values("sessions", ascending=False)
    )
    category_chart = (
        alt.Chart(by_category)
        .mark_bar()
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
    st.altair_chart(category_chart, use_container_width=True)

# --- Top duties in the latest reset week ---
with col_right:
    latest_week = trends["reset_week"].max()
    st.subheader("Most listed duties")
    st.caption(f"Reset week of {latest_week:%Y-%m-%d}.")
    top_duties = (
        trends[trends["reset_week"] == latest_week]
        .groupby("duty", as_index=False)["listings"]
        .sum()
        .sort_values("listings", ascending=False)
        .head(15)
    )
    duties_chart = (
        alt.Chart(top_duties)
        .mark_bar()
        .encode(
            x=alt.X("listings:Q", title="Listings"),
            y=alt.Y("duty:N", title=None, sort="-x"),
            tooltip=[
                alt.Tooltip("duty:N", title="Duty"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(duties_chart, use_container_width=True)
