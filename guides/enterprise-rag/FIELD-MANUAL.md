# Enterprise AI Field Manual
## Decide, build, and defend a production RAG system

**Companion to**: the *Master Enterprise AI Architecture Reference* (nine planes, full mathematics, pattern catalogue).
**This document is Artefact A of three**: the Field Manual (this), the Technical Reference (the nine planes in depth), and the Blueprint repository (tested, pinned, CI'd code).
**Revision**: 1.0 — September 2026
**Status**: Working reference. Claim classification in [Appendix: Evidence Ledger](#appendix--evidence-ledger).

---

## Why this document exists separately

The Reference is a nine-plane manual of roughly 250 pages. It is correct, and almost nobody will read it end to end. This Field Manual carries the ~20% of that material that determines whether a programme succeeds, in the order decisions actually get made, and pulls the Architecture Review Board defences to the front where they earn their keep.

Three deliberate departures from the Reference:

1. **It opens with whether to build at all.** The Reference assumes the programme is happening.
2. **The ARB defences lead rather than close each chapter.** For most readers those questions *are* the product.
3. **Numeric claims are classified, not just pattern names.** The Reference's provenance ledger is its strongest feature; it stops at pattern names, and the numbers are where credibility is actually lost.

Code lives in the Blueprint repository, not inline. An untested code block in a manual drifts from the prose it illustrates — the Reference itself documents one such case.

---

## Editorial conventions

Carried over from the Reference, extended to cover claims.

| Marker | Meaning |
| :--- | :--- |
| ✅ **STANDARD** | Published paper or specification, multiple independent implementations. Safe to cite by name at an ARB. |
| ⚠️ **EMERGING** | Real but young. Cite with a maturity caveat and a fallback plan. |
| 🔶 **ORIGINAL** | Coined in this work. **No external literature.** Defend on engineering merit, never as an industry standard. |
| 📊 **MEASURED** | Computed from a survey of 88 RAG repositories cloned and analysed. Reproducible; see the Evidence Ledger. |
| 🔗 **CITED** | Traceable to a linked public issue, commit, or vendor document. |
| 🧮 **DERIVED** | Arithmetic from stated assumptions, shown in full. |
| 🗣️ **FIELD** | Practitioner judgement. No hard citation. The parts most likely to be wrong. |
| ❌ **UNVERIFIED** | Widely repeated, not traceable to a primary source. **Never put in a business case.** |

> [!IMPORTANT]
> **Model names are illustrative of a tier, not a recommendation.** Frontier naming churns every few months; any manual that hard-codes it is stale on publication. Read every model name as a placeholder for a capability tier (Tier 0 embedded SLM / Tier 1 workhorse / Tier 2 frontier).

---

# Part 0 · Should you build this at all

The most valuable page in the manual, and the one the Reference does not have.

## 0.1 When RAG is the wrong tool

| Situation | What to do instead | Why |
| :--- | :--- | :--- |
| Corpus under ~50 stable documents | Put it in the context window with prompt caching | You remove an entire subsystem and its failure modes for a rounding error in cost |
| The question is really structured query | Text-to-SQL against the warehouse | *"How many open tickets does Acme have?"* is SQL. Embeddings make it slower and less correct |
| An authoritative system of record exists with an API | Query the system | Embedding a snapshot means fighting staleness forever (§2.3) |
| The content is contradictory, obsolete or absent | A content remediation programme | See §3. This is the most common real cause of failure and it is not technical |
| Answers must be exhaustive and provably complete | Deterministic search with human review | RAG optimises for relevance, not completeness. It cannot prove a negative |

**RAG is the right tool** when the corpus is large and unstructured, changes faster than you could fine-tune, answers must cite sources, and the questions are open-ended.

## 0.2 The pre-mortem

Before any architecture work, answer in writing:

> **If this system gives a confidently wrong answer to a customer or a regulator, what happens?**

If the answer is *material harm*, then citation enforcement, abstention, confidence gating and human escalation are **in scope from day one**, not phase two. Budget them now or do not start. The Reference's Tri-State Truth Model (🔶 ORIGINAL — `PROVEN_TRUE` / `PROVEN_FALSE` / `EXPLICIT_ABSTAIN`) exists precisely for this case; the important half is that **abstention must be a measured, rewarded outcome**, or you have trained the system to always guess.

## 0.3 Kill criteria — agree these before work starts

Stop the programme if:

- **φ < 0.85 on the dominant document class and the parser cannot be fixed.** Retrieval recall is bounded above by extraction fidelity (§2.1). No downstream sophistication raises that ceiling.
- **The corpus audit shows the answers are not written down, or authoritative sources contradict each other** and no owner will arbitrate (§3).
- **The entitlement model cannot be expressed as a filterable field** (§2.2). You will not pass security review, and retrofitting is a full reindex.
- **Retrieval recall stays below ~70% on the golden set** after layout-aware parsing, chunk-band tuning and hybrid retrieval. 🗣️ FIELD

Those are content and architecture problems. More model will not fix any of them.

---

# Part 1 · Locate yourself before proposing anything

```
L0 Prototype  →  L1 Piloted  →  L2 Production  →  L3 Governed  →  L4 Adaptive
notebook +       hybrid +       tracing +         abstention +     trace-driven
vibes eval       golden set     eval gates        audit-ready      optimisation
```

| Level | Planes operating | Typical symptom | Next move |
| :-: | :--- | :--- | :--- |
| **L0** | 2 (partial) | Demos well, breaks on real documents | Build Plane 0 properly |
| **L1** | 0, 1, 2 | Quality is real but unmeasured | Stand up tracing and a golden set |
| **L2** | 0–2, 4, 7 | Works; nobody can prove it works | Add provenance and step budgets |
| **L3** | 0–7 | Defensible; improvement is manual | Build the adaptation loop |
| **L4** | 0–8 | Compounding quality, falling unit cost | Maintain regression discipline |

> [!WARNING]
> **Most enterprise programmes attempt L4 capabilities at L0 maturity.** Agent swarms and RL fine-tuning are L4 activities. Attempted before the ingestion and governance planes exist, they produce systems that are simultaneously expensive, unmeasurable and unauditable. The sequencing is not a suggestion.

**This manual covers L0 → L2 thoroughly**, because that is where almost every programme actually sits and where the failures are decisive. Planes 3, 5, 6 and 8 are deferred to the Reference, with entry triggers in [Part 6](#part-6--what-this-manual-defers-and-when-youll-need-it).

---

# Part 2 · The three planes that decide the outcome

Ingestion, retrieval, governance. Everything else is optimisation on top of these.

## 2.1 Extraction fidelity — the ceiling on everything

Let $D$ be a source document containing ground-truth propositions $\mathcal{P}(D)$. Parsing recovers $\mathcal{P}(\hat{D}) \subseteq \mathcal{P}(D)$. Define **extraction fidelity** 🔶 ORIGINAL (the concept is sound and under-measured; the notation and proxy estimator are ours):

$$\phi(D) = \frac{|\mathcal{P}(\hat{D})|}{|\mathcal{P}(D)|} \qquad\Longrightarrow\qquad \text{Recall}_{\text{system}} \le \mathbb{E}_D[\phi(D)]$$

If a proposition did not survive parsing, retrieval recall for any query depending on it is **strictly zero**, regardless of embedding model, reranker or context window.

| Document feature | Naive extraction φ | Layout-aware φ | Why it breaks |
| :--- | :-: | :-: | :--- |
| Flowing prose | ~0.98 | ~0.99 | Rarely an issue |
| Multi-column layout | ~0.45 | ~0.95 | Reading order interleaves columns into nonsense |
| **Tables** | **~0.15** | ~0.90 | Cell relationships collapse into whitespace soup |
| Scanned pages | 0.00 | ~0.85 (OCR) | No text layer at all |
| Footnotes | ~0.30 | ~0.85 | Detached from the claim they qualify — a compliance hazard |
| Charts & figures | 0.00 | ~0.60 (VLM) | Requires a vision model |
| Formulas | ~0.10 | ~0.80 | Unicode mangling destroys meaning |

*(Figures are 🗣️ FIELD estimates for planning, not measurements. Measure your own.)*

> [!IMPORTANT]
> **Measure φ before tuning anything else.** Sample 30 documents stratified by type, have a human enumerate the propositions a user might reasonably ask about, and count how many survive parsing. If φ < 0.85 on your dominant class, **stop all other work and fix the parser.** Teams routinely tune `top_k` and swap embedding models while φ ≈ 0.6 because the PDF parser silently drops every table.

**Chunking follows from this.** Two failure modes bound the chunk size from both sides:

- **Referential decapitation** — *"This limit does not apply to Tier 2 counterparties"* is a complete sentence and a useless retrieval unit, because *which limit* lived in a heading three chunks earlier. Fix: every chunk carries its heading breadcrumb. ✅ STANDARD
- **Semantic dilution** — a 2,000-token chunk spanning four topics embeds near the centroid of all four and close to none.

The optimal band is **not** universal: dense regulatory text sits at 150–400 tokens, narrative reports at 600–1,200. Determine it against your golden set, never by copying a blog default. Tables and code blocks are **atomic** — emit whole or summarise, never split.

## 2.2 The permission propagation invariant

The principle that separates a demo from something deployable inside a bank.

> **Invariant.** For every chunk $c$ derived from document $D$: $\text{ACL}(c) \subseteq \text{ACL}(D)$ **at query time**, not at index time.

| Failure | Mechanism | Consequence |
| :--- | :--- | :--- |
| **Index-time-only ACL** | Permissions snapshotted at ingestion, never refreshed | Someone who left the department last month still retrieves its documents |
| **Post-filtering** | Retrieve top-50, then drop unauthorised results | Silently degrades top-k; leaks document existence through result-count variation |
| **Summary leakage** | Chunk is filtered, but an LLM-generated summary built from it is not | Restricted content reaches the user through the back door |

The correct pattern is **pre-filtered retrieval**: resolved group membership is pushed into the vector store's filter predicate *before* ANN search, so the candidate pool never contains unauthorised material.

```
User query → resolve identity (IdP, TTL ≤ 5 min) → build filter predicate
          → filtered ANN search (predicate INSIDE the HNSW traversal)
          → authorised candidates only

ANTI-PATTERN:  unfiltered ANN → post-filter  → leaks existence, degrades top-k
```

**📊 MEASURED — why you are on your own here.** Across 88 surveyed RAG repositories, **2 implement document-level access control at all (2%)**. The only substantial public worked example is [`Azure-Samples/azure-search-openai-demo`](https://github.com/Azure-Samples/azure-search-openai-demo).

**🔗 CITED — and on some platforms it is structurally unavailable.** [`Azure/azure-sdk-for-python` #44454](https://github.com/Azure/azure-sdk-for-python/issues/44454): the Azure AI Foundry Agents SDK's AI Search tool cannot pass `x-ms-query-source-authorization`, so it *"cannot be used safely in production, access-controlled environments."* Opened December 2025; no maintainer response as of September 2026. **Verify your platform's per-user authorisation path before committing to it**, not after.

> [!CAUTION]
> **The follow-up is always about derived artefacts.** Summaries, entity caches, knowledge-graph nodes and evaluation datasets are all built from source content and all inherit its ACL. If your summary table is not access-controlled to the same standard as the chunk table, you have moved the leak, not closed it. Enumerate every derived store and show its ACL binding.

## 2.3 Freshness, deletion, and the direction that actually hurts

**Index freshness lag** $\Delta_f$ = time between a source mutation and its visibility in the index.

| Document class | Acceptable Δ_f | Sync strategy |
| :--- | :--- | :--- |
| Pricing, rates, limits | < 5 min | Event-driven (CDC / webhook) |
| Regulatory filings | < 1 hour | Event-driven with attestation |
| Ticket / case notes | < 15 min | Streaming |
| Policy and procedure | < 24 hours | Scheduled incremental |
| Historical archives | Weeks | Batch reindex |

> [!CAUTION]
> **Deletions are the dangerous direction.** Most teams build additive sync and never test the delete path. A document withdrawn for legal reasons that remains retrievable is a far worse incident than one that indexes an hour late. **Test tombstone propagation in CI**, and include every derived store and the response cache — a purged document that still answers from cache is functionally still published.

**📊 MEASURED**: only 40% of surveyed repositories have any reindex or migration code path. The ecosystem you are copying from has no answer to this.

## 2.4 Retrieval — the two decisions that matter

**Hybrid must be fusion, not re-ranking.** Two architectures share the name:

- **True hybrid** ✅ STANDARD: lexical and dense legs run independently, ranked lists combined by Reciprocal Rank Fusion (Cormack et al., 2009).
- **Re-rank hybrid**: the lexical score merely reorders what the dense leg already returned.

In the second, **BM25 can never surface a chunk the vector search missed** — even when the query contains the exact words in that chunk. Domain jargon (part numbers, policy codes, clinical codes, internal project names) is precisely what embedding models underrepresent, so the dense leg misses exactly the queries you added lexical search to rescue.

🔗 CITED across three organisations and three engines: [`typesense` #2816](https://github.com/typesense/typesense/issues/2816) · [`weaviate` #10350](https://github.com/weaviate/weaviate/issues/10350) · [`LightRAG` #3198](https://github.com/HKUDS/LightRAG/issues/3198).

**Test in five minutes:** query for a string you know appears verbatim in exactly one document. If it is not rank 1, your hybrid is a re-rank.

**Treat embedding-model changes as schema migrations.** Vectors from different models, dimensions, pooling strategies or instruction templates occupy incompatible spaces. Comparison is meaningless but not illegal — the arithmetic succeeds, and a store with mixed vectors **returns confident nonsense rather than an error**. Dimension changes fail loudly; same-dimension model swaps fail silently, which is worse. Store the model id and dimension as index metadata and **fail closed** on mismatch. Migrate blue/green with an alias swap. 🔗 CITED: [`LightRAG` #3978](https://github.com/HKUDS/LightRAG/issues/3978) — *"a model or dimension change must fail closed."*

## 2.5 Governance — you cannot manage what you cannot measure

**📊 MEASURED: 71% of surveyed repositories compute no retrieval metric at all** (26 of 88 do). Copy the ecosystem's habits and you inherit its blindness.

**Build the golden set before the pipeline.** 30–100 questions with known correct source documents. 🗣️ FIELD

Measure retrieval (recall@k, nDCG) **separately** from generation (groundedness, answer relevance). Conflating them means you cannot tell a retrieval failure from a generation failure, which is the difference between a two-hour fix and a two-week investigation.

> [!CAUTION]
> **A golden set built from the demo questions tests only what already works.** Seed it deliberately with: questions you got wrong and fixed; multi-hop questions; questions using the exact jargon of §2.4; and questions whose correct answer is *"the documents do not say."*

For retrieval measurement specifically, the IR-research tooling ([`beir`](https://github.com/beir-cellar/beir), [`mteb`](https://github.com/embeddings-benchmark/mteb), [`pyserini`](https://github.com/castorini/pyserini)) is stronger than any RAG framework's built-in evaluation — 📊 MEASURED, they lead the retrieval-metric density table by a wide margin, and that field has been measuring retrieval for thirty years.

---

# Part 3 · The corpus problem

**The most common cause of "our RAG doesn't work" in enterprises, and it is not a technical problem.** The Reference treats the corpus as a technical substrate; in practice the substrate is organisational.

**Symptom.** Retrieval metrics are healthy. Users still say the answers are wrong.

**Mechanism.** Three policy documents disagree. Two are obsolete. None is marked authoritative. The system retrieves correctly and answers wrongly — and because it cites a real document, the answer survives casual review.

**This is invisible to every metric in Part 2.** Recall@k is fine. Groundedness is fine — the answer *is* grounded, in the wrong document.

**What to do:**

- Make **ownership** and **effective / expiry dates** required metadata. A document with no owner cannot be authoritative.
- Rank authoritative sources above derived ones at retrieval time.
- **Surface conflicts rather than silently picking.** When two authoritative sources disagree, the correct answer is to say so.
- Run the corpus audit *before* the architecture. Document count, formats, update rate, owners, and which source wins.

> [!IMPORTANT]
> Sometimes the correct deliverable of a RAG programme is a **content remediation programme**. Say so early. It is a better outcome than an elegant system that reliably retrieves the wrong policy, and clients remember advisors who said it before the money was spent.

---

# Part 4 · ARB defences

Pulled to the front, because for most readers these questions are the engagement. Each is a scripted answer plus the evidence artefact that makes it credible. **A defence without an artefact is an assertion.**

### Defence 1 — "How do we know it isn't confidently answering from documents it failed to read properly?"

> *"Extraction fidelity is a measured, gated and monitored quantity, not an assumption. Every document passes a φ estimator before indexing. Below 0.5 it is quarantined and never reaches the index. Between 0.5 and 0.85 it is indexed with a fidelity flag that propagates into chunk metadata, which the retrieval gate reads as a confidence prior — flagged chunks require a higher relevance score to survive. Quarantine backlog is an operational metric with an alert on slope, so a parser regression is detected as a trend rather than an incident. Monthly, we run a stratified sample of 30 documents through human proposition-counting to validate that the cheap proxies still track true φ. When they drift, we recalibrate the estimator, not the threshold."*

| Control | Evidence artefact |
| :--- | :--- |
| φ gate at ingest | Per-document ingest report with score and reason code |
| Fidelity flag propagation | Chunk metadata field consumed by the retrieval gate |
| Quarantine monitoring | Backlog-growth alert, review SLA |
| Proxy calibration | Monthly human-scored sample, drift report |

### Defence 2 — "An employee changes department on Monday. When do they lose access to their old team's documents, and how do you prove it?"

> *"Access is evaluated at query time against live identity resolution, not at index time against a snapshot. The chunk stores the source document's ACL group list; the user's group membership resolves from the identity provider per session with a TTL of five minutes or less; the intersection is pushed into the vector store as a pre-filter executing inside the ANN traversal. A membership change therefore propagates within one TTL, with no reindexing.*
>
> *We deliberately reject post-filtering: it leaks document existence through result-count variation and degrades top-k for legitimate users. We prove the control two ways — a CI test asserting zero results for an out-of-group principal against a known document, and a quarterly access-recertification replay in which historical queries are re-run under current group memberships and the result sets diffed. That diff is the audit artefact."*

**Strengthened by evidence.** 📊 Only 2 of 88 surveyed public RAG implementations do this at all, and 🔗 on at least one major platform the managed agent tooling structurally cannot ([`azure-sdk-for-python` #44454](https://github.com/Azure/azure-sdk-for-python/issues/44454), open 9 months). Stating that you evaluated the platform's authorisation path and rejected the managed shortcut is a stronger position than claiming the capability is routine.

> [!CAUTION]
> The follow-up is always derived artefacts. Enumerate every store built from source content and show its ACL binding.

### Defence 3 — "The regulator orders a document withdrawn. Walk me through the next sixty minutes."

> *"Withdrawal is an event, not a reindex. The connector emits a tombstone carrying the source URI. The delete path purges every chunk under that URI from the sparse index, the dense index and every derived store — summaries, graph nodes, cached responses — by content-addressed key, then records a deletion receipt with timestamp and operator identity.*
>
> *Three details matter to this board. The delete path is exercised in CI on every build, because an untested delete path is a latent compliance incident. A nightly orphan sweep reconciles index contents against source inventory, catching anything the event path missed. And response caches carry a TTL bounded by our stated withdrawal SLA, because a purged document that still answers from cache is functionally still published.*
>
> *Our committed SLA is fifteen minutes from tombstone to non-retrievability, evidenced by the deletion receipt and a post-withdrawal probe query in the audit log."*

> [!CAUTION]
> ⚠️ **Do not over-claim on vector deletion.** Removing a vector from a proximity-graph index (HNSW) removes retrievability, but the graph's structure was shaped by the deleted vectors and residual drift can persist until a rebuild. If asked directly, say that — and point to the scheduled rebuild. A reviewer who knows ANN internals will respect the precision; one who catches an overclaim will discount everything else you said.

### Defence 4 — "What does this cost at ten times the volume?"

> *"Cost is dominated by context tokens times query volume, not by embeddings. Embedding our corpus is a one-off in the tens of dollars. The controllable variable is how much context each query sends to a frontier model, which is why we rerank to a small top-k rather than passing the full candidate set, cache the static prefix, and route low-complexity queries to a cheaper tier. Cost per query is on the dashboard from day one, with an alert on trend, because this failure mode is invisible until the invoice arrives."*

🧮 **DERIVED** — 100k documents × 1,500 tokens; 500-token chunks, 15% overlap; 10,000 queries/day:

| | Context/query | Monthly at ~$3/M input |
| :--- | :-: | ---: |
| Naive: pass top-50 chunks | ~25,000 tok | **~$22,500** |
| Reranked: pass top-5 | ~2,500 tok | **~$2,250** |
| Reranked + prefix caching | ~2,500 tok | **~$1,000–1,500** |

One-time embedding of that corpus: **~$20**. Verify unit prices against current vendor pricing; the *shape* is the durable part. **A business case that models embedding cost and not context cost has modelled the wrong thing.**

### Defence 5 — "What happens when the model you built on is deprecated?"

> *"Model identity is an abstraction in our architecture, not a constant. Prompts target a capability tier, not a name. The index records the embedding model id and dimension and fails closed on mismatch rather than silently comparing incompatible vectors. Embedding migration is blue/green: build the new index alongside, validate against the golden set, swap the alias, retain the old index until confidence is established. We budget a re-embed roughly annually because deprecation is scheduled, not hypothetical."*

---

# Part 5 · Certification checklist

Sign-off gate for L2. Each line is a question a reviewer can ask for evidence on.

**Ingestion**
- [ ] φ estimated per document; human-validated sample calibrates proxies monthly
- [ ] Layout-aware parsing verified on the **dominant** document class
- [ ] Repeating headers/footers detected and excluded
- [ ] Every chunk carries its heading breadcrumb
- [ ] Chunk band determined empirically against the golden set, not copied
- [ ] Tables and code blocks atomic
- [ ] Idempotency proven — re-running ingestion produces zero writes

**Authorisation**
- [ ] ACL applied **inside** ANN traversal; post-filtering explicitly tested against
- [ ] Identity TTL documented and ≤ 5 minutes
- [ ] **Every derived store enumerated with a documented ACL binding**
- [ ] CI test: out-of-group principal returns zero results for a known document

**Lifecycle**
- [ ] Tombstone propagation asserted in CI on every build
- [ ] Response cache TTL ≤ stated withdrawal SLA
- [ ] Nightly orphan sweep reconciling source inventory against index
- [ ] Freshness SLA defined and monitored **per document class**
- [ ] Blue/green reindex with atomic alias swap; rollback tested
- [ ] Embedding model id and dimension stored; mismatch fails closed

**Retrieval**
- [ ] Hybrid verified as true rank fusion (verbatim-string test passes)
- [ ] Reranker's benefit **measured** on the golden set, not assumed

**Governance**
- [ ] Golden set exists, includes adversarial and "documents do not say" cases
- [ ] Retrieval and generation metrics reported **separately**
- [ ] Eval gate runs in CI and blocks merges
- [ ] Per-query trace: retrieved chunk ids, user, timestamp
- [ ] Cost per query on a dashboard with trend alerting
- [ ] Abstention is a measured, rewarded outcome

---

# Part 6 · What this manual defers, and when you'll need it

Deferred to the Technical Reference, with the trigger that tells you it is time.

| Plane | Deferred content | Entry trigger |
| :--- | :--- | :--- |
| **1 · Context** | Attention density, KV cache mathematics, PagedAttention, compression | Cost or latency is the binding constraint, **and** Parts 2–5 are green |
| **3 · Memory** | Working FSM, causal ledger, provenance DAG | Multi-turn sessions where cross-session bleed or unfalsifiable claims are a real risk |
| **4 · Routing** | Cascading, semantic routers, egress control, resilience | Unit economics require tiering, or single-vendor outage is unacceptable |
| **5 · Orchestration** | FSM graphs, supervisor–worker, step budgets | The task genuinely needs multi-step autonomy — most do not |
| **6 · Tooling (MCP)** | Typed schemas, gateway, sandboxing, confused-deputy defence | The system takes actions, not just answers |
| **8 · Adaptation** | Trace curation, prompt optimisation, SFT/LoRA, DPO/GRPO | L3 reached and manual improvement has plateaued |

> [!WARNING]
> Each row is a **capability with a maturity prerequisite**, not a feature to schedule. Adding agentic orchestration before retrieval is measured produces a system whose failures you cannot localise: when a five-step agent gives a wrong answer and you have no retrieval metrics, you cannot tell which step failed.

---

# Appendix · Evidence Ledger

The Reference classifies pattern *names*. This extends the same discipline to *claims*, because numbers are where credibility is lost at review.

## Patterns cited in this manual

| Pattern | Class | Origin |
| :--- | :-: | :--- |
| Okapi BM25 | ✅ STANDARD | Robertson & Walker, 1994 |
| Reciprocal Rank Fusion | ✅ STANDARD | Cormack et al., 2009 |
| Cross-encoder reranking | ✅ STANDARD | Nogueira & Cho, 2019 |
| Contextual chunk headers | ✅ STANDARD | Widely adopted practice |
| Parent-child retrieval | ✅ STANDARD | Widely adopted practice |
| Blue/green index swap | ✅ STANDARD | Established SRE practice |
| Ragas evaluation triad | ✅ STANDARD | Es et al., 2023 |
| Late chunking | ⚠️ EMERGING | Published 2024; needs a long-context embedding model, benefit is corpus-dependent. Keep a structural-chunking fallback |
| Extraction fidelity φ | 🔶 ORIGINAL | Framing device for a real, under-measured quantity. Present as *"our operational proxy for extraction completeness."* Its defensibility rests on calibration against human scoring |
| Tri-State Truth Model | 🔶 ORIGINAL | Close to three-valued logics; the formulation is ours. Fine as a design choice |
| Maturity model L0–L4 | 🔶 ORIGINAL | A teaching structure, not a standard reference architecture. Say so |

## Numeric and empirical claims

| Claim | Class | Basis |
| :--- | :-: | :--- |
| 2 of 88 repos implement document-level ACL | 📊 MEASURED | Survey of 88 cloned repos; reproducible via `tools/clone_score.py` |
| 26 of 88 (29%) compute any retrieval metric | 📊 MEASURED | Same survey |
| 36 of 88 (40%) have a reindex path | 📊 MEASURED | Same survey |
| Foundry Agents SDK cannot pass per-user auth | 🔗 CITED | [azure-sdk-for-python #44454](https://github.com/Azure/azure-sdk-for-python/issues/44454), open since Dec 2025 |
| Re-rank hybrid cannot recover a dense miss | 🔗 CITED | Three issues, three orgs, three engines (§2.4) |
| Embedding-space mismatch fails silently | 🔗 CITED | [LightRAG #3978](https://github.com/HKUDS/LightRAG/issues/3978) and others |
| Cost table (§Defence 4) | 🧮 DERIVED | Arithmetic from stated assumptions; verify unit prices |
| φ values per document feature | 🗣️ FIELD | Planning estimates. Measure your own |
| Golden set of 30–100 questions | 🗣️ FIELD | Practitioner convention |
| Chunk bands (150–400 / 600–1,200) | 🗣️ FIELD | Practitioner convention; measure against your golden set |
| Recall < 70% as a kill criterion | 🗣️ FIELD | Judgement, not a benchmark |
| *"40% of RAG queries fail"* | ❌ UNVERIFIED | Circulates widely in vendor content; not traceable to primary data. **Do not use** |
| *"Pilots cost 10× more than projected"* | ❌ UNVERIFIED | Same. **Do not use** |

> [!TIP]
> **The framing that works commercially**: *"The components are all standard and I can point you at the papers. What I'm bringing is the composition and the operational discipline around it — which is the part that's actually hard to buy."* That is both true and stronger than a claim to have invented a pattern.

## What none of this can tell you

- **Production frequencies.** The survey samples published repositories, not production systems. No claim of the form *"X% of RAG failures are Y"* is derivable from it, and none is made here.
- **The failures nobody publishes.** Tenant leakage, cost overruns and quietly cancelled programmes are commercially embarrassing and therefore absent from public sources. Their absence is a fact about disclosure, not about frequency.
- **Whether your corpus can answer your questions.** Only the audit in Part 3 tells you that, and it is the single highest-return week in the programme.
