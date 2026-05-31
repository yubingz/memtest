#!/usr/bin/env python3
"""质量校验脚本 — 生成数据库后自动检查数据质量

用法：
    python quality_check.py test_db_100.json
    python quality_check.py sample_db_100.json --verbose

检查项：
    1. 记忆ID唯一性
    2. 查询ID唯一性
    3. 查询指向有效记忆
    4. 负样本标记正确
    5. 版本文本长度分布
    6. 类别分布均衡性
    7. 链式数据完整性
    8. 聚类数据完整性
    9. 数据池多样性（城市/人名/产品）
"""

import json, sys, argparse
from collections import Counter

def check(db: dict, verbose: bool = False) -> dict:
    """执行所有质量检查，返回报告字典。"""
    mems = db.get("memories", [])
    queries = db.get("queries", [])
    report = {"passed": True, "checks": [], "warnings": 0, "errors": 0}
    
    def _ok(msg): report["checks"].append(("PASS", msg))
    def _warn(msg): report["checks"].append(("WARN", msg)); report["warnings"] += 1
    def _err(msg): report["checks"].append(("ERROR", msg)); report["errors"] += 1; report["passed"] = False
    
    # 1. 记忆ID唯一性
    mem_ids = [m["memory_id"] for m in mems]
    dup = len(mem_ids) - len(set(mem_ids))
    if dup == 0: _ok(f"记忆ID唯一性: {len(mem_ids)} 条全部唯一")
    else: _err(f"记忆ID重复: {dup} 个重复ID")
    
    # 2. 查询ID唯一性
    q_ids = [q["query_id"] for q in queries]
    dup_q = len(q_ids) - len(set(q_ids))
    if dup_q == 0: _ok(f"查询ID唯一性: {len(q_ids)} 条全部唯一")
    else: _err(f"查询ID重复: {dup_q} 个重复ID")
    
    # 3. 查询指向有效记忆
    valid_ids = set(mem_ids)
    bad = 0
    for q in queries:
        for mid in q.get("expected_memory_ids", []):
            if mid and mid not in valid_ids:
                bad += 1
                if verbose: _err(f"查询 {q['query_id']} 指向无效记忆 {mid}")
    if bad == 0: _ok("所有查询指向有效记忆")
    else: _err(f"{bad} 个查询指向无效记忆")
    
    # 4. 负样本标记正确
    neg = [q for q in queries if q.get("is_negative")]
    pos = [q for q in queries if not q.get("is_negative")]
    neg_empty = [q for q in neg if q.get("expected_memory_ids")]
    pos_empty = [q for q in pos if not q.get("expected_memory_ids")]
    if not neg_empty: _ok(f"负样本标记正确: {len(neg)} 条负样本，expected_memory_ids 全部为空")
    else: _err(f"{len(neg_empty)} 条负样本标记错误（expected_memory_ids 非空）")
    if not pos_empty: _ok(f"正样本标记正确: {len(pos)} 条正样本，expected_memory_ids 全部非空")
    else: _err(f"{len(pos_empty)} 条正样本标记错误（expected_memory_ids 为空）")
    neg_ratio = len(neg) / len(queries) if queries else 0
    if 0.15 <= neg_ratio <= 0.25: _ok(f"负样本比例合理: {neg_ratio:.1%}")
    else: _warn(f"负样本比例 {neg_ratio:.1%}，建议 15-25%")
    
    # 5. 版本文本长度分布
    lengths = []
    for m in mems:
        for v in m.get("versions", []):
            lengths.append(len(v.get("content", "")))
    if lengths:
        avg = sum(lengths) / len(lengths)
        min_len, max_len = min(lengths), max(lengths)
        if 20 <= avg <= 120: _ok(f"版本长度合理: 平均{avg:.0f}字符 (范围{min_len}-{max_len})")
        else: _warn(f"版本长度异常: 平均{avg:.0f}字符，建议30-120")
    
    # 6. 类别分布均衡性
    cats = Counter(m["category"] for m in mems)
    if len(cats) >= 6: _ok(f"类别分布: {len(cats)} 个类别")
    else: _warn(f"只有 {len(cats)} 个类别，建议6个")
    max_cat = max(cats.values()) if cats else 0
    min_cat = min(cats.values()) if cats else 0
    if max_cat / min_cat <= 2 if min_cat else True: _ok(f"类别分布均衡: {min_cat}-{max_cat} 条/类")
    else: _warn(f"类别分布不均: {min_cat}-{max_cat} 条/类，最大/最小={max_cat/min_cat:.1f}")
    
    # 7. 链式数据完整性
    chains = {}
    for m in mems:
        cid = m.get("reasoning_chain")
        if cid:
            chains.setdefault(cid, []).append(m)
    if chains:
        _ok(f"链式数据: {len(chains)} 条链，{sum(len(v) for v in chains.values())} 条记忆")
        for cid, chain_mems in chains.items():
            positions = sorted(m.get("chain_position", 0) for m in chain_mems)
            if positions and positions == list(range(1, len(positions)+1)):
                pass  # ok
            else:
                _warn(f"链 {cid} 位置不连续: {positions}")
    else:
        _warn("无链式数据（reasoning_chain 为空）")
    
    # 8. 聚类数据完整性
    clusters = {}
    for m in mems:
        cid = m.get("cluster_id")
        if cid:
            clusters.setdefault(cid, []).append(m)
    if clusters:
        _ok(f"聚类数据: {len(clusters)} 个cluster，{sum(len(v) for v in clusters.values())} 条记忆")
        for cid, cmems in clusters.items():
            if len(cmems) < 3: _warn(f"Cluster {cid} 只有 {len(cmems)} 条记忆，建议≥3")
    else:
        _warn("无聚类数据（cluster_id 为空）")
    
    # 9. 数据池多样性
    cities = set(m["location"]["city"] for m in mems if m.get("location"))
    names = set(m["person"]["name"] for m in mems if m.get("person"))
    products = set(m["event"]["product"] for m in mems if m.get("event"))
    _ok(f"数据池多样性: {len(cities)} 城市, {len(names)} 人名, {len(products)} 产品")
    if len(cities) < 10: _warn(f"城市多样性不足: {len(cities)} 个，建议≥10")
    if len(names) < 10: _warn(f"人名多样性不足: {len(names)} 个，建议≥10")
    if len(products) < 10: _warn(f"产品多样性不足: {len(products)} 个，建议≥10")
    
    # 10. 查询重复检测
    qtexts = [q.get("query_text", "") for q in queries]
    dup_text = len(qtexts) - len(set(qtexts))
    if dup_text == 0: _ok("查询文本无重复")
    else: _warn(f"查询文本重复: {dup_text} 条")
    
    return report


def print_report(report: dict):
    """打印质量报告。"""
    print("=" * 50)
    print("  MemTest 数据质量校验报告")
    print("=" * 50)
    for status, msg in report["checks"]:
        icon = {"PASS": "✅", "WARN": "⚠️", "ERROR": "❌"}[status]
        print(f"  {icon} {msg}")
    print("-" * 50)
    print(f"  总计: {len(report['checks'])} 项 | 警告: {report['warnings']} | 错误: {report['errors']}")
    print(f"  结果: {'✅ 通过' if report['passed'] else '❌ 未通过'}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MemTest 数据质量校验")
    parser.add_argument("file", help="JSON数据库文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()
    
    with open(args.file, encoding="utf-8") as f:
        db = json.load(f)
    
    report = check(db, verbose=args.verbose)
    print_report(report)
    sys.exit(0 if report["passed"] else 1)
