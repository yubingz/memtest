# v3 时序推理记忆提取 Prompt

## 目标
从语料中提取**有时间先后关系的连续事件链**，用于生成时序推理查询。

## 核心原则
1. **忠实原文**：提取的 content 必须是原文片段，不压缩不扩写
2. **时间先后**：至少 3 个事件构成时间链，标注相对关系
3. **按需提取**：只提有时间线索的事件，无关内容不提取

## 输入
语料文本片段

## 输出要求
JSON 数组，每条记录：

```json
{
  "chain_id": "TC001",
  "chain_position": 1,
  "content": "原文片段（忠实原文）",
  "person": ["人物1", "人物2"],
  "time_absolute": "1991-07-31 或 null",
  "time_relative": "eleventh birthday 或 null",
  "time_ref_id": "null（链内引用，由解析器填充）",
  "time_offset_days": "null（由解析器计算）",
  "location": "地点或 null",
  "event_type": "事件类型或 null",
  "source": "来源或 null"
}
```

## 提取规则

### 时间信息识别优先级
1. **有绝对时间** → 填 time_absolute，时间字段记原文
2. **只有相对时间**（如"次日""三个月后"）→ 填 time_relative，记相对关系原文
3. **两者都有** → 都填
4. **都没有** → 留 null

### 时间链构建
- 同一人物或相关人物的连续事件串成 chain_id
- 每组至少 3 个事件，按时间顺序排列（position 1 → 2 → 3...）
- 相对时间关系标注原文（如"次日""三个月后"），**不断链强补**

### 相对时间映射参考（仅辅助解析，不填入 content）
- "次日" → +1天
- "三天后" → +3天
- "一周后" → +7天
- "一个月后" → +30天
- "三个月后" → +90天
- "次年" → +365天

## 示例

### 输入语料
> 1980年春天，张无忌随父母回到中原。三年后，他父母在武当山上遭遇不幸。多年以后，张无忌在光明顶独战六大门派。

### 输出
```json
[
  {
    "chain_id": "TC001",
    "chain_position": 1,
    "content": "1980年春天，张无忌随父母回到中原。",
    "person": ["张无忌"],
    "time_absolute": "1980年春",
    "time_relative": null,
    "time_ref_id": null,
    "time_offset_days": null,
    "location": "中原",
    "event_type": "归来",
    "source": null
  },
  {
    "chain_id": "TC001",
    "chain_position": 2,
    "content": "三年后，他父母在武当山上遭遇不幸。",
    "person": ["张无忌父母"],
    "time_absolute": null,
    "time_relative": "三年后",
    "time_ref_id": null,
    "time_offset_days": null,
    "location": "武当山",
    "event_type": "不幸",
    "source": null
  },
  {
    "chain_id": "TC001",
    "chain_position": 3,
    "content": "多年以后，张无忌在光明顶独战六大门派。",
    "person": ["张无忌"],
    "time_absolute": null,
    "time_relative": "多年以后",
    "time_ref_id": null,
    "time_offset_days": null,
    "location": "光明顶",
    "event_type": "比武",
    "source": null
  }
]
```

## 注意事项
- **断链不补**：如果时间线索不足以形成完整时序链，标注断点，不硬凑
- **content 粒度**：每条 30-150 字，忠实原文表述
- **不归一化**：人物称呼按原文记（不把"张公子"改成"张无忌"）
- **无 alias 合并**：别名识别在 alias_resolver 阶段单独做，此处不处理
