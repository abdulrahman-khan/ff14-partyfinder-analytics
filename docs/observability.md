# Observability Runbook

How to see what the pipeline is doing and how it tells you when it breaks.
Everything here is GCP-native and sits in the free tier at this pipeline's volume.

---

## Viewing logs — Logs Explorer saved queries

Open [Logs Explorer](https://console.cloud.google.com/logs/query) (project `ff14-pf-data`),
paste a query, and **Save** it (give it a name; bookmark the URL). These are your
"what's running" panels.

### Everything across the pipeline
```
resource.type=("cloud_run_job" OR "workflows.googleapis.com/Workflow" OR "dataform.googleapis.com/Repository")
```

### Just the loader's recent runs
```
resource.type="cloud_run_job" resource.labels.job_name="ff14-pf-loader"
```
Swap `ff14-pf-loader` for `ff14-pf-scraper` or `ff14-pf-duty-extractor` as needed.

### Only failures, whole pipeline
```
severity>=ERROR
resource.type=("cloud_run_job" OR "workflows.googleapis.com/Workflow" OR "dataform.googleapis.com/Repository")
```

### Dead-letter writes (xivpf.com HTML changed / zero listings parsed)
```
resource.type="cloud_run_job"
textPayload:"Dead-letter record written"
```

> Note: the scraper logs the dead-letter line at **WARNING**, not ERROR, and the
> job still exits 0 when it parses zero listings — so this is the *only* log
> signal that catches a silent scraper break. It's also wired to an alert (below).

---

## Failure alerting

Defined as Terraform in [`terraform/monitoring.tf`](../terraform/monitoring.tf).
One email notification channel + 5 alert policies. After `terraform apply`, **verify
the channel** via the confirmation email GCP sends — alerts won't deliver until then.

| # | Policy | Catches |
|---|---|---|
| 1 | Scraper dead-letter written | xivpf.com HTML changed / zero listings (job exits 0 — only this catches it) |
| 2 | Pipeline ERROR log | loader soft per-file failures, scraper hard errors |
| 3 | Cloud Run job hard failure | crashes / OOM / timeout on any of the 3 jobs |
| 4 | Workflow execution failed | orchestration breaks |
| 5 | Dataform invocation failed | transform failures + future assertion failures |

Why log-based alerts (1, 2, 5) carry most of the weight: the loader catches
per-file errors and the scraper's "zero listings" case both **exit 0**, so a
job-failure metric alone (3) would miss them.

A single hard scraper failure can trip #1, #2, and #3 at once (intentional
over-alerting); each policy has a 1-hour notification rate limit to avoid spam.

> Heads-up: the workflow fires Dataform fire-and-forget, so a failed Dataform
> invocation (incl. assertion failures) never propagates to the workflow status.
> That's why #5 alerts on Dataform's own logs rather than relying on #4.

---

## Cost guardrail

A $5/month billing budget with email alerts at 50% / 90% / 100% is defined in
[`terraform/budget.tf`](../terraform/budget.tf), routed to the same email channel.
It's an **alert, not a hard cap** — it notifies, it does not stop spending.
Realistic steady-state spend at current volume is ~$0–2/month.
