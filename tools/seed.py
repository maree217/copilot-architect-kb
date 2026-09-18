"""Phase 1 -- build the candidate pool for the enterprise RAG survey.

Four orthogonal seeding strategies, so the pool is not shaped by the bias of a
single query. Deliberately does NOT rank or filter by stars; stars are recorded
as one field among many and excluded from scoring downstream.

Output: data/candidates.json -- {full_name: {repo metadata, seeds: [...]}}
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghclient as gh  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "candidates.json")

# --- Seed 1: vendor lineage -------------------------------------------------
# Reference architectures and first-party samples. These are where a vendor
# publishes what it tells customers to build -- and, in their commit history,
# what it quietly stopped telling them to build.
VENDOR_ORGS = [
    "Azure-Samples", "microsoft", "Azure", "aws-samples", "awslabs",
    "GoogleCloudPlatform", "google-gemini", "langchain-ai", "run-llama",
    "weaviate", "qdrant", "elastic", "pgvector", "chroma-core", "vespa-engine",
    "deepset-ai", "explodinggradients", "truera", "confident-ai", "promptfoo",
    "NVIDIA-AI-Blueprints", "opensearch-project", "milvus-io", "infiniflow",
]
VENDOR_QUERIES = [
    "rag", "retrieval augmented", "vector search", "search openai",
    "chat your data", "document intelligence", "knowledge base",
]

# --- Seed 2: dependency lineage --------------------------------------------
# Repos that IMPORT retrieval primitives are applications, not libraries. This
# is how we find the systems built on the stack rather than the stack itself.
IMPORT_PROBES = [
    'from azure.search.documents import',
    'from qdrant_client import',
    'from langchain.retrievers import',
    'from llama_index.core import VectorStoreIndex',
    'from rank_bm25 import',
    'import weaviate',
    'from FlagEmbedding import',
    'from sentence_transformers import CrossEncoder',
    'CREATE INDEX USING ivfflat',
    'from ragas import evaluate',
    'from deepeval.metrics import',
    'from trulens',
]

# --- Seed 3: failure lineage ------------------------------------------------
# Operational-pain language in issues. A repo whose tracker contains these is a
# repo somebody actually ran. This is the highest-signal seed in the set.
PAIN_QUERIES = [
    'retrieval recall dropped', 'reranker made results worse',
    'chunking splits tables', 'reindex embeddings model upgrade',
    'vector search misses exact match', 'hallucinat retrieval context',
    'stale index documents deleted', 'document level permissions search',
    'RAG latency p95', 'cost per query embeddings',
    'acronym search not found vector', 'multi tenant index isolation',
    'citation wrong source chunk', 'context window truncated retrieval',
    'groundedness score low', 'evaluation set retrieval regression',
]

# --- Seed 4: eval lineage ---------------------------------------------------
# Repos that depend on an eval harness had to define what "working" means
# numerically. That is rarer, and more informative, than any popularity metric.
EVAL_PROBES = ["ragas", "trulens-eval", "deepeval", "promptfoo", "azure-ai-evaluation"]


def add(pool, repo, seed):
    """Record a repo in the pool, accumulating which seeds surfaced it."""
    if not repo or repo.get("fork") or repo.get("archived") is None and "full_name" not in repo:
        return
    name = repo.get("full_name")
    if not name:
        return
    entry = pool.setdefault(name, {
        "full_name": name,
        "owner": repo.get("owner", {}).get("login"),
        "html_url": repo.get("html_url"),
        "description": repo.get("description"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues": repo.get("open_issues_count"),
        "language": repo.get("language"),
        "archived": repo.get("archived"),
        "fork": repo.get("fork"),
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
        "license": (repo.get("license") or {}).get("spdx_id"),
        "topics": repo.get("topics", []),
        "seeds": [],
    })
    if seed not in entry["seeds"]:
        entry["seeds"].append(seed)


def seed_vendor(pool):
    for org in VENDOR_ORGS:
        for q in VENDOR_QUERIES:
            for r in gh.search("repositories", f"{q} org:{org} fork:false", max_pages=1, per_page=50):
                add(pool, r, f"vendor:{org}")
        print(f"  vendor {org}: pool={len(pool)}", flush=True)


def seed_dependency(pool):
    for probe in IMPORT_PROBES:
        hits = gh.search("code", f'"{probe}"', max_pages=1, per_page=100)
        for h in hits:
            add(pool, h.get("repository", {}), "dependency")
        print(f"  dep {probe[:40]!r}: {len(hits)} hits, pool={len(pool)}", flush=True)


def seed_failure(pool):
    """Search issues for operational pain. Also records the issues themselves --
    these become the raw material for the failure-mode corpus in Phase 3."""
    issue_hits = []
    for q in PAIN_QUERIES:
        items = gh.search("issues", f'{q} in:title,body is:issue', max_pages=1, per_page=100)
        for it in items:
            url = it.get("repository_url", "")
            full = "/".join(url.split("/")[-2:]) if url else None
            if full:
                add(pool, {"full_name": full, "owner": {"login": full.split("/")[0]}}, "failure")
            issue_hits.append({
                "repo": full,
                "number": it.get("number"),
                "title": it.get("title"),
                "url": it.get("html_url"),
                "state": it.get("state"),
                "created_at": it.get("created_at"),
                "comments": it.get("comments"),
                "query": q,
            })
        print(f"  pain {q!r}: {len(items)} issues, pool={len(pool)}", flush=True)
    return issue_hits


def seed_eval(pool):
    for probe in EVAL_PROBES:
        for r in gh.search("repositories", f"{probe} in:readme,description fork:false", max_pages=1, per_page=50):
            add(pool, r, "eval")
        hits = gh.search("code", f'"{probe}" filename:requirements.txt', max_pages=1, per_page=100)
        for h in hits:
            add(pool, h.get("repository", {}), "eval")
        print(f"  eval {probe}: pool={len(pool)}", flush=True)


def main():
    pool = {}
    print("rate:", gh.rate_status(), flush=True)

    print("\n[1/4] vendor lineage", flush=True)
    seed_vendor(pool)
    print("\n[2/4] dependency lineage", flush=True)
    seed_dependency(pool)
    print("\n[3/4] failure lineage", flush=True)
    issues = seed_failure(pool)
    print("\n[4/4] eval lineage", flush=True)
    seed_eval(pool)

    # Hydrate entries that came from issue search (they carry no repo metadata).
    thin = [n for n, e in pool.items() if e.get("stars") is None]
    print(f"\nhydrating {len(thin)} thin entries", flush=True)
    for i, name in enumerate(thin):
        r = gh.get(f"/repos/{name}")
        if r:
            e = pool[name]
            e.update({
                "html_url": r.get("html_url"), "description": r.get("description"),
                "stars": r.get("stargazers_count"), "forks": r.get("forks_count"),
                "open_issues": r.get("open_issues_count"), "language": r.get("language"),
                "archived": r.get("archived"), "fork": r.get("fork"),
                "created_at": r.get("created_at"), "pushed_at": r.get("pushed_at"),
                "license": (r.get("license") or {}).get("spdx_id"),
                "topics": r.get("topics", []),
            })
        if i % 25 == 0:
            print(f"  {i}/{len(thin)}", flush=True)

    by_seed = defaultdict(int)
    for e in pool.values():
        for s in e["seeds"]:
            by_seed[s.split(":")[0]] += 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"candidates": pool, "pain_issues": issues}, f, indent=1)
    with open(OUT.replace("candidates.json", "pain_issues_seed.json"), "w") as f:
        json.dump(issues, f, indent=1)

    print(f"\npool={len(pool)} by_seed={dict(by_seed)}")
    print("rate:", gh.rate_status())


if __name__ == "__main__":
    main()
