# v3 因果链推理记忆提取 Prompt

## 目标
从语料中提取**有因果连接的事件链**，用于生成因果推理查询。

## 核心原则
1. **因果必须有文本依据**：文本中必须出现因果连接词（因为、所以、导致、引发、于是、因此、结果等）
2. **忠实原文**：content 是原文片段，不压缩不扩写
3. **6 跳链优先**：每条链 6 个节点（A导致B → B导致C → ... → F）

## 输入
语料文本片段

## 输出要求
JSON 数组，每条记录：

```json
{
  "chain_id": "CC001",
  "chain_position": 1,
  "content": "原文片段（忠实原文）",
  "person": ["人物列表"],
  "causal_connector": "导致/因为/于是/因此/结果/引发",
  "time_absolute": "绝对时间或 null",
  "time_relative": "相对时间或 null",
  "time_ref_id": null,
  "time_offset_days": null,
  "location": "地点或 null",
  "event_type": "事件类型或 null",
  "source": "来源或 null"
}
```

## 提取规则

### 因果连接词（必须有）
- 因为...所以...
- ...导致...
- ...引发...
- ...于是...
- ...因此...
- ...结果...
- ...紧接着...

### 链构建
- 每条链 6 跳（position 1-6）
- A导致B，B导致C，C导致D，D导致E，E导致F
- 因果关系必须在文本中明确表述
- 链内事件可以有不同人物，但必须有逻辑连接

### 示例

### 输入语料
> 因为王允使用了连环计，貂蝉成功离间了董卓和吕布。董卓因此被杀，吕布占领了长安。随后...

### 输出
```json
[
  {"chain_id": "CC001", "chain_position": 1, "content": "王允使用了连环计", "person": ["王允"], "causal_connector": "因为", "time_absolute": null, "time_relative": null, "time_ref_id": null, "time_offset_days": null, "location": null, "event_type": "谋划", "source": null},
  {"chain_id": "CC001", "chain_position": 2, "content": "貂蝉成功离间了董卓和吕布", "person": ["貂蝉", "董卓", "吕布"], "causal_connector": "因此", "time_absolute": null, "time_relative": null, "time_ref_id": null, "time_offset_days": null, "location": null, "event_type": "离间", "source": null},
  {"chain_id": "CC001", "chain_position": 3, "content": "董卓因此被杀", "person": ["董卓"], "causal_connector": "结果", "time_absolute": null, "time_relative": null, "time_ref_id": null, "time_offset_days": null, "location": null, "event_type": "死亡", "source": null},
  {"chain_id": "CC001", "chain_position": 4, "content": "吕布占领了长安", "person": ["吕布"], "causal_connector": "因此", "time_absolute": null, "time_relative": null, "time_ref_id": null, "time_offset_days": null, "location": "长安", "event_type": "占领", "source": null}
]
```

## 注意事项
- **6 跳链不足时**：如果语料中因果链不足 6 跳，提取现有链（至少 3 跳），标注 `chain_length`
- **断链不补**：因果链有断裂点时，记录断点，不硬连
- **只认文本证据**：必须有因果连接词，无则不构成因果链
