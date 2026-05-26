#!/usr/bin/env python3
"""
NOESIS-II 适配器 — 将 NOESIS-II 记忆系统接入 MemTest 评测框架

完整流程:
  1. 导入 → Working Memory（冲突消解）
  2. 巩固 → LTM + 建联想链接
  3. 检索 → 多维 RRF 融合（语义/时间/频率/关联）
  4. 评估 → LLM 语义比对（可选）

用法:
    from noesis_adapter import NoesisAdapter
    from runner import MemoryTestSuite, load_test_db, summary

    adapter = NoesisAdapter()
    db = load_test_db("test_db_10000.json")
    suite = MemoryTestSuite(adapter)
    report = suite.run(db)
    print(summary(report))
"""

import sys
import re
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional

# 添加 NOESIS-II 路径
NOESIS_ROOT = Path.home() / "NOESIS-II"
sys.path.insert(0, str(NOESIS_ROOT))

from noesis_ii.core.schema import init_db, get_connection
from noesis_ii.core.long_term_memory import LongTermMemory
from noesis_ii.core.working_memory import WorkingMemory
from noesis_ii.core.multi_criteria_retriever import MultiCriteriaRetriever

# MemTest 适配器基类
sys.path.insert(0, str(Path(__file__).parent))
from runner import MemoryAdapter


class NoesisAdapter(MemoryAdapter):
    """NOESIS-II 的 MemTest 适配器（完整流程版）"""

    def __init__(self, db_path: str = None, use_multi_criteria: bool = True):
        if db_path is None:
            db_path = str(NOESIS_ROOT / "noesis_ii" / "data" / "noesis.db")
        self.db_path = db_path
        self.ltm = LongTermMemory(self.db_path)
        self.wm = WorkingMemory(self.db_path)
        self._id_map = {}  # memory_id -> ltm_node_id
        self._meta_store = {}  # memory_id -> metadata
        self.use_multi_criteria = use_multi_criteria
        if use_multi_criteria:
            self.retriever = MultiCriteriaRetriever(self.db_path)

    def reset(self):
        """清空 NOESIS-II 所有记忆数据"""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ltm_nodes")
            cursor.execute("DELETE FROM ltm_links")
            cursor.execute("DELETE FROM working_memory")
            cursor.execute("DELETE FROM memory_traces")
            conn.commit()
        finally:
            conn.close()
        self._id_map.clear()
        self._meta_store.clear()

    def store(self, memory_text: str, metadata: dict):
        """存入一条记忆（WM → LTM 完整流程）"""
        memory_id = metadata.get("memory_id", "")
        category = metadata.get("category", "")
        person = metadata.get("person_name", "")
        location = metadata.get("location_city", "")
        event_type = metadata.get("event_type", "")
        time_abs = metadata.get("time_absolute", "")
        cluster_id = metadata.get("cluster_id")
        decay_level = metadata.get("decay_level")
        access_count = metadata.get("access_count", 0)
        weight = float(metadata.get("weight", 0.5))

        # Step 1: 进 Working Memory（冲突消解）
        full_content = memory_text
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
            full_content = memory_text + " [" + " ".join(meta_parts) + "]"

        wm_meta = {
            "memory_id": memory_id,
            "category": category,
            "person": person,
            "location": location,
            "event_type": event_type,
        }

        entry_id, op = self.wm.capture(
            content=full_content,
            metadata=wm_meta,
            conflict_check=True
        )

        # Step 2: 巩固到 LTM
        anchors = [memory_id, category]
        if person:
            anchors.append(person)
        if location:
            anchors.append(location)
        if event_type:
            anchors.append(event_type)
        if time_abs:
            anchors.append(time_abs)
        if cluster_id:
            anchors.append(cluster_id)

        ltm_id = self.ltm.store_node(
            content=full_content,
            summary=memory_id,
            emotional_weight=weight,
            raw_anchors=anchors
        )

        # 模拟访问次数（用于遗忘评估）
        if decay_level and access_count > 0:
            for _ in range(min(access_count, 10)):
                self.ltm.update_access(ltm_id)

        self._id_map[memory_id] = ltm_id
        self._meta_store[memory_id] = metadata

    def build_links(self):
        """Step 3: 建联想链接 — 按人物/事件/地点关联"""
        built = 0
        person_nodes = defaultdict(list)
        event_nodes = defaultdict(list)
        location_nodes = defaultdict(list)
        cluster_nodes = defaultdict(list)

        for mid, meta in self._meta_store.items():
            ltm_id = self._id_map.get(mid)
            if not ltm_id:
                continue
            person = meta.get("person_name", "")
            event = meta.get("event_type", "")
            loc = meta.get("location_city", "")
            cluster = meta.get("cluster_id")

            if person:
                person_nodes[person].append(ltm_id)
            if event:
                event_nodes[event].append(ltm_id)
            if loc:
                location_nodes[loc].append(ltm_id)
            if cluster:
                cluster_nodes[cluster].append(ltm_id)

        # 同人物的节点互连
        for group in [person_nodes, event_nodes, location_nodes, cluster_nodes]:
            for key, node_ids in group.items():
                if len(node_ids) < 2:
                    continue
                for i in range(len(node_ids)):
                    for j in range(i + 1, min(i + 5, len(node_ids))):  # 限连5个避免全连接
                        try:
                            self.ltm.create_link(
                                node_ids[i], node_ids[j],
                                strength=0.3,
                                link_type="co-occurrence"
                            )
                            built += 1
                        except Exception:
                            pass

        return built

    def search(self, query: str, top_k: int = 20) -> list:
        """Step 4: 多维 RRF 检索"""
        if self.use_multi_criteria:
            raw_results = self.retriever.retrieve(query, top_k=top_k * 2)
        else:
            raw_results = self.ltm.retrieve_similar(query, top_k=top_k * 2)

        output = []
        for r in raw_results:
            node_id = r.get("id")
            # 反查 memory_id
            memory_id = ""
            for mid, lid in self._id_map.items():
                if lid == node_id:
                    memory_id = mid
                    break
            if not memory_id and r.get("summary"):
                memory_id = r["summary"]

            content = r.get("content", "")
            content = re.sub(r'\s*\[人物:.+\]$', '', content)

            output.append({
                "memory_id": memory_id,
                "score": r.get("score", r.get("rrf_score", 0.0)),
                "content": content
            })

        return output[:top_k]


if __name__ == "__main__":
    adapter = NoesisAdapter()
    print("NOESIS-II Adapter (full pipeline) loaded")
    print(f"DB: {adapter.db_path}")
    print(f"Multi-criteria retrieval: {adapter.use_multi_criteria}")
