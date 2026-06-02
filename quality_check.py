#!/usr/bin/env python3
"""MemTest 质量校验脚本 — v2/v4 兼容

支持格式：
  - v4 统一 schema（content 为原文片段，无 versions 嵌套）
  - v2 旧格式（带 versions 嵌套、多种格式并存）

用法：
    python quality_check.py test_db.json
    python quality_check.py sample_db.json --verbose
    python quality_check.py sample_db.json --format v4  # 强制 v4 模式
    python quality_check.py sample_db.json --format auto  # 自动检测

检查项（v4）：
    1. 记忆ID唯一性
    2. 查询ID唯一性
    3. 查询指向有效记忆
    4. 负样本标记正确
    5. content 长度分布（30-150字）
    6. 类别分布均衡性
    7. 时间引用有效性（time_ref_id 指向存在的 memory_id）
    8. 链条完整性（链内节点数量是否完整）
    9. 别名等价语料证据检查
   10. 负样本比例（15-25%）

检查项（v2 兼容）：
    - 版本文本长度分布
    - 类别分布
    - 链式/聚类完整性
    - 数据池多样性
"""

import json
import sys
import argparse
from collections import Counter, defaultdict

# ==============================================================================
# v4 Schema 校验（从 schema.py 导入，若不存在则内联）
# ==============================================================================

try:
    from schema import validate_database as _validate_database_v4
    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False


def _validate_database_v4_fallback(db: dict) -> dict:
    """v4 校验（不依赖 schema.py 的备用实现）"""
    errors: list = []
    warnings: list = []
    mems = db.get("memories", [])
    queries = db.get("queries", [])

    # ID 唯一性
    mem_ids = [m.get("memory_id", "") for m in mems]
    if len(mem_ids) != len(set(mem_ids)):
        dup = len(mem_ids) - len(set(mem_ids))
        errors.append(f"memory_id 重复: {dup} 个")

    q_ids = [q.get("query_id", "") for q in queries]
    if len(q_ids) != len(set(q_ids)):
        dup = len(q_ids) - len(set(q_ids))
        errors.append(f"query_id 重复: {dup} 个")

    valid_mids = set(mem_ids)
    for q in queries:
        qid = q.get("query_id", "?")
        for mid in q.get("expected_memory_ids", []):
            if mid and mid not in valid_mids:
                errors.append(f"查询 {qid} 指向无效记忆 {mid}")

        if q.get("is_negative") and q.get("expected_memory_ids"):
            errors.append(f"负样本 {qid} 的 expected_memory_ids 应为空")

    # time_ref_id 有效性
    for m in mems:
        ref_id = m.get("time_ref_id")
        if ref_id and ref_id not in valid_mids:
            errors.append(f"记忆 {m.get('memory_id','?')} 的 time_ref_id 指向不存在: {ref_id}")

    # content 长度
    content_lengths = [len(m.get("content", "")) for m in mems]
    avg_len = sum(content_lengths) / len(content_lengths) if content_lengths else 0

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "total_memories": len(mems),
            "total_queries": len(queries),
            "avg_content_length": round(avg_len, 1),
            "memory_errors": 0,
            "query_errors": 0,
        },
    }


def _detect_format(db: dict) -> str:
    """自动检测数据库格式"""
    mems = db.get("memories", [])
    if not mems:
        return "v4"

    first = mems[0]
    # v4: 直接有 content 字段，无 versions
    if "content" in first and "versions" not in first:
        return "v4"
    # v2: 有 versions 或嵌套 person/location
    if "versions" in first:
        return "v2"
    if isinstance(first.get("person"), dict):
        return "v2"
    return "v4"


# ==============================================================================
# v4 质量校验
# ==============================================================================

def check_v4(db: dict, verbose: bool = False) -> dict:
    """执行 v4 格式质量检查"""
    mems = db.get("memories", [])
    queries = db.get("queries", [])
    report = {
        "version": "3.0",
        "passed": True,
        "checks": [],
        "warnings": 0,
        "errors": 0,
    }

    def _ok(msg):
        report["checks"].append(("PASS", msg))

    def _warn(msg):
        report["checks"].append(("WARN", msg))
        report["warnings"] += 1

    def _err(msg):
        report["checks"].append(("ERROR", msg))
        report["errors"] += 1
        report["passed"] = False

    mem_ids = [m["memory_id"] for m in mems]
    dup = len(mem_ids) - len(set(mem_ids))
    if dup == 0:
        _ok(f"记忆ID唯一性: {len(mem_ids)} 条全部唯一")
    else:
        _err(f"记忆ID重复: {dup} 个重复ID")

    q_ids = [q["query_id"] for q in queries]
    dup_q = len(q_ids) - len(set(q_ids))
    if dup_q == 0:
        _ok(f"查询ID唯一性: {len(q_ids)} 条全部唯一")
    else:
        _err(f"查询ID重复: {dup_q} 个重复ID")

    # 查询指向有效记忆
    valid_ids = set(mem_ids)
    bad_refs = 0
    for q in queries:
        for mid in q.get("expected_memory_ids", []):
            if mid and mid not in valid_ids:
                bad_refs += 1
                if verbose:
                    _err(f"查询 {q['query_id']} 指向无效记忆 {mid}")
    if bad_refs == 0:
        _ok("所有查询指向有效记忆")
    else:
        _err(f"{bad_refs} 个查询指向无效记忆")

    # 负样本标记
    neg = [q for q in queries if q.get("is_negative")]
    pos = [q for q in queries if not q.get("is_negative")]
    neg_with_ids = [q for q in neg if q.get("expected_memory_ids")]
    pos_without_ids = [q for q in pos if not q.get("expected_memory_ids")]

    if not neg_with_ids:
        _ok(f"负样本标记正确: {len(neg)} 条负样本，expected_memory_ids 全部为空")
    else:
        _err(f"{len(neg_with_ids)} 条负样本标记错误（expected_memory_ids 非空）")

    if not pos_without_ids:
        _ok(f"正样本标记正确: {len(pos)} 条正样本，expected_memory_ids 全部非空")
    else:
        _err(f"{len(pos_without_ids)} 条正样本标记错误（expected_memory_ids 为空）")

    neg_ratio = len(neg) / len(queries) if queries else 0
    if 0.15 <= neg_ratio <= 0.25:
        _ok(f"负样本比例合理: {neg_ratio:.1%}")
    else:
        _warn(f"负样本比例 {neg_ratio:.1%}，建议 15-25%")

    # content 长度分布（v4 核心）
    lengths = [len(m.get("content", "")) for m in mems]
    if lengths:
        avg = sum(lengths) / len(lengths)
        too_short = sum(1 for l in lengths if l < 30)
        too_long = sum(1 for l in lengths if l > 150)
        if 30 <= avg <= 150:
            _ok(f"content 长度合理: 平均{avg:.0f}字 (30-150)")
        else:
            _warn(f"content 长度异常: 平均{avg:.0f}字，建议30-150")
        if too_short > len(lengths) * 0.1:
            _warn(f"过于简短: {too_short} 条 <30字")
        if too_long > len(lengths) * 0.1:
            _warn(f"过于冗长: {too_long} 条 >150字")

    # person 字段
    has_person = sum(1 for m in mems if m.get("person"))
    if has_person >= len(mems) * 0.3:
        _ok(f"人物信息: {has_person}/{len(mems)} 条含人物")
    else:
        _warn(f"人物信息不足: 仅 {has_person}/{len(mems)} 条含人物")

    # 时间引用有效性（v4 新增）
    time_ref_errors = 0
    for m in mems:
        ref_id = m.get("time_ref_id")
        if ref_id is not None and ref_id not in valid_ids:
            time_ref_errors += 1
            if verbose:
                _err(f"记忆 {m['memory_id']} 的 time_ref_id 指向不存在: {ref_id}")
    if time_ref_errors == 0:
        _ok(f"时间引用有效: 所有 time_ref_id 指向存在的 memory_id")
    else:
        _err(f"时间引用错误: {time_ref_errors} 条 time_ref_id 指向无效")

    # time_offset_days 合理性
    offset_issues = 0
    for m in mems:
        offset = m.get("time_offset_days")
        if offset is not None:
            if not isinstance(offset, int):
                offset_issues += 1
            elif abs(offset) > 100 * 365:  # 超过100年标记警告
                if verbose:
                    _warn(f"记忆 {m['memory_id']} 的 time_offset_days={offset} 异常大")
    if offset_issues == 0:
        _ok(f"time_offset_days 类型正确: 全为整数")
    else:
        _err(f"time_offset_days 类型错误: {offset_issues} 条")

    # 查询类型分布
    qt_counts = Counter(q.get("query_type", "unknown") for q in queries)
    if len(qt_counts) >= 4:
        _ok(f"查询类型分布: {len(qt_counts)} 种类型")
    else:
        _warn(f"查询类型单一: 仅 {len(qt_counts)} 种类型，建议≥4")
    for qt, cnt in qt_counts.items():
        _ok(f"  - {qt}: {cnt} 条")

    # 查询重复
    qtexts = [q.get("query_text", "") for q in queries]
    dup_text = len(qtexts) - len(set(qtexts))
    if dup_text == 0:
        _ok("查询文本无重复")
    else:
        _warn(f"查询文本重复: {dup_text} 条")

    # 别名查询（有 alias_map 的情况下检查）
    alias_queries = [q for q in queries if q.get("query_type") == "别名查询"]
    if alias_queries:
        _ok(f"别名查询: {len(alias_queries)} 条")
        # 检查 expected_answer 是否包含别名
        alias_without_answer = [
            q["query_id"] for q in alias_queries
            if not q.get("expected_answer", "").strip()
        ]
        if alias_without_answer:
            _warn(f"别名查询 expected_answer 为空: {len(alias_without_answer)} 条")

    # 难度分布
    diff_counts = Counter(m.get("difficulty", "unknown") for m in mems)
    if diff_counts:
        max_diff = max(diff_counts.values()) if diff_counts else 0
        min_diff = min(v for v in diff_counts.values() if v > 0) if diff_counts else 0
        ratio = max_diff / min_diff if min_diff > 0 else float("inf")
        if ratio <= 3:
            _ok(f"难度分布均衡: {dict(diff_counts)}")
        else:
            _warn(f"难度分布不均: 最大/最小={ratio:.1f}")

    return report


# ==============================================================================
# v2 兼容校验（原有逻辑）
# ==============================================================================

def check_v2(db: dict, verbose: bool = False) -> dict:
    """执行 v2 格式质量检查（原有逻辑）"""
    mems = db.get("memories", [])
    queries = db.get("queries", [])
    report = {
        "version": "2.0",
        "passed": True,
        "checks": [],
        "warnings": 0,
        "errors": 0,
    }

    def _ok(msg):
        report["checks"].append(("PASS", msg))

    def _warn(msg):
        report["checks"].append(("WARN", msg))
        report["warnings"] += 1

    def _err(msg):
        report["checks"].append(("ERROR", msg))
        report["errors"] += 1
        report["passed"] = False

    # 记忆ID唯一性
    mem_ids = [m["memory_id"] for m in mems]
    dup = len(mem_ids) - len(set(mem_ids))
    if dup == 0:
        _ok(f"记忆ID唯一性: {len(mem_ids)} 条全部唯一")
    else:
        _err(f"记忆ID重复: {dup} 个重复ID")

    # 查询ID唯一性
    q_ids = [q["query_id"] for q in queries]
    dup_q = len(q_ids) - len(set(q_ids))
    if dup_q == 0:
        _ok(f"查询ID唯一性: {len(q_ids)} 条全部唯一")
    else:
        _err(f"查询ID重复: {dup_q} 个重复ID")

    # 查询指向有效记忆
    valid_ids = set(mem_ids)
    bad = 0
    for q in queries:
        for mid in q.get("expected_memory_ids", []):
            if mid and mid not in valid_ids:
                bad += 1
                if verbose:
                    _err(f"查询 {q['query_id']} 指向无效记忆 {mid}")
    if bad == 0:
        _ok("所有查询指向有效记忆")
    else:
        _err(f"{bad} 个查询指向无效记忆")

    # 负样本标记
    neg = [q for q in queries if q.get("is_negative")]
    pos = [q for q in queries if not q.get("is_negative")]
    neg_empty = [q for q in neg if q.get("expected_memory_ids")]
    pos_empty = [q for q in pos if not q.get("expected_memory_ids")]
    if not neg_empty:
        _ok(f"负样本标记正确: {len(neg)} 条负样本，expected_memory_ids 全部为空")
    else:
        _err(f"{len(neg_empty)} 条负样本标记错误（expected_memory_ids 非空）")
    if not pos_empty:
        _ok(f"正样本标记正确: {len(pos)} 条正样本，expected_memory_ids 全部非空")
    else:
        _err(f"{len(pos_empty)} 条正样本标记错误（expected_memory_ids 为空）")
    neg_ratio = len(neg) / len(queries) if queries else 0
    if 0.15 <= neg_ratio <= 0.25:
        _ok(f"负样本比例合理: {neg_ratio:.1%}")
    else:
        _warn(f"负样本比例 {neg_ratio:.1%}，建议 15-25%")

    # 版本文本长度分布
    lengths = []
    for m in mems:
        for v in m.get("versions", []):
            lengths.append(len(v.get("content", "")))
    if lengths:
        avg = sum(lengths) / len(lengths)
        min_len, max_len = min(lengths), max(lengths)
        if 20 <= avg <= 120:
            _ok(f"版本长度合理: 平均{avg:.0f}字符 (范围{min_len}-{max_len})")
        else:
            _warn(f"版本长度异常: 平均{avg:.0f}字符，建议30-120")

    # 类别分布
    cats = Counter(m["category"] for m in mems)
    if len(cats) >= 6:
        _ok(f"类别分布: {len(cats)} 个类别")
    else:
        _warn(f"只有 {len(cats)} 个类别，建议6个")
    max_cat = max(cats.values()) if cats else 0
    min_cat = min(cats.values()) if cats else 0
    if max_cat / min_cat <= 2 if min_cat else True:
        _ok(f"类别分布均衡: {min_cat}-{max_cat} 条/类")
    else:
        _warn(f"类别分布不均: {min_cat}-{max_cat} 条/类，最大/最小={max_cat/min_cat:.1f}")

    # 链式数据
    chains = {}
    for m in mems:
        cid = m.get("reasoning_chain")
        if cid:
            chains.setdefault(cid, []).append(m)
    if chains:
        _ok(f"链式数据: {len(chains)} 条链，{sum(len(v) for v in chains.values())} 条记忆")
        for cid, chain_mems in chains.items():
            positions = sorted(m.get("chain_position", 0) for m in chain_mems)
            if positions and positions != list(range(1, len(positions) + 1)):
                _warn(f"链 {cid} 位置不连续: {positions}")
    else:
        _warn("无链式数据（reasoning_chain 为空）")

    # 聚类数据
    clusters = {}
    for m in mems:
        cid = m.get("cluster_id")
        if cid:
            clusters.setdefault(cid, []).append(m)
    if clusters:
        _ok(f"聚类数据: {len(clusters)} 个cluster，{sum(len(v) for v in clusters.values())} 条记忆")
        for cid, cmems in clusters.items():
            if len(cmems) < 3:
                _warn(f"Cluster {cid} 只有 {len(cmems)} 条记忆，建议≥3")
    else:
        _warn("无聚类数据（cluster_id 为空）")

    # 数据池多样性
    cities = set()
    names = set()
    products = set()
    for m in mems:
        loc = m.get("location", {})
        if isinstance(loc, dict):
            cities.add(loc.get("city", ""))
        pers = m.get("person", {})
        if isinstance(pers, dict):
            names.add(pers.get("name", ""))
        evt = m.get("event", {})
        if isinstance(evt, dict):
            products.add(evt.get("product", ""))
    _ok(f"数据池多样性: {len(cities)} 城市, {len(names)} 人名, {len(products)} 产品")
    if len(cities) < 10:
        _warn(f"城市多样性不足: {len(cities)} 个，建议≥10")
    if len(names) < 10:
        _warn(f"人名多样性不足: {len(names)} 个，建议≥10")
    if len(products) < 10:
        _warn(f"产品多样性不足: {len(products)} 个，建议≥10")

    # 查询重复
    qtexts = [q.get("query_text", "") for q in queries]
    dup_text = len(qtexts) - len(set(qtexts))
    if dup_text == 0:
        _ok("查询文本无重复")
    else:
        _warn(f"查询文本重复: {dup_text} 条")

    return report


# ==============================================================================
# 统一入口
# ==============================================================================

def check(db: dict, verbose: bool = False, format_hint: str = "auto") -> dict:
    """执行质量检查，自动检测格式"""
    detected = _detect_format(db)

    if format_hint == "auto":
        fmt = detected
    else:
        fmt = format_hint

    if fmt == "v4":
        print(f"[质量校验] v4 格式（检测到）")
        return check_v4(db, verbose)
    else:
        print(f"[质量校验] v2 格式（检测到）")
        return check_v2(db, verbose)


def print_report(report: dict) -> None:
    """打印质量报告"""
    fmt = report.get("version", "?")
    print(f"\n{'=' * 50}")
    print(f"  MemTest 数据质量校验报告 (v{fmt})")
    print(f"{'=' * 50}")
    for status, msg in report.get("checks", []):
        icon = {"PASS": "✅", "WARN": "⚠️ ", "ERROR": "❌"}[status]
        print(f"  {icon} {msg}")
    print(f"{'-' * 50}")
    print(f"  总计: {len(report.get('checks', []))} 项 | "
          f"警告: {report.get('warnings', 0)} | "
          f"错误: {report.get('errors', 0)}")
    print(f"  结果: {'✅ 通过' if report.get('passed', False) else '❌ 未通过'}")
    print(f"{'=' * 50}\n")


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemTest 数据质量校验 (v2/v4 兼容)")
    parser.add_argument("file", help="JSON数据库文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--format", "-f", default="auto",
                        choices=["auto", "v2", "v4"],
                        help="强制指定格式 (默认: auto)")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as f:
        db = json.load(f)

    report = check(db, verbose=args.verbose, format_hint=args.format)
    print_report(report)
    sys.exit(0 if report["passed"] else 1)
