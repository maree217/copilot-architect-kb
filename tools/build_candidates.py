"""Phase 1 (clone-era) -- assemble the candidate pool.

The GitHub search API is unavailable in this environment, so the pool cannot be
assembled by query. It is built from three sources instead, and the provenance
of every entry is recorded so the bias is visible rather than laundered:

  curated   -- named from domain knowledge of the ecosystem. This is the honest
               weak point of the method: a hand-written list carries the
               author's blind spots, and repos nobody has heard of cannot appear
               in it. Recorded as such in the dataset.
  kb        -- lifted from the repository's existing mappings/external-references.json
  snowball  -- discovered by reading the dependency manifests and README links of
               repos already cloned. This is the bias corrective: it surfaces
               projects that working code actually depends on, regardless of
               whether anyone curated them.

Nothing here is ranked. This step only decides what gets measured.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "candidates.json")

# --- curated seed -----------------------------------------------------------
# Grouped by the role the repo plays, because the scorer compares within kind.
CURATED = {
    "vendor_reference": [
        "Azure-Samples/azure-search-openai-demo",
        "Azure-Samples/azure-search-openai-demo-csharp",
        "Azure-Samples/chat-with-your-data-solution-accelerator",
        "Azure-Samples/rag-postgres-openai-python",
        "Azure-Samples/azure-openai-rag-workshop",
        "Azure-Samples/miyagi",
        "Azure/GPT-RAG",
        "microsoft/sample-app-aoai-chatGPT",
        "microsoft/PubSec-Info-Assistant",
        "GoogleCloudPlatform/generative-ai",
        "NVIDIA/GenerativeAIExamples",
        "aws-samples/amazon-bedrock-workshop",
        "elastic/elasticsearch-labs",
        "vespa-engine/sample-apps",
        "pinecone-io/examples",
        "neo4j-labs/llm-graph-builder",
    ],
    "framework": [
        "langchain-ai/langchain",
        "langchain-ai/langgraph",
        "run-llama/llama_index",
        "deepset-ai/haystack",
        "microsoft/semantic-kernel",
        "microsoft/kernel-memory",
        "microsoft/graphrag",
        "stanfordnlp/dspy",
        "neuml/txtai",
        "llmware-ai/llmware",
        "SciPhi-AI/R2R",
        "HKUDS/LightRAG",
        "topoteretes/cognee",
        "mem0ai/mem0",
        "getzep/zep",
    ],
    "platform_product": [
        "infiniflow/ragflow",
        "onyx-dot-com/onyx",
        "Mintplex-Labs/anything-llm",
        "open-webui/open-webui",
        "QuivrHQ/quivr",
        "khoj-ai/khoj",
        "zylon-ai/private-gpt",
        "weaviate/Verba",
        "vanna-ai/vanna",
        "danny-avila/LibreChat",
    ],
    "vector_store": [
        "qdrant/qdrant",
        "weaviate/weaviate",
        "milvus-io/milvus",
        "chroma-core/chroma",
        "pgvector/pgvector",
        "lancedb/lancedb",
        "marqo-ai/marqo",
        "zilliztech/GPTCache",
    ],
    "ingestion": [
        "Unstructured-IO/unstructured",
        "DS4SD/docling",
        "microsoft/markitdown",
        "nlmatics/nlm-ingestor",
        "opendatalab/MinerU",
        "VikParuchuri/marker",
    ],
    "retrieval_quality": [
        "FlagOpen/FlagEmbedding",
        "castorini/pyserini",
        "beir-cellar/beir",
        "embeddings-benchmark/mteb",
        "AnswerDotAI/rerankers",
    ],
    "eval_observability": [
        "explodinggradients/ragas",
        "truera/trulens",
        "confident-ai/deepeval",
        "promptfoo/promptfoo",
        "Arize-ai/phoenix",
        "langfuse/langfuse",
        "comet-ml/opik",
        "uptrain-ai/uptrain",
    ],
}


def from_kb():
    """Repos already curated in this knowledge base, so the survey builds on the
    existing work rather than ignoring it."""
    path = os.path.join(DATA, "..", "mappings", "external-references.json")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        doc = json.load(f)
    for cat in doc.get("categories", {}).values():
        for r in cat.get("repositories", []):
            owner, name = r.get("owner"), r.get("name")
            if owner and name:
                out[f"{owner}/{name}"] = cat.get("title", "kb")
    return out


GH_LINK_RE = re.compile(r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=[)\s\"'#,<]|$)")

# Owners whose repos are infrastructure noise in READMEs rather than RAG
# candidates (CI badges, license links, language runtimes).
NOISE_OWNERS = {
    "actions", "shields", "badges", "github", "gitpod-io", "codespaces",
    "python", "nodejs", "docker", "pre-commit", "psf", "astral-sh",
    "readthedocs", "sponsors", "npm", "pypa",
}
NOISE_REPOS = {"LICENSE", "license", "blob", "tree", "releases", "issues", "actions"}


def snowball(scored_path, existing):
    """Extract GitHub references from repos already analysed.

    Only run against repos that cleared the RAG-surface filter, so the expansion
    follows real retrieval code rather than arbitrary link graphs.
    """
    found = {}
    if not os.path.exists(scored_path):
        return found
    with open(scored_path) as f:
        scored = json.load(f)
    for r in scored:
        for link in r.get("referenced_repos", []):
            if link not in existing and link not in found:
                found[link] = r["full_name"]
    return found


def main():
    pool = {}

    for group, names in CURATED.items():
        for n in names:
            pool[n] = {"full_name": n, "seeds": [f"curated:{group}"],
                       "provenance": "curated"}

    for n, cat in from_kb().items():
        if n in pool:
            pool[n]["seeds"].append(f"kb:{cat}")
        else:
            pool[n] = {"full_name": n, "seeds": [f"kb:{cat}"], "provenance": "kb"}

    for n, src in snowball(os.path.join(DATA, "scored.json"), pool).items():
        pool[n] = {"full_name": n, "seeds": [f"snowball:{src}"], "provenance": "snowball"}

    os.makedirs(DATA, exist_ok=True)
    # Preserve anything already in the file (e.g. a prior snowball round).
    if os.path.exists(OUT):
        with open(OUT) as f:
            prev = json.load(f).get("candidates", {})
        for n, v in prev.items():
            if n not in pool:
                pool[n] = v

    with open(OUT, "w") as f:
        json.dump({"candidates": pool,
                   "note": "provenance field records how each repo entered the pool; "
                           "curated entries carry the author's blind spots by construction"},
                  f, indent=1)

    from collections import Counter
    print(f"pool = {len(pool)}")
    print(dict(Counter(v.get("provenance") for v in pool.values())))


if __name__ == "__main__":
    main()
