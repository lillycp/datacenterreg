#!/usr/bin/env python3
"""
Pulls fresh data center regulation/legislation and opposition-news data and
writes it into ../data/*.json for the static site to read.

Uses only the Python standard library (urllib, json) so it runs unmodified
in GitHub Actions with no pip install step.

Sources:
  - Federal bills:  Congress.gov API   (needs CONGRESS_API_KEY env var)
  - State bills:    Open States API v3 (needs OPENSTATES_API_KEY env var)
  - Local ordinances: hand-curated data/local_seed.json (no API exists)
  - Opposition headlines: GDELT DOC 2.0 API (free, no key required)

Any source whose API key isn't set is skipped with a log line rather than
failing the whole run, so the script always produces valid output.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data"))

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY", "").strip()
OPENSTATES_API_KEY = os.environ.get("OPENSTATES_API_KEY", "").strip()

KEYWORD_RE = re.compile(r"data\s+center", re.IGNORECASE)

STATE_NAMES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
]


def log(msg):
    print(msg, file=sys.stderr)


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def http_get_json(url, headers=None, timeout=20, retries=3, backoff=5):
    req = urllib.request.Request(url, headers=headers or {})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code not in RETRYABLE_STATUSES or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            if attempt == retries - 1:
                raise
        time.sleep(backoff * (attempt + 1))
    raise last_error


# ---------------------------------------------------------------------------
# Federal: Congress.gov
# ---------------------------------------------------------------------------

CONGRESSES = [119, 118]
BILL_TYPES = ["hr", "s", "hjres", "sjres"]
CHAMBER_NAME = {
    "hr": "U.S. House of Representatives",
    "hjres": "U.S. House of Representatives",
    "s": "U.S. Senate",
    "sjres": "U.S. Senate",
}


def fetch_federal():
    if not CONGRESS_API_KEY:
        log("Congress.gov: CONGRESS_API_KEY not set, skipping federal bills.")
        return []

    log("Congress.gov: using key of length {}, starting '{}', ending '{}'.".format(
        len(CONGRESS_API_KEY), CONGRESS_API_KEY[:3], CONGRESS_API_KEY[-3:]
    ))

    results = []
    for congress in CONGRESSES:
        for bill_type in BILL_TYPES:
            url = (
                "https://api.congress.gov/v3/bill/{congress}/{bill_type}"
                "?api_key={key}&format=json&limit=250&sort=updateDate+desc"
            ).format(congress=congress, bill_type=bill_type, key=urllib.parse.quote(CONGRESS_API_KEY))
            try:
                data = http_get_json(url)
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    body = "<no body>"
                log("Congress.gov: request failed for {}/{}: {} {} -- {}".format(
                    congress, bill_type, e.code, e.reason, body
                ))
                continue
            except (urllib.error.URLError, TimeoutError) as e:
                log("Congress.gov: request failed for {}/{}: {}".format(congress, bill_type, e))
                continue
            finally:
                time.sleep(1)

            for bill in data.get("bills", []):
                title = bill.get("title") or ""
                if not KEYWORD_RE.search(title):
                    continue
                latest_action = bill.get("latestAction", {}) or {}
                number = bill.get("number", "")
                results.append({
                    "id": "federal-{}-{}-{}".format(congress, bill_type, number),
                    "level": "federal",
                    "state": "Federal",
                    "title": title.strip(),
                    "body": CHAMBER_NAME.get(bill_type, "U.S. Congress"),
                    "status": latest_action.get("text", "Introduced"),
                    "date": latest_action.get("actionDate") or bill.get("updateDate", ""),
                    "sourceUrl": "https://www.congress.gov/bill/{}th-congress/{}/{}".format(
                        congress,
                        "house-bill" if bill_type in ("hr", "hjres") else "senate-bill",
                        number,
                    ),
                })

    log("Congress.gov: found {} matching federal bills.".format(len(results)))
    return results


# ---------------------------------------------------------------------------
# State: Open States API v3
# ---------------------------------------------------------------------------

def fetch_state():
    if not OPENSTATES_API_KEY:
        log("Open States: OPENSTATES_API_KEY not set, skipping state bills.")
        return []

    results = []
    page = 1
    max_pages = 10
    headers = {"X-API-KEY": OPENSTATES_API_KEY}

    while page <= max_pages:
        params = urllib.parse.urlencode({
            "q": '"data center"',
            "sort": "updated_desc",
            "per_page": 20,
            "page": page,
            "include": "sources",
        })
        url = "https://v3.openstates.org/bills?" + params
        try:
            data = http_get_json(url, headers=headers)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            log("Open States: request failed on page {}: {}".format(page, e))
            break
        finally:
            time.sleep(1)

        results_page = data.get("results", [])
        if not results_page:
            break

        for bill in results_page:
            title = (bill.get("title") or "").strip()
            # Open States' full-text search can match bills where "data" and
            # "center" each appear separately in the full bill text, not as a
            # phrase. Only keep bills that actually name a data center in the
            # title so the listing stays relevant.
            if not KEYWORD_RE.search(title):
                continue
            jurisdiction = (bill.get("jurisdiction") or {}).get("name", "")
            org = (bill.get("from_organization") or {}).get("name", "State Legislature")
            sources = bill.get("sources") or []
            source_url = sources[0]["url"] if sources else bill.get("openstates_url", "")
            results.append({
                "id": "state-" + bill.get("id", str(len(results))),
                "level": "state",
                "state": jurisdiction,
                "title": title,
                "body": org,
                "status": bill.get("classification", ["bill"])[0].capitalize() if bill.get("classification") else "Bill",
                "date": bill.get("latest_action_date", ""),
                "sourceUrl": source_url,
            })

        pagination = data.get("pagination", {})
        if page >= pagination.get("max_page", page):
            break
        page += 1

    log("Open States: found {} matching state bills.".format(len(results)))
    return results


# ---------------------------------------------------------------------------
# Local: hand-curated seed file
# ---------------------------------------------------------------------------

def load_local_seed():
    path = os.path.join(DATA_DIR, "local_seed.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        log("Local seed: loaded {} curated local ordinances.".format(len(records)))
        return records
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log("Local seed: could not read {}: {}".format(path, e))
        return []


# ---------------------------------------------------------------------------
# Opposition headlines: GDELT DOC 2.0 API
# ---------------------------------------------------------------------------

def guess_state(text):
    for name in STATE_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", text):
            return name
    return ""


def parse_gdelt_date(seendate):
    try:
        dt = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return ""


def fetch_opposition():
    query = (
        '"data center" ("opposition" OR "oppose" OR "protest" OR "moratorium" '
        'OR "backlash" OR "pushback" OR "fight the")'
    )
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 250,
        "sort": "datedesc",
        "timespan": "2months",
    })
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + params

    try:
        data = http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        log("GDELT: request failed: {}".format(e))
        return []
    except json.JSONDecodeError as e:
        log("GDELT: could not parse response: {}".format(e))
        return []

    seen_urls = set()
    results = []
    for art in data.get("articles", []):
        url_ = art.get("url", "")
        if not url_ or url_ in seen_urls:
            continue
        seen_urls.add(url_)
        title = art.get("title", "")
        results.append({
            "title": title,
            "source": art.get("domain", "Unknown source"),
            "publishedDate": parse_gdelt_date(art.get("seendate", "")),
            "url": url_,
            "snippet": "",
            "state": guess_state(title),
        })

    log("GDELT: found {} opposition headlines.".format(len(results)))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    regulations = fetch_federal() + fetch_state() + load_local_seed()
    opposition = fetch_opposition()

    with open(os.path.join(DATA_DIR, "regulations.json"), "w", encoding="utf-8") as f:
        json.dump(regulations, f, indent=2, ensure_ascii=False)

    with open(os.path.join(DATA_DIR, "opposition.json"), "w", encoding="utf-8") as f:
        json.dump(opposition, f, indent=2, ensure_ascii=False)

    meta = {"lastUpdated": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(DATA_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    log("Done. {} regulations, {} opposition headlines.".format(len(regulations), len(opposition)))


if __name__ == "__main__":
    main()
