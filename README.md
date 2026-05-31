# MemTest — Benchmark Generator for AI Memory Systems

Generate standardized evaluation databases for AI memory systems, from procedural synthesis or real-text extraction.

**[中文文档](README_CN.md)**

## Architecture

```
memtest/
├── llm_interface.py          # LLM abstraction layer (swappable backends)
├── generator.py               # Benchmark generator (procedural / LLM-enhanced)
├── knowledge_builder.py       # Build benchmarks from text (supports EN/CN/mixed)
├── quality_check.py           # Data quality validation (10 automated checks)
├── prompts/                   # Prompt templates (hot-reloadable)
│   ├── memory_enhance.md      # Generate 3 expression variants per memory
│   ├── query_generate.md      # Generate diverse query variants
│   └── fact_extract.md        # Extract structured facts from text (EN/CN)
├── benchmarks/                # Pre-built benchmark data (optional)
├── TODO.md                    # Task backlog & changelog
└── .env                       # API keys (see .env.example)
```

## Quick Start

### 1. Procedural Generation (zero dependencies, instant)

```bash
python generator.py              # 100 memories + 50 queries
python generator.py --size=500   # custom scale
python generator.py --full       # 10,000 memories
```

Output: `sample_db_100.json` (standard MemTest format)

### 2. LLM-Enhanced Generation (more natural)

```bash
# Configure API key
cp .env.example .env
# Edit .env, add DEEPSEEK_API_KEY=...

python generator.py --llm        # LLM generates memory text and queries
```

### 3. Extract from Real Text

```bash
python knowledge_builder.py ./my_books/ output.json
python knowledge_builder.py ./my_books/ output.json --merge   # incremental append
python knowledge_builder.py existing_db.json --clean           # clean existing database
```

Input: Directory of Markdown articles (supports English, Chinese, or mixed text)
Output: Standard database with facts + chains + queries

**Performance:** 3–5× batch LLM acceleration — extraction, classification, and query pre-parsing all use `batch_generate()` for parallel processing.

### 4. Quality Validation

```bash
python quality_check.py sample_db_100.json
```

Output: 10-item automated check report covering chain/cluster/negative-sample integrity.

### 5. Additional Tools

```bash
python _gen_and_test.py            # Generate sample data + self-test
```

| Tool | Description |
|------|-------------|
| `_gen_and_test.py` | One-click generate + self-test |
| `noesis_adapter.py` | NOESIS-II memory system adapter (evaluation integration example) |
| `llm_evaluator.py` | LLM semantic evaluator (replaces exact-match with semantic relevance) |
| `benchmarks/` | Pre-built benchmark data (`llm_rerank_benchmark.json`, etc.) |

## LLM Interface

All LLM calls go through `llm_interface.py` with a unified interface:

| Adapter | Description | Usage |
|---------|-------------|-------|
| `deepseek` | DeepSeek API (default) | `create_llm("deepseek")` |
| `openai` | Any OpenAI-compatible endpoint | `create_llm("openai", api_key="", base_url="", model="")` |
| `mock` | Local mock (offline testing) | `create_llm("mock")` |

Custom adapter:

```python
from llm_interface import LLMInterface

class MyAdapter(LLMInterface):
    def generate(self, prompt, max_tokens=3000, temperature=0, system_prompt=""):
        # Your model invocation logic
        return "..."
```

## Prompt System

All prompts live in `prompts/` and support hot-reload:

- `memory_enhance.md` — Generate 3 expression styles per event (**objective** / **subjective** / **third-party**)
- `query_generate.md` — Generate diverse queries from memories (with few-shot examples)
- `fact_extract.md` — Extract structured facts from long text (with chain detection), **supports EN/CN mixed text**

Falls back to inline prompts when template files are absent.

## Data Format

Standard MemTest JSON contains:

```json
{
  "database_info": { ... },
  "memories": [
    {
      "memory_id": "MEM000001",
      "category": "retrieval_test",
      "difficulty": "medium",
      "time": { "absolute": "...", "relative": "...", "fuzzy": "..." },
      "location": { "city": "...", "place": "...", "landmark": "..." },
      "person": { "name": "...", "identity": "..." },
      "event": { "type": "...", "action": "...", "product": "..." },
      "versions": [
        { "version_id": "v1", "style": "objective", "content": "Zhang Wei purchased Maotai at Starbucks in Beijing, quantity 100" },
        { "version_id": "v2", "style": "subjective", "content": "Zhang Wei recalled: I was at Starbucks in Beijing, thought the price was decent, so I bought Maotai..." },
        { "version_id": "v3", "style": "third_party", "content": "Wang Fang said Zhang Wei bought Maotai over there in Beijing, about 100, not sure about the price" }
      ],
      "cluster_id": "CLUSTER0001",
      "reasoning_chain": "CHAIN_causal_001",
      "chain_position": 1,
      "chain_prev": "",
      "chain_next": "MEM000002"
    }
  ],
  "queries": [
    {
      "query_id": "Q0001",
      "query_text": "Zhang Wei's purchase records in Beijing",
      "query_type": "composite",
      "expected_memory_ids": ["MEM000001"],
      "expected_answer": "Zhang Wei purchased Maotai at Starbucks in Beijing, quantity 100",
      "expected_time": "2026-05-26 14:30:00",
      "is_negative": false
    }
  ]
}
```

## Documentation

| Document | Description |
|----------|-------------|
| [API.md](API.md) | MemoryAdapter interface + complete data format spec |
| [GUIDE.md](GUIDE.md) / [GUIDE_CN.md](GUIDE_CN.md) | Detailed usage guide (architecture / evaluation dimensions / extensibility) |
| [OPTIMIZATION.md](OPTIMIZATION.md) | Issue diagnosis & optimization roadmap |
| [TODO.md](TODO.md) | Task backlog & changelog |

## Security

- `.env` is in `.gitignore` — API keys are never accidentally committed
- Path traversal protection: knowledge builder rejects system directories (`/etc`, `/root`, etc.)
- JSON payload size limit: 2MB default cap

## Testing

```bash
python -m py_compile generator.py
python -m py_compile knowledge_builder.py
python -m py_compile llm_interface.py
```

## License

MIT
