# Gold Marts & the Lifecycle Model

The gold layer ships **pre-aggregated, chart-ready marts** — each one is already at the exact grain a dashboard tile needs, and each surfaces a *rate / duration / delta / flow*, not a bare count. Region is a dimension in every mart (no hardcoded NA).

Everything hangs off one keystone in silver: **`fct_listing_lifecycle`**.

---

## Keystone: `silver.fct_listing_lifecycle`

`fct_listings` is a **periodic snapshot fact** — one row per listing per 15-min scrape, i.e. a time series of each listing's state. `fct_listing_lifecycle` collapses that into an **accumulating snapshot fact**: one row per *listing session*, carrying the milestones of its life.

- **Grain:** `(listing_id, session_start)` — one row per session.
- **Sessionization (gap-and-islands):** `listing_id` is content-hashed, so an identical re-post later reuses the id. A gap > `SESSION_GAP_MIN` (30 min) between consecutive scrapes starts a new session, so re-posts become distinct rows.
- **Derived metrics:** `observed_lifetime_min`, `time_to_full_min`, `reached_full`, `fill_rate_pct`, `bottleneck_role`, `outcome` (`filled` / `expired_partial` / `flash` / `live` / `multiparty`), `is_right_censored`.
- **Fill is inferred, not observed.** A full party (8/8) is never scrapeable - the listing delists the instant it completes, and `slots_filled` (which includes the recruiter) caps at `slots_total - 1` (7/8). So `reached_full` = a multi-snapshot session last seen one short of full that has since *disappeared* from PF (its `last_seen` precedes the data frontier by more than `SESSION_GAP_MIN`). Sessions still at the frontier are `outcome = 'live'` (unresolved) and finalize on a later incremental run. The frontier is the latest scrape in the data, not `CURRENT_TIMESTAMP()`, because the loader is manual and data can lag.
- **Intent tags:** `is_practice` / `is_duty_complete` are lifted from the snapshot `[Practice]` / `[Duty Complete]` description flags via `MAX` over the session (a tag set once holds for the session), feeding `mart_prog_vs_clear`. (The `[clear]` tag does not exist in xivpf data — `Duty Complete` is the reclear proxy.)
- **Clustering:** clustered `pf_region` first (then `duty_key`, `pf_world_key`), so region-scoped analysis (`WHERE pf_region = 'JP'`) prunes storage blocks — the reason we cluster rather than split silver into per-region tables.
- **Incremental:** merges on `[listing_id, session_start]` over a 3-day lookback (`updatePartitionFilter` bounds the merge to recent partitions); closed sessions are immutable.

**Caveats (documented in the model `description`):** ±15 min time-to-fill resolution; a mid-life description edit changes the id (sessionization handles re-posts, not edits); single-snapshot "flash" sessions are right-censored (post time unknown, fill un-inferable); `fill_rate_pct` in the marts is over *resolved* sessions (`filled + expired_partial`), excluding `flash` and `live`; **multi-party content** (`slots_total > 8` - alliance raids, Chaotic, PvP custom) only ever exposes the recruiter's own 8-slot party while `slots_total` is a variable alliance-wide counter, so per-party fill is unobservable - these are `outcome = 'multiparty'` and excluded from all fill metrics (still counted for activity/volume). This is a source limitation of xivpf, not a scraper bug.

**Alliance vs Chaotic.** `dim_duties` flags Alliance Raids (`is_alliance_raid`, `content_category = 'alliance'`) and Chaotic (`is_chaotic_alliance`, `content_category = 'chaotic'`) from the curated master `reference/duties.csv`, with a `(Chaotic)` name-suffix fallback for a scraped duty not yet in the CSV. Normal alliance-raid listings are a mix of roulette-farm, mechanics tours, and **social/RP use of the 24-person alliance chat** (most have empty descriptions) - so `alliance` activity is *not* raid demand. Chaotic, by contrast, is genuine high-end recruitment (item-level gates, farm rotations). Both are `multiparty` for fill purposes.

---

## Mart catalog

| Mart | Grain | Headline metric(s) | Question it answers | Viz |
|---|---|---|---|---|
| `mart_time_to_fill` ⭐ | duty × region × DC × weekday × hour | `median_time_to_fill_min`, `p90`, `fill_rate_pct` | "When should I post to fill fast?" | weekday×hour heatmap |
| `mart_role_demand` | content_category × region × DC × hour | open tank/healer/dps **share %**, `most_common_bottleneck` | "Which role is the bottleneck?" | stacked bar |
| `mart_activity_heatmap` | region × DC × weekday × hour | `listings_posted`, `avg_lifetime_min`, `fill_rate_pct` | "When is PF busiest on my DC?" | weekday×hour heatmap |
| `mart_content_trends` | duty × region × reset_week | `wow_pct_change`, `rank_in_region_week` | "What content is hot / fading?" | ranked bars / trend |
| `mart_traveller_flow` | region × datacenter | `inbound`, `outbound`, `net_flow` | "Which DCs import/export players?" | diverging bar / sankey |
| `mart_fill_funnel` | content × region × DC | `filled_pct`, `expired_partial_pct`, `flash_pct` | "What share of listings ever fill?" | stacked / funnel bar |
| `mart_supply_demand_gap` | content × region × DC × post-hour | `gap_index`, `avg_seats_unfilled`, `fill_rate_pct` | "Where do seats stay empty (matchmaking gaps)?" | region×DC×hour heatmap |
| `mart_prog_vs_clear` | duty × region × intent | `fill_rate_pct`, `median_time_to_fill_min` | "Do prog parties fill slower than reclears?" | grouped bars (prog vs clear) |

Notes:
- All marts source from `fct_listing_lifecycle` (one row per session → no scrape double-counting).
- `mart_content_trends` still counts listings, but the *insight* is the week-over-week change and rank — the count is just the input.
- `mart_fill_funnel` is the *denominator* for the rest of the layer: a fast `median_time_to_fill` only means something once you know `filled_pct`. `flash_pct` is an ambiguity band (single-snapshot, right-censored), not a failure rate.
- `mart_supply_demand_gap` crosses party *supply* (session count) against unmet *demand* (`avg_seats_unfilled`); `gap_index = avg_seats_unfilled * (1 - fill_rate_pct/100)` is high where many parties post but seats stay empty.
- `mart_prog_vs_clear` derives `intent` from the `[Practice]` / `[Duty Complete]` description tags, now carried on `fct_listing_lifecycle` as `is_practice` / `is_duty_complete` (`MAX` over the session).
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
