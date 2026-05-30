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

        # 1. 清空 + 加载（兼容 generator 的 versions 列表和 benchmark 的 content 字符串）
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
                # Legacy benchmark format: single content field
                meta = self._flatten_meta(m)
                self.adapter.store(m.get("content", ""), meta)
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
        """Flatten metadata, handling both nested-dict (generator) and string (legacy benchmark) formats."""
        # Time: may be dict {'absolute':...} or plain string
        t = m.get("time", {})
        if isinstance(t, str):
            time_abs, time_rel = t, ""
        else:
            time_abs = t.get("absolute", "") if isinstance(t, dict) else ""
            time_rel = t.get("relative", "") if isinstance(t, dict) else ""

        # Location: may be dict {'city':...} or plain string
        loc = m.get("location", {})
        if isinstance(loc, str):
            loc_city, loc_place = loc, ""
        else:
            loc_city = loc.get("city", "") if isinstance(loc, dict) else ""
            loc_place = loc.get("place", "") if isinstance(loc, dict) else ""

        # Person: may be dict {'name':...} or plain string
        pers = m.get("person", {})
        if isinstance(pers, str):
            pers_name, pers_identity = pers, ""
        else:
            pers_name = pers.get("name", "") if isinstance(pers, dict) else ""
            pers_identity = pers.get("identity", "") if isinstance(pers, dict) else ""

        # Event: may be dict {'type':...} or plain string
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
            "decay_level": (m.get("decay") or {}).get("level") if isinstance(m.get("decay"), dict) else None,
            "access_count": (m.get("decay") or {}).get("access_count", 0) if isinstance(m.get("decay"), dict) else 0,
        }

    def _eval_storage(self, stored: int, total: int) -> dict:
        return {"stored_count": stored, "total": total,
                "integrity": stored / total if total > 0 else 0}

    def _eval_retrieval(self, queries: list) -> dict:
        by_type = {}
        total_correct, total_expected = 0, 0
        # Pre-build entity index for target_entity-based evaluation
        entity_index = self._build_entity_index() if any(q.get("target_entity") and not q.get("expected_memory_ids") for q in queries) else None
        for q in queries:
            # Support both expected_memory_ids and target_entity evaluation
            expected_ids = set(q.get("expected_memory_ids", []))
            target_entity = q.get("target_entity")
            if not expected_ids and target_entity and entity_index:
                expected_ids = entity_index.get(target_entity, set())
            if not expected_ids:
                continue
            # Support both 'query_text' (generator) and 'query' (legacy benchmark)
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

    def _build_entity_index(self) -> dict:
        """Build index of entity -> set of memory_ids for target_entity evaluation."""
        # Use a simple approach: store all content in memory and search for entity
        index = {}
        # We need to get memories from the adapter, but adapter doesn't expose list interface
        # Fallback: use JsonMemoryAdapter's internal store_dict if available
        store_dict = getattr(self.adapter, 'store_dict', None)
        if store_dict:
            for mid, content in store_dict.items():
                # Simple tokenization for entity matching
                for entity in self._extract_entities(content):
                    index.setdefault(entity, set()).add(mid)
        return index

    @staticmethod
    def _extract_entities(text: str) -> list:
        """Extract potential entity names from text for indexing."""
        import re
        # Match Chinese names (2-4 chars) and English capitalized words
        entities = []
        # Chinese consecutive characters that look like names/places
        for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
            entities.append(m.group())
        # English words with capital letters
        for m in re.finditer(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text):
            entities.append(m.group())
        return entities

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
                # Support both dict and string formats for person/event
                pers = m.get("person", {})
                pers_name = pers.get("name", "") if isinstance(pers, dict) else str(pers)
                evt = m.get("event", {})
                evt_product = evt.get("product", "") if isinstance(evt, dict) else str(evt)
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
        high_freq = [m for m in memories if (m.get("decay") or {}).get("level") == "高频记忆"]
        low_freq = [m for m in memories if (m.get("decay") or {}).get("level") in ("低频记忆", "偶发事件")]

        def check(mems, label):
            if not mems: return {"label": label, "found": 0, "total": 0, "retention": 0}
            found = 0
            for m in mems[:20]:
                # Support both 'versions' list and plain 'content' string
                versions = m.get("versions")
                if versions:
                    q = versions[0].get("content", "")
                else:
                    q = m.get("content", "")
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
                query_text = q.get("query_text") or q.get("query", "")
                results = self.adapter.search(query_text, top_k=20)
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
            # Support both 'versions' list and plain 'content' string
            versions = m.get("versions")
            if versions:
                q = versions[0].get("content", "")
            else:
                q = m.get("content", "")
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
        # Simple keyword matching: English by whitespace, Chinese by character n-grams
        import re
        query = query.replace("，", " ").replace("？", " ").replace("。", " ")
        # Collect keywords: English words (2+ chars) and single CJK characters
        keywords = []
        for token in query.split():
            if re.search(r'[\u4e00-\u9fff]', token):
                # CJK text: add each character as keyword
                keywords.extend([c for c in token if re.search(r'[\u4e00-\u9fff]', c)])
            elif len(token) >= 2:
                keywords.append(token)
        keywords = [k for k in set(keywords) if k]
        if not keywords:
            return []
        scored = []
        for mid, content in self.store_dict.items():
            score = sum(1 for k in keywords if k in content) / len(keywords)
            if score > 0:
                scored.append({"memory_id": mid, "score": score, "content": content})
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
