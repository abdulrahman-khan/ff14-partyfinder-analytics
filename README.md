# FFXIV Party Finder Data Warehouse

An end-to-end GCP data pipeline that scrapes live Party Finder listings from
[xivpf.com](https://xivpf.com) every 15 minutes and turns them into chart-ready analytics.
Raw HTML lands in BigQuery through a medallion architecture (bronze → silver → gold), hourly
SQL transforms run in Dataform, and all infrastructure is managed with Terraform.

## Project structure

```
ff14-pf/
├── services/       # Python Cloud Run jobs — scraper, loader, duty_extractor
├── dataform/       # SQL transforms — definitions/{bronze,silver,gold}/ + includes/
├── terraform/      # all infrastructure (Cloud Run, Workflows, BigQuery, scheduling, alerting)
├── reference/      # static reference data + loaders (worlds → datacenter → region)
├── tools/          # one-off utilities (historical backfill)
└── docs/           # architecture, gold marts, observability, backlog
```

## Data marts

| Mart | Question it answers |
|---|---|
| `mart_time_to_fill` ⭐ | When should I post to fill my party fastest? (median/p90 time-to-fill + fill rate by duty × region × DC × weekday × hour) |
| `mart_role_demand` | Which role is the bottleneck right now? (open tank/healer/DPS share + most common bottleneck) |
| `mart_activity_heatmap` | When is Party Finder busiest on my data center? (postings by region × DC × weekday × hour) |
| `mart_content_trends` | What content is hot or fading? (week-over-week volume change + weekly rank per duty) |
| `mart_traveller_flow` | Which data centers import vs. export players? (inbound / outbound / net travel flow) |

All marts hang off a single keystone in silver, `fct_listing_lifecycle` — one row per listing
*session*, carrying its lifetime, time-to-fill, fill outcome, and role bottleneck. See
[docs/gold_marts.md](docs/gold_marts.md) for grains, metrics, and the lifecycle model.

## Analytics this enables

- **Optimal posting times** — time-to-fill and fill-rate heatmaps across weekday × hour, so a
  player knows the best window to post a given duty on their DC.
- **Role scarcity analysis** — which role (tank/healer/DPS) is the chronic bottleneck, by
  content type, region, and time of day.
- **Content lifecycle & trends** — week-over-week popularity shifts and per-region rankings
  that surface what's rising, peaking, or dying off (e.g. new raid tiers vs. old content).
- **Data-center travel flows** — net player migration between data centers, revealing which
  DCs pull players in and which leak them out.
- **Peak-activity profiling** — when each region/DC is most active, useful for capacity and
  community insights.
- **ML foundation** — the sessionized lifecycle fact plus traveller/voyager features set up
  future fill-time regression and party-composition clustering.

## Getting started

Full setup (API enablement, Dataform credentials, one-time reference load) is in
[docs/architecture.md](docs/architecture.md). The short version, once authenticated:

```bash
make docker-auth          # one-time Artifact Registry login
make build-all push-all   # build + push the three service images
make deploy               # terraform apply
make help                 # list all build / run / deploy targets
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — repo layout, data flow, full schema, design decisions
- [docs/gold_marts.md](docs/gold_marts.md) — mart catalog + the lifecycle model
- [docs/observability.md](docs/observability.md) — logging & failure-alerting runbook
- [docs/improvements.md](docs/improvements.md) — backlog / improvement opportunities

## Disclaimer

This project scrapes publicly visible data from [xivpf.com](https://xivpf.com). Not affiliated
with Square Enix.
