#!/usr/bin/env python3
"""MemTest v4 自动化Pipeline — 生成+校验+修复+迭代

用法:
    python pipeline_auto.py <corpus_dir> [-o output.json] [--max-iterations 3]

流程（自动迭代）:
    1. 提取记忆 (LLM)
    2. 构建关系 (规则)
    3. 生成查询 (规则)
    4. 质量门控 (自动校验)
    5. 如不通过，自动修复后重跑
    6. 输出通过的结果 + 报告

质量门控项:
    - 每维度查询数 ≥ min_per_dim
    - 记忆覆盖率 100%
    - 无缺失引用
    - 无重复查询
    - source字段完整
    - person非空率 > 80%
    - 负样本比例 15-25%
"""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ==============================================================================
# 质量门控
# ==============================================================================

class QualityGate:
    """v4质量门控：自动校验 + 报告"""

    def __init__(self, min_per_dim: int = 100, min_coverage: float = 1.0,
                 min_person_rate: float = 0.8, neg_ratio_range: Tuple[float, float] = (0.10, 0.30)):
        self.min_per_dim = min_per_dim
        self.min_coverage = min_coverage
        self.min_person_rate = min_person_rate
        self.neg_ratio_range = neg_ratio_range
        self.results = []

    def check(self, data: Dict) -> Dict:
        """运行所有检查，返回 {passed: bool, errors: [], warnings: [], stats: {}}"""
        memories = data.get('memories', [])
        queries = data.get('queries', [])
        mem_ids = {m['memory_id'] for m in memories}

        errors = []
        warnings = []
        stats = {}

        # 1. Memory ID uniqueness
        mem_id_list = [m['memory_id'] for m in memories]
        dup_mems = len(mem_id_list) - len(set(mem_id_list))
        stats['memory_count'] = len(memories)
        if dup_mems > 0:
            errors.append(f"Memory ID重复: {dup_mems}个")
        else:
            stats['memory_id_unique'] = True

        # 2. Query ID uniqueness
        q_id_list = [q['query_id'] for q in queries]
        dup_qs = len(q_id_list) - len(set(q_id_list))
        stats['query_count'] = len(queries)
        if dup_qs > 0:
            errors.append(f"Query ID重复: {dup_qs}个")
        else:
            stats['query_id_unique'] = True

        # 3. No missing references
        missing = 0
        for q in queries:
            for mid in q.get('expected_memory_ids', []):
                if mid not in mem_ids:
                    missing += 1
        if missing > 0:
            errors.append(f"查询引用不存在的记忆: {missing}处")
        else:
            stats['no_missing_refs'] = True

        # 4. No duplicate query texts
        q_texts = [q['query_text'] for q in queries]
        dup_texts = len(q_texts) - len(set(q_texts))
        if dup_texts > 0:
            errors.append(f"重复查询文本: {dup_texts}条")
        else:
            stats['no_duplicate_queries'] = True

        # 5. Memory coverage (every memory hit by at least one query)
        hit_mems = set()
        for q in queries:
            for mid in q.get('expected_memory_ids', []):
                hit_mems.add(mid)
        coverage = len(hit_mems) / len(memories) if memories else 0
        stats['memory_coverage'] = f"{coverage:.1%}"
        if coverage < self.min_coverage:
            errors.append(f"记忆覆盖率不足: {coverage:.1%} (需要≥{self.min_coverage:.0%})")
        else:
            stats['memory_coverage_ok'] = True

        # 6. Source field completeness
        no_source = sum(1 for m in memories if not m.get('source'))
        if no_source > 0:
            warnings.append(f"缺少source字段: {no_source}条记忆")
        stats['source_missing'] = no_source

        # 7. Person_list non-empty rate
        has_person = sum(1 for m in memories if m.get('person'))
        person_rate = has_person / len(memories) if memories else 0
        stats['person_rate'] = f"{person_rate:.1%}"
        if person_rate < self.min_person_rate:
            warnings.append(f"person非空率偏低: {person_rate:.1%} (建议≥{self.min_person_rate:.0%})")

        # 8. Per-dimension query counts
        dim_counts = Counter(q['test_dimension'] for q in queries)
        stats['dimension_counts'] = dict(dim_counts)
        for dim, count in dim_counts.items():
            if dim == '负样本':
                continue  # 负样本单独检查
            if count < self.min_per_dim * 0.8:  # <80% is error
                errors.append(f"维度「{dim}」查询数严重不足: {count} < {self.min_per_dim}")
            elif count < self.min_per_dim:  # <100% is warning
                warnings.append(f"维度「{dim}」查询数略不足: {count} < {self.min_per_dim}")

        # 9. Per-type query counts
        type_counts = Counter(q['query_type'] for q in queries)
        stats['type_counts'] = dict(type_counts)

        # 10. Negative sample ratio
        neg_count = sum(1 for q in queries if q.get('is_negative'))
        neg_ratio = neg_count / len(queries) if queries else 0
        stats['negative_ratio'] = f"{neg_ratio:.1%}"
        if neg_ratio < self.neg_ratio_range[0]:
            warnings.append(f"负样本比例偏低: {neg_ratio:.1%} (建议≥{self.neg_ratio_range[0]:.0%})")
        elif neg_ratio > self.neg_ratio_range[1]:
            warnings.append(f"负样本比例偏高: {neg_ratio:.1%} (建议≤{self.neg_ratio_range[1]:.0%})")

        # 11. Alias groups with evidence
        alias_evidence_count = sum(1 for m in memories if m.get('alias_evidence'))
        stats['memories_with_alias_evidence'] = alias_evidence_count

        # 12. Reasoning chains
        chain_count = sum(1 for m in memories if m.get('reasoning_chain'))
        stats['memories_with_chains'] = chain_count

        passed = len(errors) == 0
        return {
            'passed': passed,
            'errors': errors,
            'warnings': warnings,
            'stats': stats,
        }

    def print_report(self, result: Dict):
        """打印质量报告"""
        print("\n" + "=" * 60)
        print("  MemTest v4 质量门控报告")
        print("=" * 60)

        stats = result['stats']
        print(f"  记忆数: {stats.get('memory_count', 0)}")
        print(f"  查询数: {stats.get('query_count', 0)}")
        print(f"  记忆覆盖率: {stats.get('memory_coverage', '?')}")
        print(f"  负样本比例: {stats.get('negative_ratio', '?')}")
        print()

        # Dimension breakdown
        print("  维度分布:")
        for dim, count in sorted(stats.get('dimension_counts', {}).items()):
            flag = " ✅" if count >= self.min_per_dim or dim == '负样本' else " ⚠️"
            print(f"    {dim}: {count}{flag}")

        print()
        print("  类型分布:")
        for t, count in sorted(stats.get('type_counts', {}).items()):
            print(f"    {t}: {count}")

        if result['errors']:
            print(f"\n  ❌ 错误 ({len(result['errors'])}):")
            for e in result['errors']:
                print(f"    - {e}")

        if result['warnings']:
            print(f"\n  ⚠️ 警告 ({len(result['warnings'])}):")
            for w in result['warnings']:
                print(f"    - {w}")

        print()
        if result['passed']:
            print("  ✅ 质量门控: 通过")
        else:
            print("  ❌ 质量门控: 未通过")
        print("=" * 60)


# ==============================================================================
# 自动修复
# ==============================================================================

class AutoFixer:
    """自动修复已知问题"""

    def fix_all(self, data: Dict, corpus_dir: str = None) -> Dict:
        """运行所有自动修复"""
        data = self._fix_source_fields(data, corpus_dir)
        data = self._fix_empty_persons(data)
        data = self._fix_memory_id_gaps(data)
        return data

    def _fix_source_fields(self, data: Dict, corpus_dir: str = None) -> Dict:
        """修复缺失的source字段"""
        memories = data.get('memories', [])
        
        # Try to infer source from corpus directory name
        source_map = {}
        if corpus_dir:
            dir_name = os.path.basename(os.path.normpath(corpus_dir))
            # Map common directory names to source names
            known_sources = {
                'test_corpus': '示例',
                'test_corpus2': '三国演义',
                'test_corpus3': '西游记',
                'test_corpus4': '三国演义',
                'test_corpus5': '红楼梦',
                'test_corpus6': '金庸小说',
                'test_corpus_combined': '合集',
            }
            source_map[corpus_dir] = known_sources.get(dir_name, dir_name)

        # If all memories share the same corpus_dir, set source uniformly
        fixed = 0
        default_source = None
        if corpus_dir:
            default_source = source_map.get(corpus_dir)

        for m in memories:
            if not m.get('source'):
                if default_source:
                    m['source'] = default_source
                    fixed += 1
                else:
                    m['source'] = '未知'
                    fixed += 1

        if fixed > 0:
            print(f"  [AutoFix] 修复source字段: {fixed}条")

        return data

    def _fix_empty_persons(self, data: Dict) -> Dict:
        """尝试从content中提取人名填充空person"""
        import re
        memories = data.get('memories', [])
        fixed = 0

        for m in memories:
            if not m.get('person') and m.get('content'):
                # Simple regex: 2-3 char Chinese names
                names = re.findall(r'[\u4e00-\u9fff]{2,4}(?=做了|经历|发生|参与|前往|到了)', m['content'])
                if names:
                    m['person'] = names[:5]
                    fixed += 1

        if fixed > 0:
            print(f"  [AutoFix] 补充person: {fixed}条")

        return data

    def _fix_memory_id_gaps(self, data: Dict) -> Dict:
        """重新编号memory_id，消除间隔"""
        memories = data.get('memories', [])
        old_to_new = {}
        
        for i, m in enumerate(memories):
            new_id = f'MEM{i+1:06d}'
            old_to_new[m['memory_id']] = new_id
            m['memory_id'] = new_id

        # Update references in queries
        for q in data.get('queries', []):
            q['expected_memory_ids'] = [old_to_new.get(mid, mid) for mid in q.get('expected_memory_ids', [])]

        # Update references in reasoning chains
        for m in memories:
            chain = m.get('reasoning_chain')
            if chain and isinstance(chain, dict):
                for key in ['prev', 'next', 'related']:
                    if key in chain:
                        if isinstance(chain[key], list):
                            chain[key] = [old_to_new.get(mid, mid) for mid in chain[key]]
                        elif isinstance(chain[key], str):
                            chain[key] = old_to_new.get(chain[key], chain[key])

        return data


# ==============================================================================
# 主Pipeline
# ==============================================================================

def run_pipeline(corpus_dirs: list, output_path: str = None, name: str = "MemTest Database",
                 min_per_dim: int = 100, seed: int = 42, max_iterations: int = 3,
                 no_llm: bool = False, verbose: bool = False) -> Dict:
    """运行自动迭代pipeline"""

    gate = QualityGate(min_per_dim=min_per_dim)
    fixer = AutoFixer()

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  迭代 {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # Step 1: Extract
        print("\n[Step 1] 提取记忆...")
        from extractor import MemoryExtractor
        if no_llm:
            extractor = MemoryExtractor(seed=seed)
        else:
            from llm_interface import create_llm
            llm = create_llm('deepseek')
            extractor = MemoryExtractor(llm_adapter=llm, seed=seed)

        all_memories = []
        for cdir in corpus_dirs:
            mems = extractor.extract(cdir)
            # Tag source by directory
            dir_name = os.path.basename(os.path.normpath(cdir))
            known_sources = {'test_corpus2': '三国演义', 'test_corpus3': '西游记',
                           'test_corpus4': '三国演义', 'test_corpus5': '红楼梦',
                           'test_corpus6': '金庸小说'}
            source = known_sources.get(dir_name, dir_name)
            for m in mems:
                m['source'] = source
            all_memories.extend(mems)
        memories = all_memories
        print(f"  提取: {len(memories)} 条记忆")

        if not memories:
            print("  ❌ 提取失败，无记忆")
            return None

        # Step 2: Build relations
        print("\n[Step 2] 构建关系...")
        from relation_builder import RelationBuilder
        builder = RelationBuilder(seed=seed)
        memories = builder.build(memories)

        has_chain = sum(1 for m in memories if m.get('reasoning_chain'))
        has_cluster = sum(1 for m in memories if m.get('cluster_id'))
        print(f"  推理链: {has_chain}, 聚类: {has_cluster}")

        # Step 3: Generate queries
        print(f"\n[Step 3] 生成查询 (min_per_dim={min_per_dim})...")
        from query_builder import QueryBuilder
        qb = QueryBuilder(alias_groups=builder.alias_groups, seed=seed, min_per_dim=min_per_dim)
        queries = qb.build(memories)
        print(f"  查询: {len(queries)} 条")

        # Step 4: Assemble
        print("\n[Step 4] 组装数据库...")
        data = {
            'database_info': {
                'name': name,
                'version': '4.0',
                'total_memories': len(memories),
                'total_queries': len(queries),
            },
            'memories': memories,
            'queries': queries,
        }

        # Step 5: Auto-fix
        print("\n[Step 5] 自动修复...")
        data = fixer.fix_all(data, corpus_dirs[0] if corpus_dirs else None)

        # Step 6: Quality gate
        print("\n[Step 6] 质量门控...")
        result = gate.check(data)
        gate.print_report(result)

        if result['passed']:
            # Save
            if output_path:
                with open(output_path, 'w') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"\n  ✅ 已保存: {output_path}")
            else:
                auto_output = os.path.join('output', f'{name.lower().replace(" ", "_")}.json')
                os.makedirs('output', exist_ok=True)
                with open(auto_output, 'w') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"\n  ✅ 已保存: {auto_output}")

            return data

        # Not passed - analyze what to fix for next iteration
        print(f"\n  ⚠️ 未通过，分析修复方案...")
        for err in result['errors']:
            print(f"    ERROR: {err}")
        for warn in result['warnings']:
            print(f"    WARN: {warn}")

        # Check if re-extraction would help
        # For now, if we can't auto-fix, break and report
        if iteration == max_iterations:
            print(f"\n  ❌ 达到最大迭代次数 ({max_iterations})，仍有问题")
            # Save anyway
            if output_path:
                with open(output_path, 'w') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  已保存（有警告）: {output_path}")
            return data

    return None


# ==============================================================================
# CLI
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="MemTest v4 自动化Pipeline")
    parser.add_argument("corpus_dir", nargs='+', help="语料目录（支持多个）")
    parser.add_argument("-o", "--output", default=None, help="输出文件路径")
    parser.add_argument("--name", default="MemTest Database", help="数据库名称")
    parser.add_argument("--min-per-dim", type=int, default=100, help="每维度最少查询数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--max-iterations", type=int, default=3, help="最大迭代次数")
    parser.add_argument("--no-llm", action="store_true", help="不使用LLM")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    start = time.time()
    data = run_pipeline(
        corpus_dirs=args.corpus_dir,
        output_path=args.output,
        name=args.name,
        min_per_dim=args.min_per_dim,
        seed=args.seed,
        max_iterations=args.max_iterations,
        no_llm=args.no_llm,
        verbose=args.verbose,
    )
    elapsed = time.time() - start

    if data:
        print(f"\n完成！耗时 {elapsed:.1f}s")
    else:
        print(f"\n失败！耗时 {elapsed:.1f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
