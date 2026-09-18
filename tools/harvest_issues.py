"""Phase 3 -- harvest the failure-mode corpus.

The premise of this whole survey: enterprises do not publish their production
RAG, but the engineers running it open issues against the frameworks they built
on. The issue tracker is the only place where "this did not work" is stated in
public, by the person it happened to, with a timestamp.

This script pulls issues from the highest-scoring repos plus the pain-language
search seeds, then tags each against a candidate failure-mode taxonomy. Tagging
here is mechanical pre-classification only -- it narrows ~thousands of issues to
a readable set. The actual mode definitions are written by hand from reading the
issues, and a mode ships only with >=3 citations from >=3 distinct orgs.

Output: data/issues_raw.json
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghclient as gh  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCORED = os.path.join(HERE, "..", "data", "scored.json")
SEEDS = os.path.join(HERE, "..", "data", "pain_issues_seed.json")
OUT = os.path.join(HERE, "..", "data", "issues_raw.json")

NOW = datetime.now(timezone.utc)

# Candidate taxonomy. These are priors stated up front so it is visible whether
# the data supported them or whether the pattern was imposed on the data.
# Modes that do not clear the citation bar get demoted to a weak-evidence
# section rather than quietly promoted.
TAXONOMY = {
    "chunking_destroys_answer": r"\b(chunk\w*)\b.{0,80}\b(table|header|split|boundar|overlap|markdown|pdf|layout|sentence)\b|\b(table|section)\b.{0,60}\bsplit across chunks?\b",
    "embedding_drift_reindex": r"\b(re-?index|re-?embed|migrat\w+ index|model upgrade|new embedding model|dimension mismatch|text-embedding-3|ada-002)\b",
    "acl_bypass": r"\b(permission|acl|access control|security trim\w*|authoriz\w+|group membership|sharepoint permission)\b.{0,90}\b(retriev|search|index|chunk|leak|expos)\b|\b(user (can|could) see|returns? documents? (they|the user) (cannot|can't|should not))\b",
    "exact_match_recall": r"\b(acronym|abbreviat|part number|sku|product code|exact match|keyword|lexical|bm25|hybrid search)\b.{0,90}\b(miss|not found|fail|poor|recall|retriev)\b",
    "stale_index": r"\b(stale|out of date|outdated|deleted document|removed document|sync|incremental|delta|change feed|tombstone)\b.{0,90}\b(index|retriev|search|vector)\b",
    "reranker_cost_no_gain": r"\b(rerank\w*|cross.?encoder|cohere rerank|semantic ranker)\b.{0,100}\b(latency|slow|expensive|cost|no improvement|worse|degrad)\b",
    "eval_set_overfit": r"\b(eval\w*|test set|golden set|ground truth|benchmark)\b.{0,100}\b(overfit|only.{0,20}demo|not representative|too easy|regress\w+ undetected|passes but)\b",
    "cost_surprise": r"\b(cost|expensive|bill|spend|budget|price)\b.{0,90}\b(per query|per document|embedding|token|index|scale|month)\b",
    "multitenant_leak": r"\b(tenant|multi.?tenant|namespace|partition|customer isolation)\b.{0,90}\b(leak|cross|isolat|mix|bleed|wrong customer)\b",
    "multilingual_cliff": r"\b(multilingual|non.?english|language|translat|chinese|japanese|german|french|arabic)\b.{0,90}\b(poor|worse|fail|not work|degrad|recall)\b",
    "citation_wrong": r"\b(citation|source|reference|footnote|attribut)\b.{0,90}\b(wrong|incorrect|mismatch|hallucin|does not match|missing)\b",
    "context_truncation": r"\b(context window|token limit|truncat|max_tokens|too long|exceeds?)\b.{0,90}\b(retriev|chunk|context|document|prompt)\b",
    "latency_p95": r"\b(latency|slow|timeout|p9[59]|response time|takes? \d+ seconds?)\b.{0,90}\b(retriev|search|index|query|rag|vector)\b",
    "ingestion_fidelity": r"\b(pdf|ocr|scanned|docx|pptx|excel|extract\w*|parse|layout)\b.{0,90}\b(fail|garbl|wrong|lost|missing|poor quality|broken)\b",
}

PAIN_HINT = re.compile(
    r"\b(production|prod\b|enterprise|customer|client|at scale|real.?world|million|thousands of (documents|users))\b", re.I)


def classify(title, body):
    text = f"{title}\n{body or ''}"[:12000]
    tags = [k for k, rx in TAXONOMY.items() if re.search(rx, text, re.I | re.S)]
    return tags, bool(PAIN_HINT.search(text))


def harvest_repo(full_name, per_repo=120, days=900):
    """Pull issues from a repo, newest first, and pre-classify them."""
    since = (NOW - timedelta(days=days)).isoformat()
    out = []
    for it in gh.paginate(f"/repos/{full_name}/issues",
                          {"state": "all", "since": since, "sort": "updated", "direction": "desc"},
                          max_pages=max(1, per_repo // 100)):
        if "pull_request" in it:
            continue
        tags, prod = classify(it.get("title", ""), it.get("body", ""))
        if not tags:
            continue
        out.append({
            "repo": full_name,
            "number": it["number"],
            "title": it.get("title"),
            "url": it.get("html_url"),
            "state": it.get("state"),
            "created_at": it.get("created_at"),
            "closed_at": it.get("closed_at"),
            "comments": it.get("comments"),
            "labels": [l.get("name") for l in it.get("labels", [])],
            "author": (it.get("user") or {}).get("login"),
            "body": (it.get("body") or "")[:6000],
            "tags": tags,
            "production_signal": prod,
            "reactions": (it.get("reactions") or {}).get("total_count", 0),
        })
        if len(out) >= per_repo:
            break
    return out


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    with open(SCORED) as f:
        scored = json.load(f)
    repos = [r["full_name"] for r in scored[:top_n]]

    corpus = []
    seen = set()
    for i, name in enumerate(repos):
        try:
            got = harvest_repo(name)
        except Exception as ex:
            print(f"  !! {name}: {ex}", flush=True)
            got = []
        for g in got:
            key = (g["repo"], g["number"])
            if key not in seen:
                seen.add(key)
                corpus.append(g)
        print(f"[{i+1}/{len(repos)}] {name}: +{len(got)} (corpus={len(corpus)}) {gh.rate_status()}", flush=True)
        if i % 5 == 0:
            with open(OUT, "w") as f:
                json.dump(corpus, f, indent=1)

    # Fold in the pain-language search seeds: these reach repos outside the
    # scored top-N, which matters because the pain is not confined to the
    # best-engineered projects.
    if os.path.exists(SEEDS):
        with open(SEEDS) as f:
            seeds = json.load(f)
        for s in seeds:
            key = (s.get("repo"), s.get("number"))
            if not s.get("repo") or key in seen:
                continue
            full = gh.get(f"/repos/{s['repo']}/issues/{s['number']}")
            if not full or "pull_request" in full:
                continue
            tags, prod = classify(full.get("title", ""), full.get("body", ""))
            if not tags:
                continue
            seen.add(key)
            corpus.append({
                "repo": s["repo"], "number": full["number"], "title": full.get("title"),
                "url": full.get("html_url"), "state": full.get("state"),
                "created_at": full.get("created_at"), "closed_at": full.get("closed_at"),
                "comments": full.get("comments"),
                "labels": [l.get("name") for l in full.get("labels", [])],
                "author": (full.get("user") or {}).get("login"),
                "body": (full.get("body") or "")[:6000],
                "tags": tags, "production_signal": prod,
                "reactions": (full.get("reactions") or {}).get("total_count", 0),
                "from_seed_query": s.get("query"),
            })
        print(f"after seed fold-in: corpus={len(corpus)}", flush=True)

    with open(OUT, "w") as f:
        json.dump(corpus, f, indent=1)

    from collections import Counter
    c = Counter(t for g in corpus for t in g["tags"])
    orgs = {t: len({g["repo"].split("/")[0] for g in corpus if t in g["tags"]}) for t in c}
    print(f"\ncorpus={len(corpus)} issues")
    for t, n in c.most_common():
        print(f"  {t:34s} {n:5d} issues  {orgs[t]:3d} distinct orgs")


if __name__ == "__main__":
    main()
