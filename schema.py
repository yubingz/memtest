#!/usr/bin/env python3
"""MemTest v4 统一 Schema 定义

统一 v4 的记忆条目、查询条目、存储层、数据库顶层 schema，
所有模块共用这一套定义。

设计原则：
- Memory = Understanding：测记没记住，不测懂没懂
- 只存原文：存储层只给 memory_id + content
- 别名只认语料证据：语料说了才算
- 时间有什么记什么：断链不补
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

# ==============================================================================
# 一、v4 Schema 定义
# ==============================================================================

# 记忆条目（内部完整格式，用于出题，不喂给被测系统）
MEMORY_SCHEMA_V3: Dict[str, Any] = {
    "memory_id": str,       # 唯一标识，格式如 "MEM000001"
    "content": str,         # 原文（也出现在存储层）
    "person": list,        # 人物列表（可多人），元素为 str
    "time_absolute": (str, type(None)),   # 绝对时间，YYYY-MM-DD 或原文表述，可空
    "time_relative": (str, type(None)),   # 相对时间原文表述，可空
    "time_ref_id": (str, type(None)),     # 相对时间参照的记忆ID，可空
    "time_offset_days": (int, type(None)), # 与参照记忆的天数差，正=之后，负=之前，可空
    "location": (str, type(None)),        # 地点，可空
    "event_type": (str, type(None)),      # 事件类型，可空
    "source": str,                           # 来源（书名/文章名），必填
    "tags": list,         # 标签列表，元素为 str
    "difficulty": str,     # easy / medium / hard
}

# 查询条目
QUERY_SCHEMA_V3: Dict[str, Any] = {
    "query_id": str,       # 唯一标识，格式如 "Q0001"
    "query_text": str,     # 查询文本
    "query_type": str,     # 时序推理 / 因果推理 / 别名查询 / 事实检索 / 对比推理 / 负样本
    "test_dimension": str, # 评测维度
    "expected_memory_ids": list,  # 预期命中的记忆ID列表
    "expected_answer": str,       # 基于理解的正确答案
    "difficulty": str,            # easy / medium / hard
    "is_negative": bool,          # 是否负样本
}

# 存储层格式（只喂给被测系统的）
STORAGE_SCHEMA: Dict[str, Any] = {
    "memory_id": str,  # 唯一标识
    "content": str,    # 原文
}

# 数据库顶层
DATABASE_SCHEMA_V3: Dict[str, Any] = {
    "database_info": dict,   # 数据库元信息
    "memories": list,        # 记忆条目列表
    "queries": list,         # 查询条目列表
}

# 数据库信息 schema
DATABASE_INFO_SCHEMA: Dict[str, Any] = {
    "name": str,
    "version": str,          # 固定 "3.0.0"
    "description": (str, type(None)),
    "created_at": str,       # ISO 8601 时间
    "source": str,
    "total_memories": int,
    "total_queries": int,
    "principles": dict,      # 设计原则标记
}

# 设计原则标记（固定为 True）
PRINCIPLES: Dict[str, bool] = {
    "memory_not_understanding": True,
    "content_only_storage": True,
    "alias_from_corpus_only": True,
    "time_as_is_no_inference": True,
}

# ==============================================================================
# 二、必填字段定义
# ==============================================================================

MEMORY_REQUIRED_V3: List[str] = [
    "memory_id",
    "content",
]

QUERY_REQUIRED_V3: List[str] = [
    "query_id",
    "query_text",
    "query_type",
    "test_dimension",
    "expected_memory_ids",
    "expected_answer",
    "difficulty",
    "is_negative",
]

# 允许的枚举值
ALLOWED_QUERY_TYPES: List[str] = [
    "时序推理", "因果推理", "别名查询", "事实检索", "对比推理", "负样本",
    "temporal", "causal", "alias", "fact", "contrast", "negative",
    # 兼容旧名称
    "时序推理链", "因果推理链", "对比推理链",
    "人物检索", "地点检索", "时间检索", "事件检索",
    "组合推理", "组合检索",
]

ALLOWED_DIFFICULTIES: List[str] = ["easy", "medium", "hard", "简单", "中等", "困难"]

# ==============================================================================
# 三、校验函数
# ==============================================================================

class SchemaValidationError(Exception):
    """Schema 校验失败异常"""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Schema 校验失败: {'; '.join(errors)}")


def _get_type_name(tp: Any) -> str:
    """获取类型的友好名称"""
    if tp is str:
        return "str"
    if tp is int:
        return "int"
    if tp is bool:
        return "bool"
    if tp is list:
        return "list"
    if tp is dict:
        return "dict"
    if tp in (str, int, bool, list, dict, type(None)):
        return str(tp)
    if isinstance(tp, tuple):
        return " | ".join(_get_type_name(t) for t in tp)
    return str(tp)


def _check_field(value: Any, expected_type: Any, field_name: str) -> Optional[str]:
    """检查单个字段的类型是否正确，返回错误信息或 None"""
    if expected_type is str:
        if not isinstance(value, str):
            return f"字段 {field_name} 应为 str，实际为 {type(value).__name__}"
    elif expected_type is int:
        if not isinstance(value, int) or isinstance(value, bool):
            return f"字段 {field_name} 应为 int，实际为 {type(value).__name__}"
    elif expected_type is bool:
        if not isinstance(value, bool):
            return f"字段 {field_name} 应为 bool，实际为 {type(value).__name__}"
    elif expected_type is list:
        if not isinstance(value, list):
            return f"字段 {field_name} 应为 list，实际为 {type(value).__name__}"
    elif expected_type is dict:
        if not isinstance(value, dict):
            return f"字段 {field_name} 应为 dict，实际为 {type(value).__name__}"
    elif isinstance(expected_type, tuple):
        # Union 类型
        if isinstance(value, bool) and bool in expected_type:
            return None  # bool 是 int 的子类，但 Union 中显式包含 bool
        ok = any(_check_field(value, t, field_name) is None for t in expected_type)
        if not ok:
            return f"字段 {field_name} 类型错误，期望 {_get_type_name(expected_type)}，实际为 {type(value).__name__}"
    elif expected_type is type(None):
        if value is not None:
            return f"字段 {field_name} 应为 None，实际为 {type(value).__name__}"
    return None


def validate_memory(memory: Dict[str, Any], strict: bool = False) -> List[str]:
    """校验单条记忆条目是否符合 v4 schema。

    Args:
        memory: 记忆条目字典
        strict: 若 True，连可选字段也校验类型；若 False，只校验必填字段

    Returns:
        错误信息列表，空列表表示校验通过
    """
    errors: List[str] = []

    # 1. 必填字段存在性
    for field in MEMORY_REQUIRED_V3:
        if field not in memory:
            errors.append(f"缺少必填字段: {field}")

    # 2. 必填字段类型
    for field in MEMORY_REQUIRED_V3:
        if field in memory:
            err = _check_field(memory[field], MEMORY_SCHEMA_V3.get(field, str), field)
            if err:
                errors.append(err)

    # 3. content 非空
    if "content" in memory and not memory["content"].strip():
        errors.append("字段 content 不能为空")

    # 4. memory_id 格式（基本检查）
    if "memory_id" in memory:
        mid = memory["memory_id"]
        if not mid or not isinstance(mid, str):
            errors.append(f"memory_id 必须为非空字符串，实际为 {type(mid).__name__}")

    # 5. difficulty 枚举
    if "difficulty" in memory and memory["difficulty"] not in ALLOWED_DIFFICULTIES:
        errors.append(f"difficulty 值非法: {memory['difficulty']}，允许值: {ALLOWED_DIFFICULTIES}")

    # 6. time_offset_days 必须为 int
    if "time_offset_days" in memory and memory["time_offset_days"] is not None:
        if not isinstance(memory["time_offset_days"], int):
            errors.append(f"time_offset_days 应为 int 或 None，实际为 {type(memory['time_offset_days']).__name__}")

    # 7. time_ref_id 若有值则必须为字符串
    if "time_ref_id" in memory and memory["time_ref_id"] is not None:
        if not isinstance(memory["time_ref_id"], str):
            errors.append(f"time_ref_id 应为 str 或 None，实际为 {type(memory['time_ref_id']).__name__}")

    # 8. strict 模式：检查所有字段类型
    if strict:
        for field, expected_type in MEMORY_SCHEMA_V3.items():
            if field in memory and memory[field] is not None:
                err = _check_field(memory[field], expected_type, field)
                if err:
                    errors.append(err)

    return errors


def validate_query(query: Dict[str, Any]) -> List[str]:
    """校验单条查询条目是否符合 v4 schema。

    Args:
        query: 查询条目字典

    Returns:
        错误信息列表，空列表表示校验通过
    """
    errors: List[str] = []

    # 1. 必填字段存在性
    for field in QUERY_REQUIRED_V3:
        if field not in query:
            errors.append(f"缺少必填字段: {field}")

    # 2. 必填字段类型
    for field in QUERY_REQUIRED_V3:
        if field in query:
            expected = QUERY_SCHEMA_V3.get(field, str)
            err = _check_field(query[field], expected, field)
            if err:
                errors.append(err)

    # 3. query_type 枚举
    if "query_type" in query and query["query_type"] not in ALLOWED_QUERY_TYPES:
        errors.append(f"query_type 值非法: {query['query_type']}，允许值: {ALLOWED_QUERY_TYPES}")

    # 4. difficulty 枚举
    if "difficulty" in query and query["difficulty"] not in ALLOWED_DIFFICULTIES:
        errors.append(f"difficulty 值非法: {query['difficulty']}，允许值: {ALLOWED_DIFFICULTIES}")

    # 5. expected_memory_ids 必须为 list
    if "expected_memory_ids" in query and not isinstance(query["expected_memory_ids"], list):
        errors.append(f"expected_memory_ids 应为 list，实际为 {type(query['expected_memory_ids']).__name__}")

    # 6. is_negative 与 expected_memory_ids 的一致性
    if "is_negative" in query and "expected_memory_ids" in query:
        if query["is_negative"] and query["expected_memory_ids"]:
            errors.append("负样本的 expected_memory_ids 必须为空列表")
        if not query["is_negative"] and not query["expected_memory_ids"]:
            errors.append("正样本的 expected_memory_ids 不能为空")

    # 7. query_text 非空
    if "query_text" in query and not query["query_text"].strip():
        errors.append("字段 query_text 不能为空")

    return errors


def validate_storage(storage_entry: Dict[str, Any]) -> List[str]:
    """校验单条存储层条目（只含 memory_id + content）。

    Returns:
        错误信息列表，空列表表示校验通过
    """
    errors: List[str] = []

    if "memory_id" not in storage_entry:
        errors.append("缺少必填字段: memory_id")
    elif not isinstance(storage_entry["memory_id"], str) or not storage_entry["memory_id"]:
        errors.append("memory_id 必须为非空字符串")

    if "content" not in storage_entry:
        errors.append("缺少必填字段: content")
    elif not isinstance(storage_entry["content"], str) or not storage_entry["content"].strip():
        errors.append("content 必须为非空字符串")

    return errors


def validate_database(db: Dict[str, Any]) -> Dict[str, Any]:
    """校验整个数据库是否符合 v4 schema。

    Args:
        db: 数据库字典

    Returns:
        {
            "valid": bool,
            "errors": List[str],    # 致命错误
            "warnings": List[str],  # 警告
            "stats": Dict          # 统计信息
        }
    """
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {
        "total_memories": 0,
        "total_queries": 0,
        "memory_errors": 0,
        "query_errors": 0,
        "negative_count": 0,
        "query_type_counts": {},
    }

    # 1. 顶层结构
    if "memories" not in db:
        errors.append("缺少顶层字段: memories")
    if "queries" not in db:
        errors.append("缺少顶层字段: queries")

    # 2. database_info
    info = db.get("database_info", {})
    if not info:
        warnings.append("缺少 database_info")
    else:
        if info.get("version") != "4.0.0":
            warnings.append(f"database_info.version 应为 4.0.0，当前为 {info.get('version', 'missing')}")

    # 3. 校验每条记忆
    memories = db.get("memories", [])
    stats["total_memories"] = len(memories)

    memory_ids: set = set()
    for i, m in enumerate(memories):
        mid = m.get("memory_id", f"<index {i}>")
        mem_errors = validate_memory(m)
        if mem_errors:
            for e in mem_errors:
                errors.append(f"记忆 {mid}: {e}")
            stats["memory_errors"] += 1
        if mid in memory_ids:
            errors.append(f"memory_id 重复: {mid}")
        memory_ids.add(mid)

    # 4. 校验每条查询
    queries = db.get("queries", [])
    stats["total_queries"] = len(queries)

    query_ids: set = set()
    for i, q in enumerate(queries):
        qid = q.get("query_id", f"<index {i}>")
        q_errors = validate_query(q)
        if q_errors:
            for e in q_errors:
                errors.append(f"查询 {qid}: {e}")
            stats["query_errors"] += 1

        if qid in query_ids:
            errors.append(f"query_id 重复: {qid}")
        query_ids.add(qid)

        if q.get("is_negative"):
            stats["negative_count"] += 1

        qt = q.get("query_type", "unknown")
        stats["query_type_counts"][qt] = stats["query_type_counts"].get(qt, 0) + 1

    # 5. expected_memory_ids 指向有效性
    for q in queries:
        qid = q.get("query_id", "?")
        for mid in q.get("expected_memory_ids", []):
            if mid not in memory_ids:
                errors.append(f"查询 {qid} 的 expected_memory_ids 包含无效 ID: {mid}")

    # 6. 时间引用有效性（time_ref_id 必须指向存在的 memory_id）
    for m in memories:
        ref_id = m.get("time_ref_id")
        if ref_id and ref_id not in memory_ids:
            errors.append(f"记忆 {m.get('memory_id', '?')} 的 time_ref_id 指向不存在: {ref_id}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


# ==============================================================================
# 四、工具函数
# ==============================================================================

def make_memory_id(index: int, prefix: str = "MEM") -> str:
    """生成标准格式的 memory_id"""
    return f"{prefix}{index:06d}"


def make_query_id(index: int) -> str:
    """生成标准格式的 query_id"""
    return f"Q{index:04d}"


def memory_to_storage(memory: Dict[str, Any]) -> Dict[str, str]:
    """将完整记忆条目转换为存储层格式（只含 memory_id + content）"""
    return {
        "memory_id": memory["memory_id"],
        "content": memory["content"],
    }


def build_database_info(
    name: str,
    description: str = "",
    source: str = "",
) -> Dict[str, Any]:
    """构建数据库元信息"""
    return {
        "name": name,
        "version": "4.0.0",
        "description": description,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "total_memories": 0,
        "total_queries": 0,
        "principles": PRINCIPLES.copy(),
    }


def finalize_database(
    db: Dict[str, Any],
    name: str = "MemTest Database",
    description: str = "",
    source: str = "",
) -> Dict[str, Any]:
    """填充数据库元信息，返回最终数据库"""
    info = db.get("database_info", {})
    info["name"] = name
    info["version"] = "4.0.0"
    info["description"] = description
    info["source"] = source
    info["total_memories"] = len(db.get("memories", []))
    info["total_queries"] = len(db.get("queries", []))
    info["principles"] = PRINCIPLES.copy()
    info.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    db["database_info"] = info
    return db


# ==============================================================================
# 五、向后兼容工具
# ==============================================================================

def is_v4_format(db: Dict[str, Any]) -> bool:
    """检测数据库是否为 v4 格式"""
    info = db.get("database_info", {})
    return info.get("version", "").startswith("4.") or info.get("version") == "4.0.0"


def normalize_v2_memory(m: Dict[str, Any]) -> Dict[str, Any]:
    """将 v2 格式记忆条目转换为 v4 格式（只做字段映射，不做语义转换）"""
    # 兼容 v2 的嵌套 person/name → person list
    person = m.get("person", {})
    if isinstance(person, str):
        person_list = [person] if person else []
    elif isinstance(person, dict):
        name = person.get("name", "")
        partner = person.get("partner", "")
        person_list = [n for n in [name, partner] if n]
    else:
        person_list = []

    # 兼容 v2 的嵌套 time/absolute
    time_data = m.get("time", {})
    if isinstance(time_data, str):
        time_abs = time_data
        time_rel = ""
    elif isinstance(time_data, dict):
        time_abs = time_data.get("absolute", "") or time_data.get("timestamp", "")
        time_rel = time_data.get("relative", "")
    else:
        time_abs = ""
        time_rel = ""

    # 兼容 v2 的嵌套 location/city
    loc_data = m.get("location", {})
    if isinstance(loc_data, str):
        location = loc_data
    elif isinstance(loc_data, dict):
        city = loc_data.get("city", "")
        place = loc_data.get("place", "")
        location = f"{city} {place}".strip() if city or place else ""
    else:
        location = ""

    # 事件类型
    evt_data = m.get("event", {})
    if isinstance(evt_data, str):
        event_type = evt_data
    elif isinstance(evt_data, dict):
        event_type = evt_data.get("type", "") or evt_data.get("action", "")
    else:
        event_type = ""

    return {
        "memory_id": m.get("memory_id", ""),
        "content": m.get("content", ""),
        "person": person_list,
        "time_absolute": time_abs or None,
        "time_relative": time_rel or None,
        "time_ref_id": None,
        "time_offset_days": None,
        "location": location or None,
        "event_type": event_type or None,
        "source": m.get("source", ""),
        "tags": m.get("tags", []),
        "difficulty": m.get("difficulty", "medium"),
    }


if __name__ == "__main__":
    # 简单自测
    ok = True

    # 测试 validate_memory
    errs = validate_memory({"memory_id": "MEM001", "content": "测试内容"})
    assert not errs, f"valid memory failed: {errs}"

    errs = validate_memory({"content": "测试内容"})
    assert "memory_id" in str(errs), f"should catch missing memory_id: {errs}"

    errs = validate_memory({"memory_id": "MEM001", "content": ""})
    assert any("空" in e for e in errs), f"should catch empty content: {errs}"

    # 测试 validate_query
    errs = validate_query({
        "query_id": "Q001",
        "query_text": "林黛玉是谁？",
        "query_type": "别名查询",
        "test_dimension": "别名等价",
        "expected_memory_ids": ["MEM001"],
        "expected_answer": "林黛玉就是林妹妹",
        "difficulty": "medium",
        "is_negative": False,
    })
    assert not errs, f"valid query failed: {errs}"

    errs = validate_query({
        "query_id": "Q001",
        "query_text": "测试",
        "query_type": "负样本",
        "test_dimension": "负样本",
        "expected_memory_ids": ["MEM001"],  # 负样本不应有 expected_memory_ids
        "expected_answer": "",
        "difficulty": "hard",
        "is_negative": True,
    })
    assert any("负样本的 expected_memory_ids 必须为空" in e for e in errs), \
        f"should catch negative with expected_ids: {errs}"

    # 测试 validate_database
    db = {
        "database_info": {"version": "4.0.0", "name": "Test"},
        "memories": [
            {"memory_id": "MEM001", "content": "测试", "person": [], "tags": [], "difficulty": "easy",
             "time_absolute": None, "time_relative": None, "time_ref_id": None, "time_offset_days": None,
             "location": None, "event_type": None, "source": "测试"},
        ],
        "queries": [
            {"query_id": "Q001", "query_text": "测试？", "query_type": "事实检索",
             "test_dimension": "fact", "expected_memory_ids": ["MEM001"],
             "expected_answer": "答案", "difficulty": "easy", "is_negative": False},
        ],
    }
    result = validate_database(db)
    assert result["valid"], f"valid db should pass: {result['errors']}"

    # 测试 storage 转换
    storage = memory_to_storage(db["memories"][0])
    assert list(storage.keys()) == ["memory_id", "content"], f"storage keys wrong: {storage}"

    print("✅ schema.py 自测通过")
