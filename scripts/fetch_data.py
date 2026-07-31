#!/usr/bin/env python3
"""
Pulls fresh data center regulation/legislation and opposition-news data and
writes it into ../data/*.json for the static site to read.

Uses only the Python standard library (urllib, json) so it runs unmodified
in GitHub Actions with no pip install step.

Sources:
  - Federal bills:  Congress.gov API   (needs CONGRESS_API_KEY env var)
  - State bills:    Open States API v3 (needs OPENSTATES_API_KEY env var)
  - Opposition headlines: GDELT DOC 2.0 API (free, no key required), plus
    hand-curated data/opposition_seed.json and data/local_seed.json (city/
    county ordinances have no standard API, and feed the headlines tab
    rather than the Regulations tab, which is federal/state only)

Any source whose API key isn't set is skipped with a log line rather than
failing the whole run, so the script always produces valid output.
"""

import json
import os
import re
import subprocess
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


class HttpStatusError(RuntimeError):
    def __init__(self, status_code, body):
        self.status_code = status_code
        super().__init__("HTTP {}: {}".format(status_code, body[:300]))


def http_get_json_via_curl(url, timeout=20, retries=3, backoff=5):
    """
    Congress.gov's Cloudflare protection blocks Python's urllib client
    (its TLS/HTTP fingerprint gets flagged) even with a valid API key, but
    plain `curl` gets through fine from the same network. Shell out to curl
    for Congress.gov requests specifically.
    """
    last_error = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                ["curl", "-s", "-w", "\n%{http_code}", "--max-time", str(timeout), url],
                capture_output=True, text=True, check=True,
            )
            body, _, status_code = proc.stdout.rpartition("\n")
            status_code = int(status_code)
            if status_code >= 400:
                raise HttpStatusError(status_code, body)
            return json.loads(body)
        except subprocess.CalledProcessError as e:
            last_error = e
            if attempt == retries - 1:
                raise
        except HttpStatusError as e:
            last_error = e
            if e.status_code not in RETRYABLE_STATUSES or attempt == retries - 1:
                raise
        time.sleep(backoff * (attempt + 1))
    raise last_error


# ---------------------------------------------------------------------------
# Federal: Congress.gov
# ---------------------------------------------------------------------------

CONGRESSES = [119, 118, 117, 116]  # covers roughly the past five years
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

    results = []
    max_pages_per_type = 30  # up to 7,500 bills per congress/type, covering a full two-year term

    for congress in CONGRESSES:
        for bill_type in BILL_TYPES:
            offset = 0
            for _ in range(max_pages_per_type):
                url = (
                    "https://api.congress.gov/v3/bill/{congress}/{bill_type}"
                    "?api_key={key}&format=json&limit=250&offset={offset}"
                ).format(
                    congress=congress, bill_type=bill_type, offset=offset,
                    key=urllib.parse.quote(CONGRESS_API_KEY),
                )
                try:
                    data = http_get_json_via_curl(url)
                except (subprocess.CalledProcessError, HttpStatusError, ValueError) as e:
                    log("Congress.gov: request failed for {}/{} at offset {}: {}".format(
                        congress, bill_type, offset, e
                    ))
                    break
                finally:
                    time.sleep(1)

                bills = data.get("bills", [])
                if not bills:
                    break

                for bill in bills:
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

                if len(bills) < 250:
                    break
                offset += 250

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
            data = http_get_json(url, headers=headers, timeout=45)
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
#
# City/county ordinances have no standard API, and unlike opposition
# headlines they're a specific legislative record (approving body, status,
# effective date) rather than a news article. The Regulations tab only
# covers federal and state legislation, so these are folded into the
# Opposition Headlines feed instead via local_seed_to_opposition().

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


def local_seed_to_opposition(local_items):
    items = []
    for item in local_items:
        url = item.get("sourceUrl", "")
        domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
        body = item.get("body", "")
        status = item.get("status", "")
        items.append({
            "title": item.get("title", ""),
            "source": domain or "Unknown source",
            "publishedDate": (item.get("date") or "")[:10],
            "url": url,
            "snippet": "{} — {}.".format(body, status) if body else "",
            "state": item.get("state", ""),
            "jurisdiction": item.get("jurisdiction", ""),
            "legislationType": item.get("legislationType", ""),
            "reasons": item.get("reasons", ""),
            "sustainability": item.get("sustainability", "No"),
            "nimbyConcerns": item.get("nimbyConcerns", "No"),
        })
    return items


def load_opposition_seed():
    """
    GDELT only monitors a fixed set of news sources and regularly misses
    smaller independent/regional outlets that break local data center
    stories (e.g. nonprofit city newsrooms). data/opposition_seed.json is
    for hand-adding real headlines GDELT didn't pick up, in the same shape
    as an opposition.json entry. Always merged in so they're never dropped.
    """
    path = os.path.join(DATA_DIR, "opposition_seed.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        log("Opposition seed: loaded {} curated headlines.".format(len(records)))
        return records
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log("Opposition seed: could not read {}: {}".format(path, e))
        return []


def load_excluded_urls():
    """
    GDELT's query matches terms anywhere in the article body, so some
    headlines pass the title check yet aren't actually about a city/county
    moratorium or zoning action once read (e.g. an existing crypto mine's
    air permit dispute). Manually reviewed misses go here so they don't
    reappear on the next automated run just because GDELT finds them again.
    """
    path = os.path.join(DATA_DIR, "opposition_excluded.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log("Opposition excluded: could not read {}: {}".format(path, e))
        return set()


# ---------------------------------------------------------------------------
# Opposition headlines: GDELT DOC 2.0 API
# ---------------------------------------------------------------------------

def guess_state(text):
    for name in STATE_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", text):
            return name
    return ""


LEGISLATION_TYPE_PATTERNS = [
    (re.compile(r"\b(reject|rejects|rejected|votes? down|voted down|shoots? down|denies|denied)\b", re.IGNORECASE), "Rejection"),
    (re.compile(r"\bban(s|ned)?\b", re.IGNORECASE), "Ban"),
    (re.compile(r"\bmoratorium\b", re.IGNORECASE), "Moratorium"),
    (re.compile(r"\bzoning\b", re.IGNORECASE), "Zoning Restriction"),
    (re.compile(r"\bordinance\b", re.IGNORECASE), "Ordinance"),
]

SUSTAINABILITY_RE = re.compile(r"\b(water|energy|power|electric|electricity|grid)\b", re.IGNORECASE)
NIMBY_RE = re.compile(
    r"\b(noise|light|glare|rural|compatib\w*|scale|precedent|setback|buffer|"
    r"property values?|quality of life|visual)\b",
    re.IGNORECASE,
)


def guess_legislation_type(title):
    """
    Best-effort classification from the headline alone, for raw GDELT
    catches that haven't been manually reviewed into the curated seed file.
    Curated entries (opposition_seed.json, local_seed.json) carry an
    explicit legislationType instead of relying on this guess.
    """
    for pattern, label in LEGISLATION_TYPE_PATTERNS:
        if pattern.search(title):
            return label
    return ""


def guess_sustainability(title):
    return "Yes" if SUSTAINABILITY_RE.search(title) else "No"


def guess_nimby(title):
    return "Yes" if NIMBY_RE.search(title) else "No"


def parse_gdelt_date(seendate):
    try:
        dt = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return ""


def fetch_opposition():
    # Targets news coverage of city/county-level action on data centers
    # specifically (moratoriums, zoning/ordinance changes, council and board
    # votes, public hearings) rather than generic "opposition" language,
    # which pulled in unrelated international and business news. Restricted
    # to US sources since only US local government action is in scope.
    # GDELT DOC 2.0 caps queries at 255 characters, so this stays terse.
    query = (
        '"data center" ("moratorium" OR "zoning" OR "ordinance" OR "rezoning" '
        'OR "city council" OR "county board" OR "board of supervisors" '
        'OR "planning commission" OR "county commission" OR "public hearing") '
        "sourcecountry:unitedstates"
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
        title = art.get("title", "")
        # GDELT's query matches terms anywhere in the full article body, so
        # articles that only mention "data center" in passing (e.g. an
        # election roundup) still come back. Requiring the headline itself
        # name a data center keeps the feed on-topic.
        if not KEYWORD_RE.search(title):
            continue
        seen_urls.add(url_)
        results.append({
            "title": title,
            "source": art.get("domain", "Unknown source"),
            "publishedDate": parse_gdelt_date(art.get("seendate", "")),
            "url": url_,
            "snippet": "",
            "state": guess_state(title),
            "jurisdiction": "",
            "legislationType": guess_legislation_type(title),
            "reasons": "",
            "sustainability": guess_sustainability(title),
            "nimbyConcerns": guess_nimby(title),
        })

    log("GDELT: found {} US local-legislation opposition headlines.".format(len(results)))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_existing(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def merge_regulations(new_federal, new_state):
    """
    A transient API failure on any one run shouldn't erase bills that were
    successfully fetched on a previous run. Keep existing federal/state
    entries and let fresh ones with the same id overwrite them.
    """
    existing = load_existing("regulations.json")
    merged = {r["id"]: r for r in existing if r.get("level") in ("federal", "state")}
    for r in new_federal + new_state:
        merged[r["id"]] = r
    return list(merged.values())


def merge_opposition(new_items, seed_items, excluded_urls, max_items=300):
    """Same idea as merge_regulations: don't let a failed GDELT call blank
    out headlines a previous run already found. Dedupe by URL, newest
    first, capped so the file doesn't grow unbounded. Hand-curated seed
    headlines are always merged in alongside whatever GDELT returned, and
    manually excluded URLs are dropped even if GDELT keeps re-finding them."""
    existing = load_existing("opposition.json")
    merged = {item["url"]: item for item in existing if item.get("url")}
    for item in new_items:
        merged[item["url"]] = item
    for item in seed_items:
        merged[item["url"]] = item
    for url in excluded_urls:
        merged.pop(url, None)
    items = sorted(merged.values(), key=lambda i: i.get("publishedDate") or "", reverse=True)
    return items[:max_items]


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    local = local_seed_to_opposition(load_local_seed())
    regulations = merge_regulations(fetch_federal(), fetch_state())
    opposition = merge_opposition(
        fetch_opposition(), load_opposition_seed() + local, load_excluded_urls()
    )

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
