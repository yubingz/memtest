# MemTest Detailed Documentation

[中文版](GUIDE_CN.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Test Data Schema](#3-test-data-schema)
4. [Evaluation Dimensions In Depth](#4-evaluation-dimensions-in-depth)
5. [Data Generation](#5-data-generation)
6. [Knowledge Builder](#6-knowledge-builder)
7. [Running Evaluations](#7-running-evaluations)
8. [Interpreting Results](#8-interpreting-results)
9. [Extending MemTest](#9-extending-memtest)

---

## 1. Overview

MemTest is a framework-agnostic benchmark for AI memory systems. It answers one question: **does your memory system actually work?**

Traditional evaluation approaches couple test data to a specific backend. MemTest decouples them through an adapter pattern — you implement 3 methods (`reset`, `store`, `search`), and MemTest handles the rest: data generation, query execution, scoring, and reporting.

### Core Principles

| Principle | What it means |
|-----------|--------------|
| **Framework-agnostic** | No dependency on any specific memory system. The adapter is the only integration point. |
| **Zero-dependency** | Pure Python stdlib + JSON. No pip install required for the core framework. |
| **Data-logic separation** | Test data (JSON) is independent of evaluation logic (runner). Swap either without touching the other. |
| **Reproducible** | `random.seed(42)` ensures the same input generates the same data every time. |

---

## 2. Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  generator.py   │────>│  test_db.json│<────│knowledge_builder│
│  (procedural)   │     │  (test data) │     │   (corpus-based)│
└─────────────────┘     └──────┬───────┘     └─────────────────┘
                               │
                               │  (test data — decoupled)
                               ▼
                     ┌──────────────────┐
                     │  Your Evaluation │  ←  接任意评测框架
                     │  (runner.py, or  │     或自己实现
                     │   your own)      │
                     └────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
           ┌──────────────┐   ┌──────────────┐
           │ Your Adapter │   │JsonMemoryAdpt│
           │ (real system)│   │ (built-in,   │
           │              │   │  keyword-only│
           └──────────────┘   └──────────────┘
```

> **注意**：`runner.py` 已从核心包剥离，作为可选评测工具保留。核心定位是**纯数据生成工具**，评测由用户自行选择或实现框架。见 [README.md](README.md) 快速开始。

- **generator.py**: Procedurally generates test data with controlled randomness
- **knowledge_builder.py**: Extracts facts from real text corpora via LLM, then structures them into the same format
- **runner.py**: The evaluation engine. Iterates through test data, calls adapter methods, computes scores
- **Your Adapter**: The only code you write — a thin wrapper around your memory system

---

## 3. Test Data Schema

### Memory Entry

Every memory in the test database follows this structure:

```json
{
  "memory_id": "MEM000001",
  "category": "存储正确性测试集",
  "difficulty": "中等",
  "weight": 1.0,
  "time": {
    "absolute": "2026-01-15 14:30:00",
    "relative": "5天前",
    "fuzzy": "前几天",
    "timestamp": 1736932200
  },
  "location": {
    "city": "北京",
    "place": "星巴克",
    "landmark": "CBD核心区"
  },
  "person": {
    "name": "张伟",
    "identity": "项目经理",
    "partner_name": "王芳",
    "partner_identity": "设计师",
    "relation": "同事"
  },
  "event": {
    "type": "交易",
    "action": "购买",
    "product": "茅台",
    "quantity": 100,
    "price": 1800
  },
  "versions": [
    {"version_id": "v1", "style": "标准叙述", "content": "张伟在北京星巴克购买了茅台，数量100"},
    {"version_id": "v2", "style": "详细描述", "content": "2026年01月15日 14时30分，张伟（项目经理）在北京市星巴克进行购买操作，涉及茅台，交易数量100股，单价1800元"},
    {"version_id": "v3", "style": "口语化", "content": "在北京出差的张伟，15号那天购买了茅台，搞了100份"}
  ],
  "tags": ["存储测试", "中等", "5d"],
  "cluster_id": null,
  "reasoning_chain": null,
  "chain_position": null,
  "decay": {"level": null, "access_count": 0}
}
```

#### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `memory_id` | string | Unique identifier, format `MEM######` |
| `category` | string | Test dimension: `存储正确性测试集`, `检索功能测试集`, `记忆整理测试集`, `遗忘功能测试集`, `逻辑推理测试集`, `长期记忆深度检索测试集` |
| `difficulty` | string | `简单` / `中等` / `困难`. Affects weight and metadata density |
| `weight` | float | 0.5 (easy) / 1.0 (medium) / 1.5 (hard). Used for weighted scoring |
| `time.absolute` | string | Exact timestamp `YYYY-MM-DD HH:MM:SS` |
| `time.relative` | string | Relative expression: `刚刚`, `昨天`, `3天前`, `2周前`, `6个月前` |
| `time.fuzzy` | string | Vague expression: `今天`, `前几天`, `上个月`, `很久以前` |
| `time.timestamp` | int | Unix timestamp |
| `location.city` | string | City name (100+ Chinese cities) |
| `location.place` | string | Venue name (cafes, malls, offices, etc.) |
| `location.landmark` | string | Area descriptor (CBD, tech park, etc.) |
| `person.name` | string | Primary person's name |
| `person.identity` | string | Job title / role |
| `person.partner_name` | string | Secondary person's name |
| `person.relation` | string | Relationship: 同事/上级/下属/朋友/闺蜜... |
| `event.type` | string | 交易/会议/决策/日常/技术/情感 |
| `event.action` | string | Specific action (购买/召开/批准/出差/开发/庆祝...) |
| `event.product` | string | Product or entity involved |
| `versions` | array | 3 stylistic versions of the same memory (see below) |
| `tags` | array | Searchable tags |
| `cluster_id` | string? | Cluster ID for organization tests (e.g. `CLUSTER0001`) |
| `reasoning_chain` | string? | Chain ID for reasoning tests |
| `chain_position` | int? | Position within a reasoning chain (1-6) |
| `decay.level` | string? | `高频记忆` / `中等频率` / `低频记忆` / `偶发事件` |
| `decay.access_count` | int | Simulated access frequency (0-100) |
| `depth.layers` | int? | Conceptual depth (3-7), deep retrieval only |
| `depth.associations` | int? | Association count (2-5), deep retrieval only |
| `depth.semantic_distance` | string? | `near` / `mid` / `far`, deep retrieval only |

#### The 3-Version Design

Every memory is rendered in 3 styles to test **paraphrase robustness**:

| Version | Style | Example |
|---------|-------|---------|
| v1 | 标准叙述 (Formal) | "张伟在北京星巴克购买了茅台，数量100" |
| v2 | 详细描述 (Detailed) | "2026年01月15日 14时30分，张伟（项目经理）在北京市星巴克进行购买操作，涉及茅台，交易数量100股，单价1800元" |
| v3 | 口语化 (Colloquial) | "在北京出差的张伟，15号那天购买了茅台，搞了100份" |

All 3 versions are stored (via `adapter.store()`). A robust retrieval system should return the correct memory regardless of which style the query resembles.

### Query Entry

```json
{
  "query_id": "Q0001",
  "query_text": "张伟在北京的购买记录",
  "query_type": "组合检索",
  "expected_memory_ids": ["MEM000001"],
  "expected_answer": "张伟在北京星巴克购买了茅台，数量100",
  "difficulty": "中等",
  "search_depth": "中层"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query_id` | string | Unique query identifier |
| `query_text` | string | The actual query string |
| `query_type` | string | `时间检索` / `地点检索` / `人物检索` / `事件检索` / `组合检索` / `组合推理` |
| `expected_memory_ids` | array | Ground truth — which memories should be retrieved |
| `expected_answer` | string | The correct answer text |
| `difficulty` | string | `简单` / `中等` / `困难` |
| `search_depth` | string | `浅层` / `中层` / `深层` |

---

## 4. Evaluation Dimensions In Depth

### 4.1 Storage Integrity

**What it tests**: Can the system faithfully store all data without loss?

**How it works**:
1. `adapter.reset()` clears the memory store
2. For each memory, all 3 versions are stored via `adapter.store(version["content"], metadata)`
3. Counts total `store()` calls vs. expected count
4. **Ideal result**: `integrity = 300%` (3 versions × N memories)

**Why 3 versions matter**: Some systems might silently drop duplicates or near-duplicates. If two versions of the same event are too similar, a naive dedup mechanism might discard one. This test catches that.

**Scoring**:
```
integrity = stored_count / total_memories
```
- `1.0` = only 1 version per memory stored (bad)
- `3.0` = all 3 versions stored (ideal)

### 4.2 Retrieval Precision/Recall

**What it tests**: Given a query, does the system return the correct memory in the top-K results?

**How it works**:
1. For each query, call `adapter.search(query_text, top_k=20)`
2. Compare returned `memory_id`s against `expected_memory_ids`
3. Compute Precision and Recall per query type and overall

**Query types and their design intent**:

| Query Type | Template | Design Intent |
|-----------|----------|---------------|
| **人物检索** | "{name}最近做了什么" | Tests whether the system can find memories by person name. Baseline difficulty. |
| **地点检索** | "在{city}{place}发生过什么" | Tests spatial retrieval. Note: queries use place names, not coordinates. |
| **事件检索** | "关于{product}的事件有哪些" | Tests event/product matching. The query may use different wording than the stored memory. |
| **时间检索** | "查找{relative}发生的事情" | **Critical test**: queries use relative/fuzzy time ("2周前"), but memories store absolute timestamps. The system must perform temporal reasoning. |
| **组合检索** | "{name}在{city}的{action}记录" | Multi-dimensional cross-constraint. The system must satisfy all conditions simultaneously. |
| **组合推理** | "请梳理{name}的完整经历脉络" | Chain reasoning. Expected to return multiple memories forming a coherent narrative. |

**Time retrieval in detail**:

This is the most architecturally significant query type. Consider:

```
Stored memory:  time.absolute = "2026-01-15 14:30:00"
Query:          "查找5天前发生的事情"
```

The system must:
1. Parse "5天前" into a date range
2. Compare against stored absolute timestamps
3. Return memories within that range

If the system only does keyword matching on time fields, it will fail: "5天前" does not appear in "2026-01-15 14:30:00".

The 4 temporal representations are designed to test different levels of temporal understanding:
- `absolute` → exact match (easy)
- `relative` → temporal arithmetic (medium)
- `fuzzy` → approximate matching (hard)
- `timestamp` → numerical range queries

**Scoring**:
```
Precision = correct_hits / (count × top_k)
Recall    = correct_hits / total_expected
```

### 4.3 Organization/Clustering

**What it tests**: Are semantically related memories grouped together? When you retrieve one memory, does the system surface its "neighbors"?

**How it works**:
1. Memories in the "记忆整理测试集" category are assigned `cluster_id`s
2. Each cluster contains ~10 memories sharing the same event type
3. For each cluster member, query with `"{person_name} {event_product}"`
4. Check if Top-10 results contain any other member of the same cluster
5. **cluster_accuracy** = queries that found a cluster-mate / total queries

**Why it matters**: In real usage, users often need "more like this" — not just one specific memory, but related context. A system that clusters well can provide richer, more useful responses.

**Scoring**:
```
cluster_accuracy = correct / total
```

### 4.4 Forgetting

**What it tests**: Does the system retain important (high-frequency) memories better than unimportant (low-frequency) ones?

**How it works**:
1. Memories are tagged with decay levels:
   - `高频记忆` (access_count: high)
   - `中等频率` (access_count: medium)
   - `低频记忆` (access_count: low)
   - `偶发事件` (access_count: very low)
2. For each memory in high-freq and low-freq groups, search using the memory's original text (v1)
3. Measure **retention rate**: can the system still find this memory in Top-10?
4. **forgetting_ratio_valid** = `high_freq_retention > low_freq_retention`

**The key insight**: We're not testing whether the system forgets (all finite-capacity systems must). We're testing whether forgetting has *directionality* — important things should be forgotten last.

**Scoring**:
```
forgetting_ratio_valid = (high_freq_retention > low_freq_retention)
```
This is a boolean: either the system has the right priority, or it doesn't.

### 4.5 Reasoning

**What it tests**: Can the system handle multi-hop queries that require connecting information across memories?

**How it works**:
- **Logic queries** (`事件检索` + `组合检索`): Single-hop but multi-constraint. The system must match multiple fields (person + location + time) simultaneously.
- **Chain queries** (`组合推理`): Multi-hop. Expected to return multiple memories from a reasoning chain. For example, "trace Zhang Wei's complete experience" should return all memories where Zhang Wei appears.

**Scoring**:
```
logic_accuracy  = logic_queries_hit / logic_queries_total
chain_accuracy  = chain_queries_hit / chain_queries_total
```

### 4.6 Deep Retrieval

**What it tests**: How does recall degrade as time distance and semantic distance increase?

**How it works**:
1. All memories in this category are from 1-2 years ago (not recent)
2. Each memory is annotated with:
   - `depth.layers` (3-7): How many conceptual hops from common knowledge
   - `depth.associations` (2-5): How many other memories it connects to
   - `depth.semantic_distance`: `near` / `mid` / `far`
3. Search using the memory's original text (v1)
4. Measure recall at each distance level

**Why separate from regular retrieval**: Regular retrieval tests are biased toward recent, high-frequency memories. Deep retrieval specifically targets the long tail — old, rare, semantically distant information that a good system should still be able to surface.

**Scoring**:
```
near_recall = near_hits / near_total
mid_recall  = mid_hits / mid_total
far_recall  = far_hits / far_total
```

---

## 5. Data Generation

### generator.py — Procedural Synthesis

**Usage**:
```bash
python generator.py              # 100-sample (quick)
python generator.py --full       # 10,000 full-scale
python generator.py --size 500   # Custom size
```

**How it works**:

1. **Base generation**: For each memory, randomly selects from data pools:
   - 100+ cities, 50+ places, 30+ landmarks
   - 100+ Chinese names, 24 job titles, 10 relationship types
   - 6 event types, each with 3-7 specific actions
   - 17 products (stocks, commodities, crypto)

2. **Time distribution**: Memories span 6 time periods:
   | Period | Range | Example relative time |
   |--------|-------|---------------------|
   | 24h | 0-1 day ago | "刚刚", "昨天" |
   | 7d | 1-7 days ago | "3天前", "1周前" |
   | 30d | 7-30 days ago | "2周前", "3周前" |
   | 90d | 30-90 days ago | "2个月前", "3个月前" |
   | 1y | 90-365 days ago | "6个月前", "10个月前" |
   | fuzzy | 365-730 days ago | "去年", "很久以前" |

3. **Category distribution**: ~17% each for 6 categories

4. **Difficulty distribution**: 30% easy, 40% medium, 30% hard

5. **Query generation**: For each selected memory, randomly pick a query type and fill in the template:
   ```python
   QUERY_TEMPLATES = {
       "时间检索": lambda m: [
           f"查找{m['time']['relative']}发生的事情",
           f"查询{m['time']['fuzzy']}在{m['location']['city']}的相关记录",
       ],
       # ... 5 types, 2 templates each
   }
   ```

6. **Reproducibility**: `random.seed(42)` — same run always produces same data

### Output Format

```json
{
  "database_info": {
    "name": "MemTest Database",
    "version": "1.0.0",
    "total_count": 100,
    "categories": {"存储正确性测试集": 17, "检索功能测试集": 17, ...},
    "created_at": "2026-05-28 05:00:00"
  },
  "memories": [...],
  "queries": [...]
}
```

---

## 6. Knowledge Builder

### knowledge_builder.py — Corpus-Based Generation

Unlike the procedural generator, the knowledge builder creates test data from **real text** using LLM extraction.

**Usage**:
```bash
python knowledge_builder.py ./my_books/ output.json
python knowledge_builder.py ./my_books/ output.json --merge  # Incremental
```

**Pipeline**:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 1. Fact  │───>│ 2. Field │───>│ 3. Build │───>│ 4. Query │───>│ 5. LLM   │
│ Extraction│    │Classify  │    │Memories  │    │Generate  │    │Cache     │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     LLM             LLM           Rules          Rules           LLM
```

**Stage 1 — Fact Extraction**: LLM reads each text file and extracts structured facts:
- `content`: Concise fact statement (15-40 characters)
- `person`: Person name
- `location`: Physical geographic location
- `time`: Specific time (year/date)
- `dynasty`: Dynasty/era (e.g., "东晋", "贞观年间")
- `event_type`: Event type label

**Stage 2 — Field Classification**: LLM validates extracted fields:
- Is "东晋" a location or a dynasty? (Should be dynasty, not location)
- Is "丞相府" a location or a concept? (Borderline — classified as concept)
- Splits compound time expressions ("383年，东晋" → time="383年", dynasty="东晋")

**Stage 3 — Memory Building**: Rules-based structuring:
- Assigns `MEM######` IDs starting from MEM010000
- Creates 3 versions (formal/detailed/colloquial)
- Builds reasoning chains: if a person appears in ≥3 memories, link them as a chain (up to 6 deep)

**Stage 4 — Query Generation**: Same templates as procedural generator, but applied to real extracted data

**Stage 5 — LLM Pre-parse Cache**: Pre-resolves each query into structured search parameters (person, location, time, dynasty) for systems that can use structured queries

**Requirements**: DeepSeek API key in `.env` file (never commit this file; copy from `.env.example`):

```bash
cp .env.example .env
# Edit .env and paste your key
```

```
DEEPSEEK_API_KEY=sk-xxx
```

> ⚠️ **Security**: `.env` is listed in `.gitignore`, but always verify with `git status` before committing. If you accidentally commit a key, revoke it immediately on the provider's platform.

**Incremental mode** (`--merge`): Processes only new files, appends to existing database

---

## 7. Running Evaluations

### Basic Usage

```python
from runner import MemoryTestSuite, MemoryAdapter, load_test_db

class MyAdapter(MemoryAdapter):
    def __init__(self):
        self.db = MyMemorySystem()
    
    def reset(self):
        self.db.clear()
    
    def store(self, memory_text: str, metadata: dict):
        self.db.insert(text=memory_text, meta=metadata)
    
    def search(self, query: str, top_k: int = 20) -> list[dict]:
        results = self.db.search(query, limit=top_k)
        return [{"memory_id": r.id, "score": r.score, "content": r.text} for r in results]

db = load_test_db("sample_db_100.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)

# Print summary
from runner import summary
print(summary(report))
```

### What happens during `suite.run(db)`

1. **Reset**: `adapter.reset()` — clear all existing data
2. **Store phase**: For each memory, store all 3 versions. Metadata is flattened from nested structure.
3. **Evaluation phase**: 6 dimensions evaluated sequentially:
   - Storage integrity (no search calls)
   - Retrieval (1 search per query)
   - Organization (up to 3 searches per cluster)
   - Forgetting (1 search per memory, up to 40 memories)
   - Reasoning (1 search per query)
   - Deep retrieval (1 search per memory, up to 30 memories)
4. **Report**: Returns a dict with all dimension scores

### Built-in Adapter: JsonMemoryAdapter

For quick validation of test data itself (not a real evaluation):

```python
from runner import JsonMemoryAdapter, MemoryTestSuite, load_test_db

adapter = JsonMemoryAdapter()  # In-memory keyword matcher
suite = MemoryTestSuite(adapter)
report = suite.run(load_test_db("sample_db_100.json"))
```

This adapter does simple keyword matching — useful for verifying that test data is structurally valid, but **not** a meaningful memory system evaluation.

### One-Click Self-Test

```bash
python runner.py  # Auto-generates sample data if missing, then runs evaluation
```

---

## 8. Interpreting Results

### Report Structure

```python
{
  "storage": {
    "stored_count": 300,
    "total": 100,
    "integrity": 3.0      # 300% = all 3 versions stored
  },
  "retrieval": {
    "by_type": {
      "人物检索": {"precision": 0.05, "recall": 0.8, "count": 10},
      "时间检索": {"precision": 0.03, "recall": 0.2, "count": 10},
      # ...
    },
    "overall_precision": 0.04,
    "overall_recall": 0.5
  },
  "organization": {
    "cluster_accuracy": 0.6,
    "clusters_tested": 5
  },
  "forgetting": {
    "high_freq_retention": 0.9,
    "low_freq_retention": 0.3,
    "forgetting_ratio_valid": true
  },
  "reasoning": {
    "logic_accuracy": 0.7,
    "chain_accuracy": 0.3
  },
  "deep_retrieval": {
    "near": 0.8,
    "mid": 0.4,
    "far": 0.1
  }
}
```

### How to Read Each Dimension

| Dimension | Good | Mediocre | Bad |
|-----------|------|----------|-----|
| Storage integrity | ≥2.5 (most versions stored) | 1.0-2.5 (some versions lost) | <1.0 (data loss) |
| Retrieval recall | >0.7 | 0.3-0.7 | <0.3 |
| Cluster accuracy | >0.5 | 0.2-0.5 | <0.2 |
| Forgetting ratio valid | `true` | `true` but margin small | `false` (inverted) |
| Chain accuracy | >0.5 | 0.2-0.5 | <0.2 |
| Deep far recall | >0.3 | 0.1-0.3 | <0.1 |

### Common Patterns

- **High retrieval, low deep recall**: System works for recent data but forgets old information. Consider adding persistent embeddings.
- **High overall recall, low time recall**: System doesn't understand temporal expressions. Needs time normalization.
- **`forgetting_ratio_valid = false`**: System has no access-frequency awareness. Low-frequency memories are returned as readily as high-frequency ones.
- **High near, low far in deep retrieval**: System can only find semantically close matches. Needs better embedding models.

---

## 9. Extending MemTest

### Adding a New Query Type

1. Add template to `QUERY_TEMPLATES` in `generator.py`
2. Add evaluation logic in the corresponding `_eval_*` method in `runner.py`

### Adding a New Evaluation Dimension

1. Add a new category in `MemoryGenerator` (e.g., `gen_temporal_reasoning`)
2. Add a new `_eval_*` method in `MemoryTestSuite`
3. Include it in the `run()` method's report dict

### Creating a Domain-Specific Generator

Replace the data pools in `generator.py` with domain-specific ones:

```python
# Example: medical records
CITIES = ["心内科", "骨科", "神经外科", ...]
EVENT_TYPES = {"诊断": ["确诊", "排除", "待查"], "治疗": ["手术", "用药", "复查"], ...}
PRODUCTS = ["阿司匹林", "布洛芬", "CT扫描", ...]
```

### Using With Your Memory System

Implement the 3-method adapter:

```python
class MyMemoryAdapter(MemoryAdapter):
    def __init__(self, connection_string):
        self.client = MemoryClient(connection_string)
    
    def reset(self):
        self.client.delete_all()
    
    def store(self, memory_text: str, metadata: dict):
        self.client.add(
            text=memory_text,
            metadata=metadata,
            id=metadata["memory_id"]
        )
    
    def search(self, query: str, top_k: int = 20) -> list[dict]:
        results = self.client.search(query, limit=top_k)
        return [
            {"memory_id": r.metadata["memory_id"], "score": r.score, "content": r.text}
            for r in results
        ]
```

---

## Appendix: Data Pool Sizes

| Pool | Size | Notes |
|------|------|-------|
| Cities | 100 | Tier 1-4 Chinese cities |
| Places | 42 | Cafes, malls, landmarks, offices |
| Landmarks | 28 | District/area descriptors |
| Names | 100 | Common Chinese surnames + given names |
| Identities | 24 | Job titles from CTO to consultant |
| Relations | 10 | 同事, 上级, 朋友, etc. |
| Event types | 6 | 交易/会议/决策/日常/技术/情感 |
| Actions | 23 | Per event type (3-7 each) |
| Products | 17 | Stocks, commodities, crypto |
