"""Shared BigQuery access for the dashboard pages.

Pulls the small pre-aggregated gold tables once per cold start, caches them in
memory, and hands back pandas frames. No per-interaction BigQuery queries -
every page does its shaping in pandas.
"""

import os

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
from streamlit.errors import StreamlitSecretNotFoundError

BQ_PROJECT = os.environ.get("BQ_PROJECT", "ff14-pf-data")
BQ_DATASET = os.environ.get("BQ_DATASET", "gold")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "3600"))  # data is refreshed manually; stale is fine
CACHE_VERSION = "2026-09-04a"  # bump to bust stale @st.cache_data when schemas change

# 1=Sunday .. 7=Saturday, matching mart_activity_heatmap.post_weekday
WEEKDAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

DEFAULT_REGION = "NA"
DEFAULT_DATACENTER = "Aether"


@st.cache_resource
def get_client() -> bigquery.Client:
    """BigQuery client from the Streamlit secret key, or ADC for local dev."""
    try:
        sa_info = st.secrets["gcp_service_account"]
    except (KeyError, StreamlitSecretNotFoundError):
        return bigquery.Client(project=BQ_PROJECT)  # local ADC; no secrets file
    creds = service_account.Credentials.from_service_account_info(sa_info)
    return bigquery.Client(credentials=creds, project=BQ_PROJECT)


@st.cache_data(ttl=CACHE_TTL)
def load(table: str, where: str | None = None, _version: str = CACHE_VERSION) -> pd.DataFrame:
    """One query per mart per cold start; everything downstream is in-memory pandas.
    _version is not used in the query but forces cache invalidation when bumped.
    where is a literal SQL condition supplied by the caller (never user input) -
    pushing a filter down here cuts bytes scanned/transferred for callers that only
    need a subset of a mart (e.g. the raid-scoped main page filtering to Savage/Ultimate)."""
    query = f"SELECT * FROM `{BQ_PROJECT}.{BQ_DATASET}.{table}`"
    if where:
        query += f" WHERE {where}"
    return get_client().query(query).to_dataframe()
