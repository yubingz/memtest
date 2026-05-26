"""MemTest 评测执行器 — 适配任意记忆系统

使用方法:
    from memtest import MemoryTestSuite, MemoryAdapter, load_test_db

    class MyAdapter(MemoryAdapter):
        def reset(self): ...
        def store(self, text, meta): ...
        def search(self, query, top_k): ...

    db = load_test_db("sample_db_100.json")
    adapter = MyAdapter()
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(report.summary())
"""

import json
from typing import List, Dict, Any


# ====== 适配器基类 ======
class MemoryAdapter:
    """被测记忆系统的抽象接口。只实现这 3 个方法即可接入评测。"""

    def reset(self):
        """清空记忆库"""
        raise NotImplementedError

    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆
        Args:
            memory_text: 记忆文本
            metadata: 标准元数据 (参见 API.md)
        """
        raise NotImplementedError

    def search(self, query: str, top_k: int = 20) -> list:
        """检索记忆
        Returns:
            [{"memory_id": str, "score": float, "content": str}, ...]
        """
        raise NotImplementedError


# ====== 评测套件 ======
class MemoryTestSuite:
    def __init__(self, adapter: MemoryAdapter):
        self.adapter = adapter
        self.report = {}

    def run(self, test_db: dict) -> dict:
        """执行全量评测"""
        memories = test_db.get("memories", [])
        queries = test_db.get("queries", [])
        if not memories:
            return {"error": "empty database"}

        # 1. 清空 + 加载
        self.adapter.reset()
        stored = 0
        for m in memories:
            for v in m.get("versions", []):
                meta = self._flatten_meta(m)
                self.adapter.store(v["content"], meta)
                stored += 1

        self.report = {
            "storage": self._eval_storage(stored, len(memories)),
            "retrieval": self._eval_retrieval(queries),
            "organization": self._eval_organization(memories),
            "forgetting": self._eval_forgetting(memories),
            "reasoning": self._eval_reasoning(memories, queries),
            "deep_retrieval": self._eval_deep(memories, queries),
        }
        return self.report

    # ---- 内部方法 ----
    def _flatten_meta(self, m: dict) -> dict:
        return {
            "memory_id": m["memory_id"],
            "category": m.get("category", ""),
            "difficulty": m.get("difficulty", ""),
            "time_absolute": m.get("time", {}).get("absolute", ""),
            "time_relative": m.get("time", {}).get("relative", ""),
            "location_city": m.get("location", {}).get("city", ""),
            "location_place": m.get("location", {}).get("place", ""),
            "person_name": m.get("person", {}).get("name", ""),
            "person_identity": m.get("person", {}).get("identity", ""),
            "event_type": m.get("event", {}).get("type", ""),
            "event_action": m.get("event", {}).get("action", ""),
            "event_product": m.get("event", {}).get("product", ""),
            "weight": m.get("weight", 1.0),
            "cluster_id": m.get("cluster_id"),
            "reasoning_chain": m.get("reasoning_chain"),
            "chain_position": m.get("chain_position"),
            "decay_level": (m.get("decay") or {}).get("level"),
            "access_count": (m.get("decay") or {}).get("access_count", 0),
        }

    def _eval_storage(self, stored: int, total: int) -> dict:
        return {"stored_count": stored, "total": total,
                "integrity": stored / total if total > 0 else 0}

    def _eval_retrieval(self, queries: list) -> dict:
        by_type = {}
        total_correct, total_expected = 0, 0
        for q in queries:
            expected = set(q.get("expected_memory_ids", []))
            if not expected: continue
            results = self.adapter.search(q["query_text"], top_k=20)
            found_ids = {r.get("memory_id", "") for r in results[:20]}
            correct = len(found_ids & expected)
            qtype = q.get("query_type", "unknown")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "expected": 0, "count": 0}
            by_type[qtype]["correct"] += correct
            by_type[qtype]["expected"] += len(expected)
            by_type[qtype]["count"] += 1
            total_correct += correct
            total_expected += len(expected)

        for t in by_type.values():
            t["precision"] = t["correct"] / (t["count"] * 20) if t["count"] > 0 else 0
            t["recall"] = t["correct"] / t["expected"] if t["expected"] > 0 else 0

        return {
            "by_type": {k: {"precision": round(v["precision"], 3), "recall": round(v["recall"], 3),
                             "count": v["count"]} for k, v in by_type.items()},
            "overall_precision": round(total_correct / (len(queries) * 20), 3) if queries else 0,
            "overall_recall": round(total_correct / total_expected, 3) if total_expected > 0 else 0,
        }

    def _eval_organization(self, memories: list) -> dict:
        clusters = {}
        for m in memories:
            cid = m.get("cluster_id")
            if cid: clusters.setdefault(cid, []).append(m["memory_id"])
        if not clusters:
            return {"cluster_accuracy": "N/A", "clusters_tested": 0}
        correct = 0; total = 0
        for cid, mem_ids in clusters.items():
            if len(mem_ids) < 2: continue
            for mid in mem_ids[:3]:
                m = next((x for x in memories if x["memory_id"] == mid), None)
                if not m: continue
                query = f"{m['person']['name']} {m['event']['product']}"
                results = self.adapter.search(query, top_k=10)
                found = {r.get("memory_id") for r in results[:10]}
                if any(cmid in found for cmid in mem_ids if cmid != mid):
                    correct += 1
                total += 1
        return {"cluster_accuracy": round(correct / total, 3) if total > 0 else 0,
                "clusters_tested": len(clusters)}

    def _eval_forgetting(self, memories: list) -> dict:
        high_freq = [m for m in memories if (m.get("decay") or {}).get("level") == "高频记忆"]
        low_freq = [m for m in memories if (m.get("decay") or {}).get("level") in ("低频记忆", "偶发事件")]

        def check(mems, label):
            if not mems: return {"label": label, "found": 0, "total": 0, "retention": 0}
            found = 0
            for m in mems[:20]:
                q = m["versions"][0]["content"]
                results = self.adapter.search(q, top_k=10)
                ids = {r.get("memory_id") for r in results[:10]}
                if m["memory_id"] in ids: found += 1
            return {"label": label, "found": found, "total": min(20, len(mems)),
                    "retention": round(found / min(20, len(mems)), 3)}

        h = check(high_freq, "高频"); l = check(low_freq, "低频")
        valid = h["retention"] > l["retention"]
        return {"high_freq_retention": h["retention"], "low_freq_retention": l["retention"],
                "forgetting_ratio_valid": valid}

    def _eval_reasoning(self, memories: list, queries: list) -> dict:
        reasoning_queries = [q for q in queries if q.get("query_type") == "组合推理"]
        logic_queries = [q for q in queries if q.get("query_type") in ("事件检索", "组合检索")]

        def score(qs):
            if not qs: return 0, 0
            correct = 0
            for q in qs:
                expected = set(q.get("expected_memory_ids", []))
                results = self.adapter.search(q["query_text"], top_k=20)
                found = {r.get("memory_id") for r in results[:20]}
                if found & expected: correct += 1
            return correct, len(qs)

        lc, lt = score(logic_queries); rc, rt = score(reasoning_queries)
        return {"logic_accuracy": round(lc / lt, 3) if lt > 0 else 0,
                "chain_accuracy": round(rc / rt, 3) if rt > 0 else 0}

    def _eval_deep(self, memories: list, queries: list) -> dict:
        deep_mems = [m for m in memories if m.get("category") == "长期记忆深度检索测试集"]
        if not deep_mems:
            return {"near": "N/A", "mid": "N/A", "far": "N/A"}
        result = {"near": [0, 0], "mid": [0, 0], "far": [0, 0]}
        for m in deep_mems[:30]:
            dist_map = {"近": "near", "中": "mid", "远": "far"}
            dist_raw = (m.get("depth") or {}).get("semantic_distance", "近")
            dist = dist_map.get(dist_raw, dist_raw)
            q = m["versions"][0]["content"]
            results = self.adapter.search(q, top_k=10)
            ids = {r.get("memory_id") for r in results[:10]}
            if m["memory_id"] in ids: result[dist][0] += 1
            result[dist][1] += 1
        return {d: round(c / t, 3) if t > 0 else 0 for d, (c, t) in result.items()}


# ====== 内置 MemoryAdapter：JSON 文件模拟（用于快速验证生成的数据） ======
class JsonMemoryAdapter(MemoryAdapter):
    """基于 JSON 文件的内存记忆系统 — 用于验证测试数据本身"""

    def __init__(self):
        self.store_dict = {}

    def reset(self):
        self.store_dict.clear()

    def store(self, memory_text: str, metadata: dict):
        mid = metadata.get("memory_id", "")
        if mid: self.store_dict[mid] = memory_text

    def search(self, query: str, top_k: int = 20) -> list:
        keywords = set(query.replace("，", " ").replace("？", " ").split())
        scored = []
        for mid, content in self.store_dict.items():
            score = sum(1 for k in keywords if k in content) / max(len(keywords), 1)
            if score > 0: scored.append({"memory_id": mid, "score": score, "content": content})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]


# ====== 工具函数 ======
def load_test_db(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summary(report: dict) -> str:
    """生成可读的评测摘要"""
    lines = ["=" * 60, "MemTest 评测报告", "=" * 60]
    if "storage" in report:
        s = report["storage"]
        lines.append(f"存储完整性: {s.get('integrity', 0):.1%} ({s.get('stored_count', 0)}/{s.get('total', 0)})")
    if "retrieval" in report:
        r = report["retrieval"]
        lines.append(f"检索 Precision: {r.get('overall_precision', 0):.1%} Recall: {r.get('overall_recall', 0):.1%}")
        for t, v in r.get("by_type", {}).items():
            lines.append(f"  {t}: P={v['precision']:.1%} R={v['recall']:.1%} (n={v['count']})")
    if "organization" in report:
        lines.append(f"整理聚类: {report['organization'].get('cluster_accuracy', 'N/A')}")
    if "forgetting" in report:
        fg = report["forgetting"]
        lines.append(f"遗忘: 高频保留={fg.get('high_freq_retention', 0):.1%} 低频保留={fg.get('low_freq_retention', 0):.1%} {'\u2713合理' if fg.get('forgetting_ratio_valid') else '\u2717异常'}")
    if "reasoning" in report:
        rs = report["reasoning"]
        lines.append(f"逻辑推理: {rs.get('logic_accuracy', 0):.1%} 链推理: {rs.get('chain_accuracy', 0):.1%}")
    if "deep_retrieval" in report:
        d = report["deep_retrieval"]
        lines.append(f"深度检索: 近={d.get('near', 'N/A')} 中={d.get('mid', 'N/A')} 远={d.get('far', 'N/A')}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ====== 快速自测 ======
if __name__ == "__main__":
    import sys, os
    db_path = "sample_db_100.json"
    if not os.path.exists(db_path):
        print("Generating sample data first...")
        from generator import build_database
        db = build_database(100)
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    db = load_test_db(db_path)
    adapter = JsonMemoryAdapter()
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(summary(report))
