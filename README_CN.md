# MemTest — AI 记忆系统评测数据库生成器

从任意语料生成标准化、可复现的测试数据库，用于评估 AI 记忆系统的检索质量。

## 为什么需要 MemTest？

当前的记忆系统评测各自为战：手写查询、凭感觉评估、私有 benchmark 无法跨系统对比。MemTest 提供**确定性、可复现的测试数据库**，ground truth 基于记忆 ID。

核心洞察：**评测检索，不评测生成**。答案是记忆 ID 集合（不是文本），指标是精确匹配，确定且可比。

## 快速开始

### 1. 克隆并试用

```bash
git clone https://github.com/yubingz/memtest.git
cd memtest

# 用内置 sample 数据库跑评测
python3 -c "
from runner import MemoryTestSuite, JsonMemoryAdapter, load_test_db
db = load_test_db('sample_db.json')
suite = MemoryTestSuite(JsonMemoryAdapter())
report = suite.run(db)
print(suite.summary())
"
```

### 2. 生成自己的测试数据库

```bash
cp .env.example .env
# 编辑 .env：添加 DEEPSEEK_API_KEY=...

python3 pipeline.py ./my_corpus/ -o test_db.json --name "我的测试数据库"
```

只有提取步骤使用 LLM，查询生成是**确定性的**（纯模板，不用 LLM）。

### 3. 接入你的记忆系统

实现 3 个方法即可：

```python
from runner import MemoryAdapter, MemoryTestSuite, load_test_db

class MyAdapter(MemoryAdapter):
    def reset(self):
        # 清空你的记忆存储
        ...
    def store(self, memory_text: str, metadata: dict):
        # 存入记忆（v4模式下 metadata 只有 memory_id）
        ...
    def search(self, query: str, top_k: int = 20) -> list:
        # 返回 [{"memory_id": str, "score": float, "content": str}, ...]
        ...

db = load_test_db("sample_db.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)
print(suite.summary())
```

## 评测维度

| 维度 | 测什么 | 指标 |
|------|--------|------|
| **精确检索** | 能不能找到对的记忆？ | Precision@K, Recall@K, MRR |
| **组合检索** | 能不能按多个属性组合查？ | 同上，按查询类型分组 |
| **时序推理** | 能不能跨时间检索？ | 时序召回率 |
| **负样本** | 查不到的东西会不会返回空？ | 负样本准确率 |

## 样本数据库

仓库自带 `sample_db.json`：
- **131 条记忆**，来自三国演义、红楼梦、西游记、金庸小说
- **1157 条查询**，7 种类型（人物检索、地点检索、时间检索、事件检索、组合检索、别名查询、组合推理）
- **100% 记忆覆盖率** — 每条记忆至少被一个查询命中

大型数据库（5000+ 记忆）见 [GitHub Releases](https://github.com/yubingz/memtest/releases)。

## 设计原则

1. **只有提取用 LLM** — 查询生成是纯模板 × 属性，确定性可复现
2. **ID-based 答案** — 无文本相似度歧义，精确匹配评测
3. **Content-only 存储** — 元数据（人物/时间/地点）用于出题，不喂给被测系统
4. **Memory ≠ Understanding** — 测"记没记住"，不测"懂没懂"

## 许可证

MIT
