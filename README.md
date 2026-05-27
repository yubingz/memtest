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

### 1. Storage Integrity

**Design purpose**: Verify that the memory system can write all entries completely and accurately. This is the most fundamental capability — if it can't store, retrieval is moot.

**What it tests**:
- Memories generated at 3 difficulty levels (easy/medium/hard), hard level includes more metadata fields
- Each memory includes 3 stylistic versions (formal, detailed, colloquial) — the system must store all of them
- Final check: `stored_count / total_memories`, ideal value is 300% (3 versions per memory)

**Breadth**: 6 event types (trade/meeting/decision/daily/tech/emotion), 100+ cities, 70+ place types

### 2. Retrieval Precision/Recall

**Design purpose**: The core dimension — given a query, can the system find the correct memory? This is the lifeline of any memory system.

**What it tests**: 5 query types, escalating from single-dimension to multi-dimensional:

| Query Type | Example | Difficulty |
|-----------|---------|-----------|
| **Person** | "What has Wei Qiang done recently?" | Single dimension: name matching |
| **Location** | "What happened at Meeting Room B in Yinchuan?" | Single dimension: location matching |
| **Event** | "What events involve Moutai?" | Single dimension: event/product matching |
| **Time** | "Find records in Taiyuan from 2 weeks ago" | Single dimension: **time matching with relative time computation** |
| **Composite** | "Lu Jie's tech event at the gym 1 week ago" | Triple constraint: time + person + location |

**Special design for time queries**: Each memory includes 4 temporal representations:
- `absolute`: exact timestamp (`2026-03-15 21:21:12`)
- `relative`: relative time (`2 months ago`, `3 days ago`, `1 week ago`)
- `fuzzy`: vague time (`last month`, `a few days ago`, `long ago`)
- `timestamp`: Unix timestamp

Queries use `relative`/`fuzzy` expressions, but memories store `absolute` timestamps. The system must understand that "2 weeks ago" maps to a specific date range — this is not simple string matching.

**Difficulty scaling**: Each memory is labeled easy/medium/hard. Hard queries include more distractors and vaguer phrasing.

### 3. Organization/Clustering

**Design purpose**: Are semantically related memories recognized as "the same group"? When retrieving one memory, can the system also surface others in the same cluster?

**What it tests**:
- Every 10 memories share a `cluster_id` (e.g. `CLUSTER0001`), grouped by event type
- Query with one member's keywords (person + product), check if Top-10 results include other members of the same cluster
- `cluster_accuracy` = queries that hit a cluster-mate / total queries

**Breadth**: 10 memories per cluster, covering all event types

### 4. Forgetting

**Design purpose**: Human memory follows "use it or lose it" — frequently accessed memories should be retained preferentially, while rarely-used ones can fade. A good AI memory system should exhibit this property.

**What it tests**:
- Each memory is labeled with one of 4 decay levels: `high-frequency`, `medium-frequency`, `low-frequency`, `rare-event`
- Includes `access_count` (0-100) simulating usage frequency
- Retrieve using the memory's original text, measure retention rate for high-freq vs. low-freq groups
- `forgetting_ratio_valid = high_freq_retention > low_freq_retention` — does the system correctly prioritize important memories?

**Judging criterion**: Not that the system never forgets, but that forgetting has directionality — important memories are preserved first.

### 5. Reasoning

**Design purpose**: Real-world queries often require cross-memory inference. Can the system support multi-hop queries?

**What it tests**:
- 5 reasoning types: **causal / temporal / comparative / inclusive / deductive**
- `Composite retrieval` queries: multi-dimensional cross-constraints (time + person + location)
- `Composite reasoning` queries: chain reasoning across multiple memories
- `logic_accuracy`: hit rate for logic queries
- `chain_accuracy`: complete hit rate for chain reasoning

### 6. Deep Retrieval

**Design purpose**: The real challenge of long-term memory isn't recalling "yesterday" — it's recalling "that one thing mentioned 6 months ago." As time distance and semantic distance grow, retrieval difficulty increases exponentially. Can the system maintain recall at different depth levels?

**What it tests**:
- All memories span 1-2 years ago (unlike other dimensions' recent memories)
- Each memory is annotated with:
  - `layers` (3-7): conceptual depth
  - `associations` (2-5): number of associations
  - `semantic_distance`: `near` / `mid` / `far`
- Recall is measured separately for near/mid/far layers
- Ideal system: near ~100%, far still has reasonable recall

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

The following results are from our custom-built **NOESIS-II** memory system, evaluated against the Four Classical Novels dataset (11,794 memories, 8,907 queries) with a 500-query random sample, top-20 retrieval:

| Method | Overall Recall | Water Margin | Journey to the West | Romance of the Three Kingdoms | Dream of the Red Chamber |
|--------|---------------|-------------|--------------------|-------------------------------|-------------------------|
| jieba + SQL LIKE | 2.2% | 0.9% | 1.0% | 2.2% | 4.5% |
| TF-IDF + Cosine Similarity | 53.0% | 85.1% | 53.1% | 47.8% | 28.2% |
| Sentence-Transformers | *TBD* | - | - | - | - |

**Method details**:
- **jieba + SQL LIKE**: Query tokenized via jieba, multi-token OR LIKE clauses run directly against NOESIS-II's SQLite database, top-20 results
- **TF-IDF + Cosine Similarity**: jieba-tokenized TF-IDF matrix (sklearn) over all memories and queries, cosine similarity with threshold 0.3, top-20 results
- **Sentence-Transformers**: `paraphrase-multilingual-MiniLM-L12-v2` encoding with ChromaDB vector search — evaluation in progress

**Key findings**:
- Keyword matching (jieba + LIKE) is effectively broken for semantic retrieval — "What did Yuan Shao do?" cannot find "Yuan Shao led his troops to Bohai"
- TF-IDF provides a 24x improvement but struggles with classical Chinese (Dream of the Red Chamber: 28.2%) — jieba tokenization is poor for semi-classical text, and word-frequency similarity cannot bridge the semantic gap
- By query type: composite reasoning 100% (more keywords = easier hit), person 55.1%, time 52.6%, event 45.7%, location 29.7%
- Neural embeddings are expected to push recall to 70-80%+, especially improving the classical Chinese scenario

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
