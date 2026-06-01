# v3 查询校验 Prompt（LLM 交叉验证）

## 目标
用 LLM 交叉验证 expected_answer 是否正确，确保答案与语料内容一致。

## 核心原则
1. **答案与 content 一致性**：expected_answer 是否与 expected_memory_ids 的 content 一致
2. **别名等价证据**：别名查询的等价关系是否有语料原文证据
3. **时序排序正确性**：时序查询的 expected_answer 是否按正确时间顺序排列
4. **逻辑推理支撑**：因果/对比查询的链条是否在语料中有支撑

## 输入
单条查询 + 对应记忆条目的 content

## 校验项目

### 1. 答案与内容一致性
检查 expected_answer 中的事实是否能在 content 中找到依据。
- 如果 expected_answer 包含 content 没有的信息 → 标记为"答案超出原文"
- 如果 expected_answer 与 content 矛盾 → 标记为"答案与原文矛盾"

### 2. 别名等价证据检查
对于别名查询，检查：
- expected_answer 中的别名等价（A就是B）是否有语料原文证据
- 如果 evidence 不存在 → 标记为"别名缺乏语料证据"

### 3. 时序排序检查
对于时序推理查询，检查：
- expected_answer 中的事件是否按正确时间顺序排列
- 如果顺序错误 → 标记为"时序排序错误"

### 4. 逻辑链完整性
对于因果/对比查询，检查：
- expected_answer 中的逻辑关系（因为→所以）是否在 content 中有支撑
- 如果逻辑跳跃太大 → 标记为"逻辑链断裂"

## 输出格式
```json
{
  "query_id": "Q0001",
  "checks": [
    {"item": "内容一致性", "passed": true, "detail": "答案与原文一致"},
    {"item": "别名等价证据", "passed": true, "detail": "等价关系有语料证据"},
    {"item": "时序排序", "passed": true, "detail": "时间顺序正确"},
    {"item": "逻辑链完整性", "passed": false, "detail": "第3跳到第4跳缺少文本支撑"}
  ],
  "overall": "通过 | 不通过 | 需人工确认",
  "issues": ["问题1", "问题2"]
}
```

## 示例

### 输入
```json
{
  "query_id": "Q0020",
  "query_type": "别名查询",
  "query_text": "林妹妹指的是谁？",
  "expected_answer": "林妹妹就是林黛玉，颦儿也是她的别称。",
  "memories": [
    {"memory_id": "MEM010", "content": "林黛玉，大名颦儿，林妹妹是贾府上下对她的昵称。"}
  ]
}
```

### 输出
```json
{
  "query_id": "Q0020",
  "checks": [
    {"item": "内容一致性", "passed": true, "detail": "答案与原文一致"},
    {"item": "别名等价证据", "passed": true, "detail": "等价关系有原文证据：'林妹妹是贾府上下对她的昵称'"},
    {"item": "时序排序", "passed": true, "detail": "N/A（别名查询）"},
    {"item": "逻辑链完整性", "passed": true, "detail": "N/A（别名查询）"}
  ],
  "overall": "通过",
  "issues": []
}
```
