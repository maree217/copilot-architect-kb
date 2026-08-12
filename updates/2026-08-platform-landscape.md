# Platform Landscape Update — August 2026

The Microsoft AI platform moved substantially since this KB's v1.0 (October 2025).
This page is the delta: what renamed, what shipped, what retired, and the current
verified model/pricing picture. Facts verified 12 August 2026 against Microsoft Learn,
vendor primary sources, and live GitHub API pulls.

---

## The stack, as of August 2026

```
EXPERIENCE     M365 Copilot ($30/u/mo, agent mode GA Apr 2026) · Copilot Chat (free tier)
               · Copilot Cowork (agentic task execution, GA 16 Jun 2026, credit-metered)
─────────────────────────────────────────────────────────────────────────────
AGENT BUILD    Copilot Studio (low-code, Copilot Credits)  ⇄  Microsoft Foundry (pro-code,
               Azure consumption — renamed from Azure AI Foundry, Jan 2026)
─────────────────────────────────────────────────────────────────────────────
GATEWAY        Model traffic control in the request path: Azure APIM AI gateway
               (llm-* policies) · LiteLLM · Portkey — token metering, chargeback,
               content safety, routing/failover
─────────────────────────────────────────────────────────────────────────────
GROUNDING      The "IQ" layer (Ignite 2025 → Build 2026): Work IQ (Graph semantic index
               productized, API GA 16 Jun 2026) · Fabric IQ (semantics/ontology over
               OneLake) · Foundry IQ (knowledge bases on Azure AI Search) · Web IQ
─────────────────────────────────────────────────────────────────────────────
DATA           Microsoft Graph · Microsoft Fabric/OneLake · Azure AI Search ·
               Graph connectors (synced) & MCP federated connectors
─────────────────────────────────────────────────────────────────────────────
GOVERNANCE     Purview (data, eDiscovery for agents) · Entra Agent ID (agent identity)
               · Agent 365 (agent registry — GA 1 May 2026, $15/u/mo)
```

Key disambiguation for architects: **Purview** governs data, **Entra Agent ID** governs
agent identity, **Agent 365** is the agent fleet registry, and the **AI gateway** governs
model traffic. Four different jobs; the gateway is the one that sits in the request path.

## What changed since v1.0 of this KB

| Was (Oct 2025) | Now (Aug 2026) |
|---|---|
| Azure AI Foundry | **Microsoft Foundry** (renamed Jan 2026; core services now "Foundry Tools") |
| Semantic Kernel + AutoGen (separate) | **microsoft/agent-framework** — unified SDK, MCP-native (12.7k★) |
| Copilot Studio billed in "messages" | **Copilot Credits** (renamed 1 Sep 2025): PAYG ~$0.01/credit or $200/mo per 25k pack; tenant-graph grounding ≈10 credits, autonomous actions ≈25+ |
| Copilot suggests | **Agent mode** edits/builds documents autonomously — GA in Word/Excel/PowerPoint 22 Apr 2026, now default |
| — | **Copilot Cowork** (GA 16 Jun 2026): hand it a task, it returns a finished deliverable; $30 seat is prerequisite, execution metered in credits |
| Graph semantic index (internal) | **Work IQ** — the index productized as a public API (GA 16 Jun 2026) |
| — | **Fabric IQ** (GA "mostly" — Ontology still preview) and **Foundry IQ** (core GA via REST API; built on Azure AI Search) |
| Restricted SharePoint Search as the Copilot guardrail | **RSS retiring** — new setups blocked 31 Jul 2026, gone 31 Jan 2027; replacements: Restricted Content Discovery + SharePoint Advanced Management (bundled free with Copilot license) + Purview labels |
| — | **Agent 365** GA 1 May 2026 ($15/user/mo, per human agent-owner; bundled in M365 E7) + Entra Agent ID |
| Model picking = Azure OpenAI deployment choice | **Multi-model everywhere**: M365 Copilot defaults to GPT-5.6 (9 Jul 2026) with Claude Sonnet 5 selectable and an "Auto" router; Copilot Studio menu includes Claude models; Foundry catalog spans OpenAI, Anthropic, Mistral, Meta, xAI, DeepSeek, MAI |

## Model landscape (verified 12 Aug 2026, prices per 1M tokens)

| Model | In / Out | Microsoft Foundry status |
|---|---|---|
| GPT-5.6 Luna | $0.20 / $1.20 (cached in $0.02) | GA — Azure price parity since 1 Aug 2026 |
| GPT-5.6 Terra | $2.00 / $12.00 | GA |
| GPT-5.6 Sol | $5.00 / $30.00 | GA |
| Claude Sonnet 5 | $2.00 / $10.00 | GA, Azure-hosted |
| Claude Opus 5 | $5.00 / $25.00 | GA, Azure-hosted |
| Claude Fable 5 (Mythos-class) | $10.00 / $50.00 | Preview, Anthropic-hosted only |
| MAI-Thinking-1 | not publicly priced | Private preview |

OpenAI cut Luna 80% on 30 Jul 2026. Architectural implication: consumption economics
collapsed ~25x on the cheap tier in one quarter while per-seat licensing stays flat —
business cases priced on early-2026 token costs are stale, and the asymmetry favours
agent-shaped (consumption) deployments over seat-shaped ones.

## The deployment pattern Microsoft's own accelerators prescribe

Current generation (all actively maintained — verified via GitHub API `pushed_at`, Aug 2026):

- **`Azure/AI-Landing-Zones`** — the flagship: composable **AI Foundry Landing Zone** +
  **AI Gateway Landing Zone** modules; hub-spoke (platform hub: firewall, Bastion,
  private DNS, Log Analytics; workload spokes: Foundry, AI Search, Cosmos, Key Vault
  behind private endpoints, no public access). Standalone mode for smaller orgs.
- **`Azure-Samples/AI-Gateway`** (971★) — APIM AI-gateway labs: `llm-token-limit`,
  `llm-emit-token-metric` (chargeback), semantic caching (non-streaming only),
  multi-region load balancing, inline Content Safety — including over MCP tool calls.
- **`microsoft/agent-framework`** (12.7k★) — unified agent SDK (AutoGen + Semantic
  Kernel successor), deploys to Foundry Agent Service.
- **RAG**: `Azure-Samples/azure-search-openai-demo` (7.7k★) and `Azure/GPT-RAG`
  (zero-trust enterprise variant). **Surfacing**: Copilot Studio (Power CAT Copilot
  Studio Kit) or Teams/M365 via the unified `microsoft/agents` SDK.
- **New/early**: `microsoft/microsoft-iq-solution-accelerator` — first accelerator
  unifying Work IQ + Fabric IQ + Foundry IQ (thin, watch it mature).

**Retired generation — do not build on these**: `coe-starter-kit` (archived May 2026),
`contoso-chat` (archived), `PubSec-Info-Assistant` (dormant since Jun 2025),
`azure-openai-landing-zone` (dormant since Oct 2024), ALM Accelerator (formally
deprecated — replaced by native Power Platform Pipelines). Lesson: in this ecosystem,
buy the pattern (landing zone → gateway → framework → surfacing), not the accelerator;
re-verify quarterly.

## Five deployment archetypes seen in the field

| # | Archetype | Config | Cost shape | Evidence of traction |
|---|---|---|---|---|
| 1 | Free tier first | Copilot Chat + a few metered Studio agents | $0 licenses; ~$50–1,000/mo per agent | Where most orgs start — and stall (Gartner: only ~5–6% of pilots reach scale) |
| 2 | Seat rollout | M365 Copilot seats + SharePoint Advanced Management cleanup + training | $360/seat/yr | UBS 50k seats; Australian gov trial ~1 hr/day saved, training-dependent; activation typically ~36% |
| 3 | One instrumented agent | Scoped Copilot Studio/SharePoint agent + its analytics | ~$200/mo + a few seats | Only config producing question-level telemetry (theme clustering, outcome classification) |
| 4 | Pro-code vertical copilot | Foundry + AI Search/Foundry IQ + custom-engine agent behind a gateway | $75–500k build; ~$5–50k/mo run (order of magnitude) | BlackRock Aladdin, Morgan Stanley (OpenAI-direct variant) |
| 5 | Sell INTO Copilot (data vendors) | MCP server + federated Copilot connectors + branded agent | Engineering cost, revenue line | Moody's, LSEG, S&P Global, FactSet, Morningstar all shipped MCP/federated connectors 2025–26 — table stakes, no exclusivity |

## Adoption reality check (independent data)

- Only ~5–6% of Copilot pilots reach large-scale deployment; 40% delayed 3+ months on
  oversharing/governance (Gartner survey data).
- Microsoft's own Work Trend Index 2026: only 16% of AI users have progressed past
  individual assistance into workflow redesign.
- The most-reported real-world failure mode with landing zones: platform teams spend
  6–12 months hardening while business units drift to shadow AI — the strongest
  argument for starting with a scoped, governed pilot over a platform program.

---

*Compiled 12 Aug 2026. Sources: Microsoft Learn, microsoft.com/microsoft-365/blog,
azure.microsoft.com, openai.com, anthropic.com, GitHub API (live repo stats), Gartner
survey data as reported in trade press. Prices are list/PAYG and move fast — reverify
before quoting.*
