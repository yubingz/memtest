# MemTest API 接口规范

## MemoryAdapter — 被测系统接口

任何待评测的AI记忆系统，只需实现以下3个方法：

```python
class MemoryAdapter:
    def reset(self):
        """清空记忆库，准备下一轮评测"""
        pass

    def store(self, memory_text: str, metadata: dict):
        """
        存入一条记忆。

        Args:
            memory_text: 记忆文本(version.content)
            metadata: {
                "memory_id": "MEM000001",
                "category": "存储正确性测试集",
                "difficulty": "中等",
                "time_absolute": "2026-01-15 14:30:00",
                "time_relative": "5天前",
                "location_city": "北京",
                "location_place": "星巴克",
                "person_name": "张伟",
                "person_identity": "项目经理",
                "event_type": "交易",
                "event_action": "购买",
                "event_product": "茅台",  # 产品名示例
                "cluster_id": "CLUSTER0001",  # 整理类测试用
                "reasoning_chain": "CHAIN_0001",  # 推理链用
                "chain_position": 1,
                "chain_relation": "因果",  # 时序/因果/对比/包含/推导
                "chain_prev": "MEM000001",  # 前一条记忆ID
                "chain_next": "MEM000003",  # 下一条记忆ID
                "weight": 1.0,
                "decay_level": "高频记忆",  # 遗忘类测试用
                "access_count": 50,
            }
        """
        pass

    def search(self, query: str, top_k: int = 20) -> list:
        """
        检索记忆。

        Args:
            query: 查询文本
            top_k: 最大返回数

        Returns:
            [{"memory_id": "MEM000001", "score": 0.95, "content": "..."}, ...]
            按 score 降序排列
        """
        pass
```

## 测试数据格式

### 记忆条目（Memory Entry）

```json
{
  "memory_id": "MEM000001",
  "category": "存储正确性测试集",
  "difficulty": "中等",
  "weight": 1.0,
  "time": {
    "absolute": "2026-01-15 14:30:00",
    "relative": "5天前",
    "fuzzy": "上个月",
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
    {"version_id": "v1", "style": "客观叙述", "content": "..."},
    {"version_id": "v2", "style": "主观视角", "content": "..."},
    {"version_id": "v3", "style": "第三方转述", "content": "..."}
  ],
  "tags": ["存储测试", "中等", "5d"],
  "cluster_id": null,
  "reasoning_chain": null,
  "chain_position": null,
  "chain_relation": null,
  "chain_prev": null,
  "chain_next": null,
  "decay": {"level": null, "access_count": 0}
}
```

### 查询条目（Query Entry）

```json
{
  "query_id": "Q0001",
  "query_text": "张伟在北京的购买记录",
  "query_type": "组合检索",
  "test_dimension": "组合检索",
  "expected_memory_ids": ["MEM000001"],
  "expected_answer": "张伟在北京星巴克购买了茅台，数量100",
  "expected_time": "2026-05-26 14:30:00",
  "difficulty": "中等",
  "search_depth": "中层",
  "is_negative": false
}
```

## 评测维度

| 维度 | 说明 | 核心指标 |
|------|------|----------|
| 存储完整性 | 所有记忆是否成功写入 | integrity = stored / total |
| 检索 Precision/Recall | 查询是否命中正确记忆 | by_type + overall |
| 整理聚类 | 同 cluster 记忆是否检索相关 | cluster_accuracy |
| 遗忘合理性 | 高频记忆保留率 > 低频 | forgetting_ratio_valid |
| 逻辑推理 | 组合查询链推理准确率 | logic_accuracy / chain_accuracy |
| 深度检索 | 按语义距离分层召回 | near / mid / far |

## 时间链与逻辑关系

### 时间作为逻辑关系的一种

`chain_relation` 字段标记链的逻辑关系类型：
- `时序`：事件按时间先后排列
- `因果`：A导致B，B引发C
- `对比`：A做X，B相反做Y
- `包含`：A包含B，B涵盖C
- `推导`：从观察到结论的递进

### 时间排序策略

| 场景 | 排序依据 | 相对时间处理 |
|------|---------|------------|
| 有绝对时间 | 按 `time.absolute` 时间戳排序 | 保留在字段中，但不干预排序 |
| 无绝对时间，有相对时间 | 按相对偏移排序 | 直接用于排序 |
| 两者都有 | 绝对时间排序为主 | 保留，矛盾由被测记忆系统自行判断 |

当同一chain内的记忆同时包含绝对时间和相对时间词（如"次日"、"一个月后"），以绝对时间为准建立排序，相对时间信息保留供被测系统判断一致性。评测工具不负责检测矛盾。

### 链连接字段

- `chain_prev`：前一条记忆在链中的 `memory_id`
- `chain_next`：下一条记忆在链中的 `memory_id`
- `chain_position`：当前记忆在链中的位置（1-based）

时序链按 `time.absolute` 排序后重新计算 `chain_position`，确保位置与时间顺序一致。

## 查询评测维度（test_dimension）

每个查询带有 `test_dimension` 字段，标明该查询测试的具体能力维度：

| 维度 | 比例 | 说明 |
|------|------|------|
| 精确检索 | 20% | 单维度精确匹配（人物/地点/事件） |
| 组合检索 | 15% | 多维度组合查询 |
| 时序推理 | 12% | 时间先后链推理 |
| 因果推理 | 12% | 因果关系链推理 |
| 对比推理 | 8% | 对比关系识别 |
| 包含推理 | 8% | 层级包含关系 |
| 推导推理 | 8% | 逻辑推导链 |
| 聚类检索 | 7% | 主题聚类检索 |
| 跨版本 | 5% | 同一记忆不同表述匹配 |
| 负样本 | 20% | 不相关查询过滤 |

生成查询时按上述比例平衡分配，确保评测覆盖全面。链式推理查询引用链中相邻记忆（如"在A之后发生了什么"），释放多跳推理评测价值。
