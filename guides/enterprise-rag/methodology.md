# Methodology

How this survey decides a repository is worth your attention, why star count is
absent, and what the method cannot see.

## The premise

Enterprises do not open-source their production RAG systems. There is no repo
called `bank-kyc-rag-prod`. Any survey that treats GitHub as a catalogue of
enterprise deployments is reading vendor demos and calling them evidence.

What GitHub does hold truthfully is narrower and more useful:

1. **Issue trackers of the frameworks enterprises build on.** The only public
   place where "this did not work" is stated by the person it happened to, with
   a date and a version.
2. **Commit history of vendor reference architectures.** What a vendor *deleted*
   from its own showcase is the closest thing to a public admission.
3. **What the code does versus what the README claims.** Access control,
   reindex strategy, cost accounting — present or absent, no interpretation
   required.

The survey is built on those three and makes no claim beyond them.

## Why star count is not used

Stars measure how many people heard about a repo, lagged by months to years, and
they never decay. A repo can be abandoned, broken, and highly starred at the same
time — this survey found exactly that case (see `microsoft/kernel-memory` in the
findings). Popularity is not an input to any score here.

The stronger version of the same trap is subtler: **any metric that grows with
repo size is star count wearing a lab coat.** The first working version of this
scorer had that fault. It counted pattern presence across the whole tree, so a
6,267-file project tripped every pattern at least once and scored 0.977 — top of
the table, on the strength of being large. Two fixes:

- **Density, not presence.** Each pattern contributes in proportion to hits per
  100 RAG-surface files, capped at a per-pattern target density. One `timeout=`
  in 3,000 files earns nothing.
- **Scoped to the RAG surface.** Signals are computed only over files that touch
  retrieval (see `RAG_SURFACE_RE` in `tools/clone_score.py`). Without this, the
  instrument measures project size. It also produced a concrete false positive:
  one repo scored a perfect evaluation signal because it contained a Go
  coding-agent `evals/` directory with no connection to retrieval quality.

After both fixes the same repo scored 0.860, and the signal that matters started
discriminating: document-level ACL density of 28.7 per 100 files for a project
that implements security trimming, against 0.0 for one that does not.

## The seven signals

| Signal | Weight | What it detects |
|---|---|---|
| Operational burden | 0.18 | Retry/backoff, timeouts, rate-limit handling, idempotency, cost accounting, reindex paths, tracing — code nobody writes until they have been paged |
| Retrieval evaluation | 0.20 | recall@k, nDCG, MRR, groundedness, golden sets, regression gates. Unit tests are not evaluation |
| Enterprise gate | 0.20 | AuthN, **document-level ACL**, tenancy, PII, audit, residency — what kills pilots at security review |
| Maintenance | 0.14 | Distinct months with substantive commits over 24 months. Detects abandoned-in-bursts vs. continuously tended |
| Bus factor | 0.12 | Sustained contributors over 12 months, penalised by top-author concentration |
| Dependency honesty | 0.08 | Lockfile presence and pin ratio |
| Substantive recency | 0.08 | 90-day commits excluding badge bumps, dependabot, formatting, typo fixes |

Document-level ACL carries the heaviest single pattern weight (3.5) because it is
the most common reason a working pilot cannot ship, and the thing demo repos
never implement.

## Scoring is within kind, not across

Repos are classified as `reference_architecture`, `platform`, `library`,
`application`, `deployable_sample`, `eval_harness` or `tutorial`, and compared
only within that class.

This matters more than it sounds. An evaluation library trivially maxes the
evaluation signal by *being* the thing that does evaluation. A library scores
near zero on the enterprise gate because deployment is not its job — that is a
category fact, not a defect. Ranking a library against a deployable architecture
on one scale is how "top 10 RAG repos" lists produce confidently wrong tables.

**The kind classifier is heuristic and gets things wrong.** In this run it
labelled `Arize-ai/phoenix` a reference architecture and `langchain-ai/langchain`
an application. Treat `kind` as a grouping aid, not a verdict, and check
`kind_evidence` in the dataset when it matters.

## Anti-signals

Recorded here because they were encountered, not hypothesised:

- **README benchmark numbers with no eval code.** Common.
- **Repo-cloning spam.** A single search returned four byte-identical
  `rag-chunker` repos under four different owners, with identical descriptions.
  Another returned two identical `awesome-rag-production` lists. Search relevance
  ranking surfaces these alongside real projects; a survey that harvests search
  results without an evidence filter ingests them as data.
- **Awesome-list membership as evidence.** Circular: lists cite lists.
- **Doc-only commits masking a dead codebase.** The recency signal excludes
  badge, dependabot, typo and formatting commits for this reason.
- **Green squares from one person.** See bus factor.

## What this method cannot see

Stated plainly, because the gaps are structural rather than fixable with more
effort:

- **Production scale, real cost, real user satisfaction.** Not observable from a
  repository. Where a claim would need them, this survey does not make it.
- **The systems that failed so badly nobody published them.** The strongest
  evidence about enterprise RAG failure is, by definition, absent from GitHub.
- **Private enterprise deployments.** The actual subject of interest is not here.
- **Mode frequency.** The failure-mode catalogue is *evidenced*, not
  *quantified*. It cannot tell you that N% of production RAG problems are
  chunking, because the sample is not a sample of production systems — it is a
  sample of what got written down in public. Claims of the form "X% of RAG
  failures are Y" elsewhere on the internet are not derivable from this data
  either.
- **Candidate-pool bias.** The GitHub search API was unavailable in the
  environment that produced this run (see below), so the pool was assembled from
  a hand-written list plus this repository's existing references plus snowball
  expansion from cloned repos' own manifests. A hand-written list carries its
  author's blind spots, and repos nobody has heard of cannot appear in it. The
  `provenance` field in `data/candidates.json` records how each repo entered the
  pool. This is the weakest part of the method.

## Environment constraint affecting this run

The session that produced this dataset had GitHub API access scoped to a single
repository: `/search/*` and `/repos/{other}/*` both returned 403. Consequences:

- Repo discovery used curated seeding and snowball expansion rather than search.
- Scoring reads `git clone` rather than the API. This is **better** for six of
  the seven signals — real commit history beats a paginated sample, and file
  deletions become visible — but it removes star counts and issue metadata from
  the dataset entirely.
- The issue-health signal, the one that genuinely needed the API, was replaced by
  a maintenance signal derived from commit cadence.
- The failure-mode corpus was gathered by web search and page fetch rather than
  bulk issue harvesting, which is why it is evidenced rather than quantified.

`tools/harvest_issues.py` implements the API-based corpus harvest and is retained
unused: run it in an environment with a normal GitHub token to quantify what this
run could only cite.

## Reproducing

```bash
python3 tools/build_candidates.py   # assemble the pool
python3 tools/clone_score.py        # clone, score, delete; checkpoints per repo
python3 tools/gen_tables.py         # regenerate the markdown tables
```

Weights live in `WEIGHTS` at the top of `tools/clone_score.py`. Disagree with
them, change them, re-run, and the tables change. That is the point of shipping
the dataset rather than only the conclusions.
