import os
import json
import logging
import re
import hashlib
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from google.cloud import storage as gcs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GCS_BUCKET = os.environ.get("GCS_BUCKET", "ff14-pf-raw")
XIVPF_URL = "https://xivpf.com/listings"
USER_AGENT = "xivpf-scraper/2.0 (personal archiver; 15-min interval)"


def write_to_gcs(listings):
    client = gcs.Client()
    bucket = client.bucket(GCS_BUCKET)
    ts = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
    gcs_path = f"raw/{ts}.json"

    payload = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "listing_count": len(listings),
        "listings": listings,
    }
    bucket.blob(gcs_path).upload_from_string(
        json.dumps(payload, default=str),
        content_type="application/json",
    )

    full_path = f"gs://{GCS_BUCKET}/{gcs_path}"
    log.info("Wrote %d listings -> %s", len(listings), full_path)
    return full_path


def write_dead_letter(error, context=""):
    # keep a record of failed runs without losing the timestamp
    try:
        client = gcs.Client()
        bucket = client.bucket(GCS_BUCKET)
        ts = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
        payload = {
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(error),
            "context": context,
        }
        bucket.blob(f"dead-letter/{ts}.json").upload_from_string(
            json.dumps(payload), content_type="application/json"
        )
        log.warning("Dead-letter record written -> gs://%s/dead-letter/%s.json", GCS_BUCKET, ts)
    except Exception as dl_err:
        log.error("Failed to write dead-letter record: %s", dl_err)


def fetch_html(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    return resp.text


def make_id(*parts):
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_listings(html):
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now(timezone.utc).isoformat()

    cards = soup.select("div.listing") or soup.select("li.listing")
    if not cards:
        log.warning("Could not find listing cards - page structure may have changed")
        return []

    log.info("Found %d listing cards", len(cards))
    results = []

    for card in cards:
        # duty name + category
        duty_el = card.select_one("div.duty")
        duty = duty_el.get_text(strip=True) if duty_el else None
        category = None
        if duty_el:
            classes = duty_el.get("class", [])
            category = " ".join(c for c in classes if c != "duty") or None

        desc_el = card.select_one("div.description")
        description = desc_el.get_text(strip=True) if desc_el else None

        # party slots
        total_el = card.select_one("div.party div.total")
        slots_text = total_el.get_text(strip=True) if total_el else ""
        m = re.search(r"(\d+)\s*/\s*(\d+)", slots_text)
        slots_filled = int(m.group(1)) if m else None
        slots_total = int(m.group(2)) if m else None

        slot_list = []
        for slot in card.select("div.party div.slot"):
            classes = slot.get("class", [])
            slot_list.append({
                "roles": [c for c in classes if c not in ("slot", "filled", "empty")],
                "jobs": slot.get("title", "").strip(),
                "filled": "filled" in classes,
            })
        slot_details = slot_list or None

        min_ilvl = None
        for stat in card.select("div.stat"):
            name_el = stat.select_one("div.name")
            value_el = stat.select_one("div.value")
            if name_el and value_el and "il" in name_el.get_text(strip=True).lower():
                try:
                    min_ilvl = int(value_el.get_text(strip=True))
                except ValueError:
                    pass

        creator = None
        creator_server = None
        creator_el = card.select_one("div.item.creator span.text")
        if creator_el:
            raw = creator_el.get_text(strip=True)
            if " @ " in raw:
                creator, creator_server = (s.strip() for s in raw.split(" @ ", 1))
            else:
                creator = raw.strip()

        world_el = card.select_one("div.item.world span.text")
        world = world_el.get_text(strip=True) if world_el else None

        expires_el = card.select_one("div.item.expires span.text")
        expires = expires_el.get_text(strip=True) if expires_el else None

        updated_el = card.select_one("div.item.updated span.text")
        updated = updated_el.get_text(strip=True) if updated_el else None

        listing_id = make_id(creator, duty, description)

        if not duty and not description and not creator:
            continue

        results.append({
            "listing_id": listing_id,
            "duty": duty,
            "category": category,
            "description": description,
            "creator": creator,
            "creator_server": creator_server,
            "world": world,
            "min_ilvl": min_ilvl,
            "slots_filled": slots_filled,
            "slots_total": slots_total,
            "slot_details": slot_details,
            "expires_in": expires,
            "updated_at": updated,
            "scraped_at": now,
        })

    return results


def run():
    log.info("Fetching %s", XIVPF_URL)
    try:
        html = fetch_html(XIVPF_URL)
    except Exception as e:
        log.error("Failed to fetch page: %s", e)
        write_dead_letter(e, context="fetch_html")
        raise

    log.info("Page fetched (%d bytes)", len(html))

    try:
        listings = parse_listings(html)
    except Exception as e:
        log.error("Failed to parse listings: %s", e)
        write_dead_letter(e, context="parse_listings")
        raise

    log.info("Parsed %d listings", len(listings))

    if not listings:
        log.warning("No listings found - page structure may have changed!")
        write_dead_letter(
            Exception("Zero listings parsed"),
            context="empty_parse - check xivpf.com HTML structure",
        )
        return {"listings": 0, "gcs_path": None}

    gcs_path = write_to_gcs(listings)
    return {"listings": len(listings), "gcs_path": gcs_path}


if __name__ == "__main__":
    print(run())
