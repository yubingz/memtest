#!/usr/bin/env python3
"""MemTest v3 别名等价检测器

核心原则：只认语料证据，不靠外部知识建立等价关系。

v3 设计：等价组模型
- 同一等价组内所有成员平等，无"标准名"概念
- 人名、地名、物品名统一处理
- 检测到等价关系后，整组存入 person/location 字段
- 出题时用任意组员提问，答案覆盖该组所有成员的记忆

工作方式：
1. 在语料中搜索等价证据（"X 就是 Y""X，即 Y""X，别名 Y"等模式）
2. 构建等价组：合并有交集的组（并查集）
3. 提供 get_equivalence_group() 获取完整等价组
4. 提供 are_equivalent() 判断两个称呼是否等价
"""

from __future__ import annotations
import os
import re
import json
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# 一、等价证据模式（正则）
# ==============================================================================

ALIAS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"([^，。,；;、\n]{1,20})\s*(?:就是|即是|便是|等于|相当于)\s*([^，。,；;、\n]{1,20})"), "direct_equivalence"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:即|也就是|亦即)\s*([^，。,；;、\n]{1,20})"), "aka_formal"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:别名|绰号|号称)\s*([^，。,；;、\n]{1,20})"), "nickname"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[/／]\s*([^，。,；;、\n]{1,20})"), "slash_separated"),
    (re.compile(r"([\u4e00-\u9fff]{2,20})[,，]\s*(?:大名|名|字)\s*([\u4e00-\u9fff]{1,20})"), "formal_name"),
    (re.compile(r"([\u4e00-\u9fff]{2,20})[,，]?\s*(?:别名|绰号|昵称)\s*([\u4e00-\u9fff]{1,20})"), "nickname2"),
    (re.compile(r"([\u4e00-\u9fff]{2,20})是\s*([\u4e00-\u9fff]{1,20})(?:的|就是)"), "be_verb_alias"),
    (re.compile(r"([^，。,；;、\n]{1,20})[,，]?(?:古称|又称|今为|今是)\s*([^，。,；;、\n]{1,10})(?:$|[，。,])"), "place_alias2"),
    (re.compile(r"([^，。,；;、\n]{1,20})[,，]?\s*(?:金陵|今南京|今西安|今洛阳)"), "place_alias"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*史称\s*([^，。,；;、\n]{1,20})"), "historical_alias"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:本名|原名|真名)\s*([^，。,；;、\n]{1,20})"), "real_name"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:世称|号称)\s*([^，。,；;、\n]{1,20})"), "commonly_known_as"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:法号|道号|笔名|艺名)\s*([^，。,；;、\n]{1,20})"), "title_alias"),
    (re.compile(r"([^，。,；;、\n]{1,20})\s*[,，]\s*(?:小名|乳名)\s*([^，。,；;、\n]{1,20})"), "childhood_name"),
]

# 修饰前缀清洗（时间/时代修饰）
_MODIFIER_RE = re.compile(r'^(今天的|现代的|当今的|古时的|旧时的|以前的|当时的|那时的)')

# 关系标记前缀清洗（"字玄德"→"玄德"，"又名齐天大圣"→"齐天大圣"）
_RELATIONAL_PREFIX_RE = re.compile(r'^(字|号|名|又名|又称|又叫|也叫|即|就是)')


def _clean_name(name: str) -> str:
    """清洗提取的名字：去掉修饰前缀和关系标记前缀"""
    name = _MODIFIER_RE.sub('', name).strip()
    name = _RELATIONAL_PREFIX_RE.sub('', name).strip()
    return name


# ==============================================================================
# 二、并查集
# ==============================================================================

class UnionFind:
    """并查集，用于合并有交集的等价组"""

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
        """返回 {根: {组员集合}}"""
        result: Dict[str, Set[str]] = {}
        for x in self._parent:
            root = self.find(x)
            if root not in result:
                result[root] = set()
            result[root].add(x)
        return result


# ==============================================================================
# 三、核心解析类
# ==============================================================================

class AliasResolver:
    """别名等价检测器（v3 等价组模型）"""

    def __init__(self, corpus_dir: str = ""):
        self.corpus_dir = corpus_dir
        self._equivalence_groups: List[Set[str]] = []
        self._name_to_group: Dict[str, int] = {}
        self._evidence: Dict[str, List[str]] = {}
        self._corpus_cache: Optional[str] = None
        self._raw_pairs: List[Tuple[str, str, str]] = []

    # --------------------------------------------------------------------------
    # 公开 API
    # --------------------------------------------------------------------------

    def find_aliases(self, corpus_dir: str = "", memories: List[Dict[str, Any]] = None) -> List[Set[str]]:
        """在语料目录和/或记忆条目中搜索等价证据，构建等价组。"""
        self._equivalence_groups.clear()
        self._name_to_group.clear()
        self._evidence.clear()
        self._raw_pairs.clear()

        if corpus_dir:
            corpus_text = self._read_corpus(corpus_dir)
            self._scan_text_for_aliases(corpus_text)

        if memories:
            for m in memories:
                content = m.get("content", "")
                if content:
                    self._scan_text_for_aliases(content, source=m.get("memory_id", ""))

        self._build_equivalence_groups()
        return self._equivalence_groups

    def are_equivalent(self, name_a: str, name_b: str) -> bool:
        """判断两个称呼是否等价（属于同一等价组）。"""
        if not name_a or not name_b:
            return False
        if name_a == name_b:
            return True
        if name_a not in self._name_to_group or name_b not in self._name_to_group:
            return False
        return self._name_to_group[name_a] == self._name_to_group[name_b]

    def get_equivalence_group(self, name: str) -> Set[str]:
        """获取名称所在的完整等价组。"""
        if name not in self._name_to_group:
            return {name} if name else set()
        return self._equivalence_groups[self._name_to_group[name]]

    def get_all_groups(self) -> List[Set[str]]:
        """获取所有等价组。"""
        return self._equivalence_groups

    def get_evidence(self, name: str) -> List[str]:
        """获取等价关系的语料证据。"""
        if name not in self._name_to_group:
            return []
        return self._evidence.get(str(self._name_to_group[name]), [])

    def export_alias_map(self) -> Dict[str, Any]:
        """导出等价组（用于保存/调试）"""
        return {
            "equivalence_groups": [
                {"members": sorted(list(g)), "evidence": self._evidence.get(str(i), [])}
                for i, g in enumerate(self._equivalence_groups)
            ],
        }

    # --------------------------------------------------------------------------
    # 兼容旧接口
    # --------------------------------------------------------------------------

    @property
    def _alias_map(self) -> Dict[str, List[str]]:
        """兼容属性：返回 {组代表: [其他成员]} 的映射。"""
        result = {}
        for i, group in enumerate(self._equivalence_groups):
            members = sorted(list(group))
            if len(members) < 2:
                continue
            representative = members[0]
            result[representative] = members[1:]
        return result

    # --------------------------------------------------------------------------
    # 内部实现
    # --------------------------------------------------------------------------

    def _build_equivalence_groups(self) -> None:
        """用并查集从原始等价对构建等价组"""
        uf = UnionFind()

        for name_a, name_b, evidence in self._raw_pairs:
            uf.union(name_a, name_b)

        uf_groups = uf.groups()
        self._equivalence_groups = []
        self._name_to_group.clear()
        self._evidence.clear()

        for root, members in uf_groups.items():
            if len(members) < 2:
                continue
            group_idx = len(self._equivalence_groups)
            self._equivalence_groups.append(members)

            for member in members:
                self._name_to_group[member] = group_idx

            # 收集该组所有证据
            group_evidence = []
            for name_a, name_b, evidence in self._raw_pairs:
                if name_a in members and name_b in members:
                    if evidence not in group_evidence:
                        group_evidence.append(evidence)
            self._evidence[str(group_idx)] = group_evidence

    def _read_corpus(self, corpus_dir: str) -> str:
        texts: List[str] = []
        try:
            for root, dirs, files in os.walk(corpus_dir):
                for fn in files:
                    if fn.endswith(('.txt', '.md', '.text')):
                        path = os.path.join(root, fn)
                        try:
                            with open(path, encoding='utf-8') as f:
                                texts.append(f.read())
                        except (OSError, IOError):
                            pass
        except Exception:
            pass
        return "\n".join(texts)

    def _scan_text_for_aliases(self, text: str, source: str = "") -> None:
        """在文本中扫描等价关系"""
        # 策略1: 标准正则模式
        for pattern, pattern_type in ALIAS_PATTERNS:
            for match in pattern.finditer(text):
                self._process_alias_match(match, pattern_type, source)

        # 策略2: "X是...的昵称" 模式
        nick_pattern = re.compile(r"([\u4e00-\u9fff]{2,10})(?:是|就是)\s*[\u4e00-\u9fff]*?的\s*(?:昵称|别名|绰号)")
        for match in nick_pattern.finditer(text):
            alias = match.group(1)
            if alias and len(alias) >= 2:
                known_entity = self._find_known_entity_before(text, match.start())
                if known_entity:
                    self._add_pair(known_entity, alias, source)

        # 策略3: "X，也叫/也称/又称Y"
        also_pattern = re.compile(r"([\u4e00-\u9fff]{2,10})(?:，|,)\s*(?:又名|也叫|也称|又称|也叫作|也写作)\s*([\u4e00-\u9fff]{2,10})")
        for match in also_pattern.finditer(text):
            a, b = match.group(1), match.group(2)
            self._add_pair(a, b, source)

        # 策略4: "X，字Z，人称Y" — 三者等价
        renchen_with_title = re.compile(
            r"([\u4e00-\u9fff]{2,4})\s*[,，]\s*(?:字|号|名)\s*([\u4e00-\u9fff]+)\s*[,，]\s*(?:江湖人称|世称|人称|又称)\s*([\u4e00-\u9fff]{2,10})"
        )
        for match in renchen_with_title.finditer(text):
            main_name, style_name, title = match.group(1), match.group(2), match.group(3)
            self._add_pair(main_name, style_name, source)
            self._add_pair(main_name, title, source)

        # 策略5: "X，人称Y"（没有字/号中间插入，且 X 不以字/号结尾）
        renchen_simple = re.compile(
            r"(?:^|(?<=[，。,；;、\n]))"  # X 在句首或标点后，避免匹配长名字子串
            r"([\u4e00-\u9fff]{2,4})\s*[,，]\s*(?:江湖人称|世称|人称|又称)\s*([\u4e00-\u9fff]{2,10})"
        )
        for match in renchen_simple.finditer(text):
            a, b = match.group(1), match.group(2)
            if a and b and len(b) >= 2:
                self._add_pair(a, b, source)

    def _process_alias_match(self, match: re.Match, pattern_type: str, source: str) -> None:
        """处理一条别名匹配结果"""
        if pattern_type == 'be_verb_alias':
            return

        groups = match.groups()
        if len(groups) < 2:
            return

        raw_a, raw_b = groups[0].strip(), groups[1].strip()
        a = raw_a.split('，')[0].split(',')[0].split('、')[0].strip()
        b = raw_b.split('，')[0].split(',')[0].split('、')[0].strip()

        # 清洗修饰前缀和关系标记前缀
        a = _clean_name(a)
        b = _clean_name(b)

        if not a or not b or len(a) < 2 or len(b) < 2:
            return

        self._add_pair(a, b, source)

    def _add_pair(self, name_a: str, name_b: str, source: str) -> None:
        """添加一对等价关系（暂存，稍后由并查集合并）"""
        if name_a == name_b:
            return

        # 清洗
        name_a = _clean_name(name_a)
        name_b = _clean_name(name_b)
        if name_a == name_b:
            return

        evidence = f"[{source}] {name_a} = {name_b}" if source else f"{name_a} = {name_b}"
        self._raw_pairs.append((name_a, name_b, evidence))

    def _find_known_entity_before(self, text: str, pos: int) -> Optional[str]:
        """在 pos 之前的文本中查找已知的实体名"""
        before = text[:pos]
        search_window = before[-60:] if len(before) > 60 else before

        for name_a, name_b, _ in self._raw_pairs:
            if name_a in search_window:
                return name_a
            if name_b in search_window:
                return name_b
        return None


# ==============================================================================
# 四、便捷函数
# ==============================================================================

def extract_aliases_from_text(text: str) -> List[Dict[str, Any]]:
    """从文本中提取所有等价组"""
    resolver = AliasResolver()
    resolver._scan_text_for_aliases(text)
    resolver._build_equivalence_groups()
    return [
        {"members": sorted(list(g)), "evidence": resolver._evidence.get(str(i), [])}
        for i, g in enumerate(resolver._equivalence_groups)
    ]


# ==============================================================================
# 五、自测
# ==============================================================================

if __name__ == "__main__":
    test_texts = [
        "林黛玉，大名颦儿，林妹妹是贾府上下对她的昵称。",
        "刘备，字玄德，江湖人称刘皇叔。",
        "金陵，也就是今天的南京。",
        "孙悟空，又名齐天大圣，又称弼马温。",
        "诸葛亮，字孔明，卧龙先生是世人对他的称呼。",
        "李商隐，字义山，号玉溪生。",
        "张三丰，道号张三丰，武当派创始人。",
        "曹操，字孟德，小名吉利。",
        "西安，古称长安。",
        "贾宝玉和林黛玉经常一起读书。",  # 不构成等价关系
        "慕容复，人称南慕容。",
    ]

    combined_text = "\n".join(test_texts)
    resolver = AliasResolver()
    resolver._scan_text_for_aliases(combined_text)
    resolver._build_equivalence_groups()

    print("等价组检测结果：")
    for i, group in enumerate(resolver._equivalence_groups):
        print(f"  组{i+1}: {sorted(list(group))}")
        print(f"    证据: {resolver._evidence.get(str(i), [])}")

    # 测试 are_equivalent
    test_pairs = [
        ("林黛玉", "林妹妹", True),
        ("林黛玉", "颦儿", True),
        ("刘备", "刘皇叔", True),
        ("刘备", "玄德", True),
        ("金陵", "南京", True),
        ("孙悟空", "齐天大圣", True),
        ("孙悟空", "弼马温", True),
        ("孙悟空", "唐僧", False),
        ("曹操", "刘备", False),
        ("曹操", "孟德", True),
        ("西安", "长安", True),
    ]

    print("\n等价判断测试：")
    all_pass = True
    for a, b, expected in test_pairs:
        result = resolver.are_equivalent(a, b)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} are_equivalent('{a}', '{b}') = {result} (期望 {expected})")

    # 检查不应该出现的前缀
    print("\n清洗质量检查：")
    bad_prefixes = False
    for i, group in enumerate(resolver._equivalence_groups):
        for member in group:
            if member.startswith("字") or member.startswith("又名") or member.startswith("又称"):
                print(f"  ❌ 组{i+1} 含有未清洗前缀: '{member}'")
                bad_prefixes = True
    if not bad_prefixes:
        print("  ✅ 无残留关系标记前缀")

    if all_pass and not bad_prefixes:
        print("\n🎉 全部测试通过！")
    else:
        print("\n⚠️ 存在问题，需修复")
