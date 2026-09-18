# Enterprise RAG: what the code actually shows

An evidence-based guide to enterprise retrieval-augmented generation, built by
cloning and measuring 109 repositories rather than by reading their READMEs.

**No score in this guide uses star count.** [Why, and what replaced it](./methodology.md).

- [**Build guide**](./BUILD-GUIDE.md) — how to actually build one: architecture, build order, 12 failure modes, security, cost model, business archetypes, 90-day plan
- [Failure modes](./failure-modes.md) — the catalogue, with evidence grading
- [Repository evaluations](./repo-evaluations.md) — 88 scored repos, compared within kind
- [Methodology](./methodology.md) — the rubric, the anti-signals, and what this cannot see
- Raw data: [`data/scored.json`](../../data/scored.json), [`data/candidates.json`](../../data/candidates.json)

---

## The four numbers

Measured across 88 repositories that passed a retrieval-surface filter. These are
the findings that should change a decision.

| Finding | Number | So what |
|---|---|---|
| Repos implementing **document-level access control** | **2 of 88 (2%)** | The thing that blocks enterprise deployment is the thing almost nobody builds. You will be writing it yourself. |
| Repos that **measure retrieval quality** numerically | 26 of 88 (29%) | 71% cannot detect a retrieval regression. Neither can you, if you copy them. |
| Repos with any **reindex / migration path** | 36 of 88 (40%) | Embedding-model deprecation is scheduled, not hypothetical. Most codebases have no answer to it. |
| Repos with **both** ACL and retrieval metrics | **1 of 88** | There is essentially no public example of a secured, measured RAG system to copy. |

That last row is the guide's central point. The gap between "RAG demo" and
"system that survives a security review" is not a small engineering increment —
it is almost the entire job, and it is almost entirely unpublished.

## Start here: the four questions

Ask these before choosing a stack. Each maps to a confirmed failure mode.

1. **Can retrieval accept a per-request user identity, and does ingestion write a
   filterable identity field?** If no, you have no document security, and
   retrofitting it means reindexing everything.
   → [Mode 1](./failure-modes.md#1-document-level-access-control-is-absent-and-often-structurally-unavailable)
2. **Is your hybrid search true rank fusion, or does the lexical score only
   reorder vector candidates?** If the latter, exact identifiers will never be
   recoverable. → [Mode 2](./failure-modes.md#2-hybrid-search-that-only-re-ranks-cannot-recover-a-vector-miss)
3. **Does your index store the embedding model id and refuse to serve on
   mismatch?** If not, a model swap will degrade quality silently.
   → [Mode 3](./failure-modes.md#3-changing-the-embedding-model-silently-invalidates-the-index)
4. **Are tables and code blocks atomic at chunk time?** If not, you have baked
   wrong answers into the index. → [Mode 4](./failure-modes.md#4-chunking-splits-structure-and-the-damage-is-invisible)

A stack that answers all four is unusual. In this dataset, one repository did.

## Two findings that star count would have hidden

**`microsoft/kernel-memory` is effectively retired.** A well-known Microsoft RAG
library. In the last 12 months it received 26 commits, **all from a single
author**, and its most recent commit is titled *"Research project archive"*
(June 2026). Its star count reflects none of this. Verified directly from git
history; the bus-factor signal flagged it before the archive commit was read.

**Microsoft abandoned its own prompt format in its flagship RAG sample.**
`azure-search-openai-demo` migrated from Prompty to Jinja2 for prompt templates
in February 2026 — visible only in deletion history. If you standardised on
Prompty because the reference architecture used it, the reference architecture no
longer does.

Both are the kind of fact that only commit history tells you, and both are
invisible in every "awesome RAG" list.

## Where the strong work is

Scores are comparable **within** a kind, never across (a library scoring low on
the enterprise gate is a category fact, not a defect). Full tables in
[repository evaluations](./repo-evaluations.md).

| Kind | Leaders |
|---|---|
| Reference architecture | `GoogleCloudPlatform/generative-ai` (0.850), `elastic/elasticsearch-labs` (0.834), `Azure-Samples/azure-search-openai-demo` (0.756) |
| Platform / product | `topoteretes/cognee` (0.887), `infiniflow/ragflow` (0.860), `HKUDS/LightRAG` (0.803) |
| Retrieval measurement | `vespa-engine/sample-apps`, `castorini/pyserini`, `beir-cellar/beir`, `embeddings-benchmark/mteb` |
| Observability / eval | `Arize-ai/phoenix` (0.954), `langfuse/langfuse` (0.758), `promptfoo/promptfoo` (0.811) |

**`Azure-Samples/azure-search-openai-demo` is the single most useful repository
in this survey for enterprise work** — not because it scores highest (it does
not), but because it is the only reference architecture that implements
document-level security trimming at meaningful density (28.7 hits per 100 RAG
files, against 0.0 for almost everything else). On the question that actually
blocks deployment, it is close to the only worked example in public.

For retrieval measurement, the IR-research repos (`pyserini`, `beir`, `mteb`)
are more useful than any RAG framework's built-in eval. They were built by people
whose field has been measuring retrieval for thirty years.

## How to read the tables

`Ops` operational burden · `Eval` retrieval evaluation · `Ent` enterprise gate ·
`Bus` bus factor · `ACL` document-ACL density per 100 RAG files ·
`RetrMetrics` retrieval-metric density.

A low `Ent` on a library means nothing. A low `Ent` on a reference architecture
you plan to deploy means you are writing the security layer yourself. A `Bus`
below 0.25 means one person can end the project.

## Honest limits

Read [the methodology](./methodology.md#what-this-method-cannot-see) before
citing any of this. In short:

- **This is not a sample of production systems.** It is a sample of what got
  written down in public. No frequency claim ("X% of RAG failures are Y") is
  derivable from it, and the guide makes none.
- **Four of ten predicted failure modes cleared the evidence bar.** The other six
  are published as [weak evidence](./failure-modes.md#weak-evidence) rather than
  dressed up. Their absence mostly reflects commercial embarrassment — nobody
  files a public issue saying they leaked one tenant's documents to another.
- **The candidate pool was hand-seeded**, because the GitHub search API was
  unavailable in the environment that produced this run. Hand-written lists carry
  their author's blind spots. `provenance` in `data/candidates.json` records how
  every repo entered. Snowball expansion from the scored repos' own manifests has
  since grown the pool to **553 candidates**, of which 109 are scored here — the
  remaining 444 are queued for a second pass and may well displace some of the
  leaders above.
- **The kind classifier is heuristic and misfiled several repos.** Check
  `kind_evidence` before relying on it.

## Reproducing and disagreeing

```bash
python3 tools/build_candidates.py
python3 tools/clone_score.py
python3 tools/gen_tables.py
```

Weights are at the top of `tools/clone_score.py`. Change them, re-run, and the
tables change. The dataset ships with the conclusions precisely so the
conclusions can be contested — which is the difference between this and a
curated list.
