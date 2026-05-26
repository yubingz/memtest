# MemTest — AI 记忆系统通用评测工具包

> 独立于任何特定记忆系统的评测库。给一个记忆系统，给一份评测报告。

## 设计原则

- **零依赖**：纯 Python 标准库 + JSON，不绑定 NOESIS 或任何特定系统
- **适配器模式**：被测系统只需实现 3 个函数（store / search / reset），即可接入评测
- **标准化数据**：评测数据与评测逻辑完全分离

## 快速开始

```python
from memtest import MemoryTestSuite, MemoryAdapter, load_test_db

# 1. 定义适配器：告诉评测框架你的记忆系统怎么用
class MyMemoryAdapter(MemoryAdapter):
    def reset(self):
        """清空数据库"""
        self.db.clear()

    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆，metadata 含 memory_id/time/location/person/event"""
        self.db.insert(text=memory_text, **metadata)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """检索记忆，返回 [{memory_id, score}, ...]"""
        return self.db.query(query, limit=top_k)

# 2. 加载评测数据
db = load_test_db("sample_db_100.json")  # 或自己生成

# 3. 跑评测
adapter = MyMemoryAdapter()
suite = MemoryTestSuite(adapter)
report = suite.run(db)
print(report.summary())
```

## 评测数据

| 数据 | 来源 | 规模 |
|------|------|------|
| `sample_db_100.json` | 程序合成，100 条 | 即开即用 |
| `test_db_10000.json` | `generator.py` 生成 | 全量 6 类 |
| `your_books.json` | `knowledge_builder.py <语料目录>` | 自定义 |

## 输出

评测报告含 6 维指标：存储完整性 / 检索 Precision/Recall / 整理聚类 / 遗忘合理性 / 逻辑推理 / 深度检索。

## 文件结构

```
memtest/
├── README.md              # 本文件
├── API.md                 # 接口规范（MemoryAdapter 定义 + 数据格式 Schema）
├── generator.py           # 程序合成数据生成器（6 大类，10000 条）
├── knowledge_builder.py   # 语料→测试库（LLM 提取事实，支持经典书籍）
├── runner.py              # 评测执行器 + MemoryAdapter 基类
├── _gen_and_test.py       # 一键生成样例 + 自测
├── sample_db_100.json     # 样例库（占位，运行 generator 生成）
└── sample_queries.json    # 样例查询（运行 generator 生成）
```

## License

MIT
