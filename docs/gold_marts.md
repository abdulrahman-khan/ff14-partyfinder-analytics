# Gold Marts & the Lifecycle Model

The gold layer ships **pre-aggregated, chart-ready marts** — each one is already at the exact grain a dashboard tile needs, and each surfaces a *rate / duration / delta*, not a bare count. Region is a dimension in every mart (no hardcoded NA).

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

The layer is deliberately lean — six marts across two families plus one denominator. Every mart
earns its place against a distinct analytical question; anything strictly derivable from another
mart (e.g. the old `mart_weekly_datacenter`, a content rollup of `mart_duty_trends`) was retired.
**Datacenter is the primary scope**: a Party Finder listing is exclusive to the DC it is hosted
on (a JP listing never appears in NA Crystal; NA Aether never appears in NA Crystal), so every
mart carries `pf_datacenter` and region is only a rollup dimension.

### Pattern family — recent rolling window, intraday ("when should I post *now*?")

These answer intraday timing/role questions and are restricted to the last `PATTERN_WINDOW_WEEKS`
(8) reset weeks, anchored on the **data frontier** (`MAX(first_seen_date)`, not `CURRENT_DATE()`,
since the loader is manual). The window keeps intraday patterns tied to the current tier instead
of smearing across patch boundaries. Each carries `window_start_date` / `window_end_date` so a
dashboard can label the window. They are **not** date-filterable — use the trend family for that.

| Mart | Grain | Headline metric(s) | Question it answers | Viz |
|---|---|---|---|---|
| `mart_time_to_fill` ⭐ | duty × region × DC × weekday × hour | `median_time_to_fill_min`, `p90`, `fill_rate_pct` | "When should I post to fill fast?" | weekday×hour heatmap |
| `mart_role_demand` | content_category × region × DC × hour | open tank/healer/dps **share %**, `most_common_bottleneck` | "Which role is the bottleneck right now?" | stacked bar |
| `mart_activity_heatmap` | region × DC × weekday × hour | `listings_posted`, `avg_lifetime_min`, `fill_rate_pct` | "When is PF busiest on my DC?" | weekday×hour heatmap |

### Trend family — date-filterable, DC-primary, `reset_week` grain ("trends through patch history")

These carry an FFXIV `reset_week` (Tuesday 08:00 UTC via `dim_date`) so **one date-range filter**
serves both "recent (past few weeks)" and "full patch-history summary" — the dashboard filters on
`reset_week` and re-aggregates in pandas.

| Mart | Grain | Headline metric(s) | Question it answers | Viz |
|---|---|---|---|---|
| `mart_duty_trends` ⭐ | duty × region × DC × reset_week | `listings`, `wow_pct_change`, `rank_in_dc_week`, `fill_rate_pct`, `median_time_to_fill_min` | "How have popularity, fill rate and speed for this duty on my DC moved patch to patch?" | trend lines / ranked bars |
| `mart_role_trends` | content_category × region × DC × reset_week | open tank/healer/dps **share %**, `most_common_bottleneck` | "Has the tank shortage on my DC eased or worsened over patches?" | role-share-over-time |

### Denominator mart

| Mart | Grain | Headline metric(s) | Question it answers | Viz |
|---|---|---|---|---|
| `mart_fill_funnel` | content × region × DC | `filled_pct`, `expired_partial_pct`, `flash_pct` | "What share of listings ever fill?" | stacked / funnel bar |

Notes:
- All marts source from `fct_listing_lifecycle` (one row per session → no scrape double-counting).
- `mart_duty_trends` is the **hero trend mart**; it supersedes the retired `mart_content_trends`
  (region-only, volume-only) and `mart_weekly_datacenter` (content rollup) — both are recovered by
  summing/grouping DCs and duties in pandas. It counts listings, but the *insight* is
  `wow_pct_change`, `rank_in_dc_week`, and how `fill_rate_pct` / time-to-fill move across patches.
- `mart_role_trends` is the date-filterable sibling of `mart_role_demand`. Open-slot share is
  *unmet role demand*: the role with the largest share is the bottleneck, and its inverse (the
  role whose slots fill fastest, usually DPS) is the read for "what role people play most".
- `mart_fill_funnel` is the *denominator* for the fill/time-to-fill marts: a fast
  `median_time_to_fill` only means something once you know `filled_pct`. `flash_pct` is an
  ambiguity band (single-snapshot, right-censored), not a failure rate.
- `mart_activity_heatmap` measures **posting activity** from the session table (cheap), not
  concurrent-live snapshots — it replaces the old `mart_activity_hour_datacenter`.
- **Retired** (2026-07): `mart_weekly_datacenter` (derivable from `mart_duty_trends`),
  `mart_supply_demand_gap` (composite gap index overlapping fill-rate + role signals),
  `mart_prog_vs_clear` (niche intent split), and `mart_traveller_flow` (DC travel, off the core
  when/what/roles/fill question set). Removed to keep the layer lean; the lifecycle facts still
  carry the underlying columns if any are ever revived.

---

## Shared logic — `dataform/includes/ffxiv.js`

- `SESSION_GAP_MIN` — sessionization threshold (30).
- `PATTERN_WINDOW_WEEKS` (8) / `patternWindowCutoff(lifecycleRef)` — the recent-window bound for the
  pattern-family marts. `patternWindowCutoff` returns `DATE_SUB(MAX(first_seen_date) - N weeks)`
  anchored on the data frontier, not `CURRENT_DATE()`, so a lagging manual load never empties the
  window.
- `resetWeekStart(tsExpr)` / `resetWeekBounds(period)` — FFXIV reset-week math (Tuesday 08:00 UTC), centralized instead of copy-pasted across marts. Used by `dim_date` and available to any model.

## Data quality

- `silver.assert_lifecycle_freshness` — blocking assertion; fails if the newest session is > 3h old.
- `silver.qa_unmatched_worlds` — non-blocking monitoring view; lists `raw_listings.world` values that don't match `dim_worlds` (these silently drop from region/DC rollups — see [`improvements.md`](improvements.md) #2).
- Each mart carries `rowConditions` assertions (shares/rates within 0–100, non-negative durations).
