# MemTest 数据库质量审查报告

**审查时间**: 2026-06-01  
**审查方法**: DeepSeek V3 大模型审查 + 程序化统计分析  
**审查范围**: sample_db.json, four_novels_benchmark.json, hp_benchmark_db.json

---

## 总览

| 数据库 | 记忆数 | 查询数 | LLM评分 | 状态 |
|--------|--------|--------|---------|------|
| sample_db.json (随机生成) | 156 | 46 | 4/10 | 🟡 需修复 |
| four_novels_benchmark.json (四大名著) | 11,794 | 360 | 5/10 | 🔴 需重建 |
| hp_benchmark_db.json (哈利波特) | 5,925 | 200 | 4/10 | 🔴 需重建 |

---

## 1. sample_db.json — 随机生成库

**问题等级**: 🟡 中等（可修复）

### 已发现问题

| 问题类型 | 数量 | 严重性 | 说明 |
|---------|------|--------|------|
| 动作-产品搭配不合理 | 8 | HIGH | "造成了海底电缆""实施了药品""进行了基金"等 |
| 语法不通（模板痕迹） | 3 | MEDIUM | "进行了基金"应为"购买了基金" |
| 城市地标不匹配 | 0 | — | 当前数据无此问题（LLM审查误报） |

### 典型问题
- `MEM000071`: 造成+海底电缆 @ 清真寺 — 动词和产品不搭配
- `MEM000091`: 进行了基金 — 语法错误
- `MEM000120`: 实施+药品 @ 维修站 — 三重不合理

### 根因
`generator.py` 的数据池中 `ACTIONS` 和 `PRODUCTS` 随机组合，无语义约束。

### 修复建议
- 在 generator.py 中为 ACTIONS 添加合法 PRODUCTS 约束（如"购买"→基金/保险/房产）
- 或改用 generate_ai_v2.py 生成（已验证质量好很多）

---

## 2. four_novels_benchmark.json — 四大名著语料库

**问题等级**: 🔴 严重（需重建部分数据）

### 已发现问题

| 问题类型 | 数量 | 严重性 | 说明 |
|---------|------|--------|------|
| 水浒传空泛内容 | 1,775/2,100 (84.5%) | CRITICAL | 内容仅为"第X回情节发展"，无实际文本 |
| person字段不匹配内容 | 6,174/11,794 (52.4%) | HIGH | person字段与内容中实际人物不一致 |
| 查询缺少expected_answer | 360/360 (100%) | HIGH | 无法评估检索准确性 |
| 查询缺少expected_memory_ids | 360/360 (100%) | HIGH | 无法定位ground truth记忆 |

### 分库详情

| 书名 | 记忆数 | person不匹配率 | 空泛内容 | 状态 |
|------|--------|---------------|---------|------|
| 三国演义 | 3,706 | 6.9% | 0 | 🟢 较好 |
| 西游记 | 2,138 | 80.2% | 0 | 🔴 person需修复 |
| 红楼梦 | 3,850 | 69.0% | 0 | 🔴 person需修复 |
| 水浒传 | 2,100 | 85.9% | 84.5% | 🔴 需重建 |

### 根因
- **水浒传**: knowledge_builder.py 对水浒传的文本提取失败，大量条目只保留了章节标记"第X回情节发展"
- **Person不匹配**: LLM提取时 person 和 content 分离提取，未做交叉校验。西游记尤其严重——raw text是原文片段，person字段按章节级人物列表分配，但实际片段中可能是其他角色
- **查询格式不统一**: 四大名著查询缺少 expected_answer 和 expected_memory_ids

### 典型问题
- `MEM013850`: person=玉帝, content=势镇汪洋...（花果山描写，玉帝不在场）
- `MEM013851`: person=观音, content=跳树攀枝...（猴群嬉戏，观音不在场）
- `MEM016005`: person=吴用, content=第1回情节发展（第1回吴用未出场）

---

## 3. hp_benchmark_db.json — 哈利波特英文语料库

**问题等级**: 🔴 严重（需重建）

### 已发现问题

| 问题类型 | 数量 | 严重性 | 说明 |
|---------|------|--------|------|
| person字段与内容不匹配 | 4,584/5,925 (77.4%) | CRITICAL | person字段随机分配，非基于内容 |
| 大小写拼写错误 | 3,158+614+263 | HIGH | "harry""hermione""horcruxe" |
| 自指模式 | 1,061 | MEDIUM | "Harry remembered that harry..." |
| 查询中Horcruxe拼写错误 | 13 | MEDIUM | expected_answer含typo |
| 部分查询缺少expected_memory_ids | 113/200 | MEDIUM | 57%查询无ground truth ID |

### 根因
- **Person随机分配**: 生成脚本从角色列表中随机选择 person，而非从 content 中提取实际主语
- **大小写**: 生成时未对专有名词做 capitalization 处理
- **自指模式**: 内容模板 "X remembered that X..." 中第二个X用了小写

### 典型问题
- `HPM000387`: person=Fawkes, content="Harry remembered that fawkes's tears..." — Fawkes是凤凰名，不是回忆主体
- `HPM005309`: "vodermorts"→Voldemort's, "nagini"→Nagini, "horcruxe"→Horcrux
- `HPM003787`: person=Fleur Delacour, content="Hermione noted that hermione granger solved..."

---

## 4. generate_ai_v2.py — 新版随机生成器

**状态**: 🟢 质量良好

- 12个真实人名（张伟/李明/王芳等）
- city-place 语义一致（北京/中关村创业大街, 上海/陆家嘴房产中心）
- 无模板语法痕迹
- 无动作-产品不合理搭配
- 100条记忆 + 30条查询

**建议**: 用此替代 generator.py 作为默认生成器

---

## 5. 跨库格式不一致

| 字段 | sample_db | four_novels | HP |
|------|-----------|-------------|-----|
| expected_memory_ids | ✅ 有 | ❌ 无 | ⚠️ 部分有(87/200) |
| expected_answer | ✅ 有 | ❌ 无 | ✅ 有 |
| acceptable_answers | ✅ 有 | ❌ 无 | ❌ 无 |
| is_negative | ✅ 有 | ❌ 无 | ❌ 无 |

查询格式严重不统一，四大名著库完全无法做自动化评测。

---

## 修复优先级

1. **🔴 P0 - 水浒传重建**: 1,775条空泛内容需重新提取，或直接删除
2. **🔴 P0 - HP库person修复**: 77%的person字段需重新提取（用LLM从content中提取主语）
3. **🔴 P0 - HP库拼写修复**: 批量修复 lowercase 和 typo
4. **🟠 P1 - 四大名著person修复**: 西游记/红楼梦person字段需重新提取
5. **🟠 P1 - 查询格式统一**: 为所有库补充 expected_memory_ids 和 expected_answer
6. **🟡 P2 - 随机库修复**: 修复8条动作-产品搭配 + 3条语法问题
7. **🟢 P3 - 默认生成器切换**: 从 generator.py 切换到 generate_ai_v2.py
