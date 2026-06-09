# MemTest — Benchmark Database Generator for AI Memory Systems

Generate standardized, reproducible test databases for evaluating AI memory recall quality. Feed any text corpus → get structured memories + ground-truth queries with ID-based answers.

**[中文文档](README_CN.md)**

## Why MemTest?

Current memory system evaluations are ad-hoc: hand-crafted queries, "feels right" assessments, proprietary benchmarks that can't be compared across systems. MemTest provides **deterministic, reproducible test databases** with controlled ground truth.

Key insight: **evaluate retrieval, not generation**. Answers are memory ID sets (not text), so metrics are exact-match, deterministic, and comparable across any memory system.

## Quick Start

### 1. Clone & Try

```bash
git clone https://github.com/yubingz/memtest.git
cd memtest

# Run built-in evaluation with sample database
python3 -c "
from runner import MemoryTestSuite, JsonMemoryAdapter, load_test_db
db = load_test_db('sample_db.json')
suite = MemoryTestSuite(JsonMemoryAdapter())
report = suite.run(db)
print(suite.summary())
"
```

### 2. Generate Your Own Test Database

```bash
# Set up API key (needed for LLM extraction)
cp .env.example .env
# Edit .env: add DEEPSEEK_API_KEY=...

# One-command pipeline
python3 pipeline.py ./my_corpus/ -o test_db.json --name "My Test Database"
```

Only the extraction step uses LLM. Query generation is **deterministic** (pure templates, no LLM).

### 3. Evaluate Your Memory System

Implement 3 methods:

```python
from runner import MemoryAdapter, MemoryTestSuite, load_test_db

class MyAdapter(MemoryAdapter):
    def reset(self):
        # Clear your memory store
        ...
    def store(self, memory_text: str, metadata: dict):
        # Store memory (v4: metadata only has memory_id)
        ...
    def search(self, query: str, top_k: int = 20) -> list:
        # Return [{"memory_id": str, "score": float, "content": str}, ...]
        ...

db = load_test_db("sample_db.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)
print(suite.summary())
```

## Evaluation Dimensions

| Dimension | What it tests | Metric |
|-----------|--------------|--------|
| **Precision Retrieval** | Can you find the right memories? | Precision@K, Recall@K, MRR |
| **Combination Retrieval** | Can you find by multiple attributes? | Same, per query type |
| **Temporal Reasoning** | Can you retrieve across time? | Temporal recall |
| **Negative Samples** | Do you return nothing for non-existent queries? | Negative accuracy |

## Sample Database

The repo includes `sample_db.json` with:
- **131 memories** from 三国演义, 红楼梦, 西游记, 金庸小说
- **1157 queries** across 7 types (人物检索, 地点检索, 时间检索, 事件检索, 组合检索, 别名查询, 组合推理)
- **100% memory coverage** — every memory is referenced by at least one query

For larger databases (5000+ memories), see [GitHub Releases](https://github.com/yubingz/memtest/releases).

## Architecture (v4)

```
memtest/
├── pipeline.py              # One-command pipeline
├── extractor.py             # LLM-based memory extraction (only step using LLM)
├── relation_builder.py      # Build alias groups + reasoning chains (pure rules)
├── query_builder.py         # Generate queries from memory attributes (pure templates)
├── assemble.py              # Assemble into standard v4 format
├── runner.py                 # Run evaluation against a memory system
├── schema.py                 # v4 data format definitions + validation
├── quality_check.py          # Data quality validation (10 automated checks)
├── llm_interface.py          # LLM abstraction (DeepSeek / OpenAI compatible)
├── alias_resolver.py         # Resolve character aliases
├── time_resolver.py          # Normalize temporal expressions
│
├── test_corpus6/             # Input: 四大名著 corpus
│
├── sample_db.json            # Pre-built sample database (v4 format)
└── test_v4.py               # Unit tests
```

## Data Format

### Memory (internal, not fed to system under test)

```json
{
  "memory_id": "MEM000001",
  "content": "刘备，字玄德，人称刘皇叔，涿郡涿县人。",
  "person": ["刘备", "玄德", "刘皇叔"],
  "time_absolute": "",
  "time_relative": "早年",
  "location": "涿县",
  "event_type": "出生",
  "source": "三国演义"
}
```

### Query

```json
{
  "query_id": "Q0001",
  "query_text": "刘备的经历有哪些？",
  "query_type": "人物检索",
  "test_dimension": "精确检索",
  "expected_memory_ids": ["MEM000001", "MEM000002"],
  "is_negative": false,
  "difficulty": "medium"
}
```

### What gets fed to the system under test

Only `{memory_id, content}` — no metadata. This prevents "cheating" by leaking ground-truth labels.

## Design Principles

1. **Only extraction uses LLM** — query generation is pure template × attribute, deterministic and reproducible
2. **ID-based answers** — no text similarity ambiguity, exact match evaluation
3. **Content-only storage** — metadata (person/time/location) is for generating queries, not for the system under test
4. **Self-selected corpus** — feed any text, pipeline auto-extracts facts and generates queries
5. **Memory ≠ Understanding** — we test "did you remember it?", not "did you understand it?"

## License

MIT
