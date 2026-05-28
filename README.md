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

Build a test database from any text corpus (novels, documentation, conversation logs):

```bash
python knowledge_builder.py /path/to/corpus
```

Tested with the Four Great Classical Novels of Chinese literature (~12,000 memories, ~9,000 queries). See [benchmark results](#benchmark-results).

## Benchmark Results

The following results are from our custom-built **NOESIS-II** memory system, evaluated against the Four Classical Novels dataset (11,794 unique memories, 577 queries) with a 500-query random sample, top-20 retrieval:

**Evaluation method**: A retrieved memory is considered relevant if the target entity (person, location, event, dynasty) appears in its content. This ensures fair comparison — e.g., "Daiyu and Baoyu chatting" counts as a correct result for both "Daiyu" and "Baoyu" queries.

| Method | Precision@20 | Recall@20 | MRR@20 |
|--------|:------------:|:---------:|:------:|
| jieba + SQL LIKE | ~2% | ~2% | N/A |
| **TF-IDF + jieba + Cosine** | **49.6%** | **83.2%** | **0.862** |
| Sentence-Transformers (MiniLM) | 9.1% | 12.4% | 0.201 |

**Breakdown by query type**:

| Query Type | TF-IDF P@20 | TF-IDF R@20 | ST P@20 | ST R@20 |
|-----------|:-----------:|:-----------:|:-------:|:-------:|
| Person | 67.5% | 89.2% | 4.3% | 4.7% |
| Location | 36.9% | 73.2% | 10.7% | 15.7% |
| Event | 43.9% | 88.9% | 8.0% | 12.7% |
| Time | 78.3% | 85.6% | 55.0% | 55.0% |
| Composite | 59.1% | 62.1% | 21.9% | 22.6% |

**Breakdown by novel**:

| Novel | TF-IDF P@20 | TF-IDF R@20 | ST P@20 | ST R@20 |
|-------|:-----------:|:-----------:|:-------:|:-------:|
| Water Margin | 50.2% | 88.3% | 13.3% | 18.6% |
| Journey to the West | 48.1% | 82.8% | 6.6% | 12.1% |
| Romance of the Three Kingdoms | 45.1% | 81.4% | 5.0% | 7.4% |
| Dream of the Red Chamber | 72.6% | 84.3% | 24.9% | 27.7% |

**Method details**:
- **jieba + SQL LIKE**: Query tokenized via jieba, multi-token OR LIKE clauses against NOESIS-II's SQLite, top-20
- **TF-IDF + jieba + Cosine**: Structured content (person + event + location + dynasty + text) tokenized via jieba, TF-IDF matrix with cosine similarity, top-20
- **Sentence-Transformers**: `paraphrase-multilingual-MiniLM-L12-v2` (384d) encoding the same structured content, cosine similarity, top-20

**Key findings**:
1. **Keyword matching is broken** — jieba + SQL LIKE at 2% recall is essentially non-functional for semantic retrieval
2. **TF-IDF + jieba is surprisingly strong** — 83.2% recall for entity-oriented queries on Chinese text, proving that proper tokenization + term frequency matching is hard to beat for named-entity retrieval
3. **MiniLM underperforms on Chinese classical text** — the multilingual paraphrase model (9.1% precision) fails at entity-level discrimination: it returns semantically related passages but cannot pinpoint the specific entity being queried
4. **ST has an edge on abstract queries** — Time queries (55% vs 78% recall) and Composite queries (22% vs 62%) show a smaller gap, suggesting neural embeddings help when queries are less entity-specific
5. **Better Chinese embedding models** (e.g., bge-large-zh-v1.5) may significantly close this gap — this is a clear next step for the benchmark


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
