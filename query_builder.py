#!/usr/bin/env python3
"""MemTest v4 查询生成器

纯模板，确定性，无LLM。

查询 = 记忆属性 × 模板

核心原则：
- 一个属性值 → 一个查询 → 所有匹配记忆作为答案
- 每个维度至少生成 MIN_PER_DIM 条查询
- 答案 = 全部匹配记忆的ID集合，不截断
- 保证覆盖：每条记忆至少被一个查询命中

输入：relation_builder.py 输出的记忆列表
输出：查询列表（v2格式）
"""

import json
import os
import random
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from relation_builder import AliasGroups


# ==============================================================================
# 配置
# ==============================================================================

MIN_PER_DIM = 100  # 每个维度最少查询数

# ==============================================================================
# 查询模板
# ==============================================================================

PERSON_TEMPLATES = [
    "{name}做了什么？",
    "{name}的经历有哪些？",
    "关于{name}的事情",
    "{name}发生了什么？",
    "查找与{name}相关的记录",
    "{name}的相关信息",
    "与{name}有关的事件",
    "{name}参与的事情",
]

LOCATION_TEMPLATES = [
    "在{location}发生了什么？",
    "关于{location}的事件",
    "{location}有什么事情？",
    "查找在{location}的记录",
    "与{location}相关的事情",
    "{location}发生的事情",
]

TIME_TEMPLATES = [
    "查找{time}发生的事情",
    "{time}有什么事件？",
    "关于{time}的记录",
    "{time}发生了什么？",
    "在{time}有哪些事情？",
    "{time}期间发生的事件",
]

EVENT_TEMPLATES_PRODUCT = [
    "关于{product}的事件有哪些？",
    "与{product}相关的记录",
    "{product}方面的事情",
]

EVENT_TEMPLATES_TYPE = [
    "{event_type}方面有什么事情？",
    "关于{event_type}的事件",
    "查找{event_type}相关的记录",
    "{event_type}类的事件有哪些？",
]

ALIAS_TEMPLATES = [
    "{alias}是谁？",
    "{alias}是什么？",
    "{alias}指的是谁？",
    "{alias}指的是什么？",
    "{alias}是什么意思？",
]

NEGATIVE_PERSON_NAMES = [
    "赵钱孙",
    "周吴郑",
    "冯陈褚",
    "蒋沈韩",
    "朱秦尤",
    "何吕施",
    "周吴郑王",
    "张三丰",
    "李四光",
    "王五福",
    "火星基地",
    "月球殖民地",
    "木卫二站",
    "半人马座",
    "天狼星系",
    "钱孙李",
    "吴郑王",
    "陈褚卫",
    "沈韩杨",
    "秦尤许",
    "吕施张",
    "孔曹严",
    "金魏陶",
    "姜戚谢",
    "邹喻柏",
    "窦章云",
    "苏潘葛",
    "范彭郎",
    "鲁韦昌",
    "马苗凤",
    "花方俞",
    "任袁柳",
    "鲍史唐",
    "费廉岑",
    "薛雷贺",
    "倪汤滕",
    "殷罗毕",
    "郝邬安",
    "常乐于",
    "时傅皮",
    "卞齐康",
    "伍余元",
    "卜顾孟",
    "平黄和",
    "穆萧尹",
    "姚邵湛",
    "汪祁毛",
    "禹狄米",
    "贝明臧",
    "计伏成",
    "戴谈宋",
    "茅庞熊",
    "纪舒屈",
    "项祝董",
    "梁杜阮",
    "蓝闵席",
    "季麻强",
    "贾路娄",
    "危江童",
    "颜郭梅",
    "盛林刁",
    "钟徐邱",
    "骆高夏",
    "蔡田樊",
    "胡凌霍",
    "虞万支",
    "柯昝管",
    "卢莫经",
    "房裘缪",
    "干解应",
    "宗丁宣",
    "贲邓郁",
    "单杭洪",
    "包诸左",
    "石崔吉",
    "钮龚程",
    "嵇邢滑",
    "裴陆荣",
    "翁荀羊",
    "惠甄曲",
    "家封芮",
    "羿储靳",
    "汲邴糜",
    "松井段",
    "富巫乌",
    "焦巴弓",
    "牧隗山",
    "谷车侯",
    "宓蓬全",
    "郗班仰",
    "秋仲伊",
    "宫宁仇",
    "栾暴甘",
    "钭厉戎",
    "祖武符",
]

NEGATIVE_LOCATIONS = [
    "火星",
    "月球基地",
    "亚特兰蒂斯",
    "香格里拉",
    "乌托邦",
    "银河中心",
    "仙女座",
    "半人马座阿尔法",
    "赛博坦",
    "瓦坎达",
    "冥王星站",
    "猎户座星云",
    "天琴座",
    "大犬座",
    "小熊座",
    "天鹅座",
    "室女座",
    "天蝎座",
    "人马座",
    "白羊座",
    "金牛座",
    "双子座",
    "巨蟹座",
    "狮子座",
    "处女座",
    "天秤座",
    "射手座",
    "摩羯座",
    "水瓶座",
    "双鱼座",
    "北欧星港",
    "维纳斯城",
    "宙斯空间站",
    "阿波罗基地",
    "赫拉要塞",
    "波塞冬深海站",
    "哈迪斯地下城",
    "雅典娜学院",
    "阿瑞斯堡垒",
    "赫尔墨斯中转站",
    "阿尔忒弥斯月面",
    "狄俄尼索斯酒庄",
    "赫菲斯托斯锻造厂",
    "德墨忒尔农场",
    "珀尔塞福涅冥界",
    "厄洛斯花园",
    "赫柏青春泉",
    "伊里斯虹桥",
    "尼刻胜利门",
    "潘多拉魔盒",
    "奥林帕斯山巅",
    "塔耳塔洛斯深渊",
    "埃律西昂净土",
    "阿斯加德",
    "约顿海姆",
    "尼福尔海姆",
    "穆斯贝尔海姆",
    "瓦纳海姆",
    "亚尔夫海姆",
    "斯瓦塔尔法海姆",
    "米德加尔德",
    "赫尔海姆",
    "华纳海姆",
    "光之国",
    "暗之域",
    "星海学院",
    "银河联邦",
    "宇宙枢纽",
    "时空裂缝",
    "量子隧道",
    "反物质空间",
    "暗物质海洋",
    "奇点之城",
    "虫洞驿站",
    "超弦之塔",
    "弦理论殿",
    "量子纠缠港",
    "波函数山",
    "不确定平原",
    "薛定谔谷",
    "麦克斯韦山",
    "法拉第林",
    "特斯拉塔",
    "欧拉桥",
    "高斯峰",
    "黎曼面",
    "傅里叶变换谷",
    "拉普拉斯海",
    "贝叶斯湾",
    "马尔可夫链",
    "蒙特卡洛城",
    "冯诺依曼机",
    "图灵站",
    "哥德尔环",
    "纳什均衡点",
    "帕累托前沿",
    "香农极限",
    "维纳滤波",
    "卡尔曼追踪",
    "辛普森悖论",
    "蒙提霍尔门",
    "费马大定理",
    "黎曼猜想",
    "P_vs_NP堡垒",
    "千禧难题",
]


# ==============================================================================
# 查询生成器
# ==============================================================================

class QueryBuilder:
    """基于记忆属性生成查询，纯模板，确定性

    核心逻辑：按属性值分组 -> 每个唯一属性值出一个查询 -> 所有匹配记忆作为答案
    保证：每维度≥MIN_PER_DIM，每条记忆至少被一个查询命中
    """

    def __init__(self, alias_groups: AliasGroups = None, seed=42, min_per_dim=MIN_PER_DIM):
        self.alias_groups = alias_groups or AliasGroups()
        self.seed = seed
        self.rng = random.Random(seed)
        self.query_counter = 0
        self.min_per_dim = min_per_dim

    def build(self, memories: List[Dict[str, Any]], max_queries: int = None) -> List[Dict[str, Any]]:
        """从记忆列表生成查询
        
        Args:
            memories: 记忆列表
            max_queries: 若指定，则查询与记忆独立，固定总量（方案A）
        """
        if max_queries is not None and max_queries > 0:
            return self._build_independent(memories, max_queries)
        
        # 原有逻辑：记忆驱动，自动比例
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

        # 9. 覆盖兜底：为没被命中的记忆补查询
        queries.extend(self._build_coverage_queries(memories, queries))

        return self._finalize_queries(queries)

    def _build_independent(self, memories: List[Dict[str, Any]], max_queries: int, min_per_dim: int = 100) -> List[Dict[str, Any]]:
        """方案A：查询与记忆独立，7维度保底分配
        
        7个考察维度，每个至少 min_per_dim 条（默认100）。
        总查询 = max_queries（默认700=7x100）。
        优先满足各维度保底，剩余按比例分配。
        """
        queries = []
        
        # 7个维度定义
        dim_builders = [
            ("person", self._dim_person),
            ("location", self._dim_location),
            ("time", self._dim_time),
            ("event", self._dim_event),
            ("combined", self._dim_combined),
            ("alias", self._dim_alias),
            ("negative", self._dim_negative),
        ]
        
        # 收集各维度数据
        dim_data = {
            "person": self._collect_persons(memories),
            "location": self._collect_locations(memories),
            "time": self._collect_times(memories),
            "event": self._collect_events(memories),
            "combined": self._collect_combined(memories),
            "alias": self._collect_aliases(memories),
            "negative": None,
        }
        
        # 计算各维度可用数量
        available = {}
        for name, _ in dim_builders:
            if name == "negative":
                available[name] = len(NEGATIVE_PERSON_NAMES) + len(NEGATIVE_LOCATIONS)
            else:
                available[name] = len(dim_data.get(name, {}))
        
        # 保底分配：每个维度至少 min_per_dim，但不超过可用数量
        quotas = {}
        for name, _ in dim_builders:
            quotas[name] = min(min_per_dim, available.get(name, 0))
        
        total_quota = sum(quotas.values())
        
        # 如果 max_queries 更大，剩余按比例追加
        remaining = max_queries - total_quota
        if remaining > 0:
            expandable = {k: v for k, v in available.items() if quotas[k] < v}
            if expandable:
                total_expandable = sum(v - quotas[k] for k, v in expandable.items())
                for name in expandable:
                    extra = int(remaining * (available[name] - quotas[name]) / total_expandable)
                    quotas[name] += extra
                # 余数加到人物（通常最丰富）
                used = sum(quotas.values())
                if used < max_queries:
                    quotas["person"] += (max_queries - used)
        
        # 各维度生成查询
        for name, builder_func in dim_builders:
            items = dim_data.get(name)
            dim_queries = builder_func(items, quotas.get(name, 0), memories)
            queries.extend(dim_queries)
        
        return self._finalize_queries(queries[:max_queries])

    def _collect_persons(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """收集人名->记忆ID映射，按出现频率排序"""
        person_map: Dict[str, List[str]] = defaultdict(list)
        for m in memories:
            for p in m.get("person", []):
                person_map[p].append(m["memory_id"])
        # 去重
        return {k: list(dict.fromkeys(v)) for k, v in sorted(person_map.items(), key=lambda x: -len(x[1]))}

    def _collect_locations(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """收集地点->记忆ID映射"""
        loc_map: Dict[str, List[str]] = defaultdict(list)
        for m in memories:
            loc = m.get("location", {})
            city = loc.get("city", "") if isinstance(loc, dict) else str(loc) if loc else ""
            if city:
                loc_map[city].append(m["memory_id"])
        return {k: list(dict.fromkeys(v)) for k, v in sorted(loc_map.items(), key=lambda x: -len(x[1]))}

    def _collect_times(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """收集时间->记忆ID映射"""
        time_map: Dict[str, List[str]] = defaultdict(list)
        for m in memories:
            for key in ["time_relative", "time_absolute"]:
                val = m.get(key, "")
                if val:
                    time_map[str(val)].append(m["memory_id"])
                    break
        return {k: list(dict.fromkeys(v)) for k, v in sorted(time_map.items(), key=lambda x: -len(x[1]))}

    def _collect_events(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """收集事件->记忆ID映射"""
        evt_map: Dict[str, List[str]] = defaultdict(list)
        for m in memories:
            evt_type = m.get("event_type", "")
            if evt_type:
                evt_map[str(evt_type)].append(m["memory_id"])
        return {k: list(dict.fromkeys(v)) for k, v in sorted(evt_map.items(), key=lambda x: -len(x[1]))}

    def _collect_aliases(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """收集别名->记忆ID映射"""
        alias_map: Dict[str, List[str]] = defaultdict(list)
        # 从 alias_groups 获取
        groups = self.alias_groups.groups()
        for name, group in groups.items():
            # 获取该组对应的记忆ID
            for mem in memories:
                content = mem.get("content", "")
                for alias in group:
                    if alias in content:
                        alias_map[name].append(mem["memory_id"])
                        break
        # 去重
        return {k: list(dict.fromkeys(v)) for k, v in sorted(alias_map.items(), key=lambda x: -len(x[1]))}

    def _sample_items(self, items: Dict[str, List[str]], n: int) -> List[Tuple[str, List[str]]]:
        """从属性映射中采样 n 个，优先高频，不重复"""
        all_items = list(items.items())
        # 取前 n 个（已按频率排序）
        return all_items[:n]

    def _finalize_queries(self, queries: List[Dict]) -> List[Dict]:
        """去重、编号、格式化"""
        # 去重（按 query_text + expected_memory_ids 联合去重）
        seen = set()
        unique = []
        for q in queries:
            key = (q["query_text"], tuple(sorted(q.get("expected_memory_ids", []))))
            if key not in seen:
                seen.add(key)
                unique.append(q)
        
        # 重新编号
        for i, q in enumerate(unique):
            q["query_id"] = f"Q{(i+1):04d}"
            q["expected_answer"] = ", ".join(q["expected_memory_ids"]) if q["expected_memory_ids"] else ""
        
        return unique

    # ==========================================================================
    # 7维度独立查询生成器（方案A）
    # ==========================================================================

    def _collect_combined(self, memories: List[Dict]) -> Dict[Tuple[str, str], List[str]]:
        """收集组合属性对：(人物, 地点) -> 记忆ID列表"""
        combined_map: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for m in memories:
            loc = m.get("location", {})
            city = loc.get("city", "") if isinstance(loc, dict) else str(loc) if loc else ""
            for p in m.get("person", []):
                if city and p:
                    combined_map[(p, city)].append(m["memory_id"])
        # 去重并按频率排序
        result = {}
        for k, v in sorted(combined_map.items(), key=lambda x: -len(x[1])):
            result[k] = list(dict.fromkeys(v))
        return result

    def _dim_person(self, items: Dict[str, List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """人物检索维度"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = self._sample_items(items, quota)
        for name, mem_ids in sampled:
            template = self.rng.choice(PERSON_TEMPLATES)
            queries.append({
                "query_id": self._next_id(),
                "query_text": template.format(name=name),
                "query_type": "人物检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": mem_ids,
                "difficulty": "中等" if len(mem_ids) < 4 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })
        return queries

    def _dim_location(self, items: Dict[str, List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """地点检索维度"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = self._sample_items(items, quota)
        for loc, mem_ids in sampled:
            template = self.rng.choice(LOCATION_TEMPLATES)
            queries.append({
                "query_id": self._next_id(),
                "query_text": template.format(location=loc),
                "query_type": "地点检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": mem_ids,
                "difficulty": "中等" if len(mem_ids) < 4 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })
        return queries

    def _dim_time(self, items: Dict[str, List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """时间检索维度"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = self._sample_items(items, quota)
        for time_val, mem_ids in sampled:
            template = self.rng.choice(TIME_TEMPLATES)
            queries.append({
                "query_id": self._next_id(),
                "query_text": template.format(time=time_val),
                "query_type": "时间检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": mem_ids,
                "difficulty": "中等" if len(mem_ids) < 3 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })
        return queries

    def _dim_event(self, items: Dict[str, List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """事件检索维度"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = self._sample_items(items, quota)
        templates = EVENT_TEMPLATES_PRODUCT + EVENT_TEMPLATES_TYPE
        for val, mem_ids in sampled:
            template = self.rng.choice(templates)
            var_name = "product" if "{product}" in template else "event_type"
            queries.append({
                "query_id": self._next_id(),
                "query_text": template.format(**{var_name: val}),
                "query_type": "事件检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": mem_ids,
                "difficulty": "中等" if len(mem_ids) < 4 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })
        return queries

    def _dim_combined(self, items: Dict[Tuple[str, str], List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """组合检索维度（人物+地点）"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = list(items.items())[:quota]
        for (person, loc), mem_ids in sampled:
            queries.append({
                "query_id": self._next_id(),
                "query_text": f"{person}在{loc}的记录",
                "query_type": "组合检索",
                "test_dimension": "组合推理",
                "expected_memory_ids": mem_ids,
                "difficulty": "困难" if len(mem_ids) < 2 else "困难",
                "search_depth": "深层",
                "is_negative": False,
            })
        return queries

    def _dim_alias(self, items: Dict[str, List[str]], quota: int, memories: List[Dict]) -> List[Dict]:
        """别名查询维度"""
        if not items or quota <= 0:
            return []
        queries = []
        sampled = self._sample_items(items, quota)
        for alias, mem_ids in sampled:
            template = self.rng.choice(ALIAS_TEMPLATES)
            queries.append({
                "query_id": self._next_id(),
                "query_text": template.format(alias=alias),
                "query_type": "别名查询",
                "test_dimension": "精确检索",
                "expected_memory_ids": mem_ids,
                "difficulty": "中等",
                "search_depth": "中层",
                "is_negative": False,
            })
        return queries

    def _dim_negative(self, items: Any, quota: int, memories: List[Dict]) -> List[Dict]:
        """负样本维度"""
        if quota <= 0:
            return []
        return self._build_negative_queries(memories, max_count=quota)

    def _build_negative_queries(self, memories: List[Dict], max_count: int = None) -> List[Dict]:
        """生成负样本（可限制数量）"""
        # ... 原有逻辑，但支持 max_count
        queries = []
        
        # 人物负样本
        used_names = set()
        for m in memories:
            for p in m.get("person", []):
                used_names.add(p)
        
        neg_candidates = [n for n in NEGATIVE_PERSON_NAMES if n not in used_names]
        self.rng.shuffle(neg_candidates)
        
        person_neg_count = max_count // 2 if max_count else 100
        for name in neg_candidates[:person_neg_count]:
            queries.append({
                "query_id": self._next_id(),
                "query_text": f"{name}做了什么？",
                "query_type": "负样本",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "difficulty": "简单",
                "search_depth": "浅层",
                "is_negative": True,
            })
        
        # 地点负样本
        used_locs = set()
        for m in memories:
            loc = m.get("location", {})
            city = loc.get("city", "") if isinstance(loc, dict) else str(loc) if loc else ""
            if city:
                used_locs.add(city)
        
        neg_locs = [l for l in NEGATIVE_LOCATIONS if l not in used_locs]
        self.rng.shuffle(neg_locs)
        
        loc_neg_count = max_count // 2 if max_count else 200
        for loc in neg_locs[:loc_neg_count]:
            queries.append({
                "query_id": self._next_id(),
                "query_text": f"在{loc}发生了什么？",
                "query_type": "负样本",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "difficulty": "简单",
                "search_depth": "浅层",
                "is_negative": True,
            })
        
        if max_count:
            queries = queries[:max_count]
        
        return queries

    # --------------------------------------------------------------------------
    # 辅助方法
    # --------------------------------------------------------------------------

    def _next_id(self) -> str:
        self.query_counter += 1
        return f"Q{self.query_counter:04d}"

    # --------------------------------------------------------------------------
    # 各维度查询
    # --------------------------------------------------------------------------

    def _build_person_queries(self, memories: List[Dict]) -> List[Dict]:
        """人物检索：按人名分组"""
        person_memories: Dict[str, List[Dict]] = defaultdict(list)
        for m in memories:
            for p in m.get("person", []):
                person_memories[p].append(m)

        queries = []
        seen_groups = set()
        for name, mems in sorted(person_memories.items(), key=lambda x: -len(x[1])):
            group_key = frozenset(self.alias_groups.get_group(name))
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)

            template = self.rng.choice(PERSON_TEMPLATES)
            query_text = template.format(name=name)

            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "人物检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": [m["memory_id"] for m in mems],
                "difficulty": "中等" if len(mems) < 4 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })

        # 如果不够，为单次出现的人名也出题
        if len(queries) < self.min_per_dim:
            for name, mems in sorted(person_memories.items(), key=lambda x: -len(x[1])):
                group_key = frozenset(self.alias_groups.get_group(name))
                if group_key in seen_groups:
                    continue
                seen_groups.add(group_key)

                template = self.rng.choice(PERSON_TEMPLATES)
                query_text = template.format(name=name)

                queries.append({
                    "query_id": self._next_id(),
                    "query_text": query_text,
                    "query_type": "人物检索",
                    "test_dimension": "精确检索",
                    "expected_memory_ids": [m["memory_id"] for m in mems],
                    "difficulty": "简单",
                    "search_depth": "浅层",
                    "is_negative": False,
                })

                if len(queries) >= self.min_per_dim:
                    break

        return queries

    def _build_location_queries(self, memories: List[Dict]) -> List[Dict]:
        """地点检索：按地点分组"""
        location_memories: Dict[str, List[Dict]] = defaultdict(list)
        for m in memories:
            loc = m.get("location", {})
            city = loc.get("city", "") if isinstance(loc, dict) else ""
            if city:
                location_memories[city].append(m)

        queries = []
        for loc, mems in sorted(location_memories.items(), key=lambda x: -len(x[1])):
            template = self.rng.choice(LOCATION_TEMPLATES)
            query_text = template.format(location=loc)

            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "地点检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": [m["memory_id"] for m in mems],
                "difficulty": "中等" if len(mems) < 4 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })

        return queries

    def _build_time_queries(self, memories: List[Dict]) -> List[Dict]:
        """时间检索：按时间值分组"""
        time_memories: Dict[str, List[Dict]] = defaultdict(list)
        for m in memories:
            time_key = m.get("time_relative", "") or m.get("time_absolute", "")
            if time_key:
                time_memories[time_key].append(m)

        queries = []
        for time_val, mems in sorted(time_memories.items(), key=lambda x: -len(x[1])):
            template = self.rng.choice(TIME_TEMPLATES)
            query_text = template.format(time=time_val)

            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "时间检索",
                "test_dimension": "精确检索",
                "expected_memory_ids": [m["memory_id"] for m in mems],
                "difficulty": "中等" if len(mems) < 3 else "困难",
                "search_depth": "中层",
                "is_negative": False,
            })

        # 如果不够，为单条记忆时间也用不同模板多出几个变体
        if len(queries) < self.min_per_dim:
            existing_texts = {q["query_text"] for q in queries}
            idx = 0
            for time_val, mems in sorted(time_memories.items(), key=lambda x: -len(x[1])):
                for tpl in TIME_TEMPLATES:
                    qt = tpl.format(time=time_val)
                    if qt not in existing_texts:
                        queries.append({
                            "query_id": self._next_id(),
                            "query_text": qt,
                            "query_type": "时间检索",
                            "test_dimension": "精确检索",
                            "expected_memory_ids": [m["memory_id"] for m in mems],
                            "difficulty": "中等",
                            "search_depth": "中层",
                            "is_negative": False,
                        })
                        existing_texts.add(qt)
                        if len(queries) >= self.min_per_dim:
                            break
                if len(queries) >= self.min_per_dim:
                    break

        return queries

    def _build_event_queries(self, memories: List[Dict]) -> List[Dict]:
        """事件检索：按事件产物/类型分组"""
        product_memories: Dict[str, List[Dict]] = defaultdict(list)
        type_memories: Dict[str, List[Dict]] = defaultdict(list)

        for m in memories:
            evt_type = m.get("event_type", "")
            if evt_type:
                type_memories[evt_type].append(m)

        queries = []
        existing_texts = set()

        # 按product出题
        for product, mems in sorted(product_memories.items(), key=lambda x: -len(x[1])):
            for tpl in EVENT_TEMPLATES_PRODUCT:
                qt = tpl.format(product=product)
                if qt not in existing_texts:
                    queries.append({
                        "query_id": self._next_id(),
                        "query_text": qt,
                        "query_type": "事件检索",
                        "test_dimension": "精确检索",
                        "expected_memory_ids": [m["memory_id"] for m in mems],
                        "difficulty": "中等",
                        "search_depth": "中层",
                        "is_negative": False,
                    })
                    existing_texts.add(qt)
                    break

        # 按event_type出题
        for evt_type, mems in sorted(type_memories.items(), key=lambda x: -len(x[1])):
            for tpl in EVENT_TEMPLATES_TYPE:
                qt = tpl.format(event_type=evt_type)
                if qt not in existing_texts:
                    queries.append({
                        "query_id": self._next_id(),
                        "query_text": qt,
                        "query_type": "事件检索",
                        "test_dimension": "精确检索",
                        "expected_memory_ids": [m["memory_id"] for m in mems],
                        "difficulty": "中等",
                        "search_depth": "中层",
                        "is_negative": False,
                    })
                    existing_texts.add(qt)
                    break

        # 如果不够，同一product/type用不同模板多出变体
        if len(queries) < self.min_per_dim:
            for product, mems in sorted(product_memories.items(), key=lambda x: -len(x[1])):
                for tpl in EVENT_TEMPLATES_PRODUCT:
                    qt = tpl.format(product=product)
                    if qt not in existing_texts:
                        queries.append({
                            "query_id": self._next_id(),
                            "query_text": qt,
                            "query_type": "事件检索",
                            "test_dimension": "精确检索",
                            "expected_memory_ids": [m["memory_id"] for m in mems],
                            "difficulty": "中等",
                            "search_depth": "中层",
                            "is_negative": False,
                        })
                        existing_texts.add(qt)
                        if len(queries) >= self.min_per_dim:
                            break
                if len(queries) >= self.min_per_dim:
                    break

            for evt_type, mems in sorted(type_memories.items(), key=lambda x: -len(x[1])):
                for tpl in EVENT_TEMPLATES_TYPE:
                    qt = tpl.format(event_type=evt_type)
                    if qt not in existing_texts:
                        queries.append({
                            "query_id": self._next_id(),
                            "query_text": qt,
                            "query_type": "事件检索",
                            "test_dimension": "精确检索",
                            "expected_memory_ids": [m["memory_id"] for m in mems],
                            "difficulty": "中等",
                            "search_depth": "中层",
                            "is_negative": False,
                        })
                        existing_texts.add(qt)
                        if len(queries) >= self.min_per_dim:
                            break
                if len(queries) >= self.min_per_dim:
                    break

        return queries

    def _build_combined_queries(self, memories: List[Dict]) -> List[Dict]:
        """组合检索：所有两属性组合"""
        queries = []
        existing_texts = set()

        def _add_combo(query_text, mems, is_multi=True):
            if query_text in existing_texts:
                return
            queries.append({
                "query_id": self._next_id(),
                "query_text": query_text,
                "query_type": "组合检索",
                "test_dimension": "组合检索",
                "expected_memory_ids": [m["memory_id"] for m in mems],
                "difficulty": "困难",
                "search_depth": "深层",
                "is_negative": False,
            })
            existing_texts.add(query_text)

        # --- 人名+地点 ---
        name_loc: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for m in memories:
            person_list = m.get("person", [])
            person_name = person_list[0] if isinstance(person_list, list) and person_list else ""
            loc = m.get("location", {})
            location = loc.get("city", "") if isinstance(loc, dict) else ""
            if person_name and location:
                name_loc[(person_name, location)].append(m)

        for (name, location), mems in sorted(name_loc.items(), key=lambda x: -len(x[1])):
            _add_combo(f"{name}在{location}的记录", mems)

        # --- 人名+事件类型 ---
        name_evt: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for m in memories:
            person_list = m.get("person", [])
            person_name = person_list[0] if isinstance(person_list, list) and person_list else ""
            evt_type = m.get("event_type", "")
            if person_name and evt_type:
                name_evt[(person_name, evt_type)].append(m)

        for (name, evt_type), mems in sorted(name_evt.items(), key=lambda x: -len(x[1])):
            _add_combo(f"{name}的{evt_type}经历", mems)

        # --- 人名+时间 ---
        name_time: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for m in memories:
            person_list = m.get("person", [])
            person_name = person_list[0] if isinstance(person_list, list) and person_list else ""
            time_val = m.get("time_relative", "") or m.get("time_absolute", "")
            if person_name and time_val:
                name_time[(person_name, time_val)].append(m)

        for (name, time_val), mems in sorted(name_time.items(), key=lambda x: -len(x[1])):
            _add_combo(f"{name}在{time_val}的记录", mems)

        # --- 地点+事件类型 ---
        loc_evt: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for m in memories:
            loc = m.get("location", {})
            location = loc.get("city", "") if isinstance(loc, dict) else ""
            evt_type = m.get("event_type", "")
            if location and evt_type:
                loc_evt[(location, evt_type)].append(m)

        for (location, evt_type), mems in sorted(loc_evt.items(), key=lambda x: -len(x[1])):
            _add_combo(f"{location}的{evt_type}事件", mems)

        # --- 地点+时间 ---
        loc_time: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
        for m in memories:
            loc = m.get("location", {})
            location = loc.get("city", "") if isinstance(loc, dict) else ""
            time_val = m.get("time_relative", "") or m.get("time_absolute", "")
            if location and time_val:
                loc_time[(location, time_val)].append(m)

        for (location, time_val), mems in sorted(loc_time.items(), key=lambda x: -len(x[1])):
            _add_combo(f"{location}在{time_val}的事件", mems)

        return queries

    def _build_alias_queries(self, memories: List[Dict]) -> List[Dict]:
        """别名查询：按等价组出题"""
        queries = []
        existing_texts = set()

        for group in self.alias_groups.groups().values():
            if len(group) < 2:
                continue

            members = sorted(list(group), key=len)
            primary = max(members, key=len)

            relevant_mems = []
            for m in memories:
                for member in members:
                    if member in m["content"] or member in m.get("person", []):
                        relevant_mems.append(m)
                        break

            if not relevant_mems:
                continue

            for alias in members:
                if alias == primary:
                    continue

                is_person = any(alias in m.get("person", []) for m in relevant_mems)
                # 每个别名用多种模板
                for tpl in ALIAS_TEMPLATES:
                    qt = tpl.format(alias=alias)
                    is_person_tpl = "谁" in tpl
                    if is_person != is_person_tpl:
                        continue  # 人用"谁"，物用"什么"
                    if qt not in existing_texts:
                        queries.append({
                            "query_id": self._next_id(),
                            "query_text": qt,
                            "query_type": "别名查询",
                            "test_dimension": "跨版本",
                            "expected_memory_ids": [m["memory_id"] for m in relevant_mems],
                            "difficulty": "中等",
                            "search_depth": "中层",
                            "is_negative": False,
                        })
                        existing_texts.add(qt)
                        break

            # 主名问别称
            qt = f"{primary}还有哪些称呼？"
            if qt not in existing_texts:
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": qt,
                    "query_type": "别名查询",
                    "test_dimension": "跨版本",
                    "expected_memory_ids": [m["memory_id"] for m in relevant_mems],
                    "difficulty": "中等",
                    "search_depth": "中层",
                    "is_negative": False,
                })
                existing_texts.add(qt)

            # 额外：别名之间的互问
            if len(members) >= 2:
                qt = f"{members[0]}和{members[-1]}是什么关系？"
                if qt not in existing_texts:
                    queries.append({
                        "query_id": self._next_id(),
                        "query_text": qt,
                        "query_type": "别名查询",
                        "test_dimension": "跨版本",
                        "expected_memory_ids": [m["memory_id"] for m in relevant_mems],
                        "difficulty": "中等",
                        "search_depth": "中层",
                        "is_negative": False,
                    })
                    existing_texts.add(qt)

        return queries

    def _build_chain_queries(self, memories: List[Dict]) -> List[Dict]:
        """链式推理：按chain分组"""
        queries = []

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

            chain_mems.sort(key=lambda m: m.get("chain_position", 0))

            person_data = chain_mems[0].get("person", {})
            person_name = person_data.get("name", "") if isinstance(person_data, dict) else ""

            # 梳理完整经历
            if person_name:
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"梳理{person_name}的完整经历",
                    "query_type": "组合推理",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": [m["memory_id"] for m in chain_mems],
                    "difficulty": "困难",
                    "search_depth": "深层",
                    "is_negative": False,
                })

            # 每一步的"之后发生了什么"
            for i in range(len(chain_mems) - 1):
                prev = chain_mems[i]
                subsequent_mems = chain_mems[i + 1:]
                prev_desc = prev["content"][:30]
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"在{prev_desc}之后发生了什么？",
                    "query_type": "组合推理",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": [m["memory_id"] for m in subsequent_mems],
                    "difficulty": "中等" if len(subsequent_mems) < 3 else "困难",
                    "search_depth": "中层",
                    "is_negative": False,
                })

            # 额外：从中间某步问"之前发生了什么"
            for i in range(1, len(chain_mems)):
                curr = chain_mems[i]
                prior_mems = chain_mems[:i]
                curr_desc = curr["content"][:20]
                queries.append({
                    "query_id": self._next_id(),
                    "query_text": f"{curr_desc}之前发生了什么？",
                    "query_type": "组合推理",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": [m["memory_id"] for m in prior_mems],
                    "difficulty": "中等" if len(prior_mems) < 3 else "困难",
                    "search_depth": "中层",
                    "is_negative": False,
                })

                if len(queries) >= self.min_per_dim * 2:
                    break

        return queries

    def _build_coverage_queries(self, memories: List[Dict], existing_queries: List[Dict]) -> List[Dict]:
        """覆盖率兜底：为没被任何查询命中的记忆补查询"""
        # 统计已有查询覆盖的记忆
        covered_ids = set()
        for q in existing_queries:
            ids = q.get("expected_memory_ids", [])
            covered_ids.update(ids)

        uncovered = [m for m in memories if m["memory_id"] not in covered_ids]
        if not uncovered:
            return []

        queries = []
        for m in uncovered:
            # 根据记忆的属性选择最佳查询类型
            person_list = m.get("person", [])
            person_name = person_list[0] if isinstance(person_list, list) and person_list else ""
            loc = m.get("location", {})
            location = loc.get("city", "") if isinstance(loc, dict) else ""
            time_val = m.get("time_relative", "") or m.get("time_absolute", "")

            # 优先组合，其次单属性
            if person_name and location:
                qt = f"{person_name}在{location}的记录"
                qtype = "组合检索"
            elif person_name and time_val:
                qt = f"{person_name}在{time_val}的记录"
                qtype = "组合检索"
            elif person_name:
                qt = f"关于{person_name}的事情"
                qtype = "人物检索"
            elif location:
                qt = f"在{location}发生了什么？"
                qtype = "地点检索"
            elif time_val:
                qt = f"查找{time_val}发生的事情"
                qtype = "时间检索"
            else:
                qt = f"关于「{m['content'][:15]}」的记录"
                qtype = "事件检索"

            queries.append({
                "query_id": self._next_id(),
                "query_text": qt,
                "query_type": qtype,
                "test_dimension": "覆盖兜底",
                "expected_memory_ids": [m["memory_id"]],
                "difficulty": "简单",
                "search_depth": "浅层",
                "is_negative": False,
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

    from relation_builder import RelationBuilder
    builder = RelationBuilder()
    builder._build_alias_groups(memories)

    qb = QueryBuilder(alias_groups=builder.alias_groups)
    queries = qb.build(memories)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)

    by_type = {}
    multi_answer = 0
    for q in queries:
        t = q["query_type"]
        by_type[t] = by_type.get(t, 0) + 1
        if len(q["expected_memory_ids"]) > 1:
            multi_answer += 1

    print(f"查询生成完成: {len(queries)} 条")
    print(f"  多答案查询: {multi_answer} 条 ({multi_answer*100//max(len(queries),1)}%)")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c} 条")
