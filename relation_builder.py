#!/usr/bin/env python3
"""MemTest v4 关系构建器

在提取的记忆上构建关系，纯规则，无LLM：
- 别名等价组
- 时序链（chain_prev/chain_next）
- 聚类分组（cluster_id）
- 遗忘衰减（decay）
- 深度标注（depth）

输入：extractor.py 输出的记忆列表
输出：添加了关系的记忆列表（v2完整格式）
"""

import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# 别名等价组（并查集）
# ==============================================================================

class AliasGroups:
    """别名等价组管理"""

    def __init__(self):
        self._parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def groups(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for x in self._parent:
            root = self.find(x)
            if root not in result:
                result[root] = set()
            result[root].add(x)
        return result

    def are_equivalent(self, a: str, b: str) -> bool:
        if a not in self._parent or b not in self._parent:
            return False
        return self.find(a) == self.find(b)

    def get_group(self, name: str) -> Set[str]:
        if name not in self._parent:
            return {name}
        root = self.find(name)
        return self.groups().get(root, {name})


# ==============================================================================
# 关系构建器
# ==============================================================================

class RelationBuilder:
    """在提取的记忆上构建关系"""

    # 别名检测模式（从content中检测）
    ALIAS_PATTERNS = [
        re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]?\s*(?:人称|又名|又称|又叫|即|也就是|便是)\s*([\u4e00-\u9fff]{1,20})"),
        re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]\s*(?:俗名|绰号|号|字|别号|雅号|昵称)\s*([\u4e00-\u9fff]{1,20})"),
        re.compile(r"([\u4e00-\u9fff]{2,10})\s*(?:就是|便是|即是|等于)\s*([\u4e00-\u9fff]{1,20})"),
    ]

    # 别名噪音过滤
    NOISE_WORDS = {"指的", "这种", "那个", "这是", "也就是", "的", "了", "在", "是", "有", "和", "与", "被", "把"}

    def __init__(self, seed=42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.alias_groups = AliasGroups()

    def build(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建所有关系，返回完整的v2格式记忆列表"""
        if not memories:
            return memories

        # 1. 别名等价组
        self._build_alias_groups(memories)

        # 2. 时序链
        self._build_temporal_chains(memories)

        # 3. 聚类
        self._build_clusters(memories)

        # 4. 遗忘衰减
        self._assign_decay(memories)

        # 5. 深度标注
        self._assign_depth(memories)

        # 6. 生成3个版本
        self._generate_versions(memories)

        # 7. 分配category和difficulty
        self._assign_categories(memories)

        return memories

    # --------------------------------------------------------------------------
    # 别名等价组
    # --------------------------------------------------------------------------

    def _build_alias_groups(self, memories: List[Dict[str, Any]]) -> None:
        """从记忆中构建别名等价组"""
        # 从alias_evidence字段收集
        for m in memories:
            for ae in m.get("alias_evidence", []):
                entity = ae.get("entity", "").strip()
                alias = ae.get("alias", "").strip()
                if entity and alias and entity not in self.NOISE_WORDS and alias not in self.NOISE_WORDS:
                    if len(entity) >= 2 and len(alias) >= 2:
                        self.alias_groups.union(entity, alias)

        # 从content中检测额外别名
        all_content = " ".join(m["content"] for m in memories)
        for pattern in self.ALIAS_PATTERNS:
            for match in pattern.finditer(all_content):
                entity = match.group(1).strip()
                alias = match.group(2).strip()
                if entity and alias and entity not in self.NOISE_WORDS and alias not in self.NOISE_WORDS:
                    if len(entity) >= 2 and len(alias) >= 2:
                        self.alias_groups.union(entity, alias)

        # 简称检测：如果"林黛玉"和"黛玉"都出现在person_list中，合并
        all_persons = set()
        for m in memories:
            for p in m.get("person_list", []):
                if p and len(p) >= 2:
                    all_persons.add(p)

        # 对每个人名，检查是否是另一个的前缀/后缀
        person_list = sorted(all_persons, key=len, reverse=True)
        for i, long_name in enumerate(person_list):
            for short_name in person_list[i+1:]:
                if len(short_name) >= 2 and short_name in long_name and len(short_name) >= len(long_name) - 1:
                    # 只在两者都在同一段落content中共现时才算别名
                    cooccur = sum(1 for m in memories if short_name in m["content"] and long_name in m["content"])
                    if cooccur >= 1:
                        self.alias_groups.union(long_name, short_name)

    # --------------------------------------------------------------------------
    # 时序链
    # --------------------------------------------------------------------------

    def _build_temporal_chains(self, memories: List[Dict[str, Any]]) -> None:
        """按人物分组，构建时序链"""
        # 按person分组
        person_memories: Dict[str, List[Dict[str, Any]]] = {}
        for m in memories:
            for p in m.get("person_list", []):
                if p not in person_memories:
                    person_memories[p] = []
                person_memories[p].append(m)

        chain_id = 0
        for person, mems in person_memories.items():
            if len(mems) < 3:
                continue

            # 按时间排序（有absolute的排前面，没时间的按原文顺序）
            def sort_key(m):
                t = m.get("time", {})
                abs_time = t.get("absolute") if isinstance(t, dict) else None
                if abs_time:
                    return (0, abs_time)
                return (1, "")

            sorted_mems = sorted(mems, key=sort_key)

            # 每条链最多6条记忆
            for start in range(0, len(sorted_mems), 6):
                chain = sorted_mems[start:start+6]
                if len(chain) < 3:
                    continue

                chain_id += 1
                chain_name = f"CHAIN_{chain_id:04d}"

                for i, m in enumerate(chain):
                    m["reasoning_chain"] = chain_name
                    m["chain_position"] = i + 1
                    m["chain_relation"] = "时序"
                    m["chain_prev"] = chain[i-1]["memory_id"] if i > 0 else None
                    m["chain_next"] = chain[i+1]["memory_id"] if i < len(chain)-1 else None

    # --------------------------------------------------------------------------
    # 聚类
    # --------------------------------------------------------------------------

    def _build_clusters(self, memories: List[Dict[str, Any]]) -> None:
        """按event_type和共同person分组"""
        # 按event_type分组
        event_groups: Dict[str, List[Dict[str, Any]]] = {}
        for m in memories:
            evt = m.get("event", {})
            evt_type = evt.get("type", "日常") if isinstance(evt, dict) else "日常"
            if evt_type not in event_groups:
                event_groups[evt_type] = []
            event_groups[evt_type].append(m)

        cluster_id = 0
        for evt_type, mems in event_groups.items():
            if len(mems) < 3:
                continue

            cluster_id += 1
            cluster_name = f"CLUSTER{cluster_id:04d}"
            for m in mems[:10]:  # 每个cluster最多10条
                m["cluster_id"] = cluster_name

    # --------------------------------------------------------------------------
    # 遗忘衰减
    # --------------------------------------------------------------------------

    def _assign_decay(self, memories: List[Dict[str, Any]]) -> None:
        """随机分配遗忘衰减级别"""
        decay_levels = ["高频记忆", "中等频率", "低频记忆", "偶发事件"]
        decay_weights = [0.2, 0.3, 0.3, 0.2]

        for m in memories:
            level = self.rng.choices(decay_levels, weights=decay_weights, k=1)[0]
            access_counts = {"高频记忆": (50, 100), "中等频率": (10, 49), "低频记忆": (1, 9), "偶发事件": (0, 1)}
            lo, hi = access_counts[level]
            m["decay"] = {"level": level, "access_count": self.rng.randint(lo, hi)}

    # --------------------------------------------------------------------------
    # 深度标注
    # --------------------------------------------------------------------------

    def _assign_depth(self, memories: List[Dict[str, Any]]) -> None:
        """为部分记忆分配深度检索标注"""
        # 选30%的记忆做深度标注
        depth_memories = self.rng.sample(memories, min(len(memories) // 3 + 1, len(memories)))
        distances = ["near", "mid", "far"]

        for m in depth_memories:
            m["depth"] = {
                "layers": self.rng.randint(3, 7),
                "associations": self.rng.randint(2, 5),
                "semantic_distance": self.rng.choice(distances),
            }

    # --------------------------------------------------------------------------
    # 3版本生成
    # --------------------------------------------------------------------------

    def _generate_versions(self, memories: List[Dict[str, Any]]) -> None:
        """为每条记忆生成3个风格版本"""
        for m in memories:
            content = m["content"]

            # v1: 客观叙述（原文）
            v1 = content

            # v2: 详细描述（补充元数据）
            parts = []
            time_info = m.get("time", {})
            if isinstance(time_info, dict):
                if time_info.get("absolute"):
                    parts.append(time_info["absolute"])
            person_info = m.get("person", {})
            if isinstance(person_info, dict) and person_info.get("name"):
                parts.append(person_info["name"])
            loc_info = m.get("location", {})
            if isinstance(loc_info, dict) and loc_info.get("city"):
                parts.append(f"在{loc_info['city']}")
            parts.append(content)
            v2 = "，".join(parts) if parts else content

            # v3: 口语化（简化）
            v3 = content
            # 去掉"的"字句等书面语
            v3 = re.sub(r"乃是", "是", v3)
            v3 = re.sub(r"亦即", "就是", v3)
            v3 = re.sub(r"便$", "了", v3)

            m["versions"] = [
                {"version_id": "v1", "style": "客观叙述", "content": v1},
                {"version_id": "v2", "style": "主观视角", "content": v2},
                {"version_id": "v3", "style": "第三方转述", "content": v3},
            ]

    # --------------------------------------------------------------------------
    # category和difficulty
    # --------------------------------------------------------------------------

    def _assign_categories(self, memories: List[Dict[str, Any]]) -> None:
        """分配测试集category和difficulty"""
        categories = [
            "存储正确性测试集",
            "检索功能测试集",
            "记忆整理测试集",
            "遗忘功能测试集",
            "逻辑推理测试集",
            "长期记忆深度检索测试集",
        ]

        for i, m in enumerate(memories):
            # 按属性分配category
            if m.get("decay", {}).get("level"):
                if m["decay"]["level"] in ("低频记忆", "偶发事件"):
                    m["category"] = "遗忘功能测试集"
            if m.get("cluster_id"):
                m["category"] = "记忆整理测试集"
            if m.get("reasoning_chain"):
                m["category"] = "逻辑推理测试集"
            if m.get("depth"):
                m["category"] = "长期记忆深度检索测试集"

            # 默认
            if "category" not in m or m["category"] == "检索功能测试集":
                m["category"] = "检索功能测试集"

            # difficulty
            content_len = len(m["content"])
            if content_len < 50:
                m["difficulty"] = "简单"
                m["weight"] = 0.5
            elif content_len < 100:
                m["difficulty"] = "中等"
                m["weight"] = 1.0
            else:
                m["difficulty"] = "困难"
                m["weight"] = 1.5


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MemTest v4 关系构建器")
    parser.add_argument("input", help="extractor输出的JSON文件")
    parser.add_argument("-o", "--output", default="memories_with_relations.json", help="输出文件")
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        memories = json.load(f)

    builder = RelationBuilder()
    memories = builder.build(memories)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    # 统计
    has_chain = sum(1 for m in memories if m.get("reasoning_chain"))
    has_cluster = sum(1 for m in memories if m.get("cluster_id"))
    has_decay = sum(1 for m in memories if m.get("decay", {}).get("level"))
    has_depth = sum(1 for m in memories if m.get("depth"))
    has_alias = sum(1 for m in memories if m.get("alias_evidence"))

    print(f"关系构建完成: {len(memories)} 条记忆")
    print(f"  时序链: {has_chain} 条")
    print(f"  聚类: {has_cluster} 条")
    print(f"  遗忘: {has_decay} 条")
    print(f"  深度: {has_depth} 条")
    print(f"  别名: {has_alias} 条")
    print(f"  别名等价组: {len([g for g in builder.alias_groups.groups().values() if len(g) >= 2])} 组")
    for root, members in builder.alias_groups.groups().items():
        if len(members) >= 2:
            print(f"    {members}")
