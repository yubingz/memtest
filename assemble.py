#!/usr/bin/env python3
"""MemTest v4 组装器

把 extractor → relation_builder → query_builder 的输出
组装成标准 v2 格式的 test_db.json

输出的数据库可直接用 runner.py 跑评测。
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List


def assemble(memories: List[Dict[str, Any]], queries: List[Dict[str, Any]],
             name: str = "MemTest Database", source: str = "") -> Dict[str, Any]:
    """组装成标准v2格式数据库"""

    # 统计
    categories = {}
    for m in memories:
        cat = m.get("category", "检索功能测试集")
        categories[cat] = categories.get(cat, 0) + 1

    db = {
        "database_info": {
            "name": name,
            "version": "1.0.0",  # v2格式用1.0.0
            "total_count": len(memories),
            "categories": categories,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "memories": memories,
        "queries": queries,
    }

    return db


if __name__ == "__main__":
    memories_file = sys.argv[1]
    queries_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else "test_db.json"

    with open(memories_file, 'r', encoding='utf-8') as f:
        memories = json.load(f)

    with open(queries_file, 'r', encoding='utf-8') as f:
        queries = json.load(f)

    db = assemble(memories, queries)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"数据库组装完成: {len(memories)} 条记忆, {len(queries)} 条查询")
    print(f"输出: {output_file}")
