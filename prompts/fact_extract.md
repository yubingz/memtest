# 提示词：从文本提取结构化事实

## 任务
从给定文本中提取关键事实，每个事实是一个包含 who/where/when/what 的 JSON 对象。

## 输入格式
一段自由文本（小说片段、新闻文章、历史记录等）。支持中文和英文混合文本。

## 输出格式
```json
{
  "facts": [
    {
      "content": "事件摘要（1-2句话）",
      "person": "主要人物",
      "location": "地点/场所",
      "time": "时间描述（原文或标准化）",
      "event_type": "事件类型（交易/会议/发现/冲突/转折/情感等）",
      "action": "具体动作",
      "object": "涉及对象/物品",
      "context": "额外背景信息",
      "chain_id": "如果文本中存在因果关系链，标注链编号（如CHAIN_001）"
    }
  ]
}
```

## 提取原则
1. **原子化**：每个事实只包含一个独立事件，不要合并多个事件
2. **完整性**：尽可能包含 who/where/when/what 四要素
3. **客观性**：只提取文本中明确陈述的内容，不要推断
4. **去重**：如果同一事件被多次提及，只提取一次
5. **粒度**：太琐碎的细节（如"他喝了一口水"）可以忽略，但关键动作必须保留
6. **链式识别**：如果文本中有因果连接词（"因为""所以""导致""引发""随后""接着""之后""因此""于是"），标注 chain_id

## 多语言支持
- 中文文本：提取中文人名、地名、时间
- 英文文本：提取英文人名、地名、时间（如 "Harry Potter" / "London" / "1991"）
- 混合文本：分别提取中英文实体，保持原文语言

## Few-shot 示例

### 示例1：中文商务场景
输入：2023年10月15日，李明在北京中关村的一家咖啡馆与王芳会面，讨论了关于人工智能项目的合作细节。李明是这个项目的技术负责人，王芳来自投资部门。

输出：
```json
{
  "facts": [
    {
      "content": "李明与王芳在北京中关村咖啡馆会面，讨论AI项目合作",
      "person": "李明、王芳",
      "location": "北京中关村咖啡馆",
      "time": "2023-10-15",
      "event_type": "会议",
      "action": "会面、讨论",
      "object": "人工智能项目合作",
      "context": "李明是技术负责人，王芳来自投资部门",
      "chain_id": ""
    }
  ]
}
```

### 示例2：英文场景（Harry Potter）
输入：On July 31, 1991, Hagrid visited Harry Potter on the island Hut and told him he was a wizard. Harry then traveled to Diagon Alley with Hagrid to buy school supplies.

输出：
```json
{
  "facts": [
    {
      "content": "Hagrid visited Harry Potter on the island Hut and told him he was a wizard",
      "person": "Hagrid, Harry Potter",
      "location": "island Hut",
      "time": "July 31, 1991",
      "event_type": "visit",
      "action": "visited, told",
      "object": "wizard identity",
      "context": "",
      "chain_id": "CHAIN_HP_001"
    },
    {
      "content": "Harry traveled to Diagon Alley with Hagrid to buy school supplies",
      "person": "Harry Potter, Hagrid",
      "location": "Diagon Alley",
      "time": "1991-07-31",
      "event_type": "shopping",
      "action": "traveled, buy",
      "object": "school supplies",
      "context": "after learning he was a wizard",
      "chain_id": "CHAIN_HP_001"
    }
  ]
}
```

### 示例3：因果链场景（中文）
输入：2023年10月15日，李明在北京中关村咖啡馆与王芳会面，讨论了AI项目合作。由于市场变化，10月20日王芳决定追加投资500万。随后11月1日，李明团队完成了第一版原型。

输出：
```json
{
  "facts": [
    {
      "content": "李明与王芳在北京中关村咖啡馆会面，讨论AI项目合作",
      "person": "李明、王芳",
      "location": "北京中关村咖啡馆",
      "time": "2023-10-15",
      "event_type": "会议",
      "action": "会面、讨论",
      "object": "AI项目合作",
      "context": "",
      "chain_id": "CHAIN_001"
    },
    {
      "content": "王芳因市场变化追加投资500万",
      "person": "王芳",
      "location": "",
      "time": "2023-10-20",
      "event_type": "交易",
      "action": "追加投资",
      "object": "500万",
      "context": "市场变化导致",
      "chain_id": "CHAIN_001"
    },
    {
      "content": "李明团队完成第一版原型",
      "person": "李明团队",
      "location": "",
      "time": "2023-11-01",
      "event_type": "技术",
      "action": "完成",
      "object": "第一版原型",
      "context": "追加投资后的结果",
      "chain_id": "CHAIN_001"
    }
  ]
}
```

## 注意
- 如果文本中没有明确时间，time 字段可为空
- 如果涉及多个人物，用顿号或逗号分隔
- 历史文本中的朝代可放入 context
- 因果连接词标记："因为""所以""导致""引发""随后""接着""之后""因此""于是"
- 英文文本中因果词："because" "so" "led to" "resulted in" "then" "after" "therefore"
- 中文输出
- 如果文本中没有链式关系，所有 chain_id 留空即可