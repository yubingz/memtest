#!/usr/bin/env python3
"""MemTest v4 一条龙 Pipeline

用法:
    python pipeline_v4.py <corpus_dir> [-o output.json] [--no-llm]

流程:
    extractor → relation_builder → query_builder → assemble → test_db.json

v4 核心改变:
    - 查询 = 记忆属性 × 模板（不需要LLM生成查询）
    - 回归v2完整schema（6大评测维度全覆盖）
    - 只有提取步骤用LLM，其余全规则
"""

import argparse
import json
import sys
import os
import time

def main():
    parser = argparse.ArgumentParser(description="MemTest v4 Pipeline")
    parser.add_argument("corpus_dir", help="语料目录")
    parser.add_argument("-o", "--output", default="test_db.json", help="输出文件")
    parser.add_argument("--no-llm", action="store_true", help="不使用LLM，纯规则提取")
    parser.add_argument("--name", default="MemTest Database", help="数据库名称")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    start = time.time()

    # Step 1: 提取记忆
    print("=" * 60)
    print("  MemTest v4 Pipeline")
    print("=" * 60)
    print(f"  语料: {args.corpus_dir}")
    print(f"  LLM: {'关闭' if args.no_llm else 'DeepSeek'}")
    print()

    from extractor import MemoryExtractor
    from llm_interface import create_llm

    if args.no_llm:
        extractor = MemoryExtractor(seed=args.seed)
    else:
        llm = create_llm("deepseek")
        extractor = MemoryExtractor(llm_adapter=llm, seed=args.seed)

    memories = extractor.extract(args.corpus_dir)
    print(f"[Step 1] 提取完成: {len(memories)} 条记忆")

    # Step 2: 构建关系
    from relation_builder import RelationBuilder
    builder = RelationBuilder(seed=args.seed)
    memories = builder.build(memories)

    has_chain = sum(1 for m in memories if m.get("reasoning_chain"))
    has_cluster = sum(1 for m in memories if m.get("cluster_id"))
    alias_group_count = len([g for g in builder.alias_groups.groups().values() if len(g) >= 2])

    print(f"[Step 2] 关系构建: {has_chain}条链, {has_cluster}个聚类, {alias_group_count}组别名")

    # Step 3: 生成查询
    from query_builder import QueryBuilder
    qb = QueryBuilder(alias_groups=builder.alias_groups, seed=args.seed)
    queries = qb.build(memories)

    by_type = {}
    for q in queries:
        t = q["query_type"]
        by_type[t] = by_type.get(t, 0) + 1
    print(f"[Step 3] 查询生成: {len(queries)} 条 ({', '.join(f'{t}:{c}' for t, c in sorted(by_type.items()))})")

    # Step 4: 组装
    from assemble import assemble
    db = assemble(memories, queries, name=args.name, source=args.corpus_dir)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  完成! {len(memories)} 条记忆, {len(queries)} 条查询")
    print(f"  输出: {args.output}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"{'='*60}")

    # 快速质量检查
    from quality_check import check
    report = check(db, verbose=False)
    errs = report.get("errors", 0) if isinstance(report.get("errors"), int) else len(report.get("errors", []))
    warns = report.get("warnings", 0) if isinstance(report.get("warnings"), int) else len(report.get("warnings", []))
    status = "✅ 通过" if errs == 0 else f"❌ {errs} 个错误"
    print(f"  质量检查: {status} ({warns} 个警告)")


if __name__ == "__main__":
    main()
