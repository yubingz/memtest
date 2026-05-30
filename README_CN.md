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
| `hp_benchmark_db.json` | 哈利波特系列（英文） | 1,626 条记忆，133 条查询（清洗自 5,925 条） | 仓库自带 |
| `four_novels_benchmark.json` | 中国四大名著（中文） | 11,794 条记忆，230 条查询，155 条推理链 | 仓库自带 |
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
python knowledge_builder.py /path/to/corpus                   # 自动检测语言
python knowledge_builder.py /path/to/corpus --lang en     # 指定英文
python knowledge_builder.py /path/to/corpus --lang zh     # 指定中文
```

已用中国四大名著验证（4,058 条记忆，187 条查询（清洗自 21,793 条））。详见[评测结果](#评测结果)。

### 哈利波特评测库 (`hp_benchmark_db.json`)

基于哈利波特系列7本书构建的英文记忆检索评测库，采用手写核心事件+程序化扩展方式生成。

**统计（清洗后）：**
- 1,626 条记忆，覆盖7本书（清洗自 5,925 条 — 去除 626 条完全重复、641 条跨视角重复、裁剪主人公刷屏）
- 133 条查询，8种类型（平衡自 200 条 — 每人物上限 15 条）
- 3 条六跳逻辑链，追踪主要剧情线（预言链、魂器链、斯内普/邓布利多链）
- 难度分布：简单 52% / 中等 42% / 困难 6%

**为什么需要清洗：** 原始 5,925 条记忆中，"Harry" 出现在 81.7% 的记忆里，同一事件被5+角色重复描述。关键词检索几乎随机（BM25 P@20 仅 4.8%）。清洗后 BM25 Hit@20 从 62.5% 提升到 76.5%。

**记忆字段：** `memory_id`, `content`, `person`, `location`, `time`, `era`, `event_type`, `book`, `house`, `tags`, `difficulty`

**使用：**
```python
from runner import MemoryTestSuite, MemoryAdapter, load_test_db

db = load_test_db("hp_benchmark_db.json")
suite = MemoryTestSuite(MyAdapter())
report = suite.run(db)
```

**质量保证：** 零模板生成内容，零跨书错误，所有记忆 ≥20 词，每条事件符合原著。

**BM25 基线结果（清洗后数据库）：**

| 指标 | 未清洗 (5,925条) | 清洗后 (1,626条) |
|------|:---------------:|:---------------:|
| Precision@20 | 4.8% | 5.7% |
| Hit Rate@20 | 62.5% | 76.5% |
| MRR@20 | 0.261 | 0.332 |

未清洗数据库的低分是主人公霸屏和跨视角重复的假象，不是检索本身的问题。清洗后的评测基线更公平。


### 语料准备方法

知识构建器需要 `.md` 文件作为输入。以下是常见来源的准备方法：

**从小说/书籍准备（推荐，提取效果最好）：**

1. **获取文本** — 公共领域来源：
   - 中文：[古登堡计划中文区](https://www.gutenberg.org/browse/languages/zh)、[维基文库](https://zh.wikisource.org/)、[中国哲学书电子化计划](https://ctext.org/)
   - 英文：[Project Gutenberg](https://www.gutenberg.org/)、[Wikisource](https://en.wikisource.org/)、[Standard Ebooks](https://standardebooks.org/)
   - 版权作品需自行获取授权文本
2. **按章节拆分为独立 .md 文件**：
   ```bash
   # 中文小说按"第X回"拆分：
   python -c "
   import re
   with open('novel.txt', encoding='utf-8') as f: text = f.read()
   chapters = re.split(r'(?=第.{1,3}[回章节])', text)
   for i, ch in enumerate(chapters):
       if len(ch.strip()) >= 500:
           with open(f'chapter_{i:03d}.md', 'w', encoding='utf-8') as out:
               out.write(ch.strip())
   "
   # 英文小说按"Chapter X"拆分：
   python -c "
   import re
   with open('novel.txt', encoding='utf-8') as f: text = f.read()
   chapters = re.split(r'(?=Chapter \\d+)', text, flags=re.IGNORECASE)
   for i, ch in enumerate(chapters):
       if len(ch.strip()) >= 500:
           with open(f'chapter_{i:03d}.md', 'w', encoding='utf-8') as out:
               out.write(ch.strip())
   "
   ```
3. **按目录组织** — 目录名会作为分类标签：
   ```
   my_corpus/
   ├── book_one/
   │   ├── chapter_001.md
   │   └── ...
   └── book_two/
       ├── chapter_001.md
       └── ...
   ```

**从其他格式转换：**

| 来源 | 转换方法 |
|------|---------|
| `.txt` | 直接重命名为 `.md`，或 `cp novel.txt novel.md` |
| `.pdf` | `pandoc book.pdf -t markdown -o book.md`，再按章节拆分 |
| `.epub` | `pandoc book.epub -t markdown -o book.md`，再按章节拆分 |
| `.docx` | `pandoc book.docx -t markdown -o book.md`，再按章节拆分 |
| 网页文章 | 浏览器扩展或 `pandoc -f html -t markdown URL -o article.md` |

**注意事项：**
- 每个文件必须 **≥ 500 字符**（过短会跳过）
- 每个文件只处理 **前 3000 字符**——长章节需拆分为小段
- 最佳效果：每文件 **500–3000 字符**
- 叙事类文本（小说、传记）提取效果最好

**快速测试：**
```bash
echo "任意文本内容（至少500字符）..." > test_article.md
mkdir test_corpus && mv test_article.md test_corpus/
python knowledge_builder.py test_corpus/ test_output.json --lang zh
```


## 评测结果

以下结果基于我们的 **NOESIS-II** 记忆系统，使用四大名著数据集（11,794 条去重记忆，577 条查询）进行评测。TF-IDF 和 ST 结果使用 500 条随机采样；LLM 重排结果使用 100 条随机采样，均为 Top-20 检索。

**评测方法**：检索结果中只要包含目标实体（人物、地点、事件、朝代），即判定为正确。例如"黛玉和宝玉聊天"对"林黛玉"和"贾宝玉"的查询都算命中。

| 方法 | Precision@20 | Recall@20 | MRR@20 |
|------|:----------:|:---------:|:------:|
| jieba + SQL LIKE | ~2% | ~2% | N/A |
| TF-IDF + jieba + Cosine | 49.6% | 83.2% | 0.862 |
| Sentence-Transformers (MiniLM) | 9.1% | 12.4% | 0.201 |
| **LLM 重排 (TF-IDF → LLM)** | **87.0%** | **84.9%** | **0.923** |

**按查询类型对比（LLM 重排 vs TF-IDF）**：

| 查询类型 | TF-IDF P@20 | LLM P@20 | TF-IDF R@20 | LLM R@20 |
|---------|:----------:|:--------:|:----------:|:--------:|
| 人物 | 67.0% | 90.5% | 90.3% | 87.6% |
| 地点 | 39.8% | 92.8% | 76.6% | 88.2% |
| 事件 | 41.9% | 80.9% | 82.6% | 80.8% |
| 时间 | 60.0% | 93.8% | 92.5% | 100.0% |
| 组合 | 51.0% | 70.0% | 51.0% | 70.0% |

**按小说对比（LLM 重排 vs TF-IDF）**：

| 小说 | TF-IDF P@20 | LLM P@20 | TF-IDF R@20 | LLM R@20 |
|-----|:----------:|:--------:|:----------:|:--------:|
| 水浒传 | 60.0% | 90.3% | 86.3% | 87.1% |
| 西游记 | 52.8% | 98.9% | 78.0% | 98.3% |
| 三国演义 | 42.0% | 84.6% | 81.1% | 82.1% |
| 红楼梦 | 62.5% | 85.0% | 79.2% | 85.0% |

**方法说明**：
- **jieba + SQL LIKE**：用 jieba 分词后多 token OR LIKE 查询 NOESIS-II 的 SQLite，取 Top-20
- **TF-IDF + jieba + Cosine**：结构化内容（人物+事件+地点+朝代+文本）经 jieba 分词，TF-IDF 矩阵余弦相似度，取 Top-20
- **Sentence-Transformers**：`paraphrase-multilingual-MiniLM-L12-v2`（384维）编码同样结构化内容，余弦相似度，取 Top-20
- **LLM 重排 (TF-IDF → LLM)**：两阶段流水线——先用 TF-IDF 检索 Top-50 候选，再由大语言模型（通过 Coze session API）按相关性重排，从重排结果中取 Top-20

**核心发现**：
1. **关键词匹配几乎不可用** — jieba + SQL LIKE 的 2% 召回率说明它对语义检索基本无效
2. **TF-IDF + jieba 是强基线** — 83.2% 的召回率证明，正确的分词+词频匹配对实体类查询效果很好
3. **MiniLM 在中文古典文本上表现差** — 多语言释义模型（9.1% 精确率）无法精准区分实体
4. **LLM 重排效果显著** — 精确率从 49.6% 几乎翻倍到 87.0%，召回率持平（83.2% → 84.9%），证明大模型能有效识别候选集中的相关记忆
5. **两阶段检索（检索器+重排器）是实际最优解** — TF-IDF 的高召回 + LLM 的高精确 = 最佳综合表现（MRR 0.923）

## 项目结构

```
memtest/
├── README.md                # 英文文档
├── README_CN.md             # 中文文档
├── GUIDE.md                 # 英文详细说明文档
├── GUIDE_CN.md              # 中文详细说明文档
├── API.md                   # 适配器接口 & 数据格式规范
├── generator.py             # 程序化测试数据生成器
├── knowledge_builder.py     # 语料 → 测试库构建器（含 --clean 清洗模式）
├── runner.py                # 评测执行器 & MemoryAdapter 基类
├── _gen_and_test.py         # 一键生成 & 自测
├── benchmark/               # 清洗后的评测数据库
│   ├── hp_benchmark_db.json       # 哈利波特（英文，1,626 条记忆）
│   ├── four_novels_benchmark.json # 四大名著（中文，11,794 条记忆，155 条推理链）
│   └── tianlongbabu_db.json       # 天龙八部（中文，48 条记忆）
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
