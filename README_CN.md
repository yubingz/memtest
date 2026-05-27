# MemTest

> AI 记忆系统通用评测工具包。接入任意记忆系统，输出完整评测报告。

[English](README.md) | [📖 详细文档](GUIDE_CN.md)

---

## 为什么需要 MemTest？

AI Agent 越来越依赖长期记忆——但你怎么知道你的记忆系统是否真的*好用*？大多数团队用临时脚本做检索评测，测试数据和后端强耦合。MemTest 把它们解耦：

- **一次编写，处处评测** — 同一套测试可跑在任意记忆系统上
- **6 大评测维度** — 不只看召回率，还看存储完整性、聚类、遗忘、推理和检索深度
- **零依赖** — 纯 Python 标准库 + JSON，无框架锁定，无安装地狱
- **合成或真实数据** — 程序化生成万级测试用例，或从自有语料构建

## 快速开始

```python
from runner import MemoryTestSuite, MemoryAdapter, load_test_db

# 1. 为你的记忆系统实现 3 个方法
class MyAdapter(MemoryAdapter):
    def reset(self):
        self.db.clear()

    def store(self, memory_text: str, metadata: dict):
        self.db.insert(text=memory_text, **metadata)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        return self.db.query(query, limit=top_k)

# 2. 加载评测数据 & 跑评测
db = load_test_db("sample_db_100.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)
print(report.summary())
```

## 评测维度

| 维度 | 测什么 | 核心指标 |
|------|--------|----------|
| **存储完整性** | 所有记忆是否成功写入？3 种风格版本是否全部保留？ | `stored / total`（理想 300%） |
| **检索 Precision/Recall** | 5 种查询类型（人物/地点/事件/时间/组合），能否命中正确记忆？时间检索含相对时间计算 | Precision, Recall by type |
| **整理聚类** | 语义相关的记忆是否被归为一组？检索一条时能否浮现同组其他记忆？ | Cluster accuracy |
| **遗忘合理性** | 高频记忆保留率是否高于低频？遗忘是否有方向性？ | `high_freq > low_freq` |
| **逻辑推理** | 多约束交叉查询和跨记忆链式推理，系统能否支持多跳？ | Logic/chain accuracy |
| **深度检索** | 1-2 年前的记忆，近/中/远语义距离的召回率如何衰减？ | Near / Mid / Far recall |

> 📖 每个维度的设计意图、测试方法、评分公式和结果解读，详见 [GUIDE_CN.md](GUIDE_CN.md)

## 测试数据

| 数据集 | 来源 | 规模 | 获取方式 |
|--------|------|------|----------|
| `sample_db_100.json` | 程序合成 | 100 条记忆，50 条查询 | 仓库自带 |
| `test_db_10000.json` | `generator.py` 生成 | 10,000 条记忆，~5,000 条查询 | `python generator.py --full` |
| 自定义 | `knowledge_builder.py` | 任意语料 | `python knowledge_builder.py <语料目录>` |

### 程序化数据生成器

```bash
python generator.py              # 100 条样例（快速）
python generator.py --full       # 10,000 条全量
python generator.py --size 500   # 自定义规模
```

6 大类记忆按比例分配（各约 17%），每条记忆包含 3 种风格版本测试改写鲁棒性。

### 知识构建器

从任意文本语料（小说、文档、对话记录）构建测试库：

```bash
python knowledge_builder.py /path/to/corpus
```

已用中国四大名著验证（~12,000 条记忆，~9,000 条查询）。详见[评测结果](#评测结果)。

## 评测结果

以下结果基于我们自研的 **NOESIS-II** 记忆系统，使用四大名著数据集（11,794 条记忆，8,907 条查询）的 500 条随机采样，Top-20 召回：

| 方法 | 整体 Recall | 水浒传 | 西游记 | 三国演义 | 红楼梦 |
|------|------------|--------|--------|---------|--------|
| jieba + SQL LIKE | 2.2% | 0.9% | 1.0% | 2.2% | 4.5% |
| TF-IDF + 余弦相似度 | 53.0% | 85.1% | 53.1% | 47.8% | 28.2% |
| Sentence-Transformers | *待测* | - | - | - | - |

**评测方法说明**：
- **jieba + SQL LIKE**：对查询做 jieba 分词，生成多词 OR LIKE 子句，直接在 NOESIS-II 的 SQLite 数据库中 SQL 查询，取 Top-20
- **TF-IDF + 余弦相似度**：对全量记忆和查询做 jieba 分词后构建 TF-IDF 矩阵（sklearn），计算查询与记忆的余弦相似度，阈值 0.3，取 Top-20
- **Sentence-Transformers**：使用 `paraphrase-multilingual-MiniLM-L12-v2` 编码，ChromaDB 向量检索，评测进行中

**关键发现**：
- 关键词匹配（jieba + LIKE）对语义检索基本失效——"袁绍做了什么"搜不到"袁绍引兵往渤海而去"
- TF-IDF 提升了 24 倍，但在半文言文本上仍吃力（红楼梦：28.2%）——jieba 分词对古汉语效果差，语义鸿沟靠词频无法弥合
- 神经向量检索预期可将 Recall 推到 70-80%+，尤其改善红楼梦半文言场景

## 项目结构

```
memtest/
├── README.md                # 英文文档（本文件）
├── README_CN.md             # 中文文档
├── GUIDE.md                 # 英文详细说明文档
├── GUIDE_CN.md              # 中文详细说明文档
├── API.md                   # 适配器接口 & 数据格式规范
├── generator.py             # 程序化测试数据生成器
├── knowledge_builder.py     # 语料 → 测试库构建器
├── runner.py                # 评测执行器 & MemoryAdapter 基类
├── _gen_and_test.py         # 一键生成 & 自测
├── sample_db_100.json       # 样例数据库（100 条记忆）
└── sample_queries.json      # 样例查询
```

## API 参考

详见 [API.md](API.md) 获取完整的适配器接口规范和数据格式。

### 最小适配器

只需实现三个方法：

```python
class MemoryAdapter:
    def reset(self):
        """每次评测前清空记忆库"""
        
    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆，附带标准元数据"""
        
    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """检索记忆，返回 [{"memory_id": str, "score": float, "content": str}, ...]"""
```

## 贡献

欢迎贡献，特别是：
- 新的测试数据生成器（特定领域语料）
- 流行记忆系统的适配器实现
- 评测维度扩展

## 许可证

MIT
