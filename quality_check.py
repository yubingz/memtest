#!/usr/bin/env python3
"""MemTest 质量校验脚本 — v4 only

用法:
    python quality_check.py test_db.json
    python quality_check.py test_db.json --verbose

检查项:
    1. 记忆ID唯一性
    2. 查询ID唯一性
    3. 查询指向有效记忆
    4. 负样本标记正确
    5. content 长度分布
    6. 查询维度分布
    7. 时间引用有效性（time_ref_id 指向存在的 memory_id）
    8. 别名等价语料证据检查
    9. 负样本比例
    10. source字段完整性
"""

import json
import sys
import argparse
from collections import Counter

try:
    from schema import validate_database as _validate_database
except ImportError:
    _validate_database = None


def check(db: dict, verbose: bool = False) -> dict:
    """执行 v4 格式质量检查"""
    memories = db.get("memories", [])
    queries = db.get("queries", [])
    mem_ids = {m.get("memory_id") for m in memories}

    errors = []
    warnings = []
    stats = {}

    # 1. Memory ID uniqueness
    mem_id_list = [m.get("memory_id", "") for m in memories]
    dup_mems = len(mem_id_list) - len(set(mem_id_list))
    stats["memory_count"] = len(memories)
    if dup_mems > 0:
        errors.append(f"Memory ID重复: {dup_mems}个")

    # 2. Query ID uniqueness
    q_id_list = [q.get("query_id", "") for q in queries]
    dup_qs = len(q_id_list) - len(set(q_id_list))
    stats["query_count"] = len(queries)
    if dup_qs > 0:
        errors.append(f"Query ID重复: {dup_qs}个")

    # 3. No missing references
    missing_refs = 0
    for q in queries:
        for mid in q.get("expected_memory_ids", []):
            if mid not in mem_ids:
                missing_refs += 1
    if missing_refs > 0:
        errors.append(f"查询引用不存在的记忆: {missing_refs}个")
    stats["missing_refs"] = missing_refs

    # 4. Negative samples marked correctly
    neg_errors = 0
    for q in queries:
        if q.get("is_negative"):
            if q.get("expected_memory_ids"):
                neg_errors += 1
    if neg_errors > 0:
        errors.append(f"负样本有expected_memory_ids: {neg_errors}个")

    # 5. Content length distribution
    if memories:
        lengths = [len(m.get("content", "")) for m in memories]
        short = sum(1 for l in lengths if l < 10)
        long_ = sum(1 for l in lengths if l > 500)
        if short > 0:
            warnings.append(f"内容过短(<10字)的记忆: {short}条")
        if long_ > len(memories) * 0.5:
            warnings.append(f"内容过长(>500字)的记忆占比: {long_}/{len(memories)}")
        stats["content_length"] = {
            "min": min(lengths), "max": max(lengths),
            "avg": round(sum(lengths) / len(lengths), 1),
        }

    # 6. Query dimension distribution
    qtypes = Counter(q.get("query_type", "unknown") for q in queries)
    stats["query_types"] = dict(qtypes)

    # 7. Time reference validity
    broken_time_refs = 0
    for m in memories:
        ref_id = m.get("time_ref_id")
        if ref_id and ref_id not in mem_ids:
            broken_time_refs += 1
    if broken_time_refs > 0:
        warnings.append(f"time_ref_id指向不存在的记忆: {broken_time_refs}条")
    stats["broken_time_refs"] = broken_time_refs

    # 8. Alias evidence check
    alias_evidence_count = 0
    for m in memories:
        for ae in m.get("alias_evidence", []):
            entity = ae.get("entity", "")
            alias = ae.get("alias", "")
            if entity and alias:
                alias_evidence_count += 1
    stats["alias_evidence_count"] = alias_evidence_count

    # 9. Negative sample ratio
    neg_count = sum(1 for q in queries if q.get("is_negative"))
    if queries:
        neg_ratio = neg_count / len(queries)
        stats["neg_ratio"] = round(neg_ratio, 3)
        if neg_ratio < 0.05:
            warnings.append(f"负样本比例过低: {neg_ratio:.1%}")
        elif neg_ratio > 0.4:
            warnings.append(f"负样本比例过高: {neg_ratio:.1%}")

    # 10. Source completeness
    no_source = sum(1 for m in memories if not m.get("source"))
    if no_source > 0:
        warnings.append(f"缺少source字段: {no_source}条记忆")
    stats["source_missing"] = no_source

    # Schema validation (if available)
    if _validate_database:
        try:
            _validate_database(db)
        except Exception as e:
            errors.append(f"Schema校验失败: {e}")

    # Coverage check
    hit_memories = set()
    for q in queries:
        for mid in q.get("expected_memory_ids", []):
            hit_memories.add(mid)
    coverage = len(hit_memories) / len(memories) if memories else 0
    stats["memory_coverage"] = round(coverage, 3)
    if coverage < 0.8:
        warnings.append(f"记忆覆盖率低: {coverage:.1%}")

    passed = len(errors) == 0
    result = {
        "passed": passed,
        "errors": len(errors),
        "warnings": len(warnings),
        "error_list": errors,
        "warning_list": warnings,
        "stats": stats,
    }

    if verbose:
        print(f"\n{'✅' if passed else '❌'} 质量检查: {'通过' if passed else '失败'} "
              f"({len(errors)} 错误, {len(warnings)} 警告)")
        for e in errors:
            print(f"  ❌ {e}")
        for w in warnings:
            print(f"  ⚠️  {w}")
        print(f"\n统计:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemTest 数据质量校验 (v4)")
    parser.add_argument("db_path", help="测试数据库JSON文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    with open(args.db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    result = check(db, verbose=True)
    sys.exit(0 if result["passed"] else 1)
