# MemTest — Benchmark Database Generator for AI Memory Systems

Generate standardized, reproducible test databases for evaluating AI memory recall quality. Feed any text corpus → get structured memories + ground-truth queries with ID-based answers.

**[中文文档](README_CN.md)**

## Why MemTest?

Current memory system evaluations are ad-hoc: hand-crafted queries, "feels right" assessments, proprietary benchmarks that can't be compared across systems. MemTest provides **deterministic, reproducible test databases** with controlled ground truth.

Key insight: **evaluate retrieval, not generation**. Answers are memory ID sets (not text), so metrics are exact-match, deterministic, and comparable across any memory system.

## Architecture (v4)

```
memtest/
├── pipeline_v4.py           # One-command pipeline
├── extractor.py             # LLM-based memory extraction (only step using LLM)
├── relation_builder.py       # Build alias groups + reasoning chains (pure rules)
├── query_builder.py          # Generate queries from memory attributes (pure templates)
├── alias_resolver.py         # Resolve character aliases across corpus
├── time_resolver.py          # Normalize temporal expressions
├── runner.py                  # Run evaluation against a memory system
├── quality_check.py          # Data quality validation (10 automated checks)
├── schema.py                  # Data format definitions
├── llm_interface.py          # LLM abstraction (DeepSeek / OpenAI compatible)
│
├── test_corpus*/             # Input: plain text corpora
│   ├── test_corpus3/xiyouji.md
│   ├── test_corpus4/sgyy_extended.md
│   ├── test_corpus5/hongloumeng_extended.md
│   └── test_corpus6/          # 四大名著：三国演义、红楼梦、水浒传、西游记
│
└── output/                   # Generated test databases
    ├── v4_full.json          # 5736 memories, 700 queries (四大名著) ⭐ 最新
    ├── four_novels.json      # 131 memories, 1157 queries (4 novels)
    ├── hongloumeng.json      # 23 memories, 155 queries
    └── sgyy_full.json        # 17 memories, 173 queries
```

## Quick Start

### 1. Install & Configure

```bash
git clone https://github.com/yubingz/memtest.git
cd memtest
cp .env.example .env
# Edit .env, add DEEPSEEK_API_KEY=... (for memory extraction only)
```

### 2. One-Command Pipeline

```bash
python pipeline_v4.py ./my_corpus/ -o test_db.json --name "My Test Database"
```

This runs: `extract → build relations → generate queries → assemble → validate`

Only the extraction step uses LLM. Query generation is **deterministic** (pure templates, no LLM).

### 3. Custom Corpus

Create a directory with `.md` or `.txt` files containing your text:

```
my_corpus/
├── chapter1.md
├── chapter2.md
└── ...
```

MemTest extracts structured memories, resolves aliases, builds reasoning chains, and generates queries across 6 evaluation dimensions.

## Evaluation Dimensions

| Dimension | Count | Description |
|-----------|-------|-------------|
| **精确检索** | 100 | 人物、地点、时间、事件、别名检索（5 query types） |
| **组合检索** | 100 | 多属性组合查询（人物+地点、人物+时间等） |
| **时序推理** | 100 | 基于时序链的 before/after 推理查询 |
| **负样本** | 100 | 无匹配记忆的查询（应返回空） |
| **跨版本/别名** | 100 | 别名等价查询（如"刘皇叔" = "刘备" = "玄德"） |
| **组合推理** | 100 | 多条件跨维度推理 |
| **总计** | **700** | 6大维度，全覆盖 |

*Stats from `v4_full.json` (5736 memories, 4 novels)*

### Query Types

| Type | Templates | Example |
|------|-----------|---------|
| 人物检索 | 8 | "刘备的经历有哪些？" |
| 地点检索 | 6 | "在涿县发生了什么？" |
| 时间检索 | 6 | "早年有什么事件？" |
| 事件检索 | 7 | "关于玉的事件有哪些？" |
| 别名查询 | 5 | "刘皇叔是谁？" |
| 组合检索 | 12+ | "刘备在涿县的记录" |
| 组合推理 | auto | "...之前发生了什么？" |

## Data Format

### Memory

```json
{
  "memory_id": "MEM000001",
  "content": "刘备，字玄德，人称刘皇叔，是汉景帝之子中山靖王刘胜的后代。",
  "person_list": ["刘备", "字玄德", "玄德", "刘皇叔", "中山靖王刘胜", "汉景帝"],
  "location": {"city": "涿县", "place": "楼桑村"},
  "time": {"relative": "早年"},
  "event": {"type": "日常", "action": "出生"},
  "source": "三国演义",
  "alias_evidence": [{"entity": "刘备", "alias": "刘皇叔", "evidence": "人称刘皇叔"}]
}
```

### Query

```json
{
  "query_id": "Q0001",
  "query_text": "刘备的经历有哪些？",
  "query_type": "人物检索",
  "test_dimension": "精确检索",
  "expected_memory_ids": ["MEM000001", "MEM000002", "MEM000005"],
  "is_negative": false,
  "difficulty": "困难"
}
```

### ID-Based Evaluation

Answers are **memory ID sets**, not text. This means:
- **Exact match**: No ambiguity from text similarity
- **Deterministic**: Same database → same results, always
- **Comparable**: Any memory system can be evaluated against the same ground truth

## Pre-built Databases

| Database | Memories | Queries | Sources | Pipeline |
|----------|----------|---------|---------|----------|
| `v4_full.json` | **5736** | **700** | 三国演义 + 红楼梦 + 水浒传 + 西游记 | v4 (latest) |
| `four_novels.json` | 131 | 1157 | 三国演义 + 红楼梦 + 西游记 + 金庸5部 | v3 |
| `hongloumeng.json` | 23 | 155 | 红楼梦 | v3 |
| `sgyy_full.json` | 17 | 173 | 三国演义 | v3 |

## Design Principles

1. **Only extraction uses LLM** — query generation is pure template × attribute, deterministic and reproducible
2. **ID-based answers** — no text similarity ambiguity, exact match evaluation
3. **Self-selected corpus** — feed any text, pipeline auto-extracts facts and generates queries
4. **Original text preservation** — memories stored as-is, no transformation at storage time
5. **6 evaluation dimensions** — covering precision, combination, temporal reasoning, negatives, and alias equivalence
6. **Alias-aware** — character aliases (e.g., 孙悟空=齐天大圣=美猴王) resolved and tested as equivalence groups

## License

MIT
