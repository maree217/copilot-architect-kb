# Enterprise RAG failure modes

Each mode below is graded by the evidence actually behind it. The bar set before
collection started was **three citations from three distinct organisations**.
Modes that cleared it are in the first section. Modes that did not are in
[Weak evidence](#weak-evidence) rather than quietly promoted — that section is
the honest part of this document and is published deliberately.

Nothing here is a synthesised war story. Every citation is a link to a public
issue, a commit, or code you can read.

---

## Confirmed modes

### 1. Document-level access control is absent, and often structurally unavailable

**Symptom.** Retrieval returns chunks from documents the asking user cannot open.
Discovered at security review, after the pilot has been demoed to executives.

**Mechanism.** Vector search has no native concept of per-user authorisation.
Enforcing it requires a filterable identity field written at ingestion and a
security filter applied at query time, propagated from the caller's token. Every
layer must cooperate; if any layer drops the identity, the system fails open —
it returns results, just the wrong ones. Azure AI Search states this directly:
it "doesn't provide native document-level permissions and can't vary search
results from within an index by user permissions."

**Evidence.**

- **Measured in this survey: 2 of 88 repos (2%)** show any document-level ACL
  implementation pattern at all. See `data/scored.json`, `doc_acl` density.
  The two are [`Azure-Samples/azure-search-openai-demo`](https://github.com/Azure-Samples/azure-search-openai-demo)
  (28.7 hits per 100 RAG files) and [`Arize-ai/phoenix`](https://github.com/Arize-ai/phoenix) (3.7).
- [`Azure/azure-sdk-for-python` #44454](https://github.com/Azure/azure-sdk-for-python/issues/44454)
  — the Azure AI Foundry Agents SDK's AI Search tool cannot pass
  `x-ms-query-source-authorization`, so it "cannot be used safely in production,
  access-controlled environments." Opened December 2025, **still open with no
  maintainer response as of September 2026**. A nine-month-old unanswered issue
  on a first-party SDK is a structural limitation, not a bug.
- Microsoft's own documentation treats this as an application responsibility
  rather than a platform feature:
  [`search-document-level-access-overview.md`](https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/search/search-document-level-access-overview.md),
  [`login_and_acl.md`](https://github.com/azure-samples/azure-search-openai-demo/blob/main/docs/login_and_acl.md).

**Why it matters more than the others.** This is the mode that converts a
successful pilot into a cancelled project. It cannot be retrofitted cheaply: the
identity field has to exist at ingestion time, so discovering it late means
reindexing the entire corpus.

**Detection.** Before writing any code: can your retrieval layer accept a
per-request identity token, and does your ingestion pipeline write a filterable
identity field? If either answer is no, you do not have document security.

---

### 2. Hybrid search that only re-ranks cannot recover a vector miss

**Symptom.** Queries containing exact identifiers — part numbers, SKUs,
acronyms, error codes, internal project names — return plausible but wrong
chunks, while the correct chunk containing the literal string is never returned.
"Hybrid search" is enabled, and it does not help.

**Mechanism.** Two architectures are both marketed as hybrid. In true hybrid
retrieval, lexical and vector legs run independently and their ranked lists are
fused (typically reciprocal rank fusion). In re-rank-only hybrid, the lexical
score merely reorders candidates the vector search already returned. In the
second architecture, **BM25 can never surface a chunk the vector leg missed,
even when the query contains the exact words in that chunk.** Domain jargon is
precisely what embedding models underrepresent, so the vector leg misses exactly
the queries the lexical leg was added to rescue.

**Evidence.**

- [`typesense/typesense` #2816](https://github.com/typesense/typesense/issues/2816)
  — hybrid search returns 0 results when a quoted phrase has no keyword match,
  despite the vector leg having relevant results on its own.
- [`weaviate/weaviate` #10350](https://github.com/weaviate/weaviate/issues/10350)
  — BM25 results merged incorrectly into hybrid results.
- [`HKUDS/LightRAG` #3198](https://github.com/HKUDS/LightRAG/issues/3198)
  — RFC for BM25 + vector with graph seeding specifically for jargon-heavy
  domains, i.e. an acknowledgement that vector-only fails there.

Three distinct organisations, three independent vector engines. Architectural.

**Detection.** Query your index for a string you know appears verbatim in one
document and nowhere else. If it does not come back first, your hybrid is a
re-rank.

---

### 3. Changing the embedding model silently invalidates the index

**Symptom.** After an embedding-model upgrade, retrieval quality degrades without
any error. In the worse variant, writes fail silently and the index quietly stops
growing.

**Mechanism.** Vectors from different models, dimensions, pooling strategies or
instruction templates occupy incompatible spaces. Comparing them is meaningless
but not illegal — the arithmetic succeeds. A store holding mixed vectors
**returns confident nonsense rather than an error**. Dimension changes fail
loudly; same-dimension model swaps fail silently, which is worse.

**Evidence.**

- [`HKUDS/LightRAG` #3978](https://github.com/HKUDS/LightRAG/issues/3978)
  — a model or dimension change "must fail closed", and rebuild must be
  recoverable on every backend. That this needed filing is the finding.
- [`openclaw/openclaw` #32277](https://github.com/openclaw/openclaw/issues/32277)
  — indexer does not detect dimension mismatch between stored vectors and the
  active provider.
- [`volcengine/OpenViking` #1066](https://github.com/volcengine/OpenViking/issues/1066)
  — feature request to auto-detect embedding model change and trigger rebuild.

**Corroborating measurement.** Only **36 of 88 repos (40%)** show any reindex or
migration code path at all. The majority of RAG codebases have no answer to
"what happens when we change the embedding model" — and model deprecation is
scheduled, not hypothetical.

**Detection.** Store the embedding model id and dimension as index metadata and
refuse to serve when the configured model disagrees. Fail closed.

---

### 4. Chunking splits structure, and the damage is invisible

**Symptom.** Answers drawn from tables are wrong in a specific way: correct
column headers, wrong numbers, or a value attributed to the wrong row. Retrieval
"works" — it returns a relevant-looking chunk.

**Mechanism.** Fixed-window chunking splits a table from its header row, a code
block mid-fence, or a value from the unit label that gives it meaning. The
resulting chunk embeds fine and retrieves fine; it is simply no longer true.
Researchers call this boundary fragmentation. It is a correctness fault baked
into the index at ingestion, which makes it far more expensive to find than to
prevent — the failure surfaces at answer time, many layers from its cause.

**Evidence.**

- [`infiniflow/ragflow` #19520](https://github.com/infiniflow/ragflow/issues/19520)
  — table/image chunks emitted before the preceding text paragraph, with
  `context_above`/`context_below` flipped.
- Structure-aware chunkers exist specifically to fix this and describe the
  failure in their own terms, e.g.
  [`jarstorm/chunkwise`](https://github.com/jarstorm/chunkwise) ("never breaks
  code blocks or tables"), [`GiovanniPasq/chunky`](https://github.com/GiovanniPasq/chunky).
- Documented as a named pattern in
  [`ombharatiya/ai-system-design-guide`](https://github.com/ombharatiya/ai-system-design-guide/blob/main/06-retrieval-systems/02-chunking-strategies.md).

**Caveat on this evidence.** Two of the corroborating repos are small projects
rather than production systems, and this search surfaced obvious repo-cloning
spam alongside them (four byte-identical `rag-chunker` repos under different
owners). The mechanism is well-attested; the citation quality here is the
weakest of the confirmed four.

**Mitigations seen in the wild.** Atomic table emission with heading breadcrumbs;
store a natural-language table summary for embedding but return the full
Markdown table to the model; parent-child chunking where the child matches and
the parent is what gets sent.

---

## Weak evidence

These modes are real in the practitioner literature, and I did not find three
independent, credible citations for them in this run. They are listed so the
gaps in the survey are visible, and so a later run with issue-tracker access can
promote or drop them on evidence.

| Mode | What was found | What is missing |
|---|---|---|
| **Deletion never fully propagates** | Strongest single finding in the set: correct deletion from a proximity-graph (HNSW) index leaves measurable retrieval drift, and rebuilds do not remove it. Directly relevant to GDPR erasure. Also [`ArcadeData/arcadedb` #7931](https://github.com/ArcadeData/arcadedb/issues/7931) on tombstones leaving orphan vector ids. | Citations are one real engine plus small projects. Needs corroboration in a major vector store's tracker. |
| **Reranker triples latency for no measurable gain** | Widely discussed; the cross-encoder cost is undisputed. | No issue found where someone measured the gain as zero and said so. Suspected because nobody publishes a negative result. |
| **Eval set built from demo questions** | Measured obliquely: only **26 of 88 repos (29%)** compute any retrieval metric numerically, so most projects cannot detect regression at all. | No direct citation of a team discovering their eval set was unrepresentative. |
| **Cost discovered in month three** | Token-cost tooling is abundant, implying the problem. | Cost surprises are discussed in blogs and closed rooms, not issue trackers. |
| **Multi-tenant leakage via shared index** | Implied by mode 1 and by tenancy patterns in the data. | No public incident found. Unsurprising — nobody files a public issue saying they leaked one customer's data to another. |
| **Multilingual cliff** | Acknowledged in embedding-model documentation. | No production-grade citation in this run. |

**Read the absence correctly.** "No public citation" mostly means the failure is
commercially embarrassing, not that it is rare. Multi-tenant leakage and cost
overruns are the two clearest cases: their absence from GitHub is evidence about
GitHub, not about RAG.

---

## Priors stated before collection, and how they held up

The ten modes predicted at the planning stage are recorded in
`tools/harvest_issues.py` as regex priors, committed before any data was
gathered, so that imposing a pattern on the data would be visible.

| Predicted | Outcome |
|---|---|
| Chunking destroys the answer | Confirmed (weakest citations of the four) |
| Embedding drift on model upgrade | Confirmed, plus a measured 40% figure |
| ACL bypass | Confirmed, and stronger than predicted — a structural SDK gap, not a config error |
| Recall collapse on acronyms and IDs | Confirmed, with a sharper mechanism than predicted (re-rank vs. true fusion) |
| Stale index divergence | Weak evidence |
| Reranker cost with no gain | Weak evidence |
| Eval set overfit to demo questions | Weak evidence, measured obliquely |
| Cost surprise in month three | Weak evidence |
| Multi-tenant leakage | Weak evidence |
| Multilingual cliff | Weak evidence |

Four of ten cleared the bar. That ratio is itself a finding: the modes that
survive public scrutiny are the ones a vendor or maintainer must admit in a
tracker, and the ones that stay private are the ones that embarrass a customer.
