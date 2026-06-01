# v3 查询生成 Prompt

## 目标
基于已提取的记忆条目，生成查询（query）和期望答案（expected_answer）。

## 核心原则
1. **用 LLM 的理解能力生成答案**：知道别名等价、时间顺序、逻辑关系
2. **expected_answer 要精确**：答案必须准确反映语料内容
3. **expected_memory_ids 要正确**：指向正确的记忆条目

## 输入
已提取的记忆条目（JSON 数组，每条含 content、person、time、location 等）

## 输出要求
JSON 数组，每条查询：

```json
{
  "query_id": "Q0001",
  "query_text": "查询文本（自然语言问句）",
  "query_type": "时序推理 | 因果推理 | 别名查询 | 事实检索 | 对比推理 | 负样本",
  "test_dimension": "评测维度描述",
  "expected_memory_ids": ["MEM001", "MEM002"],
  "expected_answer": "基于理解的正确答案",
  "difficulty": "easy | medium | hard",
  "is_negative": false
}
```

## 按类型生成规则

### 1. 时序推理
- **问法示例**："A 和 B 谁先发生？""A 之后发生了什么？"
- **expected_answer**：按时间顺序排列的事实
- **expected_memory_ids**：涉及的全部记忆
- **难度**：easy=只问顺序，medium=问中间事件，hard=问完整链

### 2. 因果推理
- **问法示例**："A 导致了什么？""为什么会有 B？"
- **expected_answer**：因果链的完整描述
- **expected_memory_ids**：因果链上的全部记忆
- **难度**：easy=单跳因果，medium=两跳，hard=完整链

### 3. 别名查询
- **问法示例**："林妹妹是谁？""颦儿指谁？"
- **expected_answer**："林妹妹（颦儿）就是林黛玉"
- **expected_memory_ids**：包含别名证据的那条记忆
- **关键**：expected_answer 中的别名等价关系，必须在语料原文中有证据
- **难度**：easy=直接别名，medium=间接别名，hard=组合别名

### 4. 事实检索
- **问法示例**："A 在 B 做了什么？""C 地发生了什么事？"
- **expected_answer**：直接答案
- **expected_memory_ids**：对应的记忆
- **难度**：easy=单要素，medium=双要素，hard=多要素组合

### 5. 对比推理
- **问法示例**："A 和 B 有什么不同？""为什么 A 和 B 的选择不同？"
- **expected_answer**：对比描述（谁做了什么 vs 谁做了什么）
- **expected_memory_ids**：对比对的两条记忆
- **难度**：easy=直接对比，medium=原因对比，hard=深层原因对比

### 6. 负样本
- **问法示例**："X 在 Y 做了什么？"（X 或 Y 在语料中不存在）
- **expected_memory_ids**：[]（空列表）
- **expected_answer**：空字符串
- **is_negative**：true
- **生成方式**：基于已有记忆，随机替换人物名或地点名为不存在的名称

## 示例（时序推理）

### 输入记忆
```json
[
  {"memory_id": "MEM001", "content": "1980年春天，张无忌随父母回到中原。", "person": ["张无忌"]},
  {"memory_id": "MEM002", "content": "三年后，他父母在武当山上遭遇不幸。", "person": ["张无忌父母"]},
  {"memory_id": "MEM003", "content": "多年以后，张无忌在光明顶独战六大门派。", "person": ["张无忌"]}
]
```

### 输出查询
```json
[
  {
    "query_id": "Q0001",
    "query_text": "张无忌是什么时候回到中原的？之后又发生了什么？",
    "query_type": "时序推理",
    "test_dimension": "时间线追踪",
    "expected_memory_ids": ["MEM001", "MEM002", "MEM003"],
    "expected_answer": "1980年春天，张无忌随父母回到中原；三年后父母在武当山遭遇不幸；多年以后张无忌在光明顶独战六大门派。",
    "difficulty": "medium",
    "is_negative": false
  }
]
```

## 示例（别名查询）

### 输入记忆
```json
[
  {"memory_id": "MEM010", "content": "林黛玉，大名颦儿，林妹妹是贾府上下对她的昵称。", "person": ["林黛玉"]}
]
```

### 输出查询
```json
[
  {
    "query_id": "Q0020",
    "query_text": "林妹妹指的是谁？",
    "query_type": "别名查询",
    "test_dimension": "别名等价识别",
    "expected_memory_ids": ["MEM010"],
    "expected_answer": "林妹妹就是林黛玉，颦儿也是她的别号。",
    "difficulty": "easy",
    "is_negative": false
  },
  {
    "query_id": "Q0021",
    "query_text": "颦儿和林妹妹是同一个人吗？",
    "query_type": "别名查询",
    "test_dimension": "别名等价识别",
    "expected_memory_ids": ["MEM010"],
    "expected_answer": "是的，颦儿和林妹妹都是林黛玉的别称。",
    "difficulty": "medium",
    "is_negative": false
  }
]
```

## 注意事项
- **expected_answer 必须基于 content**：答案内容必须能从记忆条目的 content 中找到依据
- **别名字面等价不够**：expected_answer 说"A就是B"时，必须有语料原文支撑
- **时序答案要按时间排序**：expected_answer 中的事件要按时间顺序排列
- **负样本要有挑战性**：不存在的名称要看起来合理（避免明显的假名如"火星人"）
