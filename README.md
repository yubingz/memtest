# MemTest

> A framework-agnostic benchmark toolkit for AI memory systems. Plug in any memory store, get a full evaluation report.

[中文文档](README_CN.md) | [📖 Full Documentation](GUIDE.md)

---

## Why MemTest?

AI agents increasingly rely on long-term memory — but how do you know if your memory system actually *works*? Most teams evaluate retrieval with ad-hoc scripts that couple test data to a specific backend. MemTest decouples them:

- **Write once, benchmark anywhere** — the same test suite runs against any memory system
- **6 evaluation dimensions** — not just recall, but storage integrity, clustering, forgetting, reasoning, and depth
- **Zero dependencies** — pure Python stdlib + JSON. No framework lock-in, no install hell
- **Synthetic or real data** — procedural generator for 10K+ test cases, or build from your own corpus

## Quick Start

```python
from runner import MemoryTestSuite, MemoryAdapter, load_test_db

# 1. Implement 3 methods for your memory system
class MyAdapter(MemoryAdapter):
    def reset(self):
        self.db.clear()

    def store(self, memory_text: str, metadata: dict):
        self.db.insert(text=memory_text, **metadata)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        return self.db.query(query, limit=top_k)

# 2. Load test data & run
db = load_test_db("sample_db_100.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)
print(report.summary())
```

## Evaluation Dimensions

| Dimension | What it measures | Key metric |
|-----------|-----------------|------------|
| **Storage Integrity** | Are all memories and their 3 stylistic versions successfully written? | `stored / total` (ideal: 300%) |
| **Retrieval Precision/Recall** | 5 query types (person/location/event/time/composite). Time queries require relative time computation. | Precision, Recall by type |
| **Organization/Clustering** | Are semantically related memories grouped together? Does retrieving one surface its cluster-mates? | Cluster accuracy |
| **Forgetting** | Are high-frequency memories retained over low-frequency ones? Does forgetting have directionality? | `high_freq > low_freq` |
| **Reasoning** | Multi-constraint cross queries and multi-hop chain reasoning. Can the system connect across memories? | Logic/chain accuracy |
| **Deep Retrieval** | 1-2 year old memories: how does recall decay across near/mid/far semantic distance? | Near / Mid / Far recall |

> 📖 For design rationale, scoring formulas, result interpretation, and extension guide, see [GUIDE.md](GUIDE.md)

## Test Data

| Dataset | Source | Scale | How to get it |
|---------|--------|-------|---------------|
| `sample_db_100.json` | Procedural synthesis | 100 memories, ~50 queries | Included in repo |
| `test_db_10000.json` | `generator.py` | 10,000 memories, ~5,000 queries | `python generator.py --full` |
| Custom | `knowledge_builder.py` | Any corpus | `python knowledge_builder.py <corpus_dir>` |

### Procedural Generator

```bash
python generator.py              # 100-sample (quick)
python generator.py --full       # 10,000 full-scale
python generator.py --size 500   # Custom size
```

6 categories distributed evenly (~17% each). Every memory includes 3 stylistic versions to test paraphrase robustness.

### Knowledge Builder

Build a test database from any text corpus (novels, documentation, conversation logs) using LLM-powered fact extraction:

```bash
# Prerequisites: create .env with your API key
echo "DEEPSEEK_API_KEY=sk-your-key-here" > .env

# Basic usage
python knowledge_builder.py /path/to/corpus

# Incremental mode (appends to existing database)
python knowledge_builder.py /path/to/corpus output.json --merge
```

**Corpus requirements:**
- **Format**: Markdown (`.md`) files organized in directories. Other formats (`.txt`, `.pdf`) are not supported — convert to `.md` first.
- **Language**: Currently Chinese only (extraction prompts are in Chinese). English support is planned.
- **File size**: Each file must be ≥ 500 characters (shorter files are skipped). Content beyond the first 3,000 characters per file is not processed — for long texts, split into chapter-sized `.md` files.
- **Structure**: One file per chapter/section works best. Directory names are used as category labels.
- **API dependency**: Requires a [DeepSeek API key](https://platform.deepseek.com/) (or any OpenAI-compatible API endpoint). Costs ~$0.01-0.05 per file depending on length.

**What it does:**
1. **Fact extraction**: LLM extracts structured facts (person, location, time, dynasty, event_type) from each text
2. **Field validation**: LLM classifies ambiguous fields (e.g., is "东晋" a dynasty or a location?)
3. **Memory construction**: Normalizes facts into standardized memory entries with metadata
4. **Query generation**: Creates 6 query types (person, location, event, time, composite, chain) balanced across categories
5. **LLM pre-cache**: Pre-resolves queries into structured search parameters for reproducible evaluation

**Output quality tips:**
- Narrative texts (novels, biographies) produce the richest structured data
- Technical documentation works but may have fewer person/location fields
- Very short or very long files produce lower-quality extractions — aim for 500-3000 chars per file
- Review the output and manually correct any misclassified fields

Tested with the Four Great Classical Novels of Chinese literature (~12,000 memories, ~9,000 queries). See [benchmark results](#benchmark-results).

## Benchmark Results

The following results are from our custom-built **NOESIS-II** memory system, evaluated against the Four Classical Novels dataset (11,794 unique memories, 577 queries). The TF-IDF and ST results use a 500-query random sample; the LLM Rerank result uses a 100-query random sample, all with top-20 retrieval.

**Evaluation method**: A retrieved memory is considered relevant if the target entity (person, location, event, dynasty) appears in its content. This ensures fair comparison — e.g., "Daiyu and Baoyu chatting" counts as a correct result for both "Daiyu" and "Baoyu" queries.

| Method | Precision@20 | Recall@20 | MRR@20 |
|--------|:------------:|:---------:|:------:|
| jieba + SQL LIKE | ~2% | ~2% | N/A |
| TF-IDF + jieba + Cosine | 49.6% | 83.2% | 0.862 |
| Sentence-Transformers (MiniLM) | 9.1% | 12.4% | 0.201 |
| **LLM Rerank (TF-IDF → LLM)** | **87.0%** | **84.9%** | **0.923** |

**Multi-K comparison (TF-IDF vs LLM Rerank)**:

| K | TF-IDF P@K | LLM P@K | TF-IDF R@K | LLM R@K | TF-IDF MRR | LLM MRR |
|---|:----------:|:-------:|:----------:|:-------:|:----------:|:-------:|
| 5 | 72.6% | **83.4%** | 75.9% | **86.7%** | 0.858 | **0.911** |
| 10 | 61.9% | **69.7%** | 75.6% | **83.9%** | 0.859 | **0.911** |
| 15 | 54.5% | **59.9%** | 78.6% | **84.7%** | 0.859 | **0.911** |
| 20 | 49.1% | **52.6%** | 81.5% | **85.5%** | 0.859 | **0.911** |

> LLM reranking improves precision at every K level, with the largest gain at K=5 (+10.8pp). This means LLM is especially effective at pushing the most relevant results to the top.

**Breakdown by query type (LLM Rerank vs TF-IDF)**:

| Query Type | TF-IDF P@20 | LLM P@20 | TF-IDF R@20 | LLM R@20 |
|-----------|:-----------:|:--------:|:-----------:|:--------:|
| Person | 67.0% | 90.5% | 90.3% | 87.6% |
| Location | 39.8% | 92.8% | 76.6% | 88.2% |
| Event | 41.9% | 80.9% | 82.6% | 80.8% |
| Time | 60.0% | 93.8% | 92.5% | 100.0% |
| Composite | 51.0% | 70.0% | 51.0% | 70.0% |

**Breakdown by novel (LLM Rerank vs TF-IDF)**:

| Novel | TF-IDF P@20 | LLM P@20 | TF-IDF R@20 | LLM R@20 |
|-------|:-----------:|:--------:|:-----------:|:--------:|
| Water Margin | 60.0% | 90.3% | 86.3% | 87.1% |
| Journey to the West | 52.8% | 98.9% | 78.0% | 98.3% |
| Romance of the Three Kingdoms | 42.0% | 84.6% | 81.1% | 82.1% |
| Dream of the Red Chamber | 62.5% | 85.0% | 79.2% | 85.0% |

**Method details**:
- **jieba + SQL LIKE**: Query tokenized via jieba, multi-token OR LIKE clauses against NOESIS-II's SQLite, top-20
- **TF-IDF + jieba + Cosine**: Structured content (person + event + location + dynasty + text) tokenized via jieba, TF-IDF matrix with cosine similarity, top-20
- **Sentence-Transformers**: `paraphrase-multilingual-MiniLM-L12-v2` (384d) encoding the same structured content, cosine similarity, top-20
- **LLM Rerank (TF-IDF → LLM)**: Two-stage pipeline — TF-IDF retrieves top-50 candidates, then a large language model (via Coze session API) reranks them by relevance, top-20 selected from reranked list

**Key findings**:
1. **Keyword matching is broken** — jieba + SQL LIKE at 2% recall is essentially non-functional for semantic retrieval
2. **TF-IDF + jieba is a strong baseline** — 83.2% recall proves that proper tokenization + term frequency matching works well for entity-oriented queries
3. **MiniLM underperforms on Chinese classical text** — the multilingual paraphrase model (9.1% precision) fails at entity-level discrimination
4. **LLM reranking is transformative** — precision nearly doubles from 49.6% to 87.0% while recall stays comparable (83.2% → 84.9%), confirming that a large model can effectively identify relevant memories from candidate sets
5. **Two-stage retrieval (retriever + reranker) is the practical winner** — combining TF-IDF's high recall with LLM's precision yields the best overall performance (MRR 0.923)


## Project Structure

```
memtest/
├── README.md                # This file
├── README_CN.md             # Chinese documentation
├── GUIDE.md                 # Full documentation (English)
├── GUIDE_CN.md              # Full documentation (Chinese)
├── API.md                   # Adapter interface & data schema
├── generator.py             # Procedural test data generator
├── knowledge_builder.py     # Corpus -> test database builder
├── runner.py                # Benchmark runner & MemoryAdapter base class
├── _gen_and_test.py         # One-click generate & self-test
├── sample_db_100.json       # Sample database (100 memories)
└── sample_queries.json      # Sample queries
```

## API Reference

See [API.md](API.md) for the full adapter interface specification and data schema.

### Minimal Adapter

You only need to implement three methods:

```python
class MemoryAdapter:
    def reset(self):
        """Clear the memory store before each test run."""
        
    def store(self, memory_text: str, metadata: dict):
        """Store a memory with standard metadata."""
        
    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Search memories. Return [{"memory_id": str, "score": float, "content": str}, ...]"""
```

## Contributing

Contributions welcome — especially:
- New test data generators (domain-specific corpora)
- Adapter implementations for popular memory systems
- Evaluation dimension extensions

## License

MIT
