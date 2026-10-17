#!/usr/bin/env python3
"""Hourly pipeline: crawl yeeyi + 华人贴 once, write public/jobs.json for the map site,
and print the new-jobs report (stdout) for the email step. Build logs go to stderr.

Detail pages and geocodes are cached, so a rebuild only fetches posts it hasn't seen.
Usage: python3 build_map.py [--no-report]
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yeeyi_jobs as y

HERE = Path(__file__).parent
OUT = HERE / "public" / "jobs.json"
GEOCODE_CACHE = HERE / "geocode.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search?"
GEOCODE_UA = {"User-Agent": "yeeyi-jobs-map/1.0 (personal job search map)"}
# Post fields shown on each card besides salary/hours/contact (already their own rows).
EXTRA_FIELDS = ["公司名称", "性别要求", "招聘类型", "招聘人数", "签证要求", "语言要求", "工作经验", "最低学历", "行业类型"]


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def geocode(suburb, cache):
    if suburb in cache:
        return cache[suburb]
    q = urllib.parse.urlencode({"q": f"{suburb}, Australia", "format": "json", "limit": 1, "countrycodes": "au"})
    try:
        hits = json.loads(y.http_read(urllib.request.Request(NOMINATIM + q, headers=GEOCODE_UA)))
        cache[suburb] = [round(float(hits[0]["lat"]), 4), round(float(hits[0]["lon"]), 4)] if hits else None
    except Exception as e:  # leave uncached so the next build retries
        print(f"warn: geocode {suburb!r} failed: {e}", file=sys.stderr)
        return None
    time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
    return cache[suburb]


def main():
    details = load(y.DETAIL_CACHE)
    geo = load(GEOCODE_CACHE)
    matches = y.current_matches(details)
    jobs = []
    for item, detail in matches:
        suburb = (item.get("suburb") or "").strip()
        jobs.append({
            "tid": item["tid"],
            "source": item.get("source", "yeeyi"),
            "title": item["subject"].strip(),
            "suburb": suburb,
            "latlng": geocode(suburb, geo) if suburb else None,
            "position": detail["position"],
            "salary": detail["salary"] or "面议",
            "hours": y.hours_hint(item, detail),
            "contact": detail["contact"],
            "tags": y.tags(item, detail),
            "refreshed": int(item["lastpost"]),
            "posted": int(item["dateline"]),
            "description": detail["text"],
            "fields": {k: v for k, v in detail.get("fields", {}).items() if k in EXTRA_FIELDS},
            "url": y.item_url(item),
        })

    y.DETAIL_CACHE.write_text(json.dumps(details, ensure_ascii=False))
    GEOCODE_CACHE.write_text(json.dumps(geo, ensure_ascii=False, indent=0))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"built": int(time.time()), "jobs": jobs}, ensure_ascii=False))
    located = sum(1 for j in jobs if j["latlng"])
    by_source = {s: sum(1 for j in jobs if j["source"] == s) for s in {j["source"] for j in jobs}}
    print(f"{len(jobs)} jobs {by_source}, {located} located, {len({j['suburb'] for j in jobs})} suburbs -> {OUT.relative_to(HERE)}",
          file=sys.stderr)
    if "--no-report" not in sys.argv:
        y.report_new(matches, km_by_tid={j['tid']: y.distance_km(j['latlng']) for j in jobs})


if __name__ == "__main__":
    main()
