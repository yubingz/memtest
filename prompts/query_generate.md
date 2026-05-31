# 提示词：查询生成（从记忆生成检索查询）

## 任务
给定一条记忆，生成多种查询方式，测试记忆系统能否从不同角度召回该记忆。

## 输入格式
```json
{
  "memory_id": "MEM000001",
  "person": "张伟",
  "identity": "项目经理",
  "location": "北京 星巴克",
  "event": "购买 茅台 100股",
  "time": "2026-01-15",
  "content": "..."
}
```

## 输出格式
```json
{
  "queries": [
    {"query_type": "人物检索", "query_text": "张伟最近做了什么", "difficulty": "简单"},
    {"query_type": "地点检索", "query_text": "在星巴克发生过什么", "difficulty": "简单"},
    {"query_type": "时间检索", "query_text": "1月15号有什么记录", "difficulty": "中等"},
    {"query_type": "事件检索", "query_text": "关于茅台购买的事件", "difficulty": "中等"},
    {"query_type": "组合检索", "query_text": "张伟在北京购买茅台", "difficulty": "困难"}
  ]
}
```

## 查询类型与难度定义

| 类型 | 简单 | 中等 | 困难 |
|------|------|------|------|
| 人物检索 | 只提人名 | 人名+时间范围 | 人名+地点+时间+事件特征 |
| 地点检索 | 只提地点 | 地点+时间 | 地点+人物+事件 |
| 时间检索 | 精确日期 | 模糊时间（上周/上个月） | 时间段+人物+地点 |
| 事件检索 | 只提事件 | 事件+人物 | 事件+地点+结果 |
| 组合检索 | 2个维度 | 3个维度 | 4+维度，含推理 |

## Few-shot 示例

### 示例1：购买场景
输入：张伟，项目经理，北京 星巴克，购买 茅台 100股，2026-01-15

输出：
```json
{
  "queries": [
    {"query_type": "人物检索", "query_text": "张伟最近有什么动作", "difficulty": "简单"},
    {"query_type": "人物检索", "query_text": "项目经理张伟最近在北京忙什么", "difficulty": "中等"},
    {"query_type": "地点检索", "query_text": "星巴克那边有什么记录", "difficulty": "简单"},
    {"query_type": "地点检索", "query_text": "1月中旬在北京星巴克发生的事", "difficulty": "中等"},
    {"query_type": "时间检索", "query_text": "1月15号有什么记录", "difficulty": "简单"},
    {"query_type": "时间检索", "query_text": "上个月中旬有什么重要的事", "difficulty": "中等"},
    {"query_type": "事件检索", "query_text": "关于茅台购买的相关信息", "difficulty": "简单"},
    {"query_type": "组合检索", "query_text": "张伟在北京购买茅台是什么时候", "difficulty": "中等"},
    {"query_type": "组合检索", "query_text": "1月15号项目经理张伟在星巴克购买了什么", "difficulty": "困难"}
  ]
}
```

### 示例2：会议场景
输入：李明，CTO，上海 会议室A，召开 技术评审会，2026-03-10

输出：
```json
{
  "queries": [
    {"query_type": "人物检索", "query_text": "李明最近有什么安排", "difficulty": "简单"},
    {"query_type": "地点检索", "query_text": "会议室A最近有什么活动", "difficulty": "简单"},
    {"query_type": "时间检索", "query_text": "3月10号有什么会议", "difficulty": "简单"},
    {"query_type": "事件检索", "query_text": "技术评审会的相关信息", "difficulty": "简单"},
    {"query_type": "组合检索", "query_text": "李明在上海召开技术评审会是什么时候", "difficulty": "中等"},
    {"query_type": "组合检索", "query_text": "CTO李明3月10号在会议室A主持了什么", "difficulty": "困难"}
  ]
}
```

## 规则
1. 查询文本必须自然，像用户真实提问，不要直接复制记忆原文
2. 每种查询类型至少1条，最多2条（除非特别丰富）
3. 简单/中等/困难分布建议 3:4:2
4. 组合检索必须让多个条件同时满足才能命中
5. 中文语境，口语化表达
6. 不要编造输入中没有的信息
