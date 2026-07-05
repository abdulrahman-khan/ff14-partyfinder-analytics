import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

PROJECT = "ff14-pf-data"
JOB = "ff14-pf-scraper"

BUCKET = "ff14-pf-data-raw"


def gcloud(*args):
    p = subprocess.run(
        ["gcloud", *args],
        capture_output=True,
        text=True,
        shell=(sys.platform == "win32"),
    )
    if p.returncode != 0:
        sys.exit(p.stderr.strip() or "gcloud failed")
    return p.stdout


def log_errors(hours, severity, limit):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filt = (
        f'resource.type="cloud_run_job" resource.labels.job_name="{JOB}" '
        f'severity>={severity} timestamp>="{since}"'
    )
    out = gcloud("logging", "read", filt, f"--project={PROJECT}",
                 f"--limit={limit}", "--format=json", "--order=desc")
    entries = json.loads(out) if out.strip() else []

    print(f"\nCloud Logging: {severity}+ in the last {hours}h")
    if not entries:
        print("  none")
        return
    for e in entries:
        msg = e.get("textPayload") or json.dumps(e.get("jsonPayload", ""))
        print(f"{e['timestamp']}  {e['severity']}  {msg.strip()}")
    print(f"({len(entries)} entries)")


def dead_letters(hours):
    print(f"\nDead-letter records in the last {hours}h")
    out = gcloud("storage", "ls", f"gs://{BUCKET}/dead-letter/**")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    recent = []
    for path in out.split():
        if not path.endswith(".json"):
            continue
        stamp = path.rsplit("dead-letter/", 1)[-1][:-len(".json")]
        try:
            when = datetime.strptime(stamp, "%Y/%m/%d/%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when >= cutoff:
            recent.append((when, path))

    if not recent:
        print("  none")
        return
    for when, path in sorted(recent, reverse=True):
        rec = json.loads(gcloud("storage", "cat", path))
        print(f"{when.isoformat()}  {rec.get('context')}: {rec.get('error')}")
    print(f"({len(recent)} records)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--severity", default="WARNING", choices=["WARNING", "ERROR", "CRITICAL"])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dead-letter", action="store_true")
    args = ap.parse_args()

    log_errors(args.hours, args.severity, args.limit)
    if args.dead_letter:
        dead_letters(args.hours)
