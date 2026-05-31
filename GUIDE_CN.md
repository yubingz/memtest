# MemTest 详细说明文档

[English](GUIDE.md)

---

## 目录

1. [概述](#1-概述)
2. [架构](#2-架构)
3. [测试数据格式](#3-测试数据格式)
4. [评测维度深入解读](#4-评测维度深入解读)
5. [数据生成](#5-数据生成)
6. [知识构建器](#6-知识构建器)
7. [运行评测](#7-运行评测)
8. [解读结果](#8-解读结果)
9. [扩展 MemTest](#9-扩展-memtest)

---

## 1. 概述

MemTest 是一个与框架无关的 AI 记忆系统评测工具。它回答一个核心问题：**你的记忆系统到底好不好用？**

传统评测方法把测试数据和后端系统耦合在一起。MemTest 通过适配器模式解耦——你只需实现 3 个方法（`reset`、`store`、`search`），MemTest 负责剩下的：数据生成、查询执行、评分、报告。

### 核心原则

| 原则 | 含义 |
|------|------|
| **框架无关** | 不依赖任何特定记忆系统。适配器是唯一的集成点。 |
| **零依赖** | 纯 Python 标准库 + JSON，无需 pip install。 |
| **数据逻辑分离** | 测试数据（JSON）和评测逻辑（runner）互相独立，可以单独替换。 |
| **可复现** | `random.seed(42)` 确保相同输入始终生成相同数据。 |

---

## 2. 架构

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  generator.py   │────>│  test_db.json│<────│knowledge_builder│
│  (程序化合成)    │     │  (测试数据)   │     │  (语料驱动)      │
└─────────────────┘     └──────┬───────┘     └─────────────────┘
                               │
                               │  (测试数据 — 解耦)
                               ▼
                     ┌──────────────────┐
                     │  你的评测框架     │  ←  接任意评测框架
                     │  (runner.py 或   │     或自己实现
                     │   自行实现)      │
                     └────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
           ┌──────────────┐   ┌──────────────┐
           │ 你的适配器    │   │JsonMemoryAdpt│
           │ (真实系统)    │   │ (内置，仅     │
           │              │   │  关键词匹配)  │
           └──────────────┘   └──────────────┘
```

> **注意**：`runner.py` 已从核心包剥离，作为可选评测工具保留。核心定位是**纯数据生成工具**，评测由用户自行选择或实现框架。见 [README.md](README.md) 快速开始。

- **generator.py**：程序化生成测试数据，控制随机性
- **knowledge_builder.py**：从真实文本语料通过 LLM 提取事实，再结构化为相同格式
- **runner.py**：评测引擎。遍历测试数据、调用适配器方法、计算评分
- **你的适配器**：你唯一需要写的代码——对记忆系统的薄封装

---

## 3. 测试数据格式

### 记忆条目

测试数据库中的每条记忆遵循以下结构：

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

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `memory_id` | string | 唯一标识，格式 `MEM######` |
| `category` | string | 测试维度：`存储正确性测试集`、`检索功能测试集`、`记忆整理测试集`、`遗忘功能测试集`、`逻辑推理测试集`、`长期记忆深度检索测试集` |
| `difficulty` | string | `简单` / `中等` / `困难`，影响权重和元数据密度 |
| `weight` | float | 0.5（简单）/ 1.0（中等）/ 1.5（困难），用于加权评分 |
| `time.absolute` | string | 精确时间戳 `YYYY-MM-DD HH:MM:SS` |
| `time.relative` | string | 相对时间：`刚刚`、`昨天`、`3天前`、`2周前`、`6个月前` |
| `time.fuzzy` | string | 模糊时间：`今天`、`前几天`、`上个月`、`很久以前` |
| `time.timestamp` | int | Unix 时间戳 |
| `location.city` | string | 城市名（100+ 个中国城市） |
| `location.place` | string | 场所名（咖啡馆、商场、办公室等） |
| `location.landmark` | string | 区域描述（CBD、科技园等） |
| `person.name` | string | 主要人物姓名 |
| `person.identity` | string | 职务/角色 |
| `person.partner_name` | string | 次要人物姓名 |
| `person.relation` | string | 关系：同事/上级/下属/朋友/闺蜜... |
| `event.type` | string | 交易/会议/决策/日常/技术/情感 |
| `event.action` | string | 具体动作（购买/召开/批准/出差/开发/庆祝...） |
| `event.product` | string | 涉及的产品或实体 |
| `versions` | array | 同一记忆的 3 种风格版本（见下文） |
| `tags` | array | 可搜索的标签 |
| `cluster_id` | string? | 聚类测试的组 ID（如 `CLUSTER0001`） |
| `reasoning_chain` | string? | 推理链 ID |
| `chain_position` | int? | 在推理链中的位置（1-6） |
| `chain_relation` | string? | 逻辑关系类型：`时序` / `因果` / `对比` / `包含` / `推导`。时间被视为逻辑关系的一种——存在绝对时间时按时间戳排序；仅有相对时间时按偏移排序；两者皆有时以绝对时间为准，相对时间保留供被测系统判断一致性 |
| `chain_prev` | string? | 链中前一条记忆的 ID |
| `chain_next` | string? | 链中下一条记忆的 ID |
| `decay.level` | string? | `高频记忆` / `中等频率` / `低频记忆` / `偶发事件` |
| `decay.access_count` | int | 模拟访问频率（0-100） |
| `depth.layers` | int? | 概念层级深度（3-7），仅深度检索 |
| `depth.associations` | int? | 关联数量（2-5），仅深度检索 |
| `depth.semantic_distance` | string? | `near` / `mid` / `far`，仅深度检索 |

#### 三版本设计

每条记忆以 3 种风格渲染，测试**改写鲁棒性**：

| 版本 | 风格 | 示例 |
|------|------|------|
| v1 | 标准叙述 | "张伟在北京星巴克购买了茅台，数量100" |
| v2 | 详细描述 | "2026年01月15日 14时30分，张伟（项目经理）在北京市星巴克进行购买操作，涉及茅台，交易数量100股，单价1800元" |
| v3 | 口语化 | "在北京出差的张伟，15号那天购买了茅台，搞了100份" |

3 个版本都通过 `adapter.store()` 存储。一个鲁棒的检索系统应该无论查询风格接近哪个版本，都能返回正确的记忆。

### 查询条目

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `query_id` | string | 查询唯一标识 |
| `query_text` | string | 实际查询文本 |
| `query_type` | string | `时间检索` / `地点检索` / `人物检索` / `事件检索` / `组合检索` / `组合推理` |
| `test_dimension` | string | 评测维度标签：`精确检索` / `组合检索` / `时序推理` / `因果推理` / `对比推理` / `包含推理` / `推导推理` / `聚类检索` / `跨版本` / `负样本`。每个查询都带标签，评测结果可直接映射到具体能力短板 |
| `expected_memory_ids` | array | 标准答案——应该被召回的记忆 ID |
| `expected_answer` | string | 正确答案文本 |
| `expected_time` | string? | 用于时间感知验证的绝对时间戳（负样本查询为 null） |
| `difficulty` | string | `简单` / `中等` / `困难` |
| `search_depth` | string | `浅层` / `中层` / `深层` |
| `is_negative` | bool | `true` 表示负样本查询（不存在正确答案） |

---

## 4. 评测维度深入解读

### 4.1 存储完整性

**测什么**：系统能否完整、无丢失地写入所有数据？

**怎么做**：
1. `adapter.reset()` 清空记忆库
2. 对每条记忆，通过 `adapter.store(version["content"], metadata)` 存入所有 3 个版本
3. 统计 `store()` 调用总次数 vs 期望次数
4. **理想值**：`integrity = 300%`（3 个版本 × N 条记忆）

**为什么 3 个版本很重要**：某些系统可能会静默丢弃"重复"或"近似重复"的内容。如果同一事件的两个版本太相似，朴素的去重机制可能丢弃其中一个。这个测试能发现这个问题。

**评分**：
```
integrity = stored_count / total_memories
```
- `1.0` = 每条记忆只存了 1 个版本（差）
- `3.0` = 所有 3 个版本都存了（理想）

### 4.2 检索 Precision/Recall

**测什么**：给定一条查询，系统能否在 Top-K 结果中返回正确的记忆？

**怎么做**：
1. 对每条查询调用 `adapter.search(query_text, top_k=20)`
2. 将返回的 `memory_id` 与 `expected_memory_ids` 对比
3. 按查询类型和整体计算 Precision 和 Recall

**查询类型及设计意图**：

| 查询类型 | 模板 | 设计意图 |
|---------|------|---------|
| **人物检索** | "{name}最近做了什么" | 测试系统能否按人名查找记忆。基准难度。 |
| **地点检索** | "在{city}{place}发生过什么" | 测试空间检索。注意：查询使用地名，非坐标。 |
| **事件检索** | "关于{product}的事件有哪些" | 测试事件/产品匹配。查询可能使用与存储记忆不同的措辞。 |
| **时间检索** | "查找{relative}发生的事情" | **关键测试**：查询使用相对/模糊时间（"2周前"），但记忆存的是绝对时间戳。系统必须做时间推理。 |
| **组合检索** | "{name}在{city}的{action}记录" | 多维交叉约束，系统必须同时满足所有条件。 |
| **组合推理** | "请梳理{name}的完整经历脉络" | 链式推理，期望返回多条记忆构成完整叙事。 |

**时间检索详解**：

这是架构意义最大的查询类型。考虑：

```
存储的记忆：time.absolute = "2026-01-15 14:30:00"
查询：      "查找5天前发生的事情"
```

系统必须：
1. 将"5天前"解析为日期范围
2. 与存储的绝对时间戳对比
3. 返回该范围内的记忆

如果系统只做时间字段的字符串匹配，必定失败："5天前"不会出现在"2026-01-15 14:30:00"中。

4 种时间表示的设计目的是测试不同层次的时间理解：
- `absolute` → 精确匹配（简单）
- `relative` → 时间算术（中等）
- `fuzzy` → 近似匹配（困难）
- `timestamp` → 数值范围查询

**评分**：
```
Precision = correct_hits / (count × top_k)
Recall    = correct_hits / total_expected
```

### 4.3 整理聚类

**测什么**：语义相关的记忆是否被归为一组？检索到一条记忆时，系统是否也能浮现其"邻居"？

**怎么做**：
1. "记忆整理测试集"类别中的记忆被分配 `cluster_id`
2. 每个聚类约 10 条记忆，共享事件类型
3. 对每个聚类成员，用 `"{person_name} {event_product}"` 查询
4. 检查 Top-10 结果中是否包含同聚类的其他成员
5. **cluster_accuracy** = 命中同组成员的查询数 / 总查询数

**为什么重要**：真实使用中，用户常需要"更多类似内容"——不只一条特定记忆，而是相关上下文。聚类良好的系统能提供更丰富、更有用的回答。

**评分**：
```
cluster_accuracy = correct / total
```

### 4.4 遗忘合理性

**测什么**：系统是否优先保留重要（高频访问）的记忆，而非不重要的（低频访问）记忆？

**怎么做**：
1. 记忆标注 4 种衰减级别：
   - `高频记忆`（access_count 高）
   - `中等频率`（access_count 中）
   - `低频记忆`（access_count 低）
   - `偶发事件`（access_count 极低）
2. 对高频组和低频组中的每条记忆，用记忆原文（v1）搜索
3. 测量**保留率**：系统是否还能在 Top-10 中找到这条记忆？
4. **forgetting_ratio_valid** = `高频保留率 > 低频保留率`

**核心洞察**：我们不是测试系统是否遗忘（所有有限容量的系统都必须遗忘），而是测试遗忘是否有*方向性*——重要的东西应该最后被遗忘。

**评分**：
```
forgetting_ratio_valid = (高频保留率 > 低频保留率)
```
这是一个布尔值：系统的优先级要么对了，要么没对。

### 4.5 逻辑推理

**测什么**：系统能否处理需要跨记忆关联信息的多跳查询？

**怎么做**：
- **逻辑查询**（`事件检索` + `组合检索`）：单跳但多约束。系统必须同时匹配多个字段（人物+地点+时间）。
- **链式查询**（`组合推理`）：多跳。期望返回推理链中的多条记忆。例如，"梳理张伟的完整经历"应返回所有张伟出现的记忆。

**评分**：
```
logic_accuracy  = logic_queries_hit / logic_queries_total
chain_accuracy  = chain_queries_hit / chain_queries_total
```

### 4.6 深度检索

**测什么**：随着时间距离和语义距离增大，召回率如何衰减？

**怎么做**：
1. 此类别中所有记忆来自 1-2 年前（非近期）
2. 每条记忆标注：
   - `depth.layers`（3-7）：距离常识多少个概念跳
   - `depth.associations`（2-5）：连接了多少条其他记忆
   - `depth.semantic_distance`：`near` / `mid` / `far`
3. 用记忆原文（v1）搜索
4. 测量每个距离层级的召回率

**为什么要和常规检索分开**：常规检索偏向近期、高频记忆。深度检索专门针对长尾——老的、罕见的、语义距离远的信息，而好的系统应该仍然能找到它们。

**评分**：
```
near_recall = near_hits / near_total
mid_recall  = mid_hits / mid_total
far_recall  = far_hits / far_total
```

### 4.7 时序链推理

**测什么**：系统能否跨时间有序链进行推理？当事件按时间序列链接时，系统能否回答"之后发生了什么？"或"什么导致了这？"

**怎么做**：
1. 时序链（`chain_relation = "时序"`）通过按 `time.absolute` 对同一人物的记忆排序来构建
2. 每条链包含 3-6 条记忆，通过 `chain_prev` 和 `chain_next` 链接相邻条目
3. 查询引用链邻居："在[前一事件]之后，发生了什么？"
4. 系统必须召回序列中的正确下一条记忆

**时间处理策略**：

| 场景 | 排序依据 | 相对时间处理 |
|------|---------|------------|
| 有绝对时间 | `time.absolute` 时间戳 | 保留但不干预排序 |
| 无绝对时间，有相对时间 | 相对偏移（如"次日"=1天） | 直接用于排序 |
| 两者都有 | 绝对时间为准 | 保留，矛盾由被测记忆系统自行判断 |
| 两者都无 | 原始顺序或 `chain_position` | 无法做时间推断 |

**为什么重要**：人类记忆检索常遵循时间序列（"然后..."）。无法遍历时间有序链的系统会在叙事重建上失败。

**评分**：
```
temporal_chain_accuracy = 正确下一条记忆 / 总时序链查询数
```

### 4.8 查询维度平衡

**测什么**：不直接测什么——这是一个元设计原则，确保测试套件按比例覆盖所有能力维度。

**设计理由**：一个测试套件如果90%是单跳检索查询、只有10%是链推理查询，就无法诊断记忆系统是否失败在多跳推理上。平衡确保每个维度都有足够的样本获得统计显著性。

**目标分布**：

| 维度 | 目标比例 | 查询示例 |
|------|---------|---------|
| 精确检索 | 20% | "张伟做了什么"、"在北京发生了什么" |
| 组合检索 | 15% | "张伟在北京的购买记录" |
| 时序推理 | 12% | "在投资字节跳动之后，发生了什么？" |
| 因果推理 | 12% | "为什么项目失败了？" |
| 对比推理 | 8% | "A和B的做法有什么不同？" |
| 包含推理 | 8% | "这个计划包含哪些具体措施？" |
| 推导推理 | 8% | "从观察到结论的推导过程" |
| 聚类检索 | 7% | "关于这个主题的所有记录" |
| 跨版本 | 5% | 用不同风格描述同一事件 |
| 负样本 | 20% | "张伟在火星购买茅台" |

**实现方式**：每个查询携带 `test_dimension` 字段。生成器使用 `_allocate_queries_by_dimension()` 按目标比例分配，将记忆映射到最相关的维度并比例采样。

**链式感知查询生成**：链相关维度（时序/因果/对比/包含/推导）的查询引用链中相邻记忆，而非孤立单条记忆。这将有链数据转化为实际的多跳测试用例，而非闲置浪费。

---

## 5. 数据生成

### generator.py — 程序化合成

**用法**：
```bash
python generator.py              # 100 条样例（快速）
python generator.py --full       # 10,000 条全量
python generator.py --size 500   # 自定义规模
```

**工作原理**：

1. **基础生成**：对每条记忆，从数据池随机选取：
   - 100+ 城市，50+ 场所，30+ 地标
   - 100+ 中文姓名，24 种职业，10 种关系
   - 6 种事件类型，每种 3-7 个具体动作
   - 17 种产品（股票、商品、加密货币）

2. **时间分布**：记忆覆盖 6 个时间区间：
   | 区间 | 范围 | 示例相对时间 |
   |------|------|-------------|
   | 24h | 0-1 天前 | "刚刚"、"昨天" |
   | 7d | 1-7 天前 | "3天前"、"1周前" |
   | 30d | 7-30 天前 | "2周前"、"3周前" |
   | 90d | 30-90 天前 | "2个月前"、"3个月前" |
   | 1y | 90-365 天前 | "6个月前"、"10个月前" |
   | fuzzy | 365-730 天前 | "去年"、"很久以前" |

3. **类别分布**：6 大类各约 17%

4. **难度分布**：简单 30%、中等 40%、困难 30%

5. **查询生成**：对每条选中的记忆，随机选查询类型并填入模板：
   ```python
   QUERY_TEMPLATES = {
       "时间检索": lambda m: [
           f"查找{m['time']['relative']}发生的事情",
           f"查询{m['time']['fuzzy']}在{m['location']['city']}的相关记录",
       ],
       # ... 5 种类型，各 2 个模板
   }
   ```

6. **可复现**：`random.seed(42)` — 相同运行始终产生相同数据

### 链生成细节

**逻辑链**（`gen_reasoning`）：生成 5 种推理链，每种 3-6 跳：
- **因果**：A 投资 → B 导致 → C 产生结果
- **时序**：按 `time.absolute` 排序事件，查询如"在X之后发生了什么？"
- **对比**：A 做正面动作，B 做相反动作
- **包含**：整体 → 部分 → 细节层级
- **推导**：观察 → 分析 → 推断 → 结论

**时序链后处理**（`_build_temporal_chains`）：
1. 按人物名分组所有记忆
2. 过滤出含 `time.absolute` 的记忆
3. 按时间戳升序排序
4. 分配 `chain_relation = "时序"`，重新计算 `chain_position`，链接 `chain_prev`/`chain_next`
5. 每条时序链最多 6 条记忆

**带维度平衡的查询生成**：查询不是随机生成——按 `test_dimension` 目标比例分配。链相关维度生成多跳查询，引用链中相邻记忆，将链数据转化为实际推理测试用例。

### 输出格式

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

## 6. 知识构建器

### knowledge_builder.py — 语料驱动生成

与程序化生成器不同，知识构建器从**真实文本**创建测试数据，通过 LLM 提取事实。

**用法**：
```bash
python knowledge_builder.py ./my_books/ output.json
python knowledge_builder.py ./my_books/ output.json --merge  # 增量追加
```

**流水线**：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 1. 事实  │───>│ 2. 字段  │───>│ 3. 构建  │───>│ 4. 查询  │───>│ 5. LLM   │
│    提取   │    │    分类   │    │    记忆   │    │    生成   │    │    缓存   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     LLM             LLM           规则            规则            LLM
```

**阶段 1 — 事实提取**：LLM 读取每个文本文件，提取结构化事实：
- `content`：简洁事实陈述（15-40 字）
- `person`：人物姓名
- `location`：实体地理位置
- `time`：具体时间（年份/日期）
- `dynasty`：朝代/时期（如"东晋"、"贞观年间"）
- `event_type`：事件类型标签

**阶段 2 — 字段分类**：LLM 校验提取出的字段：
- "东晋"是地点还是朝代？（应该是朝代，不是地点）
- "丞相府"是地点还是概念？（边界情况——分类为概念）
- 拆分复合时间表达式（"383年，东晋" → time="383年", dynasty="东晋"）

**阶段 3 — 构建记忆**：基于规则的结构化，带混合时间排序：
- 分配从 MEM010000 起始的 `MEM######` ID
- 创建 3 个版本（标准叙述/详细描述/口语化）
- 构建推理链，使用混合时间排序：
  - 若 LLM 提供 `chain_id`：按 chain_id 分组，按 `chain_position` 或混合时间排序
  - 若无 `chain_id`：按人物分组（≥3 条记忆），有 `time.absolute` 时按时间排序
  - 时间排序策略：绝对时间为准；相对时间词（如"次日"、"三个月后"）保留供被测系统判断一致性
  - 链类型（`chain_relation`）自动标记：有绝对时间时为 `时序`，否则为 `因果`/`关联`

**阶段 4 — 查询生成**：与程序化生成器相同的模板，但应用于真实提取数据

**阶段 5 — LLM 预解析缓存**：将每条查询预解析为结构化搜索参数（人物、地点、时间、朝代），供支持结构化查询的系统使用

**依赖**：DeepSeek API key，放在 `.env` 文件中（切勿提交；从 `.env.example` 复制）：

```bash
cp .env.example .env
# 编辑 .env 并填入你的 key
```

```
DEEPSEEK_API_KEY=sk-xxx
```

> ⚠️ **安全提示**：`.env` 已加入 `.gitignore`，但提交前务必用 `git status` 再次检查。如意外提交，请立即在服务商平台撤销该密钥。

**增量模式**（`--merge`）：只处理新文件，追加到已有数据库

---

## 7. 运行评测

### 基本用法

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

# 打印摘要
from runner import summary
print(summary(report))
```

### `suite.run(db)` 执行过程

1. **重置**：`adapter.reset()` — 清空所有已有数据
2. **存储阶段**：对每条记忆，存入所有 3 个版本。元数据从嵌套结构展平。
3. **评测阶段**：6 大维度依次评测：
   - 存储完整性（无搜索调用）
   - 检索（每条查询 1 次搜索）
   - 整理聚类（每个聚类最多 3 次搜索）
   - 遗忘（每条记忆 1 次搜索，最多 40 条记忆）
   - 推理（每条查询 1 次搜索）
   - 深度检索（每条记忆 1 次搜索，最多 30 条记忆）
4. **报告**：返回包含所有维度评分的字典

### 内置适配器：JsonMemoryAdapter

用于快速验证测试数据本身（不是真正的评测）：

```python
from runner import JsonMemoryAdapter, MemoryTestSuite, load_test_db

adapter = JsonMemoryAdapter()  # 内存中的关键词匹配器
suite = MemoryTestSuite(adapter)
report = suite.run(load_test_db("sample_db_100.json"))
```

此适配器只做简单关键词匹配——适合验证测试数据结构是否合法，但**不是**有意义的记忆系统评测。

### 一键自测

```bash
python runner.py  # 如果缺少样例数据会自动生成，然后运行评测
```

---

## 8. 解读结果

### 报告结构

```python
{
  "storage": {
    "stored_count": 300,
    "total": 100,
    "integrity": 3.0      # 300% = 所有 3 个版本都存了
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

### 各维度评判标准

| 维度 | 好 | 一般 | 差 |
|------|---|------|---|
| 存储完整性 | ≥2.5（大部分版本存了） | 1.0-2.5（部分版本丢失） | <1.0（数据丢失） |
| 检索 Recall | >0.7 | 0.3-0.7 | <0.3 |
| 聚类准确率 | >0.5 | 0.2-0.5 | <0.2 |
| 遗忘合理性 | `true` | `true` 但余量很小 | `false`（方向反了） |
| 链式推理 | >0.5 | 0.2-0.5 | <0.2 |
| 深层远距召回 | >0.3 | 0.1-0.3 | <0.1 |

### 常见模式

- **检索高，深度低**：系统对近期数据有效，但遗忘了旧信息。考虑添加持久化向量索引。
- **整体 Recall 高，时间检索低**：系统不理解时间表达式。需要时间归一化。
- **`forgetting_ratio_valid = false`**：系统没有访问频率意识。低频记忆和高频记忆一样容易被返回。
- **深度检索近高远低**：系统只能找到语义接近的匹配。需要更好的嵌入模型。

---

## 9. 扩展 MemTest

### 添加新查询类型

1. 在 `generator.py` 的 `QUERY_TEMPLATES` 中添加模板
2. 在 `runner.py` 的对应 `_eval_*` 方法中添加评测逻辑

### 添加新评测维度

1. 在 `MemoryGenerator` 中添加新类别（如 `gen_temporal_reasoning`）
2. 在 `MemoryTestSuite` 中添加 `_eval_*` 方法
3. 在 `run()` 方法的报告字典中包含

### 创建领域专用生成器

用领域专用数据池替换 `generator.py` 中的通用数据池：

```python
# 示例：医疗记录
CITIES = ["心内科", "骨科", "神经外科", ...]
EVENT_TYPES = {"诊断": ["确诊", "排除", "待查"], "治疗": ["手术", "用药", "复查"], ...}
PRODUCTS = ["阿司匹林", "布洛芬", "CT扫描", ...]
```

### 接入你的记忆系统

实现 3 方法适配器：

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

## 附录：数据池规模

| 数据池 | 规模 | 说明 |
|--------|------|------|
| 城市 | 100 | 一至四线城市 |
| 场所 | 42 | 咖啡馆、商场、地标、办公室 |
| 地标 | 28 | 区域描述 |
| 姓名 | 100 | 常见中文姓名 |
| 职业 | 24 | 从 CTO 到咨询师 |
| 关系 | 10 | 同事、上级、朋友等 |
| 事件类型 | 6 | 交易/会议/决策/日常/技术/情感 |
| 动作 | 23 | 每类 3-7 个 |
| 产品 | 17 | 股票、商品、加密货币 |
