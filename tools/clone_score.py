"""Phase 2 (clone-based) -- score candidate repos on seven evidence signals.

This session's proxy blocks the GitHub API for any repo outside its configured
set, so scoring works from `git clone` instead. That turned out to be the better
instrument: git history gives true commit-level authorship and churn rather than
a paginated API sample, and it exposes file DELETIONS, which is what Phase 4
needs to see what vendors quietly removed from their reference architectures.

Design constraint, unchanged: stars are not an input. There is no star field to
read here at all -- popularity is simply absent from the instrument, rather than
present and ignored.

Each repo is cloned, analysed, and deleted. Peak disk stays at one repo.

Output: data/scored.json  (append-safe; re-runs skip already-scored repos)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "scored.json")
NOW = datetime.now(timezone.utc)

CODE_EXT = (".py", ".ts", ".js", ".cs", ".java", ".go", ".tsx", ".jsx", ".rb",
            ".ipynb", ".bicep", ".tf", ".yaml", ".yml")
TEXT_EXT = CODE_EXT + (".md", ".rst", ".txt", ".json", ".toml", ".cfg", ".sql")

MAX_FILE_BYTES = 400_000
MAX_FILES_SCANNED = 4000

# --- RAG surface ------------------------------------------------------------
# Signals are computed ONLY over files that touch retrieval. Without this, the
# instrument measures repo size: a large polyglot project trips every pattern
# at least once somewhere in its tree and saturates the score. It also produced
# a concrete false positive in testing -- a repo scored 1.0 on evaluation
# because it contained a Go coding-agent `evals/` directory with no connection
# to retrieval quality.
#
# Scoping to the RAG surface means the question becomes "of the code that does
# retrieval, how much of it is operationally serious", which is the question the
# guide actually needs answered.
RAG_SURFACE_RE = re.compile(
    r"\b(embedding|embed_|vector_?(store|search|index|db)|retriev|rerank|chunk"
    r"|semantic_?(search|kernel|ranker)|knowledge_?base|\brag\b|similarity_?search"
    r"|faiss|qdrant|weaviate|pinecone|chroma|milvus|pgvector|azure\.search"
    r"|SearchClient|VectorStore|DocumentIntelligence|text-embedding|bm25|hybrid_?search)\b",
    re.I)

# --- Signal 1: operational burden -------------------------------------------
# Code nobody writes until they have been paged.
#
# Each entry is (regex, weight, target). `target` is the hits-per-100-RAG-files
# density at which the pattern earns its full weight. Presence alone is not
# enough: one `timeout=` in a 3000-file repo says nothing, so a pattern's
# contribution scales with density up to its target and is capped there.
OPS_PATTERNS = {
    "retry_backoff": (r"\b(exponential_?backoff|retry_with_backoff|tenacity|@retry\b|backoff\.expo|RetryPolicy|max_?retries|Polly)\b", 1.5, 4.0),
    "timeouts": (r"\b(timeout\s*=|TimeoutError|request_?timeout|ReadTimeout|HttpTimeout|WithTimeout)\b", 1.0, 6.0),
    "rate_limit": (r"\b(rate_?limit\w*|RateLimit\w*|TooManyRequests|throttl\w+|Retry-?After|quota_?exceeded)\b", 1.5, 3.0),
    "idempotency": (r"\b(idempoten\w+|upsert\w*|dedup\w*|content_?hash|merge_?or_?upload)\b", 1.0, 4.0),
    "cost_accounting": (r"\b(prompt_?tokens|completion_?tokens|total_?tokens|cost_?per_\w+|tiktoken|token_?budget)\b", 2.0, 3.0),
    "reindex_path": (r"\b(re-?index\w*|rebuild_?index|migrate_?index|backfill\w*|index_?version|swap_?alias|alias_?swap)\b", 2.5, 2.0),
    "observability": (r"\b(opentelemetry|OpenTelemetry|tracer\.start|structlog|applicationinsights|app_?insights|prometheus_client|metrics\.(record|emit|increment))\b", 1.0, 2.0),
    "circuit_breaker": (r"\b(circuit_?breaker|CircuitBreaker|bulkhead|graceful_?degrad\w*)\b", 1.5, 1.0),
}
OPS_MAX = 12.0

# --- Signal 2: retrieval evaluation -----------------------------------------
# Unit tests are not evaluation. This looks for somebody putting a number on
# whether the retrieval was right.
EVAL_PATTERNS = {
    "retrieval_metrics": (r"\b(recall_?at_?k|recall@\d|ndcg\w*|\bmrr\b|precision_?at_?k|hit_?rate|map@\d)\b", 3.0, 1.5),
    "generation_metrics": (r"\b(groundedness|faithfulness|answer_?relevanc\w+|context_?precision|context_?recall|hallucination_?rate)\b", 2.5, 1.5),
    "eval_harness": (r"\b(ragas|trulens|deepeval|promptfoo|azure-ai-evaluation|AzureAIEvaluat\w*|giskard|langsmith)\b", 1.5, 2.0),
    "golden_set": (r"\b(golden_?(set|dataset)|ground_?truth|qa_?pairs|eval_?set|testset|benchmark_?questions)\b", 2.0, 2.0),
    "regression_gate": (r"assert\w*\s*\(?[^\n]{0,60}(recall|ndcg|groundedness|faithfulness)\s*[><=]|\bmin_?score\b|\bscore_?threshold\b", 3.0, 1.0),
}
EVAL_MAX = 9.0

# --- Signal 6: enterprise-gate readiness ------------------------------------
# The things that kill enterprise RAG at security review. Document-level ACL is
# weighted highest: it is the single most common reason a working pilot cannot
# ship, and the single thing demo repos never implement.
ENTERPRISE_PATTERNS = {
    "authn": (r"\b(DefaultAzureCredential|ManagedIdentity|managed_?identity|OAuth2?|OIDC|\bmsal\b|EntraID|azure\.identity|assume_?role)\b", 1.5, 3.0),
    # Weighted highest: document-level ACL is the most common reason a working
    # pilot cannot ship, and the thing demo repos never implement.
    "doc_acl": (r"\b(security_?filter\w*|security_?trimming|acl_?filter|permission_?filter|row_?level_?security|authorized_?(users|groups)|allowed_?(groups|oids))\b", 3.5, 1.5),
    "tenancy": (r"\b(tenant_?id|multi_?tenant\w*|index_?per_?tenant|tenant_?isolation|per_?tenant)\b", 2.0, 2.0),
    "pii": (r"\b(\bpii\b|redact\w*|anonymi[sz]\w+|presidio|\bdlp\b)\b", 2.0, 1.5),
    "audit": (r"\b(audit_?log\w*|audit_?trail|compliance_?log|immutable_?log)\b", 2.0, 1.0),
    "residency": (r"\b(data_?residency|sovereign\w*|region_?lock|geo_?restrict\w*|eu_?data_?boundary)\b", 1.5, 0.5),
}
ENT_MAX = 9.0

# Churn that fakes liveness.
CHURN_RE = re.compile(
    r"^(bump\b|chore\(deps\)|chore: bump|update readme|docs?:|readme|merge branch|merge pull request"
    r"|dependabot|pre-commit autoupdate|fix typo|typo|format|lint|style:|\[skip ci\]|version bump)",
    re.I)

BOT_RE = re.compile(r"(\[bot\]|dependabot|renovate|github-actions|semantic-release)", re.I)


def run(cmd, cwd=None, timeout=240):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


def clone(full_name, dest):
    url = f"https://github.com/{full_name}.git"
    # Single branch, no tags: full history of the default branch (needed for
    # authorship, churn and deletion analysis) without dragging in every ref.
    out = subprocess.run(
        ["git", "clone", "--single-branch", "--no-tags", "--quiet", url, dest],
        capture_output=True, text=True, timeout=600)
    return out.returncode == 0


def read_tree(root):
    """Walk the repo once, returning every path plus the text of each readable
    source file, partitioned into the RAG surface and everything else.

    Scoring runs over the RAG surface only. See RAG_SURFACE_RE for why.
    """
    paths, rag_files, other_text, scanned = [], [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (
            ".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__",
            "site-packages", ".next", "target", "vendor", ".mypy_cache", "coverage")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            paths.append(rel)
            if scanned >= MAX_FILES_SCANNED or not rel.endswith(TEXT_EXT):
                continue
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    body = f.read()
            except OSError:
                continue
            scanned += 1
            # A file is on the RAG surface if its path or its content names
            # retrieval machinery.
            if RAG_SURFACE_RE.search(rel) or RAG_SURFACE_RE.search(body):
                rag_files.append((rel, body))
            else:
                other_text.append(body)
    return paths, rag_files, "\n".join(other_text)


def score_patterns(rag_files, patterns, maximum):
    """Density-normalised pattern scoring over the RAG surface.

    A pattern earns weight in proportion to how densely it appears per 100 RAG
    files, capped at its target density. This is what stops a 6000-file repo
    from saturating every signal by tripping each pattern once.
    """
    n_files = max(len(rag_files), 1)
    hits, densities, raw = {}, {}, 0.0
    for key, (rx, weight, target) in patterns.items():
        rxc = re.compile(rx, re.I)
        n = sum(len(rxc.findall(body)) for _, body in rag_files)
        if not n:
            continue
        density = n / n_files * 100.0
        frac = min(1.0, density / target)
        hits[key] = n
        densities[key] = round(density, 2)
        raw += weight * frac
    return round(min(raw / maximum, 1.0), 3), {
        "counts": hits, "per_100_rag_files": densities, "rag_files": n_files}


def sig_evaluation(paths, rag_files):
    """Evaluation must be evaluation OF RETRIEVAL. An `evals/` directory only
    counts when its contents are on the RAG surface -- in testing, a repo scored
    a perfect evaluation signal on the strength of a Go coding-agent eval
    harness that had nothing to do with retrieval quality."""
    rag_paths = {p for p, _ in rag_files}
    eval_dirs = [p for p in paths
                 if re.search(r"(^|/)(evals?|evaluation|benchmarks?)(/|$)", p, re.I)
                 and p in rag_paths]
    score, ev = score_patterns(rag_files, EVAL_PATTERNS, EVAL_MAX)
    if eval_dirs:
        score = round(min(score + 1.0 / EVAL_MAX, 1.0), 3)
    ev["eval_dirs_on_rag_surface"] = sorted(set(eval_dirs))[:8]
    return score, ev


def git_log_records(root, days=None):
    since = f"--since={days}.days.ago" if days else ""
    fmt = "%H%x1f%an%x1f%aI%x1f%s"
    args = ["git", "log", f"--pretty=format:{fmt}"]
    if since:
        args.append(since)
    out = run(args, cwd=root)
    recs = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            recs.append({"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]})
    return recs


def sig_maintenance(root):
    """Replaces the API-based issue-health signal. Measures whether the project
    is continuously tended or arrives in abandoned bursts: how many distinct
    months in the last two years saw a substantive commit."""
    recs = git_log_records(root, days=730)
    if not recs:
        return 0.0, {"commits_24mo": 0}
    months = set()
    substantive = 0
    for r in recs:
        if BOT_RE.search(r["author"]) or CHURN_RE.match(r["subject"].strip()):
            continue
        substantive += 1
        months.add(r["date"][:7])
    last = recs[0]["date"][:10]
    gap_days = (NOW - datetime.fromisoformat(recs[0]["date"])).days
    coverage = len(months) / 24.0
    freshness = max(0.0, 1.0 - gap_days / 365.0)
    score = round(min(0.6 * coverage + 0.4 * freshness, 1.0), 3)
    return score, {"commits_24mo": len(recs), "substantive_24mo": substantive,
                   "active_months_of_24": len(months), "last_commit": last,
                   "days_since_last_commit": gap_days}


def sig_bus_factor(root):
    recs = [r for r in git_log_records(root, days=365) if not BOT_RE.search(r["author"])]
    if not recs:
        return 0.0, {"commits_12mo": 0}
    counts = Counter(r["author"] for r in recs)
    substantive = [a for a, n in counts.items() if n >= 5]
    top_share = counts.most_common(1)[0][1] / sum(counts.values())
    score = min(len(substantive) / 4.0, 1.0) * (1.0 - 0.5 * max(0.0, top_share - 0.5) / 0.5)
    return round(max(0.0, min(score, 1.0)), 3), {
        "commits_12mo": len(recs), "distinct_authors": len(counts),
        "authors_5plus": len(substantive), "top_author_share": round(top_share, 2)}


def sig_recency(root):
    recs = git_log_records(root, days=90)
    subs = [r for r in recs
            if not BOT_RE.search(r["author"]) and not CHURN_RE.match(r["subject"].strip())]
    score = round(min(len(subs) / 25.0, 1.0), 3)
    return score, {"commits_90d": len(recs), "substantive_90d": len(subs),
                   "churn_ratio": round(1 - len(subs) / len(recs), 2) if recs else None}


LOCKFILES = {"poetry.lock", "uv.lock", "Pipfile.lock", "package-lock.json", "yarn.lock",
             "pnpm-lock.yaml", "requirements.lock", "packages.lock.json", "go.sum",
             "Cargo.lock", "Gemfile.lock"}
MANIFESTS = {"requirements.txt", "pyproject.toml", "package.json",
             "Directory.Packages.props", "go.mod", "Cargo.toml"}


def sig_dependency_honesty(root, paths):
    locks = [p for p in paths if os.path.basename(p) in LOCKFILES]
    mans = [p for p in paths if os.path.basename(p) in MANIFESTS]
    pinned = floating = 0
    for m in mans[:6]:
        try:
            with open(os.path.join(root, m), encoding="utf-8", errors="replace") as f:
                txt = f.read()[:120_000]
        except OSError:
            continue
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            if re.search(r"[=~^><]=?\s*v?\d+\.\d+", line) or re.search(r'":\s*"[\^~]?\d+\.\d+', line):
                pinned += 1
            elif re.match(r"^[a-zA-Z][\w\-\[\]\.]{1,50}$", line):
                floating += 1
    total = pinned + floating
    ratio = pinned / total if total else 0.0
    score = round(0.5 * (1.0 if locks else 0.0) + 0.5 * ratio, 3)
    return score, {"lockfiles": sorted({os.path.basename(p) for p in locks})[:4],
                   "pinned": pinned, "floating": floating, "pin_ratio": round(ratio, 2)}


def collect_deletions(root, limit=400):
    """Phase 4 raw material: files removed over the repo's life. A vendor
    deleting a component from its own reference architecture is the closest
    thing to a public admission that it did not work."""
    out = run(["git", "log", "--diff-filter=D", "--name-only",
               "--pretty=format:%x02%H%x1f%aI%x1f%s"], cwd=root)
    events, cur = [], None
    for line in out.splitlines():
        if line.startswith("\x02"):
            parts = line[1:].split("\x1f")
            cur = {"sha": parts[0], "date": parts[1] if len(parts) > 1 else None,
                   "subject": parts[2] if len(parts) > 2 else "", "files": []}
            events.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())
    events = [e for e in events if e["files"]]
    return events[:limit]


GH_LINK_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=[)\s\"'#,<\]]|$)")
NOISE_OWNERS = {"actions", "shields", "badges", "github", "gitpod-io", "python",
                "nodejs", "docker", "pre-commit", "psf", "astral-sh", "pypa",
                "readthedocs", "sponsors", "npm", "codecov"}
NOISE_REPOS = {"license", "blob", "tree", "releases", "issues", "actions", "workflows"}


def referenced_repos(root, paths, limit=60):
    """GitHub repos this project points at, from its docs and manifests.

    Feeds snowball expansion of the candidate pool: repos that working retrieval
    code depends on, rather than repos somebody curated.
    """
    out = set()
    interesting = [p for p in paths
                   if os.path.basename(p).lower() in (
                       "readme.md", "requirements.txt", "pyproject.toml",
                       "package.json", "go.mod", "docs.md", "architecture.md")
                   or p.lower().startswith("docs/")][:40]
    for rel in interesting:
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                body = f.read(200_000)
        except OSError:
            continue
        for owner, name in GH_LINK_RE.findall(body):
            if owner.lower() in NOISE_OWNERS or name.lower() in NOISE_REPOS:
                continue
            if "." in name and not name.endswith((".js", ".py")):
                continue
            out.add(f"{owner}/{name}")
    return sorted(out)[:limit]


def classify_kind(root, paths, rag_files):
    """Classify what KIND of thing this repo is.

    Scoring a library against a deployable application on one scale is
    apples-to-oranges: an eval library trivially maxes the evaluation signal by
    being the thing that does evaluation, and a library has no enterprise
    surface because deployment is not its job. The guide compares within kind.
    """
    base = {os.path.basename(p) for p in paths}
    lower = {p.lower() for p in paths}
    has = lambda n: n in base  # noqa: E731
    anyp = lambda frag: any(frag in p for p in lower)  # noqa: E731

    infra = (has("azure.yaml") or has("main.bicep") or anyp("infra/")
             or anyp(".tf") or has("azuredeploy.json") or has("template.yaml"))
    packaged = has("setup.py") or has("pyproject.toml") or has("package.json")
    published = False
    if has("pyproject.toml"):
        try:
            with open(os.path.join(root, "pyproject.toml"), errors="replace") as f:
                published = "[project]" in f.read() or "[tool.poetry]" in f.read()
        except OSError:
            pass
    composed = has("docker-compose.yml") or has("docker-compose.yaml")
    ui = anyp("frontend/") or anyp("webapp/") or anyp("/ui/") or anyp("app/src/")
    notebooks = sum(1 for p in lower if p.endswith(".ipynb"))
    code_files = [p for p in paths if p.endswith(CODE_EXT)]

    eval_density = 0
    if rag_files:
        rxc = re.compile(EVAL_PATTERNS["eval_harness"][0], re.I)
        eval_density = sum(len(rxc.findall(b)) for _, b in rag_files) / len(rag_files)

    if eval_density > 3 and published and not infra:
        kind = "eval_harness"
    elif infra and (ui or composed):
        kind = "reference_architecture"
    elif infra:
        kind = "deployable_sample"
    elif composed and ui and len(code_files) > 300:
        kind = "platform"
    elif published and not ui and not composed:
        kind = "library"
    elif notebooks > max(3, len(code_files) * 0.3):
        kind = "tutorial"
    else:
        kind = "application"

    return kind, {"infra": infra, "packaged": packaged, "published": published,
                  "composed": composed, "ui": ui, "notebooks": notebooks,
                  "code_files": len(code_files)}


def repo_meta(root, full_name):
    origin_head = run(["git", "rev-parse", "HEAD"], cwd=root).strip()
    first = run(["git", "log", "--reverse", "--pretty=format:%aI", "--max-count=1"], cwd=root).strip()
    lic = None
    for cand in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE"):
        p = os.path.join(root, cand)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                head = f.read(400)
            for name in ("Apache License", "MIT License", "BSD", "GNU GENERAL PUBLIC",
                         "Mozilla Public License"):
                if name.lower() in head.lower():
                    lic = name
                    break
            break
    return {"head": origin_head, "first_commit": first or None, "license_guess": lic}


WEIGHTS = {
    "operational": 0.18,
    "evaluation": 0.20,
    "maintenance": 0.14,
    "bus_factor": 0.12,
    "dependency_honesty": 0.08,
    "enterprise": 0.20,
    "recency": 0.08,
}


def score_repo(full_name, seeds):
    tmp = tempfile.mkdtemp(prefix="ragsurvey-")
    root = os.path.join(tmp, "repo")
    try:
        if not clone(full_name, root):
            return None
        paths, rag_files, _ = read_tree(root)
        if len([p for p in paths if p.endswith(CODE_EXT)]) < 3:
            return None
        # No retrieval surface means this is not a RAG system, whatever the
        # README claims. Excluded rather than scored zero, so it does not sit in
        # the dataset looking like a bad RAG repo.
        if len(rag_files) < 3:
            return {"full_name": full_name, "excluded": "no_rag_surface",
                    "rag_files": len(rag_files), "file_count": len(paths),
                    "composite": -1.0, "seeds": seeds}

        s, e = {}, {}
        s["operational"], e["operational"] = score_patterns(rag_files, OPS_PATTERNS, OPS_MAX)
        s["evaluation"], e["evaluation"] = sig_evaluation(paths, rag_files)
        s["maintenance"], e["maintenance"] = sig_maintenance(root)
        s["bus_factor"], e["bus_factor"] = sig_bus_factor(root)
        s["dependency_honesty"], e["dependency_honesty"] = sig_dependency_honesty(root, paths)
        s["enterprise"], e["enterprise"] = score_patterns(rag_files, ENTERPRISE_PATTERNS, ENT_MAX)
        s["recency"], e["recency"] = sig_recency(root)

        kind, kind_evidence = classify_kind(root, paths, rag_files)

        return {
            "full_name": full_name,
            "html_url": f"https://github.com/{full_name}",
            "seeds": seeds,
            "kind": kind,
            "kind_evidence": kind_evidence,
            "meta": repo_meta(root, full_name),
            "file_count": len(paths),
            "rag_file_count": len(rag_files),
            "signals": s,
            "evidence": e,
            "composite": round(sum(s[k] * WEIGHTS[k] for k in WEIGHTS), 4),
            "deletions": collect_deletions(root),
            "referenced_repos": referenced_repos(root, paths),
            "scored_at": NOW.isoformat(),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    cand_path = os.path.join(DATA, "candidates.json")
    with open(cand_path) as f:
        cands = json.load(f)["candidates"]

    done = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            done = {r["full_name"]: r for r in json.load(f)}

    todo = [n for n in cands if n not in done]
    print(f"{len(done)} already scored, {len(todo)} to go", flush=True)

    results = list(done.values())
    for i, name in enumerate(todo):
        try:
            r = score_repo(name, cands[name].get("seeds", []))
        except Exception as ex:
            print(f"  !! {name}: {type(ex).__name__}: {ex}", flush=True)
            r = None
        if r:
            results.append(r)
            print(f"[{i+1}/{len(todo)}] {name} -> {r['composite']}", flush=True)
        else:
            print(f"[{i+1}/{len(todo)}] {name} -> SKIP", flush=True)
        # Checkpoint every repo: a killed run must never lose completed work.
        results.sort(key=lambda r: -r["composite"])
        with open(OUT, "w") as f:
            json.dump(results, f, indent=1)

    print(f"\nscored {len(results)} repos -> {OUT}")


if __name__ == "__main__":
    main()
