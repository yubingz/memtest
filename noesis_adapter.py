#!/usr/bin/env python3
"""
NOESIS-II 适配器 — 将 NOESIS-II 记忆系统接入 MemTest 评测框架

用法:
    from noesis_adapter import NoesisAdapter
    from runner import MemoryTestSuite, load_test_db, summary

    adapter = NoesisAdapter(db_path="path/to/noesis.db")
    db = load_test_db("test_db_10000.json")
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(summary(report))
"""

import sys
import re
from pathlib import Path

# 添加 NOESIS-II 路径
NOESIS_ROOT = Path.home() / "NOESIS-II"
sys.path.insert(0, str(NOESIS_ROOT))

from noesis_ii.core.schema import init_db, get_connection
from noesis_ii.core.long_term_memory import LongTermMemory
from noesis_ii.core.working_memory import WorkingMemory

# MemTest 适配器基类
sys.path.insert(0, str(Path(__file__).parent))
from runner import MemoryAdapter


class NoesisAdapter(MemoryAdapter):
    """NOESIS-II 的 MemTest 适配器"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(NOESIS_ROOT / "noesis_ii" / "data" / "noesis.db")
        self.db_path = db_path
        self.ltm = LongTermMemory(self.db_path)
        self._id_map = {}  # memory_id -> ltm_node_id

    def reset(self):
        """清空 NOESIS-II LTM 中的所有记忆节点"""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ltm_nodes")
            cursor.execute("DELETE FROM ltm_links")
            cursor.execute("DELETE FROM working_memory")
            conn.commit()
        finally:
            conn.close()
        self._id_map.clear()

    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆到 NOESIS-II LTM"""
        memory_id = metadata.get("memory_id", "")
        category = metadata.get("category", "")
        person = metadata.get("person_name", "")
        location = metadata.get("location_city", "")
        event_type = metadata.get("event_type", "")
        time_abs = metadata.get("time_absolute", "")

        # 构建锚点（用于检索增强）
        anchors = [memory_id, category]
        if person:
            anchors.append(person)
        if location:
            anchors.append(location)
        if event_type:
            anchors.append(event_type)
        if time_abs:
            anchors.append(time_abs)

        # 把 metadata 编码进 content 以提高 TF-IDF 检索命中率
        enriched = memory_text
        meta_parts = []
        if person:
            meta_parts.append(f"人物:{person}")
        if location:
            meta_parts.append(f"地点:{location}")
        if time_abs:
            meta_parts.append(f"时间:{time_abs}")
        if event_type:
            meta_parts.append(f"事件:{event_type}")
        if meta_parts:
            enriched = memory_text + " [" + " ".join(meta_parts) + "]"

        node_id = self.ltm.store_node(
            content=enriched,
            summary=memory_id,
            emotional_weight=float(metadata.get("weight", 0.5)),
            raw_anchors=anchors
        )
        self._id_map[memory_id] = node_id

    def search(self, query: str, top_k: int = 20) -> list:
        """从 NOESIS-II LTM 检索记忆"""
        results = self.ltm.retrieve_similar(query, top_k=top_k * 2)

        output = []
        for r in results:
            # 从 summary 字段提取 memory_id
            memory_id = r.get("summary", "")
            # 从 content 中去除元数据后缀
            content = r.get("content", "")
            content = re.sub(r'\s*\[人物:.+\]$', '', content)

            output.append({
                "memory_id": memory_id,
                "score": r.get("score", 0.0),
                "content": content
            })

        return output[:top_k]


if __name__ == "__main__":
    # 快速验证
    adapter = NoesisAdapter()
    print("NOESIS-II Adapter loaded successfully")
    print(f"DB path: {adapter.db_path}")
