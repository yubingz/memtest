# MemTest 领域配置

MemTest 支持多领域 benchmark 生成。通过选择不同领域，生成对应场景的记忆和查询。

## 使用方式

```python
from generator import build_database

# 历史领域
db = build_database(100, domain="history")

# 科幻领域
db = build_database(100, domain="scifi")

# 商务领域
db = build_database(100, domain="business")

# 日常领域（默认）
db = build_database(100, domain="daily")
```

## 领域定义

| 领域 | 人物 | 地点 | 事件 | 产品 |
|------|------|------|------|------|
| `history` | 历史人物（皇帝、将领、文人） | 历史地点（长安、洛阳、金陵） | 历史事件（战争、改革、条约） | 历史物品（兵器、书籍、货币） |
| `scifi` | 科幻角色（宇航员、科学家、AI） | 科幻地点（空间站、异星、未来城） | 科幻事件（时空穿越、基因改造、星际战争） | 科技产品（飞船、机器人、全息设备） |
| `business` | 商务人物（CEO、投资人、分析师） | 商务地点（交易所、总部、工厂） | 商务事件（并购、IPO、财报发布） | 商业产品（股票、债券、衍生品） |
| `daily` | 日常人物（学生、上班族、老人） | 日常地点（学校、公司、公园） | 日常事件（考试、会议、购物） | 日常产品（手机、食品、衣物） |

## 自定义领域

```python
from generator import DOMAINS

DOMAINS["medical"] = {
    "people": ["医生", "护士", "患者", "研究员"],
    "cities": ["医院", "诊所", "实验室", "药房"],
    "events": ["手术", "会诊", "体检", "康复"],
    "products": ["药品", "器械", "疫苗", "报告"]
}

db = build_database(100, domain="medical")
```

## 领域对评测的影响

不同领域影响记忆的语义密度和查询复杂度：

- **history**: 时间跨度大，因果链长，适合测试时序推理
- **scifi**: 概念新颖，实体虚构，适合测试语义理解
- **business**: 数字密集，关系复杂，适合测试逻辑推理
- **daily**: 贴近生活，实体常见，适合测试基础检索

## 混合领域

```python
# 生成混合领域数据（自动按比例混合）
db = build_database(100, domain="mixed")
```
