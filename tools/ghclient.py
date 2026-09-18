"""Thin, rate-limit-aware GitHub REST client shared by the harvest scripts.

Uses whatever credentials the environment provides (GITHUB_TOKEN, or an
authenticating proxy). Read-only: nothing here writes to GitHub.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"

# Search is limited to 30 requests/minute; core to 5000-15000/hour. We pace
# search calls explicitly and let core calls run at natural speed, backing off
# only when GitHub tells us to.
SEARCH_MIN_INTERVAL = 2.2

_last_search = [0.0]


def _headers():
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "copilot-architect-kb-rag-survey",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def get(path, params=None, accept=None, retries=4):
    """GET an API path. Returns parsed JSON, or None on a 404/410/451."""
    url = path if path.startswith("http") else API + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    if "/search/" in url:
        wait = SEARCH_MIN_INTERVAL - (time.time() - _last_search[0])
        if wait > 0:
            time.sleep(wait)
        _last_search[0] = time.time()

    headers = _headers()
    if accept:
        headers["Accept"] = accept

    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read()
                if accept and "raw" in accept:
                    return body.decode("utf-8", "replace")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            # Absent / gone / DMCA'd resources are a normal outcome here.
            if e.code in (404, 410, 451):
                return None
            # Secondary rate limit or abuse detection.
            if e.code in (403, 429):
                retry_after = e.headers.get("Retry-After")
                delay = int(retry_after) if retry_after else (5 * 2**attempt)
                time.sleep(min(delay, 90))
                continue
            if e.code >= 500:
                time.sleep(3 * 2**attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(3 * 2**attempt)
    return None


def paginate(path, params=None, max_pages=10, per_page=100):
    """Yield items across pages for a list endpoint."""
    params = dict(params or {})
    params["per_page"] = per_page
    for page in range(1, max_pages + 1):
        params["page"] = page
        batch = get(path, params)
        if not batch:
            return
        if isinstance(batch, dict):  # search endpoints wrap in {items: []}
            batch = batch.get("items", [])
        for item in batch:
            yield item
        if len(batch) < per_page:
            return


def search(kind, query, sort=None, order=None, max_pages=3, per_page=100):
    """Search repos/code/issues. Caps at 1000 results server-side."""
    params = {"q": query, "per_page": per_page}
    if sort:
        params["sort"] = sort
    if order:
        params["order"] = order
    out = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        res = get(f"/search/{kind}", params)
        if not res:
            break
        items = res.get("items", [])
        out.extend(items)
        if len(items) < per_page or len(out) >= res.get("total_count", 0):
            break
    return out


def rate_status():
    r = get("/rate_limit")
    if not r:
        return "unknown"
    core = r["resources"]["core"]
    srch = r["resources"]["search"]
    return f"core {core['remaining']}/{core['limit']}, search {srch['remaining']}/{srch['limit']}"
