# Dashboard

Public Streamlit dashboard showcasing the FFXIV Party Finder gold marts.

It queries the small pre-aggregated `gold.*` tables **once per cold start**, caches the results in
memory (`@st.cache_data`), and does all filtering/shaping in pandas.
There is no per-interaction BigQuery traffic, so viewer activity cannot run up query costs.

Hosted free on [Streamlit Community Cloud](https://streamlit.io/cloud); one query per mart per cold
start reads only public aggregate data.

## Run locally

Uses Application Default Credentials when no Streamlit secret is present:

```bash
gcloud auth application-default login
pip install -r requirements.txt
make run-dashboard          # from repo root, or:
streamlit run services/dashboard/streamlit_app.py
```

Config via env vars (defaults in parentheses): `BQ_PROJECT` (`ff14-pf-data`), `BQ_DATASET` (`gold`),
`CACHE_TTL` seconds (`3600`).

## Service account (one-time, read-only, gold dataset only)

Community Cloud runs outside GCP, so it can't use ADC - it needs a key. Scope it so a leak only
exposes public gold aggregates (never `bronze`, which holds real character names).

```bash
# 1. dedicated service account
gcloud iam service-accounts create dashboard-reader \
  --project=ff14-pf-data --display-name="Streamlit dashboard (read-only gold)"

# 2. permission to run query jobs (project level)
gcloud projects add-iam-policy-binding ff14-pf-data \
  --member="serviceAccount:dashboard-reader@ff14-pf-data.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# 3. read access to the GOLD DATASET ONLY (dataset ACL, not project-wide dataViewer)
bq add-iam-policy-binding \
  --member="serviceAccount:dashboard-reader@ff14-pf-data.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" \
  ff14-pf-data:gold

# 4. generate a key (do NOT commit it)
gcloud iam service-accounts keys create dashboard-reader-key.json \
  --iam-account=dashboard-reader@ff14-pf-data.iam.gserviceaccount.com
```

Then map the key JSON fields into a `[gcp_service_account]` block - see `.streamlit/secrets.toml.example`.

## Deploy to Community Cloud

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io) -> **New app** -> select the repo/branch and set
   the main file to `services/dashboard/streamlit_app.py`.
3. **Advanced settings -> Secrets:** paste the `[gcp_service_account]` block.
4. Deploy. The public `*.streamlit.app` URL is your dashboard.
