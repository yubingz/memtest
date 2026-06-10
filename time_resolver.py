#!/usr/bin/env python3
"""MemTest v3 时间关系解析器

解析记忆条目中的相对时间，填充 time_ref_id 和 time_offset_days。
断链不补：时间线索不够形成完整时序链，就让它断着。
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# 一、相对时间词映射表（单位：天）
# ==============================================================================

RELATIVE_TIME_PATTERNS = {
    "当日": 0, "当天": 0, "同日": 0, "此刻": 0, "此时": 0, "眼下": 0, "现在": 0,
    "次日": 1, "第二天": 1, "隔天": 1, "翌日": 1, "第二日": 1,
    "昨天": -1, "昨日": -1, "前一天": -1, "前日": -1, "前天": -1,
    "三天后": 3, "两天后": 2, "数日后": 5, "数天后": 5, "不久": 2,
    "一周后": 7, "七天后": 7,
    "半个月后": 15, "半月后": 15, "十几天后": 12,
    "一个月后": 30, "一月后": 30, "三十天后": 30, "次月": 30,
    "两个月后": 60, "三个月后": 90, "半年后": 180, "六个月后": 180,
    "一年后": 365, "次年": 365, "第二年": 365,
    "两年后": 730, "三年后": 1095, "数年后": 1825, "多年后": 1825,
    "很多年后": 7300, "数载后": 730,
    "前一天": -1, "前一年": -365,
}
# 注意：更多年后（4字以上）的模式放在前面，确保更长匹配优先
_EXTRA_PATTERNS = [
    ("很多年后", 7300), ("数十年后", 10950), ("许久之后", 9999),
]

# 正则匹配相对时间表达式
_patterns_sorted = sorted(RELATIVE_TIME_PATTERNS.keys(), key=len, reverse=True)
_PATTERN_STR = "|".join(re.escape(k) for k in _patterns_sorted)
RELATIVE_TIME_REGEX = re.compile("(" + _PATTERN_STR + ")")

# 解析"X天后""X月后""X年后"等数字形式（支持阿拉伯数字和中文数字）
_NUMBER_PATTERN = re.compile(
    r"(?:(?P<num>\d+)|(?P<cnum>[一二两三四五六七八九十百千万亿零]+))"
    r"\s*(?P<unit>天|日|个月|月|年|周|季)?"
    r"\s*(?P<dir>后|之前|以前|之后|以内|之内|前)?",
    re.IGNORECASE
)

# 中文数字转换
CN_NUM_MAP = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "百": 100, "千": 1000, "万": 10000, "亿": 100000000,
    "两": 2, "几": 3, "数": 3, "多": 5, "半": 0.5,
}


def _parse_chinese_number(cnum: str) -> Optional[int]:
    """解析中文数字字符串，支持简单复合数字如'十三'、'二十一'、'一百零五'"""
    if not cnum:
        return None
    
    # 单字直接查表
    if len(cnum) == 1 and cnum in CN_NUM_MAP:
        val = CN_NUM_MAP[cnum]
        return int(val) if val == int(val) else None
    
    # 逐位解析（简化版，支持常见的组合）
    result = 0
    last_unit = 1
    i = 0
    while i < len(cnum):
        char = cnum[i]
        if char in CN_NUM_MAP:
            val = CN_NUM_MAP[char]
            if val >= 10:  # 是单位（十、百、千、万、亿）
                if result == 0:
                    result = val
                else:
                    result = result * val if last_unit < 10 else result + val
                last_unit = val
            else:
                # 是个位数字
                if last_unit >= 10 and i > 0:
                    result += val
                else:
                    result = result * 10 + val if result > 0 else val
        i += 1
    
    return result if result > 0 else None

# ==============================================================================
# 二、绝对时间解析（基础）
# ==============================================================================

ABSOLUTE_TIME_PATTERNS = [
    (r"\d{4}-\d{1,2}-\d{1,2}", "iso"),
    (r"\d{4}/\d{1,2}/\d{1,2}", "iso"),
    (r"\d{4}年\d{1,2}月\d{1,2}日", "cn_full"),
    (r"\d{4}年\d{1,2}月", "cn_month"),
    (r"\d{4}年", "cn_year"),
]

def has_absolute_time(text: str) -> bool:
    """判断文本是否包含绝对时间"""
    if not text:
        return False
    for pattern, _ in ABSOLUTE_TIME_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

# ==============================================================================
# 三、核心解析
# ==============================================================================

def parse_relative_days(text: str) -> Optional[int]:
    """从相对时间文本中解析出天数偏移（正=之后，负=之前）"""
    if not text:
        return None
    text = text.strip()

    # 1. 精确匹配表（按长度降序，避免"数年后"先匹配"很多年后"）
    sorted_patterns = sorted(RELATIVE_TIME_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True)
    for pattern, days in sorted_patterns:
        if pattern in text:
            return days
    # 2. 额外长模式
    for pattern, days in _EXTRA_PATTERNS:
        if pattern in text:
            return days

    # 3. 正则匹配"数字+单位"形式（支持阿拉伯数字和中文数字）
    m = _NUMBER_PATTERN.search(text)
    if m:
        num_str = m.group("num")
        cnum_str = m.group("cnum")
        unit = m.group("unit")
        dir_str = m.group("dir")
        
        if num_str:
            try:
                num = int(num_str)
            except ValueError:
                return None
        elif cnum_str:
            num = _parse_chinese_number(cnum_str)
            if num is None:
                return None
        else:
            return None
        
        unit_days = {"天": 1, "日": 1, "周": 7, "个月": 30, "月": 30, "年": 365}
        if unit and unit in unit_days:
            days = num * unit_days[unit]
            # 方向：后/之后/以后/以内/之内 = 正；前/之前/以前 = 负
            if dir_str in ("前", "之前", "以前"):
                return -days
            return days

    return None


class TimeResolver:
    """时间关系解析器"""

    def __init__(self, corpus_dir: str = ""):
        self.corpus_dir = corpus_dir

    def resolve_time_relations(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析所有记忆的时间关系，填充 time_ref_id 和 time_offset_days"""
        if not memories:
            return memories

        mem_index = {m["memory_id"]: i for i, m in enumerate(memories)}

        # 识别有绝对时间的记忆（作为锚点）
        anchored = [i for i, m in enumerate(memories)
                   if has_absolute_time(m.get("time_absolute", ""))]

        for i, m in enumerate(memories):
            if m.get("time_ref_id") is not None:
                continue

            rel_text = m.get("time_relative", "")
            abs_text = m.get("time_absolute", "")

            if has_absolute_time(abs_text):
                m["time_offset_days"] = None
                m["time_ref_id"] = None
                continue

            if not rel_text:
                m["time_offset_days"] = None
                m["time_ref_id"] = None
                continue

            offset = parse_relative_days(rel_text)
            if offset is None:
                m["time_offset_days"] = None
                m["time_ref_id"] = None
                continue

            # 寻找最近的锚点
            ref_candidates = []
            if offset >= 0:
                # 发生在当前记忆之后 → 找文本顺序上后面的锚点（j > i）
                for j in anchored:
                    if j > i:
                        ref_candidates.append((j, abs(j - i)))
            else:
                # 发生在当前记忆之前 → 找文本顺序上前面的锚点（j < i）
                for j in anchored:
                    if j < i:
                        ref_candidates.append((j, abs(j - i)))

            if ref_candidates:
                ref_candidates.sort(key=lambda x: x[1])
                ref_idx = ref_candidates[0][0]
                ref_mem = memories[ref_idx]
                m["time_ref_id"] = ref_mem["memory_id"]
                m["time_offset_days"] = offset
            else:
                m["time_offset_days"] = None
                m["time_ref_id"] = None

        return memories

    def validate_time_refs(self, memories: List[Dict[str, Any]]) -> List[str]:
        """校验所有 time_ref_id 是否指向存在的 memory_id"""
        errors = []
        valid_ids = {m["memory_id"] for m in memories}
        for m in memories:
            ref_id = m.get("time_ref_id")
            if ref_id is not None and ref_id not in valid_ids:
                errors.append(
                    f"记忆 {m.get('memory_id', '?')} 的 time_ref_id='{ref_id}' 指向不存在的记忆"
                )
        return errors


if __name__ == "__main__":
    resolver = TimeResolver()

    test_memories = [
        {"memory_id": "MEM001", "content": "1980年春天，张无忌随父母回到中原。",
         "time_absolute": "1980年春", "time_relative": None, "time_ref_id": None,
         "time_offset_days": None, "person": ["张无忌"]},
        {"memory_id": "MEM002", "content": "三年后，他父母在武当山上遭遇不幸。",
         "time_absolute": None, "time_relative": "三年后", "time_ref_id": None,
         "time_offset_days": None, "person": ["张无忌父母"]},
        {"memory_id": "MEM003", "content": "又过了很多年，张无忌在光明顶独战六大门派。",
         "time_absolute": None, "time_relative": "很多年后", "time_ref_id": None,
         "time_offset_days": None, "person": ["张无忌"]},
    ]

    updated = resolver.resolve_time_relations(test_memories)
    print("时间关系解析结果：")
    for m in updated:
        print(f"  {m['memory_id']}: ref={m['time_ref_id']}, offset={m['time_offset_days']}天, rel={m['time_relative']}")

    errors = resolver.validate_time_refs(updated)
    if errors:
        print(f"\nX 校验错误: {errors}")
    else:
        print("\nOK time_ref_id 校验通过")

    test_cases = [
        ("三年后", 1095), ("三天后", 3), ("次日", 1), ("一周后", 7),
        ("半年后", 180), ("次年", 365), ("数日后", 5), ("很多年后", 7300),
        ("", None), ("不确定", None),
    ]
    print("\n相对时间解析测试：")
    for text, expected in test_cases:
        result = parse_relative_days(text)
        status = "OK" if result == expected else "X"
        print(f"  [{status}] parse_relative_days('{text}') = {result} (期望 {expected})")
