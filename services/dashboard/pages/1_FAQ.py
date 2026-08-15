"""FAQ / About page. Sets expectations about freshness and anonymity, and
explains how the data is produced."""

import streamlit as st

from theme import CURRENT_SAVAGE_TIER, inject_css

st.set_page_config(page_title="FAQ - FFXIV Party Finder Analytics", page_icon="❓", layout="wide")
inject_css()

st.title("❓ FAQ & About")

# --- Intro card ---
st.markdown(
    f"""
<div style="background: #1B2430; border: 1px solid #2A3644; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
This dashboard is a <strong>portfolio showcase</strong> built on a real data pipeline that
scrapes public <a href="https://www.finalfantasyxiv.com" target="_blank">Final Fantasy XIV</a> Party Finder
listings from <a href="https://xivpf.com" target="_blank">xivpf.com</a>. It is meant to demonstrate a
data-engineering project end to end, not to be a live tool.
</div>
""",
    unsafe_allow_html=True,
)

st.subheader("Is this data live?")
st.markdown(
    """
**No — and that's by design.** The pipeline runs in batches and the dashboard is
refreshed manually / periodically. Numbers can be hours or days behind, and that
is intentional: this is a showcase of a batch analytics pipeline, not a real-time
Party Finder tracker. Don't rely on it to decide whether a specific party is up
right now.
"""
)

st.subheader("Can I use this to look up or track a player?")
st.markdown(
    """
**No.** Party Finder creator names are stripped of identity before they ever
reach the layers this dashboard reads. Real character names live only in the raw
(Bronze) layer, which is private to the backend administrator. Everything the
dashboard can see is reduced to a **pseudonymous hash** and **initials** at the
Bronze → Silver boundary.

So even though these are public listings, this app **cannot be used to find,
follow, or identify any individual player**. If that's what you were hoping to do:
it genuinely doesn't work that way, on purpose.
"""
)

st.subheader("Where does the data come from?")
st.markdown(
    """
The pipeline follows a standard medallion architecture on Google Cloud:

1. **Scrape** — a scheduled job pulls xivpf.com listings every ~15 minutes and
   writes the raw HTML/JSON to an append-only Cloud Storage bucket (the immutable
   source of truth).
2. **Bronze** — raw listings are loaded into BigQuery as-is.
3. **Silver** — listings are sessionized into a lifecycle fact table (a party's
   snapshots stitched into one "session"), and creator identities are replaced
   with pseudonymous hashes and initials.
4. **Gold** — small, pre-aggregated marts (fill funnel, activity heatmap, duty &
   role trends) that this dashboard reads once per load and shapes in-memory.

**Stack:** Python on Cloud Run, BigQuery (medallion architecture), Dataform for
SQL transformations, and Terraform for infrastructure.
"""
)

st.subheader("What do the numbers actually measure?")
st.markdown(
    f"""
- **Listings / sessions** — a "session" is one continuous Party Finder posting.
  Repeated snapshots of the same party are stitched into a single session.
- **Fill rate** — whether a party filled is *inferred* from it being delisted
  while one slot short of full. It's an estimate, not a confirmed outcome.
- **Roles, not jobs** — the source only exposes role buckets (tank / healer /
  DPS), not individual jobs (WAR, WHM, etc.), so per-job stats aren't available.
- **Reset week** — weeks are anchored to the FFXIV weekly reset, Tuesday 08:00 UTC.
- **Current savage tier** — {CURRENT_SAVAGE_TIER['label']}, used for context and
  to highlight current-tier duties on the main page.
"""
)

st.subheader("Which regions and data centers are covered?")
st.markdown(
    """
Coverage depends on what appears in the scraped listings — typically the NA, EU,
JP, and OCE regions and their data centers. Use the **Region** and **Data center**
filters in the **sidebar** to scope the view; it defaults to **NA / Aether**.
"""
)
