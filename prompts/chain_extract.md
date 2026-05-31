# Chain Extraction Prompt

从给定文本中提取事件因果序列，构建推理链。

## 任务

分析文本中的事件关系，识别因果链条、时间顺序、条件依赖等逻辑关系。

## 输出格式

每个链包含:
- `chain_id`: 链的唯一标识
- `chain_type`: 因果/时间/条件/对比/推导
- `events`: 按顺序排列的事件列表，每个事件包含:
  - `event_id`: 事件序号
  - `content`: 事件内容
  - `person`: 涉及人物
  - `location`: 发生地点
  - `time`: 发生时间
  - `relation_to_next`: 与下一个事件的关系（因果/时间/条件/对比/推导）

## 示例

输入: "张三在北京购买了股票，然后股价下跌，他损失惨重，决定起诉券商。"

输出:
```json
{
  "chain_id": "CHAIN_001",
  "chain_type": "因果",
  "events": [
    {"event_id": 1, "content": "购买股票", "person": "张三", "location": "北京", "time": "2024-01-01", "relation_to_next": "因果"},
    {"event_id": 2, "content": "股价下跌", "person": "张三", "location": "", "time": "2024-01-15", "relation_to_next": "因果"},
    {"event_id": 3, "content": "损失惨重", "person": "张三", "location": "", "time": "2024-01-15", "relation_to_next": "因果"},
    {"event_id": 4, "content": "起诉券商", "person": "张三", "location": "法院", "time": "2024-02-01", "relation_to_next": ""}
  ]
}
```

## 指令

请从以下文本中提取所有推理链，以JSON数组格式返回:

{text}
