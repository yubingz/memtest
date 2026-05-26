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
                "event_product": "CLUSTER0001",
                "cluster_id": "CLUSTER0001",  # 整理类测试用
                "reasoning_chain": "CHAIN_0001",  # 推理链用
                "chain_position": 1,
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
    {"version_id": "v1", "style": "标准叙述", "content": "..."},
    {"version_id": "v2", "style": "详细描述", "content": "..."},
    {"version_id": "v3", "style": "口语化", "content": "..."}
  ],
  "tags": ["存储测试", "中等", "5d"],
  "cluster_id": null,
  "reasoning_chain": null,
  "chain_position": null,
  "decay": {"level": null, "access_count": 0}
}
```

### 查询条目（Query Entry）

```json
{
  "query_id": "Q0001",
  "query_text": "张伟在北京的购买记录",
  "query_type": "组合检索",
  "expected_memory_ids": ["MEM000001"],
  "expected_answer": "...",
  "difficulty": "中等",
  "search_depth": "中层"
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
