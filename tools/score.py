"""Phase 2 -- score candidate repos on seven evidence signals.

Design constraint: stars are RECORDED but never SCORED. Popularity measures how
many people heard about a repo, lagged by a year and never decaying. None of the
seven signals below is a popularity proxy; each is an attempt to detect whether
somebody operated the thing.

Every signal stores the raw evidence (file paths, issue numbers, counts) that
produced it, so a score can be argued with rather than trusted.

Output: data/scored.json
"""

import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghclient as gh  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(HERE, "..", "data", "candidates.json")
OUT = os.path.join(HERE, "..", "data", "scored.json")

NOW = datetime.now(timezone.utc)

# --- Signal 1: operational burden -------------------------------------------
# Things nobody writes until they have been paged. Presence of these in source
# separates "ran in production" from "ran in a notebook".
OPS_PATTERNS = {
    "retry_backoff": r"\b(exponential_backoff|retry_with_backoff|tenacity|@retry|backoff\.expo|Polly|RetryPolicy|max_retries)\b",
    "timeouts": r"\b(timeout=|TimeoutError|HttpClientTimeout|request_timeout|ReadTimeout)\b",
    "rate_limit": r"\b(rate.?limit|429|TooManyRequests|throttl|RetryAfter|quota)\b",
    "idempotency": r"\b(idempoten|upsert|dedup|content_hash|etag|checksum)\b",
    "cost_accounting": r"\b(token_count|prompt_tokens|cost_per|usage\.total_tokens|tiktoken|budget)\b",
    "reindex_path": r"\b(reindex|re-index|rebuild_index|migrate_index|backfill|index_version|swap_alias)\b",
    "observability": r"\b(opentelemetry|OpenTelemetry|tracer|structlog|logger\.(info|warning|error)|app_?insights|prometheus)\b",
    "circuit_breaker": r"\b(circuit_?breaker|bulkhead|fallback_|degrade)\b",
}

# --- Signal 2: retrieval evaluation -----------------------------------------
# Unit tests are not evaluation. We look specifically for retrieval-quality
# measurement -- somebody who put a number on whether the answers were right.
EVAL_PATTERNS = {
    "retrieval_metrics": r"\b(recall_?at_?k|recall@|ndcg|mrr\b|precision_?at_?k|hit_?rate|map@)\b",
    "generation_metrics": r"\b(groundedness|faithfulness|answer_relevanc|context_precision|context_recall|hallucination_rate)\b",
    "eval_harness": r"\b(ragas|trulens|deepeval|promptfoo|azure-ai-evaluation|AzureAIEvaluat|giskard|langsmith)\b",
    "golden_set": r"\b(golden_?(set|dataset)|ground_?truth|qa_?pairs|eval_?set|testset|benchmark_?questions)\b",
    "regression_gate": r"\b(assert.*(recall|ndcg|groundedness|faithfulness)|threshold.*score|min_score)\b",
}

# --- Signal 6: enterprise gate readiness ------------------------------------
# The four things that kill enterprise RAG at security review. A repo that
# handles these was built for an environment with a security review.
ENTERPRISE_PATTERNS = {
    "authn": r"\b(DefaultAzureCredential|ManagedIdentity|OAuth|OIDC|msal|EntraID|azure\.identity|IAM role|service_?account)\b",
    "doc_acl": r"\b(acl|access_?control|security_?filter|security_?trimming|group_?ids|oid\b|permission_?filter|row_?level_?security)\b",
    "tenancy": r"\b(tenant_?id|multi_?tenant|namespace|partition_?key|index_?per_?)\b",
    "pii": r"\b(pii|redact|anonymi|presidio|scrub|mask_|dlp\b)\b",
    "audit": r"\b(audit_?log|audit_?trail|compliance_?log|immutable_?log)\b",
    "residency": r"\b(data_?residency|sovereign|region_?lock|eu_?only|geo_?restrict)\b",
}

CODE_EXT = (".py", ".ts", ".js", ".cs", ".java", ".go", ".tsx", ".jsx", ".rb", ".ipynb")
DOC_EXT = (".md", ".rst", ".txt", ".yaml", ".yml", ".json", ".bicep", ".tf")

# Churn that fakes liveness: badge bumps, dependabot, formatting.
CHURN_RE = re.compile(
    r"^(bump|chore\(deps\)|chore: bump|update readme|docs?:|readme|merge branch|merge pull request"
    r"|dependabot|pre-commit autoupdate|fix typo|typo|format|lint|style:)",
    re.I,
)


def get_tree(full_name, default_branch):
    """Full recursive file listing -- one API call, gives us paths for free."""
    t = gh.get(f"/repos/{full_name}/git/trees/{default_branch}", {"recursive": "1"})
    if not t:
        return [], False
    paths = [n["path"] for n in t.get("tree", []) if n.get("type") == "blob"]
    return paths, t.get("truncated", False)


def fetch_text(full_name, path, max_bytes=180_000):
    c = gh.get(f"/repos/{full_name}/contents/{urlq(path)}")
    if not c or c.get("size", 0) > max_bytes or "content" not in c:
        return ""
    try:
        return base64.b64decode(c["content"]).decode("utf-8", "replace")
    except Exception:
        return ""


def urlq(path):
    from urllib.parse import quote
    return quote(path)


def sample_source(full_name, paths, limit=14):
    """Read a bounded sample of source files, preferring the ones most likely to
    carry operational code (services, pipelines, indexers) over demos."""
    code = [p for p in paths if p.endswith(CODE_EXT)]
    weight = lambda p: (  # noqa: E731
        ("test" in p.lower()) * -1
        + sum(k in p.lower() for k in (
            "index", "ingest", "retriev", "search", "embed", "chunk", "service",
            "pipeline", "client", "app", "api", "eval", "rerank"))
    )
    code.sort(key=weight, reverse=True)
    blob = []
    for p in code[:limit]:
        blob.append(fetch_text(full_name, p))
    return "\n".join(blob), code[:limit]


def match_group(text, patterns):
    hits = {}
    for key, rx in patterns.items():
        m = re.findall(rx, text, re.I)
        if m:
            hits[key] = len(m)
    return hits


def sig_operational(source_text):
    hits = match_group(source_text, OPS_PATTERNS)
    # Weighted: reindex path and cost accounting are the rarest and most telling.
    weights = {"retry_backoff": 1.5, "timeouts": 1.0, "rate_limit": 1.5,
               "idempotency": 1.0, "cost_accounting": 2.0, "reindex_path": 2.5,
               "observability": 1.0, "circuit_breaker": 1.5}
    raw = sum(weights[k] for k in hits)
    return round(min(raw / 12.0, 1.0), 3), hits


def sig_eval(full_name, paths, source_text):
    eval_paths = [p for p in paths if re.search(r"(^|/)(eval|evals|evaluation|benchmark)s?(/|$)", p, re.I)]
    text = source_text
    for p in eval_paths[:6]:
        if p.endswith(CODE_EXT + DOC_EXT):
            text += "\n" + fetch_text(full_name, p)
    hits = match_group(text, EVAL_PATTERNS)
    weights = {"retrieval_metrics": 3.0, "generation_metrics": 2.5,
               "eval_harness": 1.5, "golden_set": 2.0, "regression_gate": 3.0}
    raw = sum(weights[k] for k in hits)
    if eval_paths:
        raw += 1.0
    return round(min(raw / 9.0, 1.0), 3), {"patterns": hits, "eval_paths": eval_paths[:8]}


def sig_issue_health(full_name):
    """Median hours to first maintainer response, and how issues actually close.
    Stale-bot closure is the tell for an abandoned tracker."""
    since = (NOW - timedelta(days=180)).isoformat()
    issues = list(gh.paginate(f"/repos/{full_name}/issues",
                              {"state": "all", "since": since, "sort": "created", "direction": "desc"},
                              max_pages=2))
    issues = [i for i in issues if "pull_request" not in i][:60]
    if not issues:
        return 0.0, {"sample": 0, "note": "no issues in last 180d"}

    responded, latencies, stale_closed, real_closed = 0, [], 0, 0
    for i in issues[:30]:
        num = i["number"]
        comments = gh.get(f"/repos/{full_name}/issues/{num}/comments", {"per_page": 10}) or []
        author = (i.get("user") or {}).get("login")
        for c in comments:
            cu = (c.get("user") or {}).get("login", "")
            if cu != author and not cu.endswith("[bot]"):
                responded += 1
                t0 = datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
                latencies.append((t1 - t0).total_seconds() / 3600.0)
                break
        if i.get("state") == "closed":
            body_blob = " ".join((c.get("body") or "")[:200] for c in comments[-2:]).lower()
            if "stale" in body_blob or "inactivity" in body_blob or "automatically closed" in body_blob:
                stale_closed += 1
            else:
                real_closed += 1

    sample = min(len(issues), 30)
    resp_rate = responded / sample if sample else 0
    med = sorted(latencies)[len(latencies) // 2] if latencies else None
    speed = 0.0 if med is None else max(0.0, min(1.0, 1.0 - (med / 336.0)))  # 14d -> 0
    closed_total = stale_closed + real_closed
    honesty = (real_closed / closed_total) if closed_total else 0.5
    score = round(0.45 * resp_rate + 0.30 * speed + 0.25 * honesty, 3)
    return score, {"sample": sample, "response_rate": round(resp_rate, 2),
                   "median_first_response_h": round(med, 1) if med else None,
                   "stale_closed": stale_closed, "substantively_closed": real_closed}


def sig_bus_factor(full_name):
    since = (NOW - timedelta(days=365)).isoformat()
    commits = list(gh.paginate(f"/repos/{full_name}/commits", {"since": since}, max_pages=3))
    if not commits:
        return 0.0, {"commits_12mo": 0}
    authors = {}
    for c in commits:
        a = (c.get("author") or {}).get("login") or (c.get("commit", {}).get("author", {}) or {}).get("name")
        if a and not str(a).endswith("[bot]"):
            authors[a] = authors.get(a, 0) + 1
    substantive = [a for a, n in authors.items() if n >= 5]
    top_share = max(authors.values()) / sum(authors.values()) if authors else 1.0
    score = min(len(substantive) / 4.0, 1.0) * (1.0 - 0.5 * max(0.0, top_share - 0.5) / 0.5)
    return round(max(0.0, min(score, 1.0)), 3), {
        "commits_12mo": len(commits), "distinct_authors": len(authors),
        "authors_5plus_commits": len(substantive), "top_author_share": round(top_share, 2)}


def sig_dependency_honesty(full_name, paths):
    lockfiles = [p for p in paths if os.path.basename(p) in (
        "poetry.lock", "uv.lock", "Pipfile.lock", "package-lock.json", "yarn.lock",
        "pnpm-lock.yaml", "requirements.lock", "packages.lock.json", "go.sum", "Cargo.lock")]
    manifests = [p for p in paths if os.path.basename(p) in (
        "requirements.txt", "pyproject.toml", "package.json", "Directory.Packages.props")]
    pinned = floating = 0
    for m in manifests[:4]:
        txt = fetch_text(full_name, m)
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if re.search(r"[=~^]=?\s*\d+\.\d+", line) or re.search(r'"\^?\d+\.\d+', line):
                pinned += 1
            elif re.match(r"^[a-zA-Z][\w\-\[\]\.]+$", line):
                floating += 1
    total = pinned + floating
    pin_ratio = pinned / total if total else 0.0
    score = 0.5 * (1.0 if lockfiles else 0.0) + 0.5 * pin_ratio
    return round(score, 3), {"lockfiles": lockfiles[:3], "pinned": pinned,
                             "floating": floating, "pin_ratio": round(pin_ratio, 2)}


def sig_enterprise(source_text, paths):
    path_blob = "\n".join(paths)
    hits = match_group(source_text + "\n" + path_blob, ENTERPRISE_PATTERNS)
    weights = {"authn": 1.5, "doc_acl": 3.5, "tenancy": 2.0, "pii": 2.0,
               "audit": 2.0, "residency": 1.5}
    raw = sum(weights[k] for k in hits)
    return round(min(raw / 9.0, 1.0), 3), hits


def sig_substantive_recency(full_name, default_branch):
    since = (NOW - timedelta(days=90)).isoformat()
    commits = list(gh.paginate(f"/repos/{full_name}/commits", {"since": since, "sha": default_branch}, max_pages=2))
    substantive = [c for c in commits
                   if not CHURN_RE.match((c.get("commit", {}).get("message") or "").strip())]
    score = min(len(substantive) / 25.0, 1.0)
    return round(score, 3), {"commits_90d": len(commits), "substantive_90d": len(substantive),
                             "churn_ratio": round(1 - len(substantive) / len(commits), 2) if commits else None}


WEIGHTS = {
    "operational": 0.18,
    "evaluation": 0.20,
    "issue_health": 0.14,
    "bus_factor": 0.12,
    "dependency_honesty": 0.08,
    "enterprise": 0.20,
    "recency": 0.08,
}


def score_repo(name, meta):
    repo = gh.get(f"/repos/{name}")
    if not repo:
        return None
    branch = repo.get("default_branch", "main")
    paths, truncated = get_tree(name, branch)
    if not paths:
        return None
    source_text, sampled = sample_source(name, paths)

    s = {}
    e = {}
    s["operational"], e["operational"] = sig_operational(source_text)
    s["evaluation"], e["evaluation"] = sig_eval(name, paths, source_text)
    s["issue_health"], e["issue_health"] = sig_issue_health(name)
    s["bus_factor"], e["bus_factor"] = sig_bus_factor(name)
    s["dependency_honesty"], e["dependency_honesty"] = sig_dependency_honesty(name, paths)
    s["enterprise"], e["enterprise"] = sig_enterprise(source_text, paths)
    s["recency"], e["recency"] = sig_substantive_recency(name, branch)

    composite = round(sum(s[k] * WEIGHTS[k] for k in WEIGHTS), 4)

    return {
        "full_name": name,
        "html_url": repo.get("html_url"),
        "description": repo.get("description"),
        "language": repo.get("language"),
        "license": (repo.get("license") or {}).get("spdx_id"),
        "archived": repo.get("archived"),
        "pushed_at": repo.get("pushed_at"),
        "created_at": repo.get("created_at"),
        # Recorded, deliberately excluded from `composite`.
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "seeds": meta.get("seeds", []),
        "signals": s,
        "evidence": e,
        "composite": composite,
        "files_sampled": sampled,
        "tree_truncated": truncated,
    }


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
    with open(IN) as f:
        data = json.load(f)
    cands = data["candidates"]

    # Pre-filter: drop forks, archived, and toy repos (<3 source files) before
    # spending API budget. This is a floor, not a ranking.
    names = [n for n, m in cands.items() if not m.get("fork") and not m.get("archived")]
    # Prioritise breadth of seed coverage: repos found by multiple independent
    # seeds first, since that is orthogonality, not popularity.
    names.sort(key=lambda n: (-len(cands[n].get("seeds", [])), n))
    names = names[:limit]

    out = []
    existing = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            for r in json.load(f):
                existing[r["full_name"]] = r

    for i, n in enumerate(names):
        if n in existing:
            out.append(existing[n])
            continue
        try:
            r = score_repo(n, cands[n])
        except Exception as ex:
            print(f"  !! {n}: {ex}", flush=True)
            r = None
        if r:
            out.append(r)
        if i % 10 == 0:
            print(f"[{i}/{len(names)}] {n} -> {r['composite'] if r else 'skip'}  ({gh.rate_status()})", flush=True)
            with open(OUT, "w") as f:
                json.dump(out, f, indent=1)

    out.sort(key=lambda r: -r["composite"])
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nscored {len(out)} repos -> {OUT}")


if __name__ == "__main__":
    main()
