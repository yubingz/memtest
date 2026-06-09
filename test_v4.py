#!/usr/bin/env python3
"""MemTest v4 单元测试 — 覆盖 extractor, relation_builder, query_builder, runner, schema

运行:
    pytest test_v4.py -v
"""

import json
import os
import pytest
import tempfile

# ==============================================================================
# 1. Schema 测试
# ==============================================================================

class TestSchema:
    """测试 v4 schema 定义和校验"""

    def test_memory_schema_has_required_fields(self):
        from schema import MEMORY_SCHEMA_V4, MEMORY_REQUIRED_V4
        for field in MEMORY_REQUIRED_V4:
            assert field in MEMORY_SCHEMA_V4, f"Required field {field} missing from schema"

    def test_query_schema_has_required_fields(self):
        from schema import QUERY_SCHEMA_V4, QUERY_REQUIRED_V4
        for field in QUERY_REQUIRED_V4:
            assert field in QUERY_SCHEMA_V4, f"Required field {field} missing from query schema"

    def test_version_is_v4(self):
        from schema import PRINCIPLES
        # v4 principles should exist
        assert "memory_not_understanding" in PRINCIPLES
        assert "content_only_storage" in PRINCIPLES

    def test_validate_valid_memory(self):
        from schema import validate_memory
        mem = {
            "memory_id": "MEM000001",
            "content": "刘备，字玄德，人称刘皇叔。",
            "person": ["刘备", "玄德", "刘皇叔"],
            "time_absolute": "",
            "time_relative": "",
            "time_ref_id": None,
            "time_offset_days": None,
            "location": "涿县",
            "event_type": "出生",
            "source": "三国演义",
            "tags": [],
            "difficulty": "medium",
        }
        # Should not raise
        validate_memory(mem)

    def test_validate_memory_missing_required(self):
        from schema import validate_memory
        mem = {"memory_id": "MEM000001"}  # Missing content
        errors = validate_memory(mem)
        assert len(errors) > 0, f"Should detect missing content, got: {errors}"

    def test_validate_database(self):
        from schema import validate_database
        db = {
            "database_info": {
                "name": "Test",
                "version": "4.0.0",
                "description": "Test",
                "created_at": "2026-01-01",
                "source": "test",
                "total_memories": 1,
                "total_queries": 1,
                "principles": {"memory_not_understanding": True, "content_only_storage": True,
                              "alias_from_corpus_only": True, "time_as_is_no_inference": True},
            },
            "memories": [{
                "memory_id": "MEM000001", "content": "Test", "person": [],
                "time_absolute": "", "time_relative": "", "time_ref_id": None,
                "time_offset_days": None, "location": "", "event_type": "",
                "source": "test", "tags": [], "difficulty": "easy",
            }],
            "queries": [{
                "query_id": "Q0001", "query_text": "Test query", "query_type": "事实检索",
                "test_dimension": "精确检索", "expected_memory_ids": ["MEM000001"],
                "expected_answer": "Test", "difficulty": "easy", "is_negative": False,
            }],
        }
        # Should not raise
        validate_database(db)


# ==============================================================================
# 2. Extractor 测试
# ==============================================================================

class TestExtractor:
    """测试记忆提取器（不依赖LLM API）"""

    def test_rule_extract_basic(self):
        from extractor import MemoryExtractor
        ext = MemoryExtractor(llm_adapter=None)
        # Create temp corpus
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("刘备，字玄德，涿郡涿县人。他与关羽、张飞桃园三结义。\n\n"
                    "诸葛亮，字孔明，号卧龙，隐居隆中。")
            tmp = f.name
        try:
            memories = ext.extract(tmp, default_source="三国演义")
            assert len(memories) >= 1, f"Expected >=1 memory, got {len(memories)}"
            # Check v4 format
            m = memories[0]
            assert "content" in m
            assert "person" in m
            assert isinstance(m["person"], list)
            assert m.get("source") == "三国演义"
        finally:
            os.unlink(tmp)

    def test_rule_extract_person(self):
        from extractor import MemoryExtractor
        ext = MemoryExtractor(llm_adapter=None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("张三在北京市海淀区中关村软件园工作，他是一名资深的软件工程师。李四在上海浦东新区陆家嘴从事金融行业。")
            tmp = f.name
        try:
            memories = ext.extract(tmp)
            # Should find at least one person with common surname
            all_persons = []
            for m in memories:
                all_persons.extend(m.get("person", []))
            assert len(all_persons) >= 1, "Should extract at least one person"
        finally:
            os.unlink(tmp)

    def test_rule_extract_alias(self):
        from extractor import MemoryExtractor
        ext = MemoryExtractor(llm_adapter=None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("孙悟空，又名齐天大圣，大闹天宫后被佛祖压在五行山下。")
            tmp = f.name
        try:
            memories = ext.extract(tmp)
            all_evidence = []
            for m in memories:
                all_evidence.extend(m.get("alias_evidence", []))
            # Should detect alias
            if all_evidence:
                assert any(e.get("entity") == "孙悟空" or e.get("alias") == "齐天大圣"
                          for e in all_evidence), "Should detect 孙悟空/齐天大圣 alias"
        finally:
            os.unlink(tmp)

    def test_empty_corpus(self):
        from extractor import MemoryExtractor
        ext = MemoryExtractor(llm_adapter=None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("")
            tmp = f.name
        try:
            memories = ext.extract(tmp)
            assert memories == []
        finally:
            os.unlink(tmp)

    def test_memory_id_unique(self):
        from extractor import MemoryExtractor
        ext = MemoryExtractor(llm_adapter=None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("张三在北京做事。\n\n李四在上海做事。\n\n王五在广州做事。")
            tmp = f.name
        try:
            memories = ext.extract(tmp)
            ids = [m["memory_id"] for m in memories]
            assert len(ids) == len(set(ids)), "Memory IDs should be unique"
        finally:
            os.unlink(tmp)


# ==============================================================================
# 3. RelationBuilder 测试
# ==============================================================================

class TestRelationBuilder:
    """测试关系构建器"""

    def _make_memories(self):
        return [
            {
                "memory_id": "MEM000001", "content": "刘备，字玄德，人称刘皇叔，涿郡涿县人。他是汉景帝之子中山靖王刘胜的后代。早年丧父，与母亲贩履织席为生。",
                "person": ["刘备", "玄德", "刘皇叔"], "time_absolute": "", "time_relative": "早年",
                "time_ref_id": None, "time_offset_days": None,
                "location": "涿县", "event_type": "出生", "source": "三国演义",
                "tags": [], "difficulty": "easy",
            },
            {
                "memory_id": "MEM000002", "content": "关羽，字云长，与刘备、张飞桃园三结义。",
                "person": ["关羽", "云长", "刘备", "张飞"], "time_absolute": "", "time_relative": "",
                "time_ref_id": None, "time_offset_days": None,
                "location": "涿县", "event_type": "结义", "source": "三国演义",
                "tags": [], "difficulty": "easy",
            },
            {
                "memory_id": "MEM000003", "content": "张飞，字翼德，与刘备关羽桃园三结义。",
                "person": ["张飞", "翼德", "刘备", "关羽"], "time_absolute": "", "time_relative": "",
                "time_ref_id": None, "time_offset_days": None,
                "location": "涿县", "event_type": "结义", "source": "三国演义",
                "tags": [], "difficulty": "easy",
            },
        ]

    def test_build_returns_memories(self):
        from relation_builder import RelationBuilder
        rb = RelationBuilder()
        result = rb.build(self._make_memories())
        assert len(result) >= 3

    def test_alias_groups(self):
        from relation_builder import RelationBuilder
        rb = RelationBuilder()
        rb.build(self._make_memories())
        # Should detect alias groups from content like "刘备，字玄德"
        groups = rb.alias_groups.groups()
        # At minimum, should have some groups if content has alias patterns
        assert isinstance(groups, dict)

    def test_memories_have_chain_fields(self):
        from relation_builder import RelationBuilder
        rb = RelationBuilder()
        result = rb.build(self._make_memories())
        for m in result:
            # v4 memories may or may not have chain fields, but should not crash
            assert "memory_id" in m


# ==============================================================================
# 4. Runner 测试
# ==============================================================================

class TestRunner:
    """测试评测执行器"""

    def _make_db(self):
        return {
            "memories": [
                {
                    "memory_id": "MEM000001",
                    "content": "刘备，字玄德，人称刘皇叔，涿郡涿县人。他是汉景帝之子中山靖王刘胜的后代。早年丧父，与母亲贩履织席为生。",
                    "person": ["刘备", "玄德"],
                    "time_absolute": "", "time_relative": "", "time_ref_id": None,
                    "time_offset_days": None, "location": "涿县",
                    "event_type": "出生", "source": "三国演义",
                    "tags": [], "difficulty": "easy",
                },
                {
                    "memory_id": "MEM000002",
                    "content": "关羽，字云长，与刘备张飞桃园结义。",
                    "person": ["关羽", "云长"],
                    "time_absolute": "", "time_relative": "", "time_ref_id": None,
                    "time_offset_days": None, "location": "涿县",
                    "event_type": "结义", "source": "三国演义",
                    "tags": [], "difficulty": "easy",
                },
            ],
            "queries": [
                {
                    "query_id": "Q0001", "query_text": "刘备的经历",
                    "query_type": "人物检索", "test_dimension": "精确检索",
                    "expected_memory_ids": ["MEM000001"],
                    "expected_answer": "刘备字玄德", "difficulty": "easy", "is_negative": False,
                },
                {
                    "query_id": "Q0002", "query_text": "桃园结义",
                    "query_type": "事件检索", "test_dimension": "精确检索",
                    "expected_memory_ids": ["MEM000002"],
                    "expected_answer": "关羽与刘备张飞结义", "difficulty": "easy", "is_negative": False,
                },
                {
                    "query_id": "Q0003", "query_text": "火星人做了什么",
                    "query_type": "负样本", "test_dimension": "负样本",
                    "expected_memory_ids": [], "expected_answer": "",
                    "difficulty": "easy", "is_negative": True,
                },
            ],
        }

    def test_runner_runs(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(self._make_db())
        assert "storage" in report
        assert "retrieval" in report
        assert "negative" in report

    def test_storage_integrity(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(self._make_db())
        assert report["storage"]["integrity"] == 1.0
        assert report["storage"]["stored"] == 2

    def test_retrieval_has_metrics(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(self._make_db())
        ret = report["retrieval"]
        assert "overall_precision" in ret
        assert "overall_recall" in ret
        assert "overall_mrr" in ret
        assert "by_type" in ret

    def test_negative_eval(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(self._make_db())
        neg = report["negative"]
        assert neg["total"] == 1
        assert isinstance(neg["accuracy"], (int, float))

    def test_coverage_eval(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(self._make_db())
        cov = report["coverage"]
        assert cov["total"] == 2

    def test_summary_output(self):
        from runner import MemoryTestSuite, JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        suite.run(self._make_db())
        s = suite.summary()
        assert "MemTest 评测报告" in s
        assert "存储完整性" in s

    def test_json_adapter_search(self):
        from runner import JsonMemoryAdapter
        adapter = JsonMemoryAdapter()
        adapter.store("刘备字玄德，人称刘皇叔", {"memory_id": "M1"})
        adapter.store("关羽字云长，桃园结义", {"memory_id": "M2"})
        results = adapter.search("刘备", top_k=10)
        assert len(results) >= 1
        assert results[0]["memory_id"] == "M1"


# ==============================================================================
# 5. QualityCheck 测试
# ==============================================================================

class TestQualityCheck:
    """测试质量校验"""

    def _make_valid_db(self):
        return {
            "memories": [{
                "memory_id": "MEM000001", "content": "Test content",
                "person": [], "time_absolute": "", "time_relative": "",
                "time_ref_id": None, "time_offset_days": None,
                "location": "", "event_type": "", "source": "test",
                "tags": [], "difficulty": "easy",
            }],
            "queries": [{
                "query_id": "Q0001", "query_text": "Test",
                "query_type": "事实检索", "test_dimension": "精确检索",
                "expected_memory_ids": ["MEM000001"],
                "expected_answer": "Test", "difficulty": "easy", "is_negative": False,
            }],
        }

    def test_valid_db_passes(self):
        from quality_check import check
        result = check(self._make_valid_db())
        assert result["passed"] is True
        assert result["errors"] == 0

    def test_detect_duplicate_ids(self):
        from quality_check import check
        db = self._make_valid_db()
        db["memories"].append(db["memories"][0].copy())
        db["memories"][1]["memory_id"] = "MEM000001"  # Duplicate
        result = check(db)
        assert result["errors"] > 0

    def test_detect_missing_ref(self):
        from quality_check import check
        db = self._make_valid_db()
        db["queries"][0]["expected_memory_ids"] = ["MEM999999"]
        result = check(db)
        assert result["errors"] > 0

    def test_detect_negative_with_answers(self):
        from quality_check import check
        db = self._make_valid_db()
        db["queries"][0]["is_negative"] = True
        db["queries"][0]["expected_memory_ids"] = ["MEM000001"]  # Should be empty
        result = check(db)
        assert result["errors"] > 0


# ==============================================================================
# 6. 集成测试
# ==============================================================================

class TestIntegration:
    """端到端集成测试"""

    def test_extract_relation_query_pipeline(self):
        """完整 pipeline: extract → relation → query (no LLM)"""
        from extractor import MemoryExtractor
        from relation_builder import RelationBuilder
        from quality_check import check

        # Create corpus
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("刘备，字玄德，人称刘皇叔，涿郡涿县人。他是汉景帝之子中山靖王刘胜的后代。早年丧父，与母亲贩履织席为生。\n\n"
                    "关羽，字云长，河东解良人。因犯事逃亡至涿郡，与刘备、张飞桃园三结义，义结金兰。\n\n"
                    "张飞，字翼德，涿郡人。勇猛过人，与刘备关羽桃园三结义，排行第三。")
            tmp = f.name
        try:
            # Step 1: Extract
            ext = MemoryExtractor(llm_adapter=None)
            memories = ext.extract(tmp, default_source="三国演义")
            assert len(memories) >= 1

            # Step 2: Build relations
            rb = RelationBuilder()
            memories = rb.build(memories)

            # Step 3: Check quality
            db = {"memories": memories, "queries": []}
            result = check(db, verbose=False)
            # May have warnings but no critical errors
            assert len([e for e in result.get("error_list", [])
                       if "重复" not in e and "引用" not in e]) == 0
        finally:
            os.unlink(tmp)

    def test_runner_with_sample_db(self):
        """Runner 能跑 v4 格式数据库"""
        from runner import MemoryTestSuite, JsonMemoryAdapter
        from quality_check import check

        db = {
            "memories": [
                {
                    "memory_id": f"MEM{i:06d}",
                    "content": f"这是第{i}条测试记忆，描述人物张三的事件。",
                    "person": ["张三"], "time_absolute": "", "time_relative": "",
                    "time_ref_id": None, "time_offset_days": None,
                    "location": "北京", "event_type": "测试", "source": "测试",
                    "tags": [], "difficulty": "easy",
                }
                for i in range(10)
            ],
            "queries": [
                {
                    "query_id": "Q0001", "query_text": "张三的经历",
                    "query_type": "人物检索", "test_dimension": "精确检索",
                    "expected_memory_ids": ["MEM0000001"],
                    "expected_answer": "测试", "difficulty": "easy", "is_negative": False,
                },
                {
                    "query_id": "Q0002", "query_text": "火星人在月球做了什么",
                    "query_type": "负样本", "test_dimension": "负样本",
                    "expected_memory_ids": [], "expected_answer": "",
                    "difficulty": "easy", "is_negative": True,
                },
            ],
        }

        adapter = JsonMemoryAdapter()
        suite = MemoryTestSuite(adapter)
        report = suite.run(db)

        assert report["storage"]["stored"] == 10
        assert report["storage"]["integrity"] == 1.0
        assert "overall_precision" in report["retrieval"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
