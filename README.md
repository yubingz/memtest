# MemTest

> A framework-agnostic benchmark toolkit for AI memory systems. Plug in any memory store, get a full evaluation report.

[中文文档](README_CN.md)

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
| **Storage Integrity** | Are all memories successfully written? | `stored / total` |
| **Retrieval Precision/Recall** | Does a query find the right memory? | Precision, Recall by query type |
| **Clustering** | Are semantically grouped memories retrieved together? | Cluster accuracy |
| **Forgetting** | Are high-frequency memories retained over low-frequency ones? | Forgetting ratio validity |
| **Reasoning** | Can multi-hop queries chain across memories? | Logic/chain accuracy |
| **Search Depth** | How does recall decay with semantic distance? | Near / Mid / Far recall |

## Test Data

| Dataset | Source | Scale | How to get it |
|---------|--------|-------|---------------|
| `sample_db_100.json` | Procedural synthesis | 100 memories, ~300 queries | Included in repo |
| `test_db_10000.json` | `generator.py` | 10,000 memories, ~3,000 queries | `python generator.py --full` |
| Custom | `knowledge_builder.py` | Any corpus | `python knowledge_builder.py <corpus_dir>` |

### Procedural Generator

```bash
python generator.py              # 100-sample (quick)
python generator.py --full       # 10,000 full-scale
python generator.py --size 500   # Custom size
```

Generates 6 categories of test memories:
- **Storage correctness** — can the system faithfully store and retrieve?
- **Person-centric** — queries about people, roles, relationships
- **Event-centric** — temporal and spatial event retrieval
- **Composite queries** — multi-constraint combinations
- **Clustering** — semantically related groups
- **Reasoning chains** — multi-hop inference across memories

Each memory includes 3 stylistic versions (formal, detailed, colloquial) to test robustness against paraphrase.

### Knowledge Builder

Build a test database from any text corpus (novels, documentation, conversation logs):

```bash
python knowledge_builder.py /path/to/corpus
```

Tested with the Four Great Classical Novels of Chinese literature (~12,000 memories, ~9,000 queries). See [benchmark results](#benchmark-results).

## Benchmark Results

We benchmarked three retrieval strategies against the Four Classical Novels dataset (500-query sample, top-20 retrieval):

| Method | Overall Recall | Water Margin | Journey to the West | Romance of the Three Kingdoms | Dream of the Red Chamber |
|--------|---------------|-------------|--------------------|-------------------------------|-------------------------|
| jieba + SQL LIKE | 2.2% | 0.9% | 1.0% | 2.2% | 4.5% |
| TF-IDF + Cosine | 53.0% | 85.1% | 53.1% | 47.8% | 28.2% |
| Sentence-Transformers | *TBD* | - | - | - | - |

**Key findings:**
- Keyword matching (jieba + LIKE) is effectively broken for semantic retrieval
- TF-IDF provides a 24x improvement but struggles with classical Chinese (Dream of the Red Chamber: 28.2%)
- Neural embeddings (sentence-transformers) are expected to push recall to 70-80%+

## Project Structure

```
memtest/
├── README.md                # This file
├── README_CN.md             # Chinese documentation
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
