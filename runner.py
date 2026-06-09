#!/usr/bin/env python3
"""MemTest 评测执行器 — v4 only, content-only 存储

使用方法:
    from runner import MemoryTestSuite, MemoryAdapter, load_test_db

    class MyAdapter(MemoryAdapter):
        def reset(self): ...
        def store(self, text, meta): ...
        def search(self, query, top_k): ...

    db = load_test_db("sample_db.json")
    adapter = MyAdapter()
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(report.summary())

v4 设计:
    - adapter.store() 只传 memory_id + content（不传元数据，避免泄题）
    - 4个可靠评测维度：精确检索、组合检索、时序推理、负样本
    - 遗忘/深度评测不包含（v4不生成decay/depth数据）
"""

import json
from typing import List, Dict, Any, Optional


# ==============================================================================
# 适配器基类
# ==============================================================================

class MemoryAdapter:
    """被测记忆系统的抽象接口。只实现这 3 个方法即可接入评测。"""

    def reset(self):
        """清空记忆库"""
        raise NotImplementedError

    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆。

        v4 模式下 metadata 只含 memory_id。

        Args:
            memory_text: 记忆文本（原文）
            metadata: {"memory_id": str}
        """
        raise NotImplementedError

    def search(self, query: str, top_k: int = 20) -> list:
        """检索记忆。

        Returns:
            [{"memory_id": str, "score": float, "content": str}, ...]
        """
        raise NotImplementedError


# ==============================================================================
# 评测套件
# ==============================================================================

class MemoryTestSuite:
    """v4 评测套件：4个可靠维度 + 可选推理评测"""

    def __init__(self, adapter: MemoryAdapter):
        self.adapter = adapter
        self._memories: list = []
        self._id_map: dict = {}
        self.report: dict = {}

    def run(self, test_db: dict) -> dict:
        """运行评测，返回报告。"""
        memories = test_db.get("memories", [])
        queries = test_db.get("queries", [])
        self._memories = memories
        self._id_map = {m["memory_id"]: m for m in memories}

        # Step 1: 存储
        self.adapter.reset()
        stored = 0
        for m in memories:
            content = m.get("content", "")
            if content:
                self.adapter.store(content, {"memory_id": m["memory_id"]})
                stored += 1

        # Step 2: 评测
        pos_queries = [q for q in queries if not q.get("is_negative")]
        neg_queries = [q for q in queries if q.get("is_negative")]

        self.report = {
            "storage": {
                "stored": stored,
                "total": len(memories),
                "integrity": round(stored / len(memories), 3) if memories else 0,
            },
            "retrieval": self._eval_retrieval(pos_queries),
            "negative": self._eval_negative(neg_queries),
            "temporal": self._eval_temporal(pos_queries, memories),
            "coverage": self._eval_coverage(pos_queries, memories),
        }
        return self.report

    def _eval_retrieval(self, queries: list) -> dict:
        """精确检索 + 组合检索评测"""
        by_type: Dict[str, Dict[str, Any]] = {}
        total_correct = 0
        total_expected = 0
        total_mrr = 0.0

        for q in queries:
            expected_ids = set(q.get("expected_memory_ids", []))
            if not expected_ids:
                continue

            query_text = q.get("query_text", "")
            results = self.adapter.search(query_text, top_k=20)
            found_ids = [r.get("memory_id", "") for r in results[:20]]

            # Precision / Recall
            correct = len(set(found_ids) & expected_ids)
            total_correct += correct
            total_expected += len(expected_ids)

            # MRR
            mrr = 0.0
            for rank, mid in enumerate(found_ids, 1):
                if mid in expected_ids:
                    mrr = 1.0 / rank
                    break
            total_mrr += mrr

            qtype = q.get("query_type", "unknown")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "expected": 0, "count": 0, "mrr_sum": 0.0}
            by_type[qtype]["correct"] += correct
            by_type[qtype]["expected"] += len(expected_ids)
            by_type[qtype]["count"] += 1
            by_type[qtype]["mrr_sum"] += mrr

        n_pos = len([q for q in queries if q.get("expected_memory_ids")])
        result = {
            "by_type": {
                k: {
                    "precision": round(v["correct"] / (v["count"] * 20), 3) if v["count"] > 0 else 0,
                    "recall": round(v["correct"] / v["expected"], 3) if v["expected"] > 0 else 0,
                    "mrr": round(v["mrr_sum"] / v["count"], 3) if v["count"] > 0 else 0,
                    "count": v["count"],
                }
                for k, v in by_type.items()
            },
            "overall_precision": round(total_correct / (n_pos * 20), 3) if n_pos > 0 else 0,
            "overall_recall": round(total_correct / total_expected, 3) if total_expected > 0 else 0,
            "overall_mrr": round(total_mrr / n_pos, 3) if n_pos > 0 else 0,
        }
        return result

    def _eval_negative(self, queries: list) -> dict:
        """负样本评测：查询不应返回任何结果"""
        if not queries:
            return {"total": 0, "correct": 0, "accuracy": "N/A"}

        correct = 0
        for q in queries:
            results = self.adapter.search(q.get("query_text", ""), top_k=20)
            # 负样本查询不应返回任何 expected memory
            expected_ids = set(q.get("expected_memory_ids", []))
            found_ids = {r.get("memory_id", "") for r in results[:20]}
            # 正确 = 没有返回任何 expected_id 中的记忆（expected_ids 应为空集）
            if not (found_ids & expected_ids):
                correct += 1

        return {
            "total": len(queries),
            "correct": correct,
            "accuracy": round(correct / len(queries), 3),
        }

    def _eval_temporal(self, queries: list, memories: list) -> dict:
        """时序推理评测：检查时序相关查询的检索质量"""
        temporal_queries = [q for q in queries
                           if q.get("query_type") in ("时序推理", "组合推理")]

        if not temporal_queries:
            return {"total": 0, "recall": "N/A"}

        correct = 0
        total_expected = 0
        for q in temporal_queries:
            expected_ids = set(q.get("expected_memory_ids", []))
            if not expected_ids:
                continue
            results = self.adapter.search(q.get("query_text", ""), top_k=20)
            found_ids = {r.get("memory_id", "") for r in results[:20]}
            correct += len(found_ids & expected_ids)
            total_expected += len(expected_ids)

        return {
            "total": len(temporal_queries),
            "recall": round(correct / total_expected, 3) if total_expected > 0 else 0,
        }

    def _eval_coverage(self, queries: list, memories: list) -> dict:
        """记忆覆盖率：多少条记忆至少被一个查询命中"""
        if not queries or not memories:
            return {"covered": 0, "total": len(memories), "rate": "N/A"}

        hit_memories = set()
        for q in queries:
            for mid in q.get("expected_memory_ids", []):
                hit_memories.add(mid)

        total = len(memories)
        covered = len(hit_memories)
        return {
            "covered": covered,
            "total": total,
            "rate": round(covered / total, 3) if total > 0 else 0,
        }

    def summary(self) -> str:
        """生成可读的评测摘要"""
        r = self.report
        lines = ["=" * 60, "MemTest 评测报告", "=" * 60]

        if "storage" in r:
            s = r["storage"]
            lines.append(f"存储完整性: {s['integrity']:.1%} ({s['stored']}/{s['total']})")

        if "retrieval" in r:
            ret = r["retrieval"]
            lines.append(f"检索: P={ret['overall_precision']:.1%} "
                        f"R={ret['overall_recall']:.1%} "
                        f"MRR={ret['overall_mrr']:.3f}")
            for t, v in ret.get("by_type", {}).items():
                lines.append(f"  {t}: P={v['precision']:.1%} R={v['recall']:.1%} "
                            f"MRR={v['mrr']:.3f} (n={v['count']})")

        if "negative" in r:
            neg = r["negative"]
            lines.append(f"负样本准确率: {neg.get('accuracy', 'N/A')}")

        if "temporal" in r:
            tmp = r["temporal"]
            lines.append(f"时序推理召回: {tmp.get('recall', 'N/A')} (n={tmp.get('total', 0)})")

        if "coverage" in r:
            cov = r["coverage"]
            lines.append(f"记忆覆盖率: {cov.get('rate', 'N/A')} ({cov.get('covered', 0)}/{cov.get('total', 0)})")

        lines.append("=" * 60)
        return "\n".join(lines)


# ==============================================================================
# 内置基线适配器（简单关键词匹配）
# ==============================================================================

class JsonMemoryAdapter(MemoryAdapter):
    """基于关键词匹配的内存适配器（基线对照用，非语义检索）"""

    def __init__(self):
        self.store_dict: Dict[str, str] = {}

    def reset(self):
        self.store_dict.clear()

    def store(self, memory_text: str, metadata: dict):
        mid = metadata.get("memory_id", "")
        if mid and memory_text:
            self.store_dict[mid] = memory_text

    def search(self, query: str, top_k: int = 20) -> list:
        import re
        query = query.replace("，", " ").replace("？", " ").replace("。", " ")
        keywords = []
        for token in query.split():
            if re.search(r'[\u4e00-\u9fff]', token):
                # 中文：2-gram分词
                chars = [c for c in token if re.search(r'[\u4e00-\u9fff]', c)]
                for i in range(len(chars) - 1):
                    keywords.append(chars[i] + chars[i+1])
                if not keywords and chars:
                    keywords.extend(chars)
            elif len(token) > 1:
                keywords.append(token.lower())
        keywords = list(set(keywords))
        if not keywords:
            return []

        scored = []
        for mid, content in self.store_dict.items():
            score_val = sum(1 for k in keywords if k in content) / len(keywords)
            if score_val > 0:
                scored.append({"memory_id": mid, "score": score_val, "content": content})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]


# ==============================================================================
# 工具函数
# ==============================================================================

def load_test_db(path: str) -> dict:
    """加载测试数据库"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
