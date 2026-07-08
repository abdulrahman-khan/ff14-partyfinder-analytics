# Reference data

Static reference data and the one-time scripts that load it. These are **not** part of the
hourly Dataform DAG — they change rarely and are loaded manually.

## `worlds.csv`

World → datacenter → region lookup for every FFXIV world. Source for `silver.dim_worlds`,
which `fct_listings` joins against to attach DC/region to both the PF world and the creator
world. Update this file when Square Enix adds worlds or data centers.

## `duties.csv`

Curated duty classification: one row per known duty with `content_category` and the difficulty
flags. Source for `bronze.raw_duties_reference`, which `dim_duties` treats as authoritative,
falling back to a name-suffix parse only for scraped duties not yet listed here. Reclassifying a
duty is a CSV edit, no code change. Loaded into a native table, not managed by Dataform or Terraform.

Run this whenever `duties.csv` changes:

```bash
make load-duties
```

## `load_dim_worlds.sql`

Rebuilds `silver.dim_worlds` from the `bronze.raw_worlds` external table (which points at
`worlds.csv` in GCS). `silver.dim_worlds` is intentionally **not** managed by Dataform or
Terraform — it's a static table declared as a stub in Dataform so models can `ref()` it.

### One-time / on-change load procedure

Run this whenever `worlds.csv` changes:

```bash
# 1. Upload the CSV to the raw bucket (backs the bronze.raw_worlds external table)
gsutil cp reference/worlds.csv gs://ff14-pf-data-raw/worlds_data/worlds.csv

# 2. Rebuild silver.dim_worlds from it
bq query --nouse_legacy_sql --project_id=ff14-pf-data "$(cat reference/load_dim_worlds.sql)"
```

> The `bronze.raw_worlds` external table must already exist (defined in
> `terraform/bigquery_worlds.tf`) and point at `gs://ff14-pf-data-raw/worlds_data/worlds.csv`.
