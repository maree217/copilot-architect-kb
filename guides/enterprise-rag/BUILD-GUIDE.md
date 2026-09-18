# Enterprise RAG: a build guide and failure catalogue

For the person who has to make it work, get it through security review, and still
be able to afford it in month nine.

## How to read the claims in this document

Every substantive claim is tagged, because the three sources behind this document
have very different reliability and you should weight them differently.

| Tag | Source | How much to trust it |
|---|---|---|
| **[MEASURED]** | Computed from 88 repositories cloned and analysed for this survey. Reproducible via `tools/clone_score.py`. | High for what it measures. It measures published code, not production systems. |
| **[CITED]** | A specific public issue, commit, or vendor document, linked inline. | High. Go read the link. |
| **[DERIVED]** | Arithmetic from stated assumptions, shown in full so you can substitute your own. | As good as the assumptions, which are written out. |
| **[FIELD]** | Practitioner consensus from technical writing and my own working knowledge. No hard citation. | Directional only. Treat as a hypothesis to test, not a fact. |

Where a number is widely repeated online but I could not trace it to a primary
source, it is marked **[UNVERIFIED]** and you should not put it in a business
case.

---

## The one-page version

If you read nothing else:

1. **Retrieval is the product. The LLM is a formatting layer.** Almost every
   quality complaint traces to the wrong chunks arriving, not to the model
   writing badly. [FIELD]
2. **Build the evaluation set before the pipeline.** 30–100 questions with known
   correct documents. Without it, every subsequent decision is taste. [FIELD]
3. **Document-level access control is your job, and nobody has done it for you.**
   Only 2 of 88 surveyed repositories implement it at all. [MEASURED]
4. **Retrofitting security means reindexing everything**, because the identity
   field must exist at ingestion time. Decide in week one.
5. **Pure vector search fails on the exact terms your business runs on** — part
   numbers, policy codes, acronyms. You need true hybrid retrieval, not a
   re-ranking of vector candidates. [CITED]
6. **Your cost is context size × query volume**, not embeddings. Embedding a
   large corpus is a rounding error; sending 25k tokens of context to a frontier
   model 10,000 times a day is not. [DERIVED]
7. **The corpus is the project.** Most RAG failures are document-quality
   failures wearing a technical costume.

---

## Part 1 — Decide whether you need RAG at all

The most valuable section, and the one most guides omit.

**You probably do not need RAG when:**

- The corpus is small and stable (under ~50 documents). Put it in the context
  window. Prompt caching makes this cheap and it removes an entire subsystem.
- The question is really structured query. "How many open tickets does Acme
  have?" is SQL. Wrapping it in embeddings makes it worse and slower. Text-to-SQL
  against the warehouse is a different, better-understood problem.
- The authoritative answer already lives in a system with an API. Query the
  system of record. Do not embed a snapshot of it and then fight staleness
  forever.
- **The content does not exist, is contradictory, or is wrong.** RAG cannot
  retrieve an answer nobody wrote down. If three policy documents disagree, the
  system will confidently surface one of them, and you will have automated
  the distribution of the wrong answer.

**RAG is the right tool when:** the corpus is large, unstructured, changes at a
rate you cannot fine-tune against, answers must cite sources, and the questions
are open-ended.

> **The pre-mortem question.** Before writing any code: *if this system gives a
> confidently wrong answer to a customer or a regulator, what happens?* If the
> answer is "material harm", you need citation enforcement, human review on
> low-confidence responses, and an abstention path — and you should budget for
> those now, not discover them at go-live.

---

## Part 2 — The reference architecture

The layers most demos skip are marked **★**. They are the difference between a
prototype and a system.

```
SOURCES            SharePoint · Confluence · file shares · DMS · ticketing · email
                                        │
★ ENTITLEMENT      capture ACLs AT SOURCE, at ingestion time, per document
  CAPTURE          (identity/group ids stored as filterable fields)
                                        │
  INGESTION        layout-aware extraction (not naive text dump)
                   tables/code kept atomic · headings preserved · OCR where needed
                                        │
  ENRICHMENT       metadata: source, author, effective/expiry date, classification,
                   document type, version, language
                                        │
  CHUNKING         structure-aware · heading breadcrumb on every chunk ·
                   parent-child linkage
                                        │
  INDEXING         vector + lexical (BM25) in ONE index or two synchronised ones
★                  index stores embedding-model id and dimension
                                        │
  RETRIEVAL        true rank fusion (RRF) → metadata pre-filter →
★                  SECURITY FILTER from caller's token → rerank → top-k
                                        │
  GENERATION       grounded prompt · citation required · abstention allowed
                                        │
★ GUARDRAILS       citation validation · PII egress check · confidence gating
                                        │
★ OBSERVABILITY    per-query trace · retrieved chunk ids · token + cost accounting ·
                   user feedback capture
                                        │
★ LIFECYCLE        incremental sync · deletion propagation · scheduled reindex ·
                   eval regression gate in CI
```

**[MEASURED]** Across 88 repositories: 40% have any reindex path, 29% measure
retrieval numerically, 2% implement document-level access control. The starred
layers are starred because the published ecosystem largely omits them.

---

## Part 3 — Build in this order

The order is the advice. Most teams do 3 → 5 → 1 and spend the next quarter
undoing it.

| # | Step | Why here | Done when |
|---|---|---|---|
| 1 | **Corpus audit** | You cannot retrieve what is not written down. Find the contradictions and the stale documents before they become answers. | You know your document count, formats, update rate, owners, and which sources are authoritative |
| 2 | **Entitlement model** | Determines the index schema. Retrofitting = full reindex. | You can state, for any document, which identity attribute governs access |
| 3 | **Golden evaluation set** | Every later decision needs a scoreboard. | 30–100 questions with known correct source documents [FIELD] |
| 4 | **Baseline: BM25 only** | Free, fast, and frequently 70% as good. Establishes whether embeddings earn their cost. | You have recall@10 for keyword-only retrieval |
| 5 | **Add vector + true hybrid fusion** | Measure the delta against step 4. | Hybrid beats BM25 on your golden set, with a number |
| 6 | **Chunking iteration** | Highest-leverage tuning, guided by the scoreboard. | Recall@10 plateaus |
| 7 | **Reranking** | Only now, and only if measured. | Precision@5 improves enough to justify the latency |
| 8 | **Generation + citations** | The easy part. | Answers cite retrieved chunk ids, and abstain when context is weak |
| 9 | **Guardrails, observability, lifecycle** | Before pilot, not after. | Per-query traces, cost per query visible, deletion propagates end-to-end |

> **Step 4 is the one people skip.** A BM25 baseline costs an afternoon and
> occasionally reveals that the whole vector stack buys you three points of
> recall on your corpus. That is a finding worth an afternoon. [FIELD]

---

## Part 4 — Failure modes

Ordered by how expensive they are to fix late.

### FM-1 · Access control absent, and sometimes structurally unavailable
**Severity: project-ending · Cost to fix late: full reindex**

**Symptom.** Retrieval returns content the asking user cannot open in the source
system. Usually discovered at security review, after executives have seen the
demo.

**Mechanism.** Vector search has no native per-user authorisation. Enforcement
needs an identity field written *at ingestion* and a security filter applied *at
query time*, propagated from the caller's token. Every layer must cooperate, and
if any layer drops the identity the system **fails open** — it returns results,
just the wrong ones. Microsoft states plainly that Azure AI Search "doesn't
provide native document-level permissions and can't vary search results from
within an index by user permissions." [CITED]

**Evidence.**
- 2 of 88 repositories show any ACL implementation. [MEASURED]
- [`Azure/azure-sdk-for-python` #44454](https://github.com/Azure/azure-sdk-for-python/issues/44454) — the Foundry Agents SDK's AI Search tool cannot pass `x-ms-query-source-authorization`, so it "cannot be used safely in production, access-controlled environments." Open since December 2025, no maintainer response as of September 2026. [CITED]
- [`login_and_acl.md`](https://github.com/azure-samples/azure-search-openai-demo/blob/main/docs/login_and_acl.md) — the one public worked example. [CITED]

**Detect.** Ask two questions. *Can retrieval accept a per-request identity
token?* *Does ingestion write a filterable identity field?* Either "no" means you
have no document security.

**Fix.** Capture ACLs at ingestion. Store group/identity ids as filterable
fields. Apply the filter server-side in the retrieval query — never post-filter
in application code, because post-filtering leaks through result counts, and
never let the LLM decide what the user may see.

**The trap.** Source ACLs change after ingestion. Someone leaves a group; the
index does not know. You need either periodic entitlement re-sync or query-time
group resolution against the identity provider.

---

### FM-2 · Hybrid search that only re-ranks cannot recover a vector miss
**Severity: high · Cost to fix late: re-architecture of the retrieval layer**

**Symptom.** Queries with exact identifiers — part numbers, policy codes, error
codes, internal project names — return plausible but wrong chunks. The correct
chunk containing the literal string never surfaces. "Hybrid search" is on.

**Mechanism.** Two different architectures share the name. **True hybrid**: the
lexical and vector legs run independently and their ranked lists are fused
(reciprocal rank fusion). **Re-rank hybrid**: the lexical score merely reorders
what the vector leg already returned. In the second, BM25 **can never surface a
chunk the vector search missed** — even when the query contains the exact words
in that chunk. Domain jargon is precisely what embedding models underrepresent,
so the vector leg misses exactly the queries you added lexical search to rescue.

**Evidence.** [`typesense/typesense` #2816](https://github.com/typesense/typesense/issues/2816) (hybrid returns 0 results when the phrase has no keyword match) · [`weaviate/weaviate` #10350](https://github.com/weaviate/weaviate/issues/10350) (BM25 merged incorrectly into hybrid results) · [`HKUDS/LightRAG` #3198](https://github.com/HKUDS/LightRAG/issues/3198) (BM25+vector RFC specifically for jargon-heavy domains). Three organisations, three engines. [CITED]

**Detect.** Query for a string you know appears verbatim in exactly one document.
If it is not rank 1, your hybrid is a re-rank.

**Fix.** Reciprocal rank fusion over independent legs. Route queries containing
quoted strings or unambiguous identifiers to the lexical leg with a boost.

---

### FM-3 · Changing the embedding model silently invalidates the index
**Severity: high · Cost to fix late: full re-embed**

**Symptom.** After a model upgrade, quality degrades with no error. Worse
variant: writes fail silently and the index quietly stops growing.

**Mechanism.** Vectors from different models, dimensions, pooling strategies or
instruction templates occupy incompatible spaces. Comparing them is meaningless
but not illegal — the arithmetic succeeds. A store with mixed vectors **returns
confident nonsense rather than an error.** Dimension changes fail loudly;
same-dimension model swaps fail silently, which is worse.

**Evidence.** [`HKUDS/LightRAG` #3978](https://github.com/HKUDS/LightRAG/issues/3978) (a model change "must fail closed") · [`openclaw/openclaw` #32277](https://github.com/openclaw/openclaw/issues/32277) (no dimension-mismatch detection) · [`volcengine/OpenViking` #1066](https://github.com/volcengine/OpenViking/issues/1066). Only 40% of surveyed repos have any reindex path. [CITED] [MEASURED]

**Detect.** Store the embedding model id and dimension as index metadata. Refuse
to serve when the configured model disagrees.

**Fix.** Treat embedding-model changes as schema migrations. Blue/green index with
alias swap: build the new index alongside, validate on the golden set, swap the
alias, keep the old index until you are sure. Model deprecation is scheduled, not
hypothetical — budget a re-embed roughly annually.

---

### FM-4 · Chunking splits structure, invisibly
**Severity: high · Cost to fix late: re-ingest**

**Symptom.** Answers from tables are wrong in a specific way: right column
headers, wrong numbers, or a value attributed to the wrong row. Retrieval
"worked" — it returned a relevant-looking chunk.

**Mechanism.** Fixed-window chunking splits a table from its header row, a code
block mid-fence, or a figure from its caption. The resulting chunk embeds and
retrieves perfectly well; it is simply no longer true. This is a correctness
fault baked into the index at ingestion, surfacing many layers away at answer
time. [CITED: [`infiniflow/ragflow` #19520](https://github.com/infiniflow/ragflow/issues/19520)]

**Fix.** Layout-aware extraction. Tables and code atomic — emit whole or
summarise, never split. Every chunk carries its heading breadcrumb. Parent-child
retrieval: match on small children, send the parent for context.

**Do not** tune chunk size by intuition. Tune it against the golden set from
step 3; it is one of the highest-leverage knobs you have and one of the easiest
to get backwards.

---

### FM-5 · Deletion does not propagate
**Severity: high in regulated settings · Compliance exposure**

**Symptom.** A document is deleted at source. Its content keeps appearing in
answers. Under GDPR/DSAR erasure, this is a reportable failure, not a bug.

**Mechanism.** Deletion must fan out across chunk rows, vector entries, caches,
and any derived artefacts (summaries, knowledge graphs, fine-tuned adapters).
Most pipelines implement create and update; delete is an afterthought. There is
a harder version: **correct deletion from a proximity-graph index (HNSW) can
leave measurable retrieval drift that rebuilds do not fully remove** — the graph
structure was shaped by the deleted vectors. [FIELD, with partial citation:
[`ArcadeData/arcadedb` #7931](https://github.com/ArcadeData/arcadedb/issues/7931)]

**Fix.** Document-id-keyed upsert that deletes all prior chunks before inserting
new ones. A deletion queue with verification. Periodic full rebuild for regulated
corpora. **Test erasure end-to-end before go-live** and keep the receipt.

---

### FM-6 · Evaluation that cannot detect regression
**Severity: high · Silent**

**Symptom.** Nobody can say whether last week's change helped. Quality is debated
by anecdote. Then a customer complains.

**Mechanism.** Retrieval quality drifts as the corpus grows — a chunk that was
rank 1 among 10,000 is rank 40 among 500,000. Nothing alerts you.

**Evidence.** **71% of surveyed repositories compute no retrieval metric at all**
(26 of 88 do). [MEASURED] If you copy the ecosystem's habits, you inherit this.

**Fix.** Golden set of 30–100 questions with known correct documents [FIELD].
Measure recall@k and nDCG for retrieval *separately* from groundedness and answer
relevance for generation — conflating them means you cannot tell a retrieval
failure from a generation failure. Run it in CI. Gate merges on it.

**The trap.** A golden set built from the demo questions tests only what already
works. Seed it deliberately with: questions you got wrong and fixed, multi-hop
questions, questions whose correct answer is *"the documents do not say"*, and
questions using the exact jargon of FM-2.

The IR-research repositories ([`beir`](https://github.com/beir-cellar/beir),
[`mteb`](https://github.com/embeddings-benchmark/mteb),
[`pyserini`](https://github.com/castorini/pyserini)) are more useful here than
any RAG framework's built-in evaluation — that field has been measuring retrieval
for thirty years. [MEASURED: they lead the retrieval-metric density table]

---

### FM-7 · Cost discovered in month three
**Severity: budget-ending**

**Symptom.** A pilot that cost little suddenly has a four- or five-figure monthly
line item.

**Mechanism.** Cost is dominated by **context tokens × query volume**, and both
grow after launch. See Part 6 for the arithmetic. The usual culprit is retrieving
top-50 chunks and sending them all to a frontier model.

**Fix.** Rerank to top-3–5 before generation. Cache aggressively (prompt caching
on the static system prompt; semantic caching on repeated questions). Route easy
queries to a smaller model. **Put cost-per-query on a dashboard from day one** —
you cannot manage what you cannot see, and 
[FM-7 is invisible until the invoice](#part-6--the-cost-model-you-should-actually-build).

---

### FM-8 · Stale index divergence
**Symptom.** Answers reflect last quarter's policy.
**Mechanism.** Full reindexing is expensive, so teams move to incremental sync and
then discover the change-detection is unreliable — no change feed, unreliable
modified timestamps, moved files read as new.
**Fix.** Source-side change feeds where available. Content hashing as a fallback.
An index-freshness metric on the dashboard: *oldest document whose source has
changed since indexing*. Alert on it.

---

### FM-9 · Multi-tenant leakage via a shared index
**Symptom.** One customer's content appears in another's results.
**Mechanism.** Shared index with tenant id as an ordinary metadata field, and one
code path that forgets the filter.
**Fix.** Prefer physical isolation (index or namespace per tenant) for regulated
or high-value tenants; accept the cost. If sharing, the tenant filter must be
injected server-side in one chokepoint that application code cannot bypass —
never assembled per-call.
**Note.** No public incident citation found. [MEASURED-ABSENT] That absence is
evidence about what firms publish, not about how often it happens.

---

### FM-10 · The reranker that costs latency and buys nothing
**Symptom.** p95 latency up 2–3×, quality indistinguishable.
**Mechanism.** Cross-encoders score every query-document pair; the cost is real
and certain, the benefit is corpus-dependent and assumed.
**Fix.** Measure precision@5 with and without, on your golden set, before
shipping it. Rerankers usually help — but "usually" is not "on your corpus", and
this is a cheap experiment. [FIELD]

---

### FM-11 · Citations that do not support the sentence
**Symptom.** Answers cite real documents that do not contain the claim. Worse
than no citation, because it manufactures false confidence and passes casual
review.
**Fix.** Validate post-generation: check that each cited chunk id was actually
retrieved, and ideally that the claim is entailed by it. Require the model to
abstain when context is insufficient, and make abstention a *measured, rewarded*
outcome in your eval — otherwise you have trained the system to always guess.

---

### FM-12 · The corpus was the problem all along
**Symptom.** Retrieval metrics are fine. Users still say the answers are wrong.
**Mechanism.** Three policy documents disagree; two are obsolete; none is marked
authoritative. The system retrieves correctly and answers wrongly. **This is the
most common root cause of "RAG doesn't work" in enterprises, and it is not a
technical problem.** [FIELD]
**Fix.** Ownership and effective/expiry dates as required metadata. Prefer
authoritative sources at ranking time. Surface conflicts rather than silently
picking. Sometimes the correct deliverable of a RAG project is a content
remediation programme — say so early.

---

## Part 5 — Security and compliance

Because this is where pilots die.

**The identity chain.** User authenticates → application receives token → token's
group claims flow to the retrieval call → filter applied server-side → only
permitted chunks retrieved → only permitted content reaches the model. Break any
link and you fail open.

**Design rules**

- The LLM is never a security boundary. Never retrieve broadly and instruct the
  model to ignore unauthorised content. Prompt instructions are not access
  control.
- Filter server-side inside the search query, not in application code after
  results return. Post-filtering leaks through result counts and pagination.
- Store identity ids, not names. Groups get renamed.
- Plan for entitlement drift — index ACLs go stale the moment someone changes
  team.
- Log which chunk ids were retrieved, for which user, when. You will need this
  for an incident, and possibly for an auditor.

**Classification and residency.** Carry a classification label as chunk metadata
and filter on it. For data residency, the index must live in-region and so must
the embedding and inference endpoints — an in-region index querying an
out-of-region model still moves your content across the boundary.

**PII.** Decide explicitly whether PII is redacted at ingestion (safer, lossy,
irreversible) or at egress (flexible, riskier). Redacting at ingestion breaks
retrieval for legitimate HR/legal use cases — this is a business decision, not a
technical one.

---

## Part 6 — The cost model you should actually build

**[DERIVED]** — worked from stated assumptions, so substitute your own. Verify
all unit prices against current vendor pricing pages; the *shape* is the point,
not the absolute figures.

**Assumptions:** 100,000 documents averaging 1,500 tokens = 150M tokens. Chunks
of 500 tokens with 15% overlap → ~345,000 chunks. 10,000 queries/day.

**One-time embedding.** 172M tokens at roughly $0.10–0.13 per million ≈ **$20**.
Effectively free. This is the number everyone estimates and it does not matter.

**Storage.** 345k vectors × 3,072 dimensions × 4 bytes ≈ **4 GB raw**, roughly
**6–8 GB** with index overhead. Priced as managed memory, typically tens to low
hundreds of dollars per month. Real, but not the problem.

**Generation — this is the whole cost.**

| Design | Context/query | Daily tokens | Monthly (at ~$3/M input) |
|---|---|---|---|
| Naive: top-50 chunks | ~25,000 | 250M | **~$22,000** |
| Reranked: top-5 chunks | ~2,500 | 25M | **~$2,250** |
| Reranked + prompt caching | ~2,500 | 25M | **~$1,000–1,500** |

**The lesson.** A single design decision — rerank to top-5 instead of passing
top-50 — changes the monthly bill by an order of magnitude. Embedding costs are
noise. **Anyone whose RAG business case models embedding cost and not context
cost has modelled the wrong thing.**

**Also budget:** re-embedding on model migration (roughly annual), the
reranker's own inference cost, observability storage, and the human cost of
corpus curation — which is usually the largest line and never appears in the
technical estimate.

---

## Part 7 — Four business archetypes

### A. Internal knowledge assistant (HR, IT, policy)
*Highest success rate. Start here.*
Moderate corpus, low blast radius, tolerant users. **Watch:** FM-1 (HR content is
sensitive), FM-12 (policies contradict each other). **Success metric:** deflected
tickets, not "accuracy". **Reality:** most of the work is content cleanup.

### B. Customer-facing support
*High value, high risk.*
Wrong answers reach customers. **Requires:** abstention, citation validation,
confidence gating, human escalation, and a tested rollback. **Watch:** FM-11,
FM-7 (query volume is unbounded and cost scales with it). **Do not launch**
without a measured containment rate and a kill switch.

### C. Regulated document analysis (legal, clinical, financial)
*Highest complexity.*
Exact terminology is non-negotiable, so FM-2 is existential: pure vector search
on statute numbers or clinical codes will fail. Full audit trail required. Human
review is part of the design, not a fallback. **Watch:** FM-4 (tables in
financial filings carry the meaning), FM-5 (retention and erasure).

### D. Engineering/field knowledge (manuals, diagnostics, parts)
*Underrated.*
Part numbers and error codes make FM-2 the dominant risk. Diagrams and tables
make FM-4 severe — a torque spec split from its part number is a safety issue.
**Watch:** ingestion fidelity above all; budget for real document processing, not
a PDF-to-text call.

---

## Part 8 — Choosing the stack

Choose on these, in order: **does it let me filter by identity at query time**,
**does it do true hybrid fusion**, **can I measure retrieval quality**, **can I
migrate embeddings without downtime**. Everything else is preference.

**[MEASURED] findings that should affect the choice:**

- [`Azure-Samples/azure-search-openai-demo`](https://github.com/Azure-Samples/azure-search-openai-demo)
  is the most useful reference architecture in the survey for enterprise work —
  not because it scores highest, but because it is effectively the only public
  worked example of document-level security trimming (ACL density 28.7 per 100
  RAG files, against 0.0 for nearly everything else).
- **`microsoft/kernel-memory` is effectively retired.** 26 commits in 12 months,
  all from one author, most recent commit titled *"Research project archive"*
  (June 2026). Its star count reflects none of this. Do not start here.
- **Microsoft migrated its flagship RAG sample off its own Prompty prompt format
  to Jinja2** in February 2026 — visible only in deletion history. If you adopted
  Prompty because the reference architecture used it, it no longer does.
- For evaluation, prefer the IR-research tooling (`beir`, `mteb`, `pyserini`)
  over framework-native eval.

**On frameworks generally.** LangChain and LlamaIndex are excellent for getting
to a demo in a day and are a liability if you let their abstractions own your
retrieval logic. The parts you will need to control — fusion strategy, security
filter injection, chunking, index migration — are the parts frameworks abstract
away. A defensible pattern: prototype in a framework, then own the retrieval path
in your own code and keep the framework for peripheral glue. [FIELD]

---

## Part 9 — The first 90 days

| Phase | Focus | Exit criteria |
|---|---|---|
| **1–2 wks** | Corpus audit, entitlement model, use-case selection | You can name the authoritative source for every answer type, and state the identity attribute governing access |
| **3–4 wks** | Golden set, BM25 baseline | recall@10 for keyword-only, on real questions from real users |
| **5–8 wks** | Hybrid retrieval, chunking iteration, security filter | Hybrid beats baseline *with a number*; security filter verified by an adversarial test |
| **9–12 wks** | Generation, citations, guardrails, observability | Cost per query on a dashboard; erasure tested end-to-end; eval in CI |

**Kill criteria — agree these before you start.** Stop if: the corpus audit shows
the answers are not written down anywhere; retrieval recall stays below ~70% on
the golden set after chunking and hybrid work [FIELD]; or the entitlement model
cannot be expressed as a filterable field. Those are content and architecture
problems, and more model will not fix any of them.

---

## Anti-patterns

- Choosing a vector database first. It is the most replaceable component.
- "We'll add security later." It is a reindex, and possibly a re-architecture.
- Judging quality by asking the demo questions.
- Treating chunk size as a constant rather than a tuned parameter.
- Using answer quality as the only metric, so retrieval and generation failures
  are indistinguishable.
- Passing top-50 chunks to a frontier model because context windows are large.
  Large context windows are an invitation to spend money, and more context
  measurably degrades precision.
- Adding a reranker, GraphRAG, or agentic retrieval before the baseline is
  measured. Complexity you cannot evaluate is complexity you cannot debug.
- Starting from the highest-starred repository.

---

## Provenance and limits

**What the survey behind this genuinely supports:** the 2%/29%/40% figures, the
`kernel-memory` and Prompty findings, and the observation that the enterprise
layers are systematically absent from published code. Those are measured and
reproducible.

**What it does not support:** any claim about how often these failures occur in
production. The survey samples *published repositories*, not production systems.
Frequency claims elsewhere ("40% of RAG queries fail", "pilots cost 10× more")
are **[UNVERIFIED]** — widely repeated in vendor content marketing, not traceable
to primary data. Do not put them in a business case.

**What is [FIELD] rather than measured:** the build order, the golden-set sizing,
the kill criteria, and most of Part 1. These are practitioner judgement. They are
the parts most likely to be wrong, and the parts you should argue with.

**The biggest gap.** The failures that matter most to enterprises — tenant
leakage, cost overruns, projects quietly cancelled — are almost entirely absent
from public sources, because they are commercially embarrassing. Their absence
from the evidence base is a fact about disclosure, not about frequency. Anyone
who tells you otherwise is selling something.

---

*Survey data and method: [methodology](./methodology.md) ·
[failure modes with full citations](./failure-modes.md) ·
[88 scored repositories](./repo-evaluations.md) · raw data in `data/`.*
