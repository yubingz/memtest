# MemTest — 测试库生成工具

从程序化合成或真实文本提取，生成标准化的 AI 记忆系统评测数据库。

## 架构

```
memtest/
├── llm_interface.py          # LLM 接口抽象层（可替换为任意模型）
├── generator.py               # 测试库生成器（程序化 / LLM增强）
├── knowledge_builder.py       # 从文本提取知识构建测试库
├── prompts/                   # 提示词模板（可热更新）
│   ├── memory_enhance.md      # 生成记忆的3种表达变体
│   ├── query_generate.md      # 生成查询变体
│   └── fact_extract.md        # 从文本提取结构化事实
├── benchmarks/                # 已有 benchmark 数据（可选）
└── .env                       # API key（见 .env.example）
```

## 快速开始

### 1. 程序化生成（零依赖，秒级）

```bash
python generator.py              # 生成 100 条记忆 + 50 条查询
python generator.py --size=500   # 自定义规模
python generator.py --full       # 生成 10000 条
```

输出：`sample_db_100.json`（标准 MemTest 格式）

### 2. LLM 增强生成（更自然）

```bash
# 配置 API key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=...

python generator.py --llm        # LLM 生成记忆文本和查询
```

### 3. 从真实文本提取

```bash
python knowledge_builder.py ./my_books/ output.json
```

输入：Markdown 文章目录  
输出：含 facts + chains + queries 的标准数据库

### 4. 质量校验

```bash
python quality_check.py sample_db_100.json
```

输出：10 项自动检查报告，包含链式/聚类/负样本完整性。

## LLM 接口

所有 LLM 调用通过 `llm_interface.py` 统一接口，支持：

| 适配器 | 说明 | 用法 |
|--------|------|------|
| `deepseek` | DeepSeek API（默认） | `create_llm("deepseek")` |
| `openai` | 任意 OpenAI-compatible | `create_llm("openai", api_key="", base_url="", model="")` |
| `mock` | 本地模拟（离线测试） | `create_llm("mock")` |

自定义适配器：

```python
from llm_interface import LLMInterface

class MyAdapter(LLMInterface):
    def generate(self, prompt, max_tokens=3000, temperature=0, system_prompt=""):
        # 你的模型调用逻辑
        return "..."
```

## 提示词系统

所有提示词放在 `prompts/` 目录，支持热更新：

- `memory_enhance.md` — 让 LLM 生成同一事件的3种表达风格（**客观叙述** / **主观视角** / **第三方转述**）
- `query_generate.md` — 让 LLM 从记忆生成多样化查询（含 few-shot 示例）
- `fact_extract.md` — 让 LLM 从长文本提取结构化事实（含链式检测）

提示词文件不存在时自动回退到内联提示词。

提示词文件不存在时自动回退到内联提示词。

## 数据格式

标准 MemTest JSON 包含：

```json
{
  "database_info": { ... },
  "memories": [
    {
      "memory_id": "MEM000001",
      "category": "检索功能测试集",
      "difficulty": "中等",
      "time": { "absolute": "...", "relative": "...", "fuzzy": "..." },
      "location": { "city": "...", "place": "...", "landmark": "..." },
      "person": { "name": "...", "identity": "..." },
      "event": { "type": "...", "action": "...", "product": "..." },
      "versions": [
        { "version_id": "v1", "style": "客观叙述", "content": "张伟在北京星巴克购买了茅台，数量100" },
        { "version_id": "v2", "style": "主观视角", "content": "张伟回忆道：当时在北京星巴克，我（项目经理）觉得价格还行，就买了茅台..." },
        { "version_id": "v3", "style": "第三方转述", "content": "王芳说张伟在北京那边买了茅台，大概100的样子，具体价格不太清楚" }
      ],
      "cluster_id": "CLUSTER0001",
      "reasoning_chain": "CHAIN_因果_001",
      "chain_position": 1,
      "chain_prev": "",
      "chain_next": "MEM000002"
    }
  ],
  "queries": [
    {
      "query_id": "Q0001",
      "query_text": "张伟在北京的购买记录",
      "query_type": "组合检索",
      "expected_memory_ids": ["MEM000001"]
    }
  ]
}
```

## 安全

- `.env` 已加入 `.gitignore`，API key 不会意外提交
- 路径遍历防护：知识构建器拒绝 `/etc`、`/root` 等系统目录
- JSON payload 大小限制：默认 2MB 上限

## 测试

```bash
python -m py_compile generator.py
python -m py_compile knowledge_builder.py
python -m py_compile llm_interface.py
```

## 许可

MIT
