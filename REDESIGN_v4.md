# MemTest v4 重构设计

## 核心认知

MemTest 是**纯数据生成工具**。它的价值不在评测逻辑（runner可选），而在产出一套标准化的测试数据，让任何记忆系统拿去都能跑。

v2 的 schema 已经覆盖了6大评测维度。v3 的问题不是 schema 需要重设计，而是**数据生成质量差**。

v3 试图用复杂 pipeline 修补生成质量，结果越补越碎。正确做法是回到 v2 schema，修数据生成。

## 设计原则

### 1. 查询不是创造，是推导

查询 = 记忆属性 × 模板。不需要LLM生成查询文本。

| 维度 | 需要的属性 | 查询模板 |
|------|-----------|---------|
| 人物检索 | person | "{人名}做了什么？" |
| 地点检索 | location | "在{地点}发生了什么？" |
| 时间检索 | time_absolute + time_relative | "{相对时间}发生了什么？" |
| 事件检索 | event_type + product | "关于{产品}的事件有哪些？" |
| 组合检索 | person + location | "{人名}在{地点}的记录" |
| 别名查询 | content中的别名证据 | "{别名}是谁/是什么？" |
| 时序推理 | chain_prev/chain_next | "在{前事件}之后发生了什么？" |
| 因果推理 | chain_relation="因果" | "为什么{结果事件}？" |
| 对比推理 | chain_relation="对比" | "{人A}和{人B}的做法有什么不同？" |
| 负样本 | 不存在的实体 | "赵钱孙做了什么？" |

### 2. 提取是唯一的LLM环节

从语料提取结构化记忆，这一步需要LLM。但只做一次，不按类型分别提取。

一条记忆同时包含：人物、时间、地点、事件、别名线索。按类型分别提取 = 同一段文本调5次LLM，还容易不一致。

### 3. 回归v2 schema

v2 的6大维度：存储完整性、检索、聚类、遗忘、推理、深度检索。

v2 的数据结构已经支持所有维度：
- 3个versions → 存储完整性
- person/location/time/event + 查询 → 检索
- cluster_id → 聚类
- decay.level + access_count → 遗忘
- reasoning_chain + chain_prev/chain_next → 推理
- depth.layers/semantic_distance → 深度检索

v3 把这些都砍了，只留content+person+time+location。这不是简化，是退化。

### 4. Content-only 存储不变

被测系统只收到 memory_id + content。元数据是出题用的，不泄题。

## Pipeline 设计

```
语料
  │
  ▼
┌──────────────────────┐
│ 1. 提取记忆（LLM）    │  ← 唯一的LLM步骤
│    一次调用提取完整    │     输入：语料段落
│    结构化记忆         │     输出：{content, person, time, location, event, aliases...}
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. 构建关系（规则）    │  ← 纯规则，无LLM
│    - 别名等价组        │     从content中的别名模式检测
│    - 时序链           │     按person分组+时间排序
│    - 因果链           │     从content中的因果词检测
│    - 聚类             │     按event_type/主题分组
│    - 遗忘衰减         │     随机分配decay level
│    - 深度标注         │     基于记忆间距离标注
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. 生成查询（模板）    │  ← 纯模板，无LLM
│    遍历记忆的属性，    │     有时间→时间查询
│    按属性填模板        │     有人名→人物查询
│                      │     有链→链式查询
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 4. 生成3版本（LLM）   │  ← 可选LLM步骤
│    客观/主观/转述     │     也可以用规则模板
└──────────┬───────────┘
           │
           ▼
       test_db.json
```

## 与v3的关键区别

| | v3 | v4 |
|---|---|---|
| 提取方式 | 按类型分别提取 | 一次提取完整记忆 |
| 查询生成 | LLM生成query_text | 模板填充，确定性 |
| Schema | 砍到content+person+time | 回归v2完整schema |
| 别名检测 | 复杂正则+LLM混合 | 规则检测 + 作为记忆属性 |
| 关系构建 | 无 | chain/cluster/decay/depth |
| 可复现性 | 依赖LLM随机性 | 确定性（模板+规则+seed） |
| 评测维度覆盖 | 1.5个（检索+部分别名） | 6个完整 |

## 实现路径

### Step 1: 修复提取（替代pipeline.py）

写一个新的 `extractor.py`：
- 输入：语料目录
- 输出：结构化记忆列表（v2格式）
- 一次LLM调用提取所有字段
- fallback：规则提取（不需要LLM也能跑）

### Step 2: 修复关系构建（替代alias_resolver.py + time_resolver.py）

写一个新的 `relation_builder.py`：
- 输入：结构化记忆列表
- 输出：添加了chain/cluster/decay/depth的记忆列表
- 纯规则，无LLM
- 别名：从content中用正则检测别名模式，作为记忆属性标注
- 时序：按person分组，有time_absolute的按时间排序建链
- 聚类：按event_type或共同person分组
- 遗忘/深度：随机分配（seed=42保证可复现）

### Step 3: 修复查询生成（替代v3的LLM查询）

写一个新的 `query_builder.py`：
- 输入：带关系的记忆列表
- 输出：查询列表
- 纯模板，确定性
- 每个维度按比例生成查询
- 负样本：构造不存在的实体名

### Step 4: 组装

把 Step 1-3 串起来，输出标准 v2 格式的 test_db.json。

### Step 5: 验证

用现有的 quality_check.py + runner.py 验证输出。
用红楼梦语料跑，确认6个维度都有数据。
