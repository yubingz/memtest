"""MemTest 评测执行器 — v4 兼容，content-only 存储

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

关键变更 (v4):
    - adapter.store() 只传 memory_id + content（不传元数据，避免泄题）
    - 元数据（person/time/location）由评测系统内部持有，用于出题，不喂给被测系统
    - v2 和 v4 格式均可运行，自动检测
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
        v2 模式下 metadata 含 memory_id + 元数据（兼容旧系统）。

        Args:
            memory_text: 记忆文本（原文）
            metadata: {"memory_id": str}  (v4) 或完整元数据 (v2)
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
    def __init__(self, adapter: MemoryAdapter):
        self.adapter = adapter
        self.report: Dict[str, Any] = {}
        self._db_version: str = "v4"

    def run(self, test_db: dict) -> dict:
        """执行全量评测，自动检测 v2/v4 格式"""
        memories = test_db.get("memories", [])
        queries = test_db.get("queries", [])
        if not memories:
            return {"error": "empty database"}

        # 检测版本
        self._db_version = self._detect_version(memories)
        if self._db_version == "v4":
            return self._run_v4(test_db)
        else:
            return self._run_v2(test_db)

    # --------------------------------------------------------------------------
    # v4 存储模式（content-only）
    # --------------------------------------------------------------------------

    def _run_v4(self, test_db: dict) -> dict:
        """v4 评测：只传 memory_id + content 给被测系统"""
        memories = test_db.get("memories", [])
        queries = test_db.get("queries", [])

        self.adapter.reset()
        stored = 0

        for m in memories:
            # v4: 只存 memory_id + content，不传元数据
            content = m.get("content", "")
            if content:
                # metadata 只含 memory_id（用于检索返回）
                metadata = {"memory_id": m["memory_id"]}
                self.adapter.store(content, metadata)
                stored += 1

        self.report = {
            "storage": self._eval_storage(stored, len(memories)),
            "retrieval": self._eval_retrieval_v4(queries),
        }
        return self.report

    def _eval_retrieval_v4(self, queries: list) -> dict:
        """v4 检索评估（基于 content-only 存储）"""
        by_type: Dict[str, Dict[str, Any]] = {}
        total_correct = 0
        total_expected = 0

        for q in queries:
            expected_ids = set(q.get("expected_memory_ids", []))
            if not expected_ids:
                continue

            query_text = q.get("query_text", "") or q.get("query", "")
            results = self.adapter.search(query_text, top_k=20)
            found_ids = {r.get("memory_id", "") for r in results[:20]}
            correct = len(found_ids & expected_ids)

            qtype = q.get("query_type", "unknown")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "expected": 0, "count": 0}
            by_type[qtype]["correct"] += correct
            by_type[qtype]["expected"] += len(expected_ids)
            by_type[qtype]["count"] += 1
            total_correct += correct
            total_expected += len(expected_ids)

        for t in by_type.values():
            t["precision"] = t["correct"] / (t["count"] * 20) if t["count"] > 0 else 0
            t["recall"] = t["correct"] / t["expected"] if t["expected"] > 0 else 0

        return {
            "by_type": {k: {
                "precision": round(v["precision"], 3),
                "recall": round(v["recall"], 3),
                "count": v["count"],
            } for k, v in by_type.items()},
            "overall_precision": round(total_correct / (len(queries) * 20), 3) if queries else 0,
            "overall_recall": round(total_correct / total_expected, 3) if total_expected > 0 else 0,
        }

    # --------------------------------------------------------------------------
    # v2 兼容模式（原有逻辑）
    # --------------------------------------------------------------------------

    def _run_v2(self, test_db: dict) -> dict:
        """v2 评测：传完整元数据（兼容旧系统）"""
        memories = test_db.get("memories", [])
        queries = test_db.get("queries", [])

        self.adapter.reset()
        stored = 0
        for m in memories:
            versions = m.get("versions")
            if versions:
                for v in versions:
                    meta = self._flatten_meta(m)
                    self.adapter.store(v.get("content", ""), meta)
                    stored += 1
            else:
                meta = self._flatten_meta(m)
                self.adapter.store(m.get("content", ""), meta)
                stored += 1

        self.report = {
            "storage": self._eval_storage(stored, len(memories)),
            "retrieval": self._eval_retrieval_v2(queries),
            "organization": self._eval_organization(memories),
            "forgetting": self._eval_forgetting(memories),
            "reasoning": self._eval_reasoning(memories, queries),
            "deep_retrieval": self._eval_deep(memories, queries),
        }
        return self.report

    def _eval_retrieval_v2(self, queries: list) -> dict:
        """v2 检索评估（原有逻辑）"""
        by_type = {}
        total_correct = 0
        total_expected = 0
        entity_index = (self._build_entity_index()
                       if any(q.get("target_entity") and not q.get("expected_memory_ids")
                              for q in queries) else None)
        for q in queries:
            expected_ids = set(q.get("expected_memory_ids", []))
            target_entity = q.get("target_entity")
            if not expected_ids and target_entity and entity_index:
                expected_ids = entity_index.get(target_entity, set())
            if not expected_ids:
                continue
            query_text = q.get("query_text") or q.get("query", "")
            results = self.adapter.search(query_text, top_k=20)
            found_ids = {r.get("memory_id", "") for r in results[:20]}
            correct = len(found_ids & expected_ids)
            qtype = q.get("query_type", "unknown")
            if qtype not in by_type:
                by_type[qtype] = {"correct": 0, "expected": 0, "count": 0}
            by_type[qtype]["correct"] += correct
            by_type[qtype]["expected"] += len(expected_ids)
            by_type[qtype]["count"] += 1
            total_correct += correct
            total_expected += len(expected_ids)

        for t in by_type.values():
            t["precision"] = t["correct"] / (t["count"] * 20) if t["count"] > 0 else 0
            t["recall"] = t["correct"] / t["expected"] if t["expected"] > 0 else 0

        return {
            "by_type": {k: {"precision": round(v["precision"], 3), "recall": round(v["recall"], 3),
                             "count": v["count"]} for k, v in by_type.items()},
            "overall_precision": round(total_correct / (len(queries) * 20), 3) if queries else 0,
            "overall_recall": round(total_correct / total_expected, 3) if total_expected > 0 else 0,
        }

    def _detect_version(self, memories: list) -> str:
        """检测数据库版本"""
        if not memories:
            return "v4"
        first = memories[0]
        if "content" in first and "versions" not in first:
            return "v4"
        if "versions" in first:
            return "v2"
        if isinstance(first.get("person"), dict):
            return "v2"
        return "v4"

    # --------------------------------------------------------------------------
    # v2 兼容辅助方法
    # --------------------------------------------------------------------------

    def _flatten_meta(self, m: dict) -> dict:
        """Flatten metadata (v2 模式)"""
        t = m.get("time", {})
        if isinstance(t, str):
            time_abs, time_rel = t, ""
        else:
            time_abs = (t.get("absolute", "") or t.get("timestamp", "")
                       if isinstance(t, dict) else "")
            time_rel = (t.get("relative", "") if isinstance(t, dict) else "")

        loc = m.get("location", {})
        if isinstance(loc, str):
            loc_city, loc_place = loc, ""
        else:
            loc_city = loc.get("city", "") if isinstance(loc, dict) else ""
            loc_place = loc.get("place", "") if isinstance(loc, dict) else ""

        pers = m.get("person", {})
        if isinstance(pers, str):
            pers_name, pers_identity = pers, ""
        else:
            pers_name = pers.get("name", "") if isinstance(pers, dict) else ""
            pers_identity = pers.get("identity", "") if isinstance(pers, dict) else ""

        evt = m.get("event", {})
        if isinstance(evt, str):
            evt_type, evt_action, evt_product = evt, "", ""
        else:
            evt_type = evt.get("type", "") if isinstance(evt, dict) else ""
            evt_action = evt.get("action", "") if isinstance(evt, dict) else ""
            evt_product = evt.get("product", "") if isinstance(evt, dict) else ""

        return {
            "memory_id": m["memory_id"],
            "category": m.get("category", ""),
            "difficulty": m.get("difficulty", ""),
            "time_absolute": time_abs,
            "time_relative": time_rel,
            "location_city": loc_city,
            "location_place": loc_place,
            "person_name": pers_name,
            "person_identity": pers_identity,
            "event_type": evt_type,
            "event_action": evt_action,
            "event_product": evt_product,
            "weight": m.get("weight", 1.0),
            "cluster_id": m.get("cluster_id"),
            "reasoning_chain": m.get("reasoning_chain"),
            "chain_position": m.get("chain_position"),
            "decay_level": ((m.get("decay") or {}).get("level")
                           if isinstance(m.get("decay"), dict) else None),
            "access_count": ((m.get("decay") or {}).get("access_count", 0)
                           if isinstance(m.get("decay"), dict) else 0),
        }

    def _eval_storage(self, stored: int, total: int) -> dict:
        return {"stored_count": stored, "total": total,
                "integrity": stored / total if total > 0 else 0}

    def _build_entity_index(self) -> dict:
        index = {}
        store_dict = getattr(self.adapter, 'store_dict', None)
        if store_dict:
            for mid, content in store_dict.items():
                for entity in self._extract_entities(content):
                    index.setdefault(entity, set()).add(mid)
        return index

    @staticmethod
    def _extract_entities(text: str) -> list:
        import re
        entities = []
        for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
            entities.append(m.group())
        for m in re.finditer(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text):
            entities.append(m.group())
        return entities

    def _eval_organization(self, memories: list) -> dict:
        clusters = {}
        for m in memories:
            cid = m.get("cluster_id")
            if cid:
                clusters.setdefault(cid, []).append(m["memory_id"])
        if not clusters:
            return {"cluster_accuracy": "N/A", "clusters_tested": 0}
        correct = 0
        total = 0
        for cid, mem_ids in clusters.items():
            if len(mem_ids) < 2:
                continue
            for mid in mem_ids[:3]:
                m = next((x for x in memories if x["memory_id"] == mid), None)
                if not m:
                    continue
                pers = m.get("person", {})
                pers_name = (pers.get("name", "") if isinstance(pers, dict)
                            else str(pers))
                evt = m.get("event", {})
                evt_product = (evt.get("product", "") if isinstance(evt, dict)
                              else str(evt))
                query = f"{pers_name} {evt_product}".strip()
                if not query:
                    query = m.get("content", "")[:40]
                results = self.adapter.search(query, top_k=10)
                found = {r.get("memory_id") for r in results[:10]}
                if any(cmid in found for cmid in mem_ids if cmid != mid):
                    correct += 1
                total += 1
        return {"cluster_accuracy": round(correct / total, 3) if total > 0 else 0,
                "clusters_tested": len(clusters)}

    def _eval_forgetting(self, memories: list) -> dict:
        high_freq = [m for m in memories
                    if (m.get("decay") or {}).get("level") == "高频记忆"]
        low_freq = [m for m in memories
                   if (m.get("decay") or {}).get("level") in ("低频记忆", "偶发事件")]

        def check(mems, label):
            if not mems:
                return {"label": label, "found": 0, "total": 0, "retention": 0}
            found = 0
            for m in mems[:20]:
                versions = m.get("versions")
                q = versions[0].get("content", "") if versions else m.get("content", "")
                results = self.adapter.search(q, top_k=10)
                ids = {r.get("memory_id") for r in results[:10]}
                if m["memory_id"] in ids:
                    found += 1
            return {"label": label, "found": found,
                    "total": min(20, len(mems)),
                    "retention": round(found / min(20, len(mems)), 3)}

        h = check(high_freq, "高频")
        l = check(low_freq, "低频")
        valid = h["retention"] > l["retention"]
        return {"high_freq_retention": h["retention"], "low_freq_retention": l["retention"],
                "forgetting_ratio_valid": valid}

    def _eval_reasoning(self, memories: list, queries: list) -> dict:
        reasoning_queries = [q for q in queries if q.get("query_type") == "组合推理"]
        logic_queries = [q for q in queries if q.get("query_type") in ("事件检索", "组合检索")]

        def score(qs):
            if not qs:
                return 0, 0
            correct = 0
            for q in qs:
                expected = set(q.get("expected_memory_ids", []))
                query_text = q.get("query_text") or q.get("query", "")
                results = self.adapter.search(query_text, top_k=20)
                found = {r.get("memory_id") for r in results[:20]}
                if found & expected:
                    correct += 1
            return correct, len(qs)

        lc, lt = score(logic_queries)
        rc, rt = score(reasoning_queries)
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
            versions = m.get("versions")
            q = versions[0].get("content", "") if versions else m.get("content", "")
            results = self.adapter.search(q, top_k=10)
            ids = {r.get("memory_id") for r in results[:10]}
            if m["memory_id"] in ids:
                result[dist][0] += 1
            result[dist][1] += 1
        return {d: round(c / t, 3) if t > 0 else 0 for d, (c, t) in result.items()}


# ==============================================================================
# 内置 MemoryAdapter
# ==============================================================================

class JsonMemoryAdapter(MemoryAdapter):
    """基于 JSON 的内存记忆系统（用于验证测试数据）"""

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
                keywords.extend([c for c in token if re.search(r'[\u4e00-\u9fff]', c)])
            elif len(token) > 1:
                keywords.append(token)
        keywords = [k for k in set(keywords) if k]
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summary(report: dict) -> str:
    """生成可读的评测摘要"""
    lines = ["=" * 60, "MemTest 评测报告", "=" * 60]
    if "storage" in report:
        s = report["storage"]
        lines.append(f"存储完整性: {s.get('integrity', 0):.1%} "
                    f"({s.get('stored_count', 0)}/{s.get('total', 0)})")
    if "retrieval" in report:
        r = report["retrieval"]
        lines.append(f"检索 Precision: {r.get('overall_precision', 0):.1%} "
                    f"Recall: {r.get('overall_recall', 0):.1%}")
        for t, v in r.get("by_type", {}).items():
            lines.append(f"  {t}: P={v['precision']:.1%} R={v['recall']:.1%} (n={v['count']})")
    if "organization" in report:
        lines.append(f"整理聚类: {report['organization'].get('cluster_accuracy', 'N/A')}")
    if "forgetting" in report:
        fg = report["forgetting"]
        lines.append(f"遗忘: 高频保留={fg.get('high_freq_retention', 0):.1%} "
                    f"低频保留={fg.get('low_freq_retention', 0):.1%} "
                    f"{'✓合理' if fg.get('forgetting_ratio_valid') else '✗异常'}")
    if "reasoning" in report:
        rs = report["reasoning"]
        lines.append(f"逻辑推理: {rs.get('logic_accuracy', 0):.1%} "
                    f"链推理: {rs.get('chain_accuracy', 0):.1%}")
    if "deep_retrieval" in report:
        d = report["deep_retrieval"]
        lines.append(f"深度检索: 近={d.get('near', 'N/A')} "
                    f"中={d.get('mid', 'N/A')} 远={d.get('far', 'N/A')}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ==============================================================================
# 自测
# ==============================================================================

if __name__ == "__main__":
    import os

    # 生成一个 v4 格式的测试数据库
    from schema import finalize_database, make_memory_id

    test_memories = [
        {
            "memory_id": make_memory_id(i),
            "content": f"这是测试记忆{i}的内容，描述了一个包含人物、地点和时间的事件。",
            "person": ["张三"],
            "time_absolute": "2024-01-15",
            "time_relative": None,
            "time_ref_id": None,
            "time_offset_days": None,
            "location": "北京",
            "event_type": "测试",
            "source": "测试",
            "tags": ["测试"],
            "difficulty": "easy",
        }
        for i in range(10)
    ]

    test_queries = [
        {
            "query_id": f"Q{i:04d}",
            "query_text": f"张三在{2024}年做了什么？",
            "query_type": "事实检索",
            "test_dimension": "fact",
            "expected_memory_ids": [test_memories[0]["memory_id"]],
            "expected_answer": test_memories[0]["content"],
            "difficulty": "easy",
            "is_negative": False,
        }
        for i in range(5)
    ]

    # 添加负样本
    test_queries.append({
        "query_id": "Q9999",
        "query_text": "火星人在月球基地做了什么？",
        "query_type": "负样本",
        "test_dimension": "负样本",
        "expected_memory_ids": [],
        "expected_answer": "",
        "difficulty": "medium",
        "is_negative": True,
    })

    db = finalize_database({
        "memories": test_memories,
        "queries": test_queries,
    }, name="Test DB", description="v4自测")

    # 运行评测
    adapter = JsonMemoryAdapter()
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(summary(report))
    print(f"\n✅ runner.py 自测通过 (v{suite._db_version} 模式)")
