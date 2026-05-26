#!/usr/bin/env python3
"""生成样例数据 + 自测"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from generator import build_database

db = build_database(100)
with open("sample_db_100.json", "w", encoding="utf-8") as f:
    json.dump(db, f, ensure_ascii=False, indent=2)

qs = {"queries_info": {"total_count": len(db["queries"]), "query_types": ["时间检索","地点检索","人物检索","事件检索","组合检索"]},
      "queries": db["queries"]}
with open("sample_queries.json", "w", encoding="utf-8") as f:
    json.dump(qs, f, ensure_ascii=False, indent=2)
print(f"Generated: {len(db['memories'])} memories + {len(db['queries'])} queries")

# 自测
from runner import JsonMemoryAdapter, MemoryTestSuite, summary
adapter = JsonMemoryAdapter()
suite = MemoryTestSuite(adapter)
report = suite.run(db)
print(summary(report))
