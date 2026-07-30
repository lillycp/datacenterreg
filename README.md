# Data Center Regulation & Opposition Tracker

A static site that aggregates federal, state, and local data center regulations/legislation,
plus a feed of data center opposition headlines. Data refreshes automatically once a day via
a scheduled GitHub Actions workflow.

## Live site

Once GitHub Pages is enabled (see below), the site is at:

```
https://<your-github-username>.github.io/datacenterreg/
```

## How it works

- `index.html` / `style.css` / `app.js` — static frontend, reads JSON from `data/`.
- `scripts/fetch_data.py` — stdlib-only Python script that pulls fresh data:
  - **Federal** bills from the [Congress.gov API](https://api.congress.gov/) (titles matching "data center")
  - **State** bills from the [Open States API v3](https://docs.openstates.org/api-v3/) (full-text search "data center")
  - **Local** ordinances from the hand-curated `data/local_seed.json` (no standard API exists at the county/city level)
  - **Opposition headlines** from the free, keyless [GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) —
    US news coverage of city/county-level action on data centers (moratoriums, zoning/ordinance
    changes, council and board votes, public hearings). Headlines are also required to name
    "data center" in the title itself, since GDELT's full-text match otherwise pulls in articles
    that only mention data centers in passing. GDELT only monitors a fixed set of outlets and
    regularly misses smaller independent/regional newsrooms, so `data/opposition_seed.json`
    (hand-curated, same idea as `local_seed.json`) fills those gaps.
- `.github/workflows/update-data.yml` — runs the script daily at 13:00 UTC (and on-demand via
  "Run workflow"), commits the refreshed `data/*.json` files if anything changed.

## One-time setup

1. **Get two free API keys** (both instant, no cost):
   - Congress.gov: https://api.congress.gov/sign-up/
   - Open States: https://open.pluralpolicy.com/accounts/signup/ → key is on your profile page

2. **Add them as repo secrets**: Settings → Secrets and variables → Actions → New repository secret
   - `CONGRESS_API_KEY`
   - `OPENSTATES_API_KEY`

3. **Enable GitHub Pages**: Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder `/ (root)`.

4. **Run the workflow once by hand** so real data populates immediately instead of waiting for
   the next scheduled run: Actions tab → "Update data center regulation data" → Run workflow.

Until step 4 runs successfully, the site shows the placeholder/local-only dataset that shipped
in this repo.

## Adding more local ordinances

There's no API for county/city-level rules, so `data/local_seed.json` is maintained by hand.
Add an object in the same shape as the existing entries and commit — the next daily run will
merge it in automatically:

```json
{
  "id": "local-yourcounty-st-slug-2026",
  "level": "local",
  "state": "Full State Name",
  "title": "Ordinance title",
  "body": "Approving body, e.g. Some County Board of Supervisors",
  "status": "Enacted | Proposed",
  "date": "YYYY-MM-DD",
  "sourceUrl": "https://..."
}
```

## Adding opposition headlines GDELT missed

If you spot a real city/county data center story (moratorium, hearing, zoning vote, etc.) that
isn't showing up on the Opposition Headlines tab, GDELT likely doesn't monitor that outlet. Add
it to `data/opposition_seed.json` and commit — it's merged in on every run and won't get dropped
even if GDELT never picks it up:

```json
{
  "title": "Exact headline",
  "source": "outlet-domain.com",
  "publishedDate": "YYYY-MM-DD",
  "url": "https://...",
  "snippet": "Optional one-line summary.",
  "state": "Full State Name"
}
```

## Running the fetch script locally

```
CONGRESS_API_KEY=... OPENSTATES_API_KEY=... python3 scripts/fetch_data.py
```

Any source whose key is unset is skipped (logged to stderr) rather than failing the run.
