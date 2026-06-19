# Gold Marts & the Lifecycle Model

The gold layer ships **pre-aggregated, chart-ready marts** — each one is already at the exact grain a dashboard tile needs, and each surfaces a *rate / duration / delta / flow*, not a bare count. Region is a dimension in every mart (no hardcoded NA).

Everything hangs off one keystone in silver: **`fct_listing_lifecycle`**.

---

## Keystone: `silver.fct_listing_lifecycle`

`fct_listings` is a **periodic snapshot fact** — one row per listing per 15-min scrape, i.e. a time series of each listing's state. `fct_listing_lifecycle` collapses that into an **accumulating snapshot fact**: one row per *listing session*, carrying the milestones of its life.

- **Grain:** `(listing_id, session_start)` — one row per session.
- **Sessionization (gap-and-islands):** `listing_id` is content-hashed, so an identical re-post later reuses the id. A gap > `SESSION_GAP_MIN` (30 min) between consecutive scrapes starts a new session, so re-posts become distinct rows.
- **Derived metrics:** `observed_lifetime_min`, `time_to_full_min`, `reached_full`, `fill_rate_pct`, `bottleneck_role`, `outcome` (`filled` / `expired_partial` / `flash`), `is_right_censored`.
- **Incremental:** merges on `[listing_id, session_start]` over a 3-day lookback (`updatePartitionFilter` bounds the merge to recent partitions); closed sessions are immutable.

**Caveats (documented in the model `description`):** ±15 min time-to-fill resolution; a mid-life description edit changes the id (sessionization handles re-posts, not edits); single-snapshot "flash" sessions are right-censored (instant-fill vs instant-expire indistinguishable); "filled" = last observed state reached `slots_total`.

---

## Mart catalog

| Mart | Grain | Headline metric(s) | Question it answers | Viz |
|---|---|---|---|---|
| `mart_time_to_fill` ⭐ | duty × region × DC × weekday × hour | `median_time_to_fill_min`, `p90`, `fill_rate_pct` | "When should I post to fill fast?" | weekday×hour heatmap |
| `mart_role_demand` | content_category × region × DC × hour | open tank/healer/dps **share %**, `most_common_bottleneck` | "Which role is the bottleneck?" | stacked bar |
| `mart_activity_heatmap` | region × DC × weekday × hour | `listings_posted`, `avg_lifetime_min`, `fill_rate_pct` | "When is PF busiest on my DC?" | weekday×hour heatmap |
| `mart_content_trends` | duty × region × reset_week | `wow_pct_change`, `rank_in_region_week` | "What content is hot / fading?" | ranked bars / trend |
| `mart_traveller_flow` | region × datacenter | `inbound`, `outbound`, `net_flow` | "Which DCs import/export players?" | diverging bar / sankey |

Notes:
- All marts source from `fct_listing_lifecycle` (one row per session → no scrape double-counting).
- `mart_content_trends` still counts listings, but the *insight* is the week-over-week change and rank — the count is just the input.
- `mart_traveller_flow` is scoped to intra-region DC travel (`creator_region = pf_region`), matching how FFXIV data-center travel works; within a region `net_flow` sums to ~0.
- `mart_activity_heatmap` measures **posting activity** from the session table (cheap), not concurrent-live snapshots — it replaces the old `mart_activity_hour_datacenter`.

---

## Shared logic — `dataform/includes/ffxiv.js`

- `SESSION_GAP_MIN` — sessionization threshold (30).
- `resetWeekStart(tsExpr)` / `resetWeekBounds(period)` — FFXIV reset-week math (Tuesday 08:00 UTC), centralized instead of copy-pasted across marts. Used by `dim_date` and available to any model.

## Data quality

- `silver.assert_lifecycle_freshness` — blocking assertion; fails if the newest session is > 3h old.
- `silver.qa_unmatched_worlds` — non-blocking monitoring view; lists `raw_listings.world` values that don't match `dim_worlds` (these silently drop from region/DC rollups — see improvements.md #6).
- Each mart carries `rowConditions` assertions (shares/rates within 0–100, non-negative durations).

---

## Verification (run after `dataform run`)

```sql
-- sessions >= distinct listing_id (sessionization splits, never merges)
SELECT COUNT(*) AS sessions, COUNT(DISTINCT listing_id) AS ids
FROM silver.fct_listing_lifecycle;

-- outcome distribution + mean fill time
SELECT outcome, COUNT(*) AS n, ROUND(AVG(time_to_full_min),1) AS avg_ttf_min
FROM silver.fct_listing_lifecycle GROUP BY outcome;

-- hero sanity: prime-time should fill faster
SELECT post_hour, median_time_to_fill_min, fill_rate_pct
FROM gold.mart_time_to_fill
WHERE pf_region='NA' AND content_category='savage'
ORDER BY post_hour;

-- traveller flow nets to ~0 within a region
SELECT region, SUM(net_flow) AS should_be_zero
FROM gold.mart_traveller_flow GROUP BY region;
```
