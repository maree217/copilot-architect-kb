# Hiring Signals — August 2026

A demand-side reading of the enterprise AI stack: what organizations are actually
**staffing for**, as distinct from what vendors say is being adopted. Job specifications
are a lagging but honest indicator — a company writing a tool into a job requisition has
already committed budget, headcount and a hiring manager to it.

Snapshot recorded **18 August 2026** from the public [Lenny's Jobs](https://www.lennysjobs.com/)
feed (a Lenny Rachitsky × TrueUp collaboration tracking open roles at tech companies
Series A and later). Figures are the feed's own facet counts across ~7,000+ open roles.

> **Read the caveats before citing this.** See [Sampling bias](#sampling-bias-read-this-before-citing)
> below. This board samples US product/growth/AI roles at venture-backed tech companies.
> It is not a sample of UK enterprise IT, and it should not be read as one.

---

## Tools named in job specifications

| Tool / technology | Roles | Share of feed |
|---|---:|---:|
| LLM (generic) | 867 | ~12% |
| SQL | 652 | ~9% |
| **Anthropic** | **422** | **~6%** |
| **Claude** | **383** | **~5%** |
| AWS | 297 | ~4% |
| **Cursor** | **221** | **~3%** |
| Salesforce | 216 | ~3% |
| Python | 208 | ~3% |
| Jira | 203 | ~3% |
| **MCP** | **177** | **~2.5%** |

Share is against the ~7,000 total and is indicative only — a single role can name several
tools, and the feed's facet list was not exhaustively enumerated beyond the top tier.

## What the numbers actually say

**1. MCP has crossed from specification to staffing line-item.** 177 open roles naming the
Model Context Protocol is the single most consequential number here. A protocol ratified
in late 2024 now appears in job requirements at roughly the same order of magnitude as
Jira and Python. Architects still treating MCP as speculative are behind the hiring market.

**2. Model vendors are being named in job specs, which is new.** "Anthropic" (422) and
"Claude" (383) appearing as *named requirements* marks a shift from the 2024–25 pattern
where specs said "LLM experience" generically. Buyers have stopped treating models as
interchangeable commodities at the hiring level. This is the demand-side mirror of the
multi-model reality documented in the
[August 2026 platform update](./2026-08-platform-landscape.md) — where M365 Copilot itself
now offers Claude Sonnet 5 alongside GPT-5.6.

**3. Agentic coding tools are standardizing.** Cursor at 221 roles means specific AI
development tooling is now an expected competency, not a personal preference.

**4. Generic still outweighs specific.** "LLM" (867) leads every named vendor. Most
organizations are still hiring for general capability rather than a committed stack —
which is precisely the window in which architecture decisions get made, and precisely
where an evidence-first engagement (S3 on the briefing) has leverage.

## The Microsoft question

**Microsoft Copilot does not appear in this feed's top-ranked tool facets.** That finding
needs handling honestly, because the naive reading is wrong.

This is a sampling artifact, not a measure of weakness. Enterprise M365 Copilot
deployments are staffed by internal IT functions, systems integrators and managed service
partners — none of which post "Senior PM, Copilot" to a US product-and-growth job board.
The roles that carry Copilot rollouts are internal transformation, change-management and
platform-engineering posts, and they are advertised through entirely different channels.

The useful conclusion is about **what the board measures**, not about Microsoft:

- This feed measures **builder-side** AI tooling demand — the tools engineers and PMs use
  to construct AI products.
- It does **not** measure **enterprise deployment** — the platforms organizations roll out
  to their workforce.

These are two different markets with two different buying centres, and conflating them is
a common analytical error. A vendor comparison drawn from this data alone would be invalid.

## Sampling bias — read this before citing

| Dimension | What this feed covers | What it misses |
|---|---|---|
| Geography | US-weighted | UK / EU enterprise market |
| Function | Product, growth, AI, engineering | Internal IT, change, transformation |
| Company type | Tech, Series A+ VC/PE-backed and public tech | Non-tech enterprise, public sector, NHS, housing, financial services back-office |
| Role level | Individual contributor to Director | Programme / portfolio leadership |

Further constraints on the data itself:

- Facet counts are **live and shift daily**; this is a point-in-time snapshot, not a trend.
- Counts displayed as "1K+" are a **display cap**, not a precise figure, and are excluded
  from the table above.
- The tool facet list was read at its top tier only; lower-frequency tools were not enumerated.
- One snapshot is not a time series. The value compounds only when the next snapshot lands.

## Method

Recorded by hand from the public feed. **No scraping, no automated ingestion, no API.**
The site publishes no public API, and its `robots.txt` explicitly disallows automated AI
crawlers. Future snapshots must be recorded the same way — read the public facet panel,
transcribe the counts, cite the date.

## Next snapshot

Due **November 2026**. Track the same ten facets so the deltas are comparable. The number
worth watching is MCP: if 177 becomes 350+, the protocol has won the integration layer
outright, and the grounding/connector architecture in the platform update needs revisiting.

---

*Recorded 18 August 2026. Source: [lennysjobs.com](https://www.lennysjobs.com/) public feed
· [About Lenny's Jobs](https://lenny.trueup.io/about). Part of the
[Copilot Architect knowledge base](https://maree217.github.io/copilot-architect-kb).*
