"""MemTest 单元测试 — 覆盖 generator 和 knowledge_builder 核心功能。

运行:
    pytest test_memtest.py -v          # 详细输出
    pytest test_memtest.py -q          # 简洁输出
    pytest test_memtest.py --tb=short  # 短 trace

注意: 无需 LLM API key, 纯 mock/程序化测试。
"""

import json, os, pytest, random
from datetime import datetime
from collections import Counter

# 导入被测模块
import generator
import knowledge_builder as kb
import quality_check as qc

# ============================================================================
# 1. generator.py 测试
# ============================================================================

class TestGenerator:
    """测试程序化生成器核心功能。"""

    def test_build_database_smoke(self):
        """基础冒烟测试：能生成不报错。"""
        db = generator.build_database(50)
        assert "memories" in db
        assert "queries" in db
        assert len(db["memories"]) > 0
        assert len(db["queries"]) > 0

    def test_database_info_format(self):
        """database_info 字段格式正确。"""
        db = generator.build_database(50)
        info = db["database_info"]
        assert "name" in info
        assert "version" in info
        assert "total_count" in info
        assert "categories" in info
        assert info["total_count"] == len(db["memories"])

    def test_memory_id_unique(self):
        """记忆ID全局唯一。"""
        db = generator.build_database(50)
        ids = [m["memory_id"] for m in db["memories"]]
        assert len(ids) == len(set(ids))

    def test_memory_mandatory_fields(self):
        """每条记忆有必须字段。"""
        db = generator.build_database(50)
        required = {"memory_id", "person", "location", "event", "time", "versions", "difficulty", "weight"}
        for m in db["memories"]:
            missing = required - set(m.keys())
            assert not missing, f"{m['memory_id']} missing {missing}"

    def test_memory_versions_count(self):
        """每条记忆有3个版本。"""
        db = generator.build_database(50)
        for m in db["memories"]:
            assert len(m.get("versions", [])) == 3, f"{m['memory_id']} has {len(m.get('versions',[]))} versions"

    def test_time_fields(self):
        """time 字段有 absolute/relative/fuzzy。"""
        db = generator.build_database(50)
        for m in db["memories"]:
            t = m["time"]
            assert "absolute" in t
            assert "relative" in t
            assert "fuzzy" in t

    def test_query_id_unique(self):
        """查询ID全局唯一。"""
        db = generator.build_database(50)
        ids = [q["query_id"] for q in db["queries"]]
        assert len(ids) == len(set(ids))

    def test_query_mandatory_fields(self):
        """每条查询有必须字段。"""
        db = generator.build_database(50)
        required = {"query_id", "query_text", "query_type", "expected_memory_ids", "difficulty", "search_depth", "test_dimension"}
        for q in db["queries"]:
            missing = required - set(q.keys())
            assert not missing, f"{q['query_id']} missing {missing}"

    def test_query_points_to_valid_memories(self):
        """正样本查询指向的记忆必须存在。"""
        db = generator.build_database(50)
        mem_ids = {m["memory_id"] for m in db["memories"]}
        for q in db["queries"]:
            if not q.get("is_negative"):
                for mid in q["expected_memory_ids"]:
                    assert mid in mem_ids, f"{q['query_id']} points to missing {mid}"

    def test_negative_queries(self):
        """负样本标记和字段正确。"""
        db = generator.build_database(50)
        negs = [q for q in db["queries"] if q.get("is_negative")]
        assert len(negs) > 0, "至少要有负样本"
        for q in negs:
            assert q["expected_memory_ids"] == [], f"{q['query_id']} negative but has expected_memory_ids"
            assert q.get("expected_answer", "") == "", f"{q['query_id']} negative but has expected_answer"

    def test_expected_answer_structured(self):
        """正样本 expected_answer 是 dict 格式。"""
        db = generator.build_database(50)
        for q in db["queries"]:
            if not q.get("is_negative"):
                assert isinstance(q["expected_answer"], dict), f"{q['query_id']} expected_answer is not dict"
                assert "expected_answer_text" in q, f"{q['query_id']} missing expected_answer_text"
                assert "acceptable_answers" in q, f"{q['query_id']} missing acceptable_answers"

    def test_expected_time_field(self):
        """正样本有 expected_time 字段。"""
        db = generator.build_database(50)
        for q in db["queries"]:
            if not q.get("is_negative"):
                assert "expected_time" in q, f"{q['query_id']} missing expected_time"

    def test_dimension_balance(self):
        """维度分布有多个类别，不全是单一维度。"""
        db = generator.build_database(500)
        dims = Counter(q["test_dimension"] for q in db["queries"])
        total = len(db["queries"])
        # 至少5个不同维度
        assert len(dims) >= 5, f"只有 {len(dims)} 个维度，至少要有5个"
        # 负样本约20%
        negs = sum(1 for q in db["queries"] if q.get("is_negative"))
        assert negs / total >= 0.10, f"负样本占比 {negs/total:.2%}"

    def test_chain_data_integrity(self):
        """链式数据完整性：有 chain_id 的记忆必须有 prev/next 或位置信息。"""
        db = generator.build_database(100)
        chain_mems = [m for m in db["memories"] if m.get("reasoning_chain")]
        if chain_mems:
            for m in chain_mems:
                assert m.get("chain_position") is not None, f"{m['memory_id']} has chain but no position"
                assert m.get("chain_relation") is not None, f"{m['memory_id']} has chain but no relation"

    def test_chain_link_consistency(self):
        """链的前后连接一致性。"""
        db = generator.build_database(100)
        chain_mems = [m for m in db["memories"] if m.get("reasoning_chain")]
        by_chain = {}
        for m in chain_mems:
            cid = m["reasoning_chain"]
            by_chain.setdefault(cid, []).append(m)
        for cid, mems in by_chain.items():
            if len(mems) < 2:
                continue
            mems_sorted = sorted(mems, key=lambda x: x["chain_position"])
            for i in range(len(mems_sorted) - 1):
                cur = mems_sorted[i]
                nxt = mems_sorted[i+1]
                assert cur["chain_next"] == nxt["memory_id"], f"chain {cid} link broken at pos {i+1}"
                assert nxt["chain_prev"] == cur["memory_id"], f"chain {cid} reverse link broken at pos {i+2}"

    def test_cluster_data(self):
        """聚类数据存在且合理。"""
        db = generator.build_database(100)
        clusters = {}
        for m in db["memories"]:
            cid = m.get("cluster_id")
            if cid:
                clusters.setdefault(cid, []).append(m)
        if clusters:
            for cid, mems in clusters.items():
                assert len(mems) >= 3, f"cluster {cid} has only {len(mems)} memories"

    def test_seed_reproducibility(self):
        """固定种子结果可复现。"""
        generator.random.seed(42)
        db1 = generator.build_database(50)
        generator.random.seed(42)
        db2 = generator.build_database(50)
        ids1 = [m["memory_id"] for m in db1["memories"]]
        ids2 = [m["memory_id"] for m in db2["memories"]]
        assert ids1 == ids2

    def test_no_internal_error(self):
        """build_database 不抛出异常。"""
        try:
            generator.build_database(200)
        except Exception as e:
            pytest.fail(f"build_database raised {type(e).__name__}: {e}")


# ============================================================================
# 2. knowledge_builder.py 测试
# ============================================================================

class TestKnowledgeBuilder:
    """测试知识构建器 (不依赖 LLM API)。"""

    def _fake_facts(self, n=10):
        """构造假 facts 供 build_memories 使用。"""
        return [
            {
                "content": f"张三在北京购买了{i}号产品",
                "person": "张三",
                "location": "北京",
                "time": f"2024-01-{i+1:02d}",
                "dynasty": "",
                "event_type": "交易",
                "chain_id": "CHAIN_A" if i < 5 else "",
                "chain_position": (i % 5) + 1 if i < 5 else 0,
                "chain_relation": "因果" if i < 5 else "",
            }
            for i in range(n)
        ]

    def test_build_memories_from_facts(self):
        """能从 facts 构建记忆。"""
        facts = self._fake_facts(10)
        mems = kb.build_memories(facts)
        assert len(mems) == 10
        for m in mems:
            assert "memory_id" in m
            assert "person" in m
            assert "time" in m

    def test_generate_queries_basic(self):
        """能从记忆生成查询。"""
        facts = self._fake_facts(10)
        mems = kb.build_memories(facts)
        queries = kb.generate_queries(mems)
        assert len(queries) > 0
        for q in queries:
            assert "query_id" in q
            assert "query_text" in q

    def test_negative_query_format(self):
        """负样本查询格式正确。"""
        facts = self._fake_facts(10)
        mems = kb.build_memories(facts)
        queries = kb.generate_queries(mems)
        negs = [q for q in queries if q.get("is_negative")]
        if negs:
            for q in negs:
                assert q["expected_memory_ids"] == []
                assert "is_negative" in q and q["is_negative"] is True

    def test_memory_time_fields(self):
        """记忆有时间字段。"""
        facts = self._fake_facts(5)
        mems = kb.build_memories(facts)
        for m in mems:
            assert "time" in m
            assert "absolute" in m["time"]

    def test_chain_in_memories(self):
        """带 chain_id 的 facts 会保留链信息，同时人物链也会建立。"""
        facts = self._fake_facts(10)
        mems = kb.build_memories(facts)
        chains = [m for m in mems if m.get("reasoning_chain")]
        assert len(chains) >= 5, f"链记忆太少，实际 {len(chains)}"
        # 至少要有 LLM chain 和 person chain 两类
        chain_ids = set(m.get("reasoning_chain") for m in chains)
        assert len(chain_ids) >= 2, f"应有至少2种链，实际 {chain_ids}"
        for m in chains:
            assert "chain_position" in m
            assert "chain_relation" in m


# ============================================================================
# 3. quality_check.py 测试
# ============================================================================

class TestQualityCheck:
    """测试质量校验脚本。"""

    def test_run_on_valid_db(self):
        """对有效数据库返回通过。"""
        db = generator.build_database(50)
        result = qc.check(db)
        assert result["errors"] == 0, f"Errors: {result['errors']}"
        assert result["passed"] is True

    def test_detect_duplicate_ids(self):
        """能检测重复ID。"""
        db = generator.build_database(50)
        db["memories"][0]["memory_id"] = db["memories"][1]["memory_id"]
        result = qc.check(db)
        assert result["errors"] > 0, "应检测到重复ID"
        assert result["passed"] is False

    def test_detect_negative_with_answers(self):
        """能检测负样本有 expected_memory_ids。"""
        db = generator.build_database(50)
        for q in db["queries"]:
            if q.get("is_negative"):
                q["expected_memory_ids"] = ["MEM000001"]
                break
        result = qc.check(db)
        assert result["errors"] > 0, "应检测到负样本有 expected_memory_ids"


# ============================================================================
# 4. 集成 / 回归测试
# ============================================================================

class TestIntegration:
    """端到端集成测试。"""

    def test_generator_output_passes_quality_check(self):
        """generator 输出能通过 quality_check。"""
        db = generator.build_database(100)
        result = qc.check(db)
        assert result["passed"] is True, f"Quality check failed: {result}"

    def test_save_and_load_json(self):
        """能保存和加载 JSON。"""
        db = generator.build_database(50)
        tmp = "/tmp/test_memtest_db.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        with open(tmp, "r", encoding="utf-8") as f:
            db2 = json.load(f)
        assert len(db2["memories"]) == len(db["memories"])
        assert len(db2["queries"]) == len(db["queries"])
        os.remove(tmp)

    def test_full_size_generation(self):
        """全量规模生成不崩溃。"""
        # 注意: 10K 条在 CI 上可能慢，用 1K 测试
        try:
            db = generator.build_database(1000)
            assert len(db["memories"]) > 500
            assert len(db["queries"]) > 200
        except Exception as e:
            pytest.fail(f"Full size generation failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
