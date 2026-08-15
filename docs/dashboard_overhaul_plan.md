# Dashboard & Gold Mart Overhaul Plan

Analysis pass over the current gold layer + dashboard, done 2026-08-14.
No code changed yet - this is the plan to review before implementation starts.

## 1. Current state

**6 gold marts, all already wired into 5 dashboard tabs** (Overview, When to Post, Duty
Trends, Roles, Fill Outcomes). Nothing shipped is dead weight - every mart column is used
somewhere. See `docs/gold_marts.md` for the existing catalog; not repeated here.

Everything sources from one keystone: `silver.fct_listing_lifecycle` (one row per listing
session). That table carries more columns than any gold mart currently reads.

## 2. The key constraint: gold-only vs. full silver refresh

Your last commit was specifically about avoiding a full silver refresh. That constraint
should drive prioritization here, so every proposal below is tagged:

- 🟢 **Gold-only** - the column already exists in `fct_listing_lifecycle`, just unused by any
  mart. New/changed gold table, `make dataform-run-gold`, done in minutes.
- 🟡 **Silver schema change** - needs a new column added to `fct_listing_lifecycle.sqlx`
  (e.g. lifting more description tags). Because it's an incremental merge table, backfilling
  history for a new column means a full refresh - the exact cost you just avoided.
- 🔴 **Not in current data** - would need a new reference table or scraper change.

Most of the highest-value additions below are 🟢. Lead with those.

## 3. Columns already in `fct_listing_lifecycle` that no gold mart reads

| Column | What it captures | Currently used by |
|---|---|---|
| `is_traveller`, `is_voyager` | cross-DC / cross-region posting | nothing (feature was built for the retired `mart_traveller_flow`) |
| `min_ilvl` | item-level gate on the listing | nothing |
| `is_practice`, `is_duty_complete` | prog vs. reclear-farm intent | nothing (built for the retired `mart_prog_vs_clear`) |
| `n_snapshots` | how many scrapes caught the listing (visibility proxy) | nothing |
| `initial_slots_filled`, `max_slots_filled`, `last_slots_filled` | party composition at post time vs. peak | only `max_slots_filled` internally, for `reached_full` |
| `is_right_censored` | whether the session's outcome is still unresolved | only internally, to derive `outcome` |
| `pf_world_key`, `creator_world_key`, `creator_datacenter`, `creator_region` | server-level grain, recruiter's home DC/region | rolled up into `is_traveller`/`is_voyager` and then dropped |

This is the cheap-win list: six-plus new analytical angles with zero silver changes.

## 4. Proposed additions

### 4.1 🟢 Time-to-fill distribution (upgrade, not a new mart)
Current `mart_time_to_fill` only ships `median` / `p90` / `avg`. That hides shape - a duty
with a fast median but a fat right tail looks identical to a consistently-fast one. Add a
histogram-bucket breakdown (`<15min`, `15-30`, `30-60`, `60-120`, `120+`) via `CASE` on
`time_to_full_min`, grouped the same way as today. Turns one heatmap into a heatmap +
distribution chart on drill-down. Also surface `is_right_censored` share per bucket so
"live/flash" ambiguity is visible instead of silently excluded.

### 4.2 🟢 Gear-gate trend (`mart_ilvl_gating`, new mart)
Grain: duty × region × DC × reset_week. Tracks `avg_min_ilvl`, `min_ilvl` percentiles, and
its correlation with `fill_rate_pct` / time-to-fill from the same week's `mart_duty_trends`
row. Answers "does this duty's ilvl requirement ease off as the tier ages, and do
over-geared listings fill faster?" - a real prog-community question, currently answerable
nowhere in the dashboard.

### 4.3 🟢 Listing intent split (`mart_listing_intent`, new mart)
Grain: content_category × region × DC × reset_week. Uses `is_practice` / `is_duty_complete`
to split high-end listings into practice / reclear-farm / blind-prog (neither flag) buckets,
each with its own fill rate and time-to-fill. This is a narrower, cheaper revival of the
retired `mart_prog_vs_clear` - worth reviving specifically because the columns are sitting
there unused, not because we're second-guessing the earlier retirement decision.

### 4.4 🟢 Cross-DC / cross-region travel demand (`mart_travel_demand`, new mart)
Grain: pf_region × pf_datacenter × reset_week. Uses `is_traveller`/`is_voyager` to report
what share of a DC's listings were posted by someone whose home DC/region differs. Answers
"how much of my DC's PF traffic is imported." Narrower revival of the retired
`mart_traveller_flow`, same reasoning as 4.3.

### 4.5 🟢 Market saturation / concurrency (new mart, more SQL work)
None of the existing marts answer "how many other groups are recruiting for the same duty
right now" - a real signal for whether posting now means competing with 10 other listings
or 0. Needs an interval-overlap computation (session `[session_start, last_seen]` vs. other
sessions for the same duty_key/DC), which is a step up in SQL complexity from the rest of
the gold layer (self-join or `COUNT` via sorted-event sweep) but still gold-only. Grain:
duty × region × DC × hour, metric `avg_concurrent_listings`.

### 4.6 🟢 Trend smoothing + anomaly flag (enhance `mart_duty_trends`)
`wow_pct_change` on a week-over-week basis is likely noisy for lower-volume duties (one
week's small denominator swings the percent wildly). Add a rolling N-week average
(`AVG(...) OVER (... ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)`) and a z-score
(`(listings - rolling_avg) / rolling_stddev`) so the dashboard can flag "this week is a real
outlier" vs. just showing a jumpy percentage. This is the one genuinely "advanced analytical
pattern" ask from your brief - rolling stats + z-score anomaly detection via window
functions, no new table needed.

### 4.7 🟢 World-level drill-down (dashboard-level, maybe no new mart)
`pf_world_key` already exists in `fct_listing_lifecycle` but every gold mart stops at DC.
Worth asking: do you want a world-level cut (e.g. "Excalibur vs. Gilgamesh within Crystal"),
or is DC the right floor to keep cardinality/noise down? If wanted, cheapest path is a new
`mart_activity_heatmap_world` (or add `pf_world` as an optional extra grain column to the
existing pattern marts) - still gold-only since the key is already there.

### 4.8 🟢 DC comparison / health scorecard (dashboard-only, no new mart)
Every tab today is scoped to one Region + DC via the sidebar. There's no "compare all DCs
at a glance" view. This doesn't need new gold tables - `mart_fill_funnel` +
`mart_activity_heatmap` + `mart_time_to_fill` already carry every DC's rows; it's a pandas
rollup + radar/ranked-bar chart in a new "Compare Data Centers" tab.

### 4.9 🟡 Additional description tags → lifecycle
`fct_listings` already computes `is_loot`, `is_one_per_job`, `is_weekly_unclaimed`,
`is_duty_completion`, `is_duty_incomplete` per snapshot, but only `is_practice` /
`is_duty_complete` get lifted (MAX-over-session) into `fct_listing_lifecycle`. Lifting the
rest would enable a fuller "listing tags" mart (loot rules, strictness). Requires editing
`fct_listing_lifecycle.sqlx` and a full incremental backfill - hold this until you're ready
to eat that refresh cost, or bundle it with another silver change so it's a single refresh.

### 4.10 🔴 Recruiter-level / repeat-poster analysis - not recommended
`player_hash` exists in `fct_listings` (pseudonymous) but was deliberately never carried into
`fct_listing_lifecycle`, and this dashboard is public (Streamlit Community Cloud). Even
pseudonymous "most active recruiter" leaderboards read as identity-adjacent on a public
site and don't fit the stated privacy boundary in `CLAUDE.md`. Flagging so it's an explicit
no rather than a silent gap - only revisit if you decide the dashboard becomes
access-controlled.

## 5. Suggested dashboard shape after the additions

| Tab | Status | Change |
|---|---|---|
| Overview | keep | no change |
| When to Post | keep | add time-to-fill distribution chart (4.1) as drill-down under the heatmap |
| Duty Trends | keep | add rolling-avg/anomaly flag (4.6); add ilvl-gating chart (4.2) to the duty-detail section |
| Roles | keep | no change |
| Fill Outcomes | keep | no change |
| **Compare DCs** (new) | new tab | 4.8, pandas-only |
| **Intent & Travel** (new) | new tab | 4.3 + 4.4 combined - "who's this listing for and where are they from" |
| **Market Saturation** (new) | new tab | 4.5, dedicated tab for concurrency metrics |

## 6. Recommended order

1. 🟢 4.6 rolling-avg/anomaly on `mart_duty_trends` - done.
2. 🟡 4.9 (extra description tags → lifecycle) - full refresh cost, eat it first so the
   gold marts below can use the lifted columns.
3. 🟢 4.3 + 4.4 (`mart_listing_intent`, `mart_travel_demand`) - two small new marts, columns
   already exist, ship together as one "Intent & Travel" tab.
4. 🟢 4.2 (`mart_ilvl_gating`) - one new mart, join to existing `mart_duty_trends` week.
5. 🟢 4.1 (time-to-fill distribution) - enhance existing mart, dashboard drill-down only.
6. 🟢 4.8 (Compare DCs tab) - no dataform work, pure dashboard.
7. 🟢 4.5 (concurrency/saturation) - most SQL complexity, do after the easy wins land.
8. Skip 4.10 unless the dashboard's access model changes.

## 7. Decisions (resolved 2026-08-15)

- World-level drill-down (4.7): **No** — keep DC-level only. Cardinality/noise not worth it.
- Market saturation (4.5): **Own tab** — dedicated Market Saturation tab.
- Description tags (4.9): **Include now** — do the full refresh, get it over with.
