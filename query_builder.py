#!/usr/bin/env python3
"""MemTest v4 查询生成器

纯模板，确定性，无LLM。

查询 = 记忆属性 × 模板
- 有人名 → 人物检索
- 有地点 → 地点检索
- 有时间 → 时间检索
- 有event → 事件检索
- 有chain → 链式推理
- 有别名 → 别名查询
- 负样本 → 构造不存在的实体

输入：relation_builder.py 输出的记忆列表
输出：查询列表（v2格式）
"""

import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from relation_builder import AliasGroups


# ==============================================================================
# 查询模板
# ==============================================================================

PERSON_TEMPLATES = [
    "{name}做了什么？",
    "{name}的经历有哪些？",
    "关于{name}的事情",
    "{name}发生了什么？",
    "查找与{name}相关的记录",
]

LOCATION_TEMPLATES = [
    "在{location}发生了什么？",
    "关于{location}的事件",
    "{location}有什么事情？",
    "查找在{location}的记录",
]

TIME_TEMPLATES = [
    "查找{time}发生的事情",
    "{time}有什么事件？",
    "关于{time}的记录",
]

EVENT_TEMPLATES = [
    "关于{product}的事件有哪些？",
    "{event_type}方面有什么事情？",
    "查找{action}相关的记录",
]

COMBINED_TEMPLATES = [
    "{name}在{location}的记录",
    "{name}的{event_type}经历",
    "在{location}的{event_type}事件",
]

ALIAS_TEMPLATES = [
    "{alias}是谁？",
    "{alias}是什么？",
    "{alias}指的是谁？",
    "{alias}指的是什么？",
]

CHAIN_TEMPLATES = [
    "在{prev_event}之后发生了什么？",
    "{name}的经历脉络是怎样的？",
    "梳理{name}的完整经历",
]

NEGATIVE_PERSON_NAMES = [
    "赵钱孙", "周吴郑", "冯陈褚", "蒋沈韩", "朱秦尤",
    "何吕施", "周吴郑王", "张三丰", "李四光", "王五福",
    "火星基地", "月球殖民地", "木卫二站", "半人马座", "天狼星系",
]

NEGATIVE_LOCATIONS = [
    "火星", "月球基地", "亚特兰蒂斯", "香格里拉", "乌托邦",
    "银河中心", "仙女座", "半人马座阿尔法", "赛博坦", "瓦坎达",
]


# ==============================================================================
# 查询生成器
# ==============================================================================

class QueryBuilder:
    """基于记忆属性生成查询，纯模板，确定性"""

    def __init__(self, alias_groups: AliasGroups = None, seed=42):
        self.alias_groups = alias_groups or AliasGroups()
        self.seed = seed
        self.rng = random.Random(seed)
        self.query_counter = 0

    def build(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从记忆列表生成查询"""
        queries = []

        # 1. 人物检索
        queries.extend(self._build_person_queries(memories))

        # 2. 地点检索
        queries.extend(self._build_location_queries(memories))

        # 3. 时间检索
        queries.extend(self._build_time_queries(memories))

        # 4. 事件检索
        queries.extend(self._build_event_queries(memories))

        # 5. 组合检索
        queries.extend(self._build_combined_queries(memories))

        # 6. 别名查询
        queries.extend(self._build_alias_queries(memories))

        # 7. 链式推理
        queries.extend(self._build_chain_queries(memories))

        # 8. 负样本
        queries.extend(self._build_negative_queries(memories))

        # 去重（按query_text）
        seen = set()
        unique = []
        for q in queries:
            if q["query_text"] not in seen:
                seen.add(q["query_text"])
                unique.append(q)

        # 重新编号 + 统一答案为ID集合
        for i, q in enumerate(unique):
            q["query_id"] = f"Q{(i+1):04d}"
            q["expected_answer"] = ", ".join(q["expected_memory_ids"]) if q["expected_memory_ids"] else ""

        return unique

    # --------------------------------------------------------------------------
    # 内部方法
    # --------------------------------------------------------------------------

    def _next_id(self) -> str:
        self.query_counter += 1
        return f"Q{self.query_counter:04d}"

    def _find_memories_by_person(self, memories: List[Dict], person_name: str) -> List[Dict]:
        """找包含某个人的记忆（考虑别名等价）"""
        results = []
        for m in memories:
            for p in m.get("person_list", []):
                if p == person_name or self.alias_groups.are_equivalent(p, person_name):
                    results.append(m)
                    break
        return results

    def _find_memories_by_location(self, memories: List[Dict], location: str) -> List[Dict]:
        """找包含某个地点的记忆"""
        results = []
        for m in memories:
            loc = m.get("location", {})
            loc_str = loc.get("city", "") if isinstance(loc, dict) else str(loc)
            if location in m["content"] or location in loc_str:
                results.append(m)
        return results

    def _person_queries(self, name: str, memories: List[Dict]) -> List[Dict]:
        """为一个人名生成查询"""
        mems = self._find_memories_by_person(memories, name)
        if not mems:
            return []

        template = self.rng.choice(PERSON_TEMPLATES)
        query_text = template.format(name=name)

        return [{
            "query_id": self._next_id(),
            "query_text": query_text,
            "query_type": "人物检索",
            "test_dimension": "精确检索",
            "expected_memory_ids": [m["memory_id"] for m in mems[:5]],
            "expected_answer": mems[0]["content"] if mems else "",
            "difficulty": "中等" if len(mems) < 3 else "困难",
            "search_depth": "中层",
            "is_negative": False,
        }]

    # --------------------------------------------------------------------------
    # 各维度查询
    # --------------------------------------------------------------------------

    def _build_person_queries(self, memories: List[Dict]) -> List[Dict]:
        """人物检索查询"""
        queries = []
        # 收集所有人名
        person_count: Dict[str, int] = {}
        for m in memories:
            for p in m.get("person_list", []):
                person_count[p] = person_count.get(p, 0) + 1

        # 对出现2次以上的人名生成查询
        for name, count in sorted(person_count.items(), key=lambda x: -x[1]):
            if count < 2:
                continue
            queries.extend(self._person_queries(name, memories))
            if len(queries) >= 20:  # 限制数量
                break

        return queries

    def _build_location_queries(self, memories: List[Dict]) -> List[Dict]:
        """地点检索查询"""
        queries = []
        locations = set()
        for m in memories:
            loc = m.get("location", {})
            city = loc.get("city", "") if isinstance(loc, dict) else str(loc)
            if city:
                locations.add(city)

        for loc in locations:
            mems = self._find_memories_by_location(memories, loc)
            if len(mems) < 2:
                continue

            template = self.rng.choice(LOCATION_TEMPLATES)
            query_text = template.format(location=loc)

            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "地点检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": [m["memory_id"] for m in mems[:5]],
                "expected_answer": mems[0]["content"] if mems else "",
                "difficulty": "中等",
                "search_depth": "中层",
                "is_negative": False,
            })

        return queries

    def _build_time_queries(self, memories: List[Dict]) -> List[Dict]:
        """时间检索查询"""
        queries = []
        for m in memories:
            time_info = m.get("time", {})
            if not isinstance(time_info, dict):
                continue
            rel = time_info.get("relative")
            fuzzy = time_info.get("fuzzy")
            if not rel and not fuzzy:
                continue

            time_str = rel or fuzzy
            template = self.rng.choice(TIME_TEMPLATES)
            query_text = template.format(time=time_str)

            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "时间检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": m["content"],
                "difficulty": "中等",
                "search_depth": "中层",
                "is_negative": False,
            })

        return queries[:15]  # 限制数量

    def _build_event_queries(self, memories: List[Dict]) -> List[Dict]:
        """事件检索查询"""
        queries = []
        for m in memories:
            evt = m.get("event", {})
            if not isinstance(evt, dict):
                continue
            product = evt.get("product", "")
            evt_type = evt.get("type", "")
            action = evt.get("action", "")

            if product:
                template = self.rng.choice(EVENT_TEMPLATES)
                query_text = template.format(product=product, event_type=evt_type, action=action)
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": query_text,
                    "query_type": "事件检索",
                    "test_dimension": "精确检索",
                    "expected_memory_ids": [m["memory_id"]],
                    "expected_answer": m["content"],
                    "difficulty": "中等",
                    "search_depth": "中层",
                    "is_negative": False,
                })

        return queries[:10]

    def _build_combined_queries(self, memories: List[Dict]) -> List[Dict]:
        """组合检索查询"""
        queries = []
        for m in memories:
            person_name = m.get("person", {}).get("name", "") if isinstance(m.get("person"), dict) else ""
            loc = m.get("location", {})
            location = loc.get("city", "") if isinstance(loc, dict) else ""
            evt = m.get("event", {})
            evt_type = evt.get("type", "") if isinstance(evt, dict) else ""

            if person_name and location:
                template = self.rng.choice(COMBINED_TEMPLATES)
                query_text = template.format(name=person_name, location=location, event_type=evt_type)
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": query_text,
                    "query_type": "组合检索",
                    "test_dimension": "组合检索",
                    "expected_memory_ids": [m["memory_id"]],
                    "expected_answer": m["content"],
                    "difficulty": "困难",
                    "search_depth": "深层",
                    "is_negative": False,
                })

        return queries[:10]

    def _build_alias_queries(self, memories: List[Dict]) -> List[Dict]:
        """别名查询"""
        queries = []

        for group in self.alias_groups.groups().values():
            if len(group) < 2:
                continue

            members = sorted(list(group), key=len)  # 短的排前面

            # 找包含这些名字的记忆
            relevant_mems = []
            for m in memories:
                for member in members:
                    if member in m["content"] or member in m.get("person_list", []):
                        relevant_mems.append(m)
                        break

            if not relevant_mems:
                continue

            # 对每个别名生成查询
            for alias in members:
                # 找到主名（最长的）
                primary = max(members, key=len)

                if alias == primary:
                    # 问主名的别称
                    query_text = f"{primary}还有哪些称呼？"
                    query_type = "别名查询"
                else:
                    # 用别名问
                    is_person = any(alias in m.get("person_list", []) for m in relevant_mems)
                    template = ALIAS_TEMPLATES[0] if is_person else ALIAS_TEMPLATES[1]
                    query_text = template.format(alias=alias)
                    query_type = "别名查询"

                queries.append({
                    "query_id": self._next_id(),
                    "query_text": query_text,
                    "query_type": query_type,
                    "test_dimension": "跨版本",
                    "expected_memory_ids": [m["memory_id"] for m in relevant_mems[:5]],
                    "expected_answer": f"{alias}与{primary}是同一{'人' if any(alias in m.get('person_list', []) for m in relevant_mems) else '事物'}",
                    "difficulty": "中等",
                    "search_depth": "中层",
                    "is_negative": False,
                })

        return queries

    def _build_chain_queries(self, memories: List[Dict]) -> List[Dict]:
        """链式推理查询"""
        queries = []

        # 按chain分组
        chains: Dict[str, List[Dict]] = {}
        for m in memories:
            chain = m.get("reasoning_chain")
            if chain:
                if chain not in chains:
                    chains[chain] = []
                chains[chain].append(m)

        for chain_name, chain_mems in chains.items():
            if len(chain_mems) < 3:
                continue

            # 按chain_position排序
            chain_mems.sort(key=lambda m: m.get("chain_position", 0))

            # "梳理X的完整经历"
            person_data = chain_mems[0].get("person", {})
            person_name = person_data.get("name", "") if isinstance(person_data, dict) else ""
            if person_name:
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"梳理{person_name}的完整经历",
                    "query_type": "组合推理",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": [m["memory_id"] for m in chain_mems],
                    "expected_answer": " → ".join(m["content"][:30] for m in chain_mems),
                    "difficulty": "困难",
                    "search_depth": "深层",
                    "is_negative": False,
                })

            # "在X之后发生了什么？"
            for i in range(len(chain_mems) - 1):
                prev = chain_mems[i]
                next_m = chain_mems[i + 1]
                prev_desc = prev["content"][:30]
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"在{prev_desc}之后发生了什么？",
                    "query_type": "事件检索",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": [next_m["memory_id"]],
                    "expected_answer": next_m["content"],
                    "difficulty": "中等",
                    "search_depth": "中层",
                    "is_negative": False,
                })

        return queries[:10]

    def _build_negative_queries(self, memories: List[Dict]) -> List[Dict]:
        """负样本查询"""
        queries = []

        # 不存在的人名
        used_names = set()
        for m in memories:
            for p in m.get("person_list", []):
                used_names.add(p)

        for name in NEGATIVE_PERSON_NAMES:
            if name not in used_names:
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"{name}做了什么？",
                    "query_type": "人物检索",
                    "test_dimension": "负样本",
                    "expected_memory_ids": [],
                    "expected_answer": "",
                    "difficulty": "中等",
                    "search_depth": "中层",
                    "is_negative": True,
                })

        # 不存在的地点
        for loc in NEGATIVE_LOCATIONS[:3]:
            queries.append({
                "query_id": self._next_id(),
                "query_text": f"在{loc}发生了什么？",
                "query_type": "地点检索",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "difficulty": "中等",
                "search_depth": "中层",
                "is_negative": True,
            })

        return queries


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MemTest v4 查询生成器")
    parser.add_argument("input", help="relation_builder输出的JSON文件")
    parser.add_argument("-o", "--output", default="queries.json", help="输出文件")
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        memories = json.load(f)

    # 需要重建alias_groups
    from relation_builder import RelationBuilder
    builder = RelationBuilder()
    builder._build_alias_groups(memories)

    qb = QueryBuilder(alias_groups=builder.alias_groups)
    queries = qb.build(memories)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)

    # 统计
    by_type = {}
    for q in queries:
        t = q["query_type"]
        by_type[t] = by_type.get(t, 0) + 1

    print(f"查询生成完成: {len(queries)} 条")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        neg = " (负样本)" if t == "负样本" else ""
        print(f"  {t}: {c} 条{neg}")
