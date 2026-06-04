# MemTest — AI 记忆系统评测数据库生成工具

输入任意文本语料 → 输出结构化记忆 + ground-truth 查询（ID 匹配答案），生成标准化、可复现的测试数据库。

**[English](README.md)**

## 为什么需要 MemTest？

当前记忆系统评测都是临时方案：手工写查询、"感觉对了"就过了、私有基准无法横向对比。MemTest 提供**确定性、可复现的测试数据库**，ground truth 受控。

核心思路：**评测检索，不评测生成**。答案是记忆 ID 集合（不是文本），所以指标是精确匹配、确定性的，可以在任意记忆系统之间对比。

## 架构 (v4)

```
memtest/
├── pipeline_v4_auto.py      # 自动化 Pipeline（质量门控 + 自动修复 + 迭代）
├── pipeline_v4.py            # 手动一条龙 Pipeline
├── extractor.py              # LLM 记忆提取（唯一使用 LLM 的步骤）
├── relation_builder.py       # 别名组 + 推理链构建（纯规则）
├── query_builder.py          # 查询生成（纯模板，确定性）
├── alias_resolver.py         # 人物别名解析
├── time_resolver.py          # 时间表达式归一化
├── runner.py                  # 评测执行器（接入被测记忆系统）
├── quality_check.py          # 数据质量校验（10 项自动检查）
├── schema.py                  # 数据格式定义
├── llm_interface.py          # LLM 抽象层（DeepSeek / OpenAI 兼容）
│
├── test_corpus*/              # 输入：纯文本语料
│   ├── test_corpus3/xiyouji.md
│   ├── test_corpus4/sgyy_extended.md
│   ├── test_corpus5/hongloumeng_extended.md
│   └── test_corpus6/          # 四大名著：三国演义、红楼梦、水浒传、西游记
│
└── output/                    # 生成的测试数据库
    ├── v4_full.json           # 5736 记忆, 700 查询 (四大名著) ⭐ 最新
    ├── four_novels.json       # 131 记忆, 1157 查询 (4 小说)
```

## 快速开始

### 1. 安装与配置

```bash
git clone https://github.com/yubingz/memtest.git
cd memtest
cp .env.example .env
# 编辑 .env，添加 DEEPSEEK_API_KEY=...（仅记忆提取步骤使用）
```

### 2. 一条命令生成

```bash
# 手动 Pipeline
python pipeline_v4.py ./my_corpus/ -o test_db.json --name "My Test Database"

# 自动 Pipeline（质量门控 + 自动修复 + 迭代）
python pipeline_v4_auto.py ./my_corpus/ -o test_db.json --max-iterations 3
```

流程：`提取记忆 → 构建关系 → 生成查询 → 组装 → 校验`

只有提取步骤使用 LLM，查询生成是**确定性的**（纯模板，无 LLM）。

### 3. 自定义语料

创建目录，放入 `.md` 或 `.txt` 文件：

```
my_corpus/
├── chapter1.md
├── chapter2.md
└── ...
```

MemTest 自动提取结构化记忆、解析别名、构建推理链、生成 6 维度查询。

## 评测维度

| 维度 | 数量 | 说明 |
|------|------|------|
| **精确检索** | 100 | 人物/地点/时间/事件/别名检索 |
| **组合检索** | 100 | 多属性组合查询（人物+地点、人物+时间等） |
| **时序推理** | 100 | 先后时序推理链 |
| **负样本** | 100 | 无匹配记忆的查询（应返回空） |
| **跨版本/别名** | 100 | 别名等价查询（如"刘皇叔" = "刘备" = "玄德"） |
| **组合推理** | 100 | 多条件跨维度推理 |
| **总计** | **700** | 6 维度，全覆盖 |

*数据来自 `v4_full.json`（5736 记忆，4 小说）*

### 查询类型

| 类型 | 模板数 | 示例 |
|------|--------|------|
| 人物检索 | 8 | "刘备的经历有哪些？" |
| 地点检索 | 6 | "在涿县发生了什么？" |
| 时间检索 | 6 | "早年有什么事件？" |
| 事件检索 | 7 | "关于玉的事件有哪些？" |
| 别名查询 | 5 | "刘皇叔是谁？" |
| 组合检索 | 12+ | "刘备在涿县的记录" |
| 组合推理 | auto | "...之前发生了什么？" |

## 数据格式

### 记忆条目

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

### 查询条目

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

### ID 匹配评测

答案是**记忆 ID 集合**，不是文本。这意味着：
- **精确匹配**：无文本相似度歧义
- **确定性**：同样数据库 → 同样结果，永远可复现
- **可比性**：任意记忆系统都能对标同一 ground truth

## 预构建数据库

| 数据库 | 记忆数 | 查询数 | 来源 | Pipeline |
|--------|--------|--------|------|----------|
| `v4_full.json` | **5736** | **700** | 三国演义 + 红楼梦 + 水浒传 + 西游记 | v4 (最新) |
| `four_novels.json` | 131 | 1157 | 三国演义 + 红楼梦 + 西游记 + 金庸5部 | v3 |
| `hongloumeng.json` | 23 | 155 | 红楼梦 | v3 |
| `sgyy_full.json` | 17 | 173 | 三国演义 | v3 |

## 设计原则

1. **只有提取用 LLM** — 查询生成是纯模板 × 属性，确定且可复现
2. **ID 匹配答案** — 无文本相似度歧义，精确匹配评测
3. **自选语料** — 输入任意文本，Pipeline 自动提取事实并生成查询
4. **原文保存** — 记忆按原文存储，不做变换
5. **6 评测维度** — 覆盖精确、组合、时序推理、负样本和别名等价
6. **别名感知** — 人物别名（如孙悟空=齐天大圣=美猴王）解析为等价组测试

## License

MIT
