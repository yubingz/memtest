#!/usr/bin/env python3
"""
MemTest LLM 评估器 — 用大模型判断检索结果的语义相关性

替代简单的 memory_id 精确匹配，用 LLM 判断：
  查询 Q 和检索到的内容 C 是否语义相关？

用法:
    from llm_evaluator import LLMEvaluator

    evaluator = LLMEvaluator()
    score = evaluator.judge("张伟最近做了什么", "张伟在北京星巴克购买了茅台，数量500")
    # => {"relevant": True, "reason": "...", "score": 0.9}
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

# MemTest 路径
sys.path.insert(0, str(Path(__file__).parent))
from runner import MemoryAdapter, MemoryTestSuite


class LLMEvaluator:
    """LLM 语义评估器"""

    def __init__(self, adapter: MemoryAdapter = None, batch_size: int = 15):
        self.adapter = adapter
        self.batch_size = batch_size
        self._cache = {}

    def judge_single(self, query: str, content: str) -> Dict:
        """单条语义判定（由调用方提供 LLM 能力时使用）"""
        prompt = f"""判断查询和检索内容是否语义相关。

查询: {query}
内容: {content}

严格输出JSON:
{{"relevant": true/false, "score": 0.0-1.0, "reason": "简短说明"}}"""
        return prompt  # 返回 prompt，由外部 LM 执行

    def judge_batch(self, query: str, results: List[Dict]) -> str:
        """批量生成判定 prompt"""
        items = []
        for i, r in enumerate(results):
            items.append(f"{i}. [{r.get('memory_id', '?')}] {r.get('content', '')[:200]}")

        prompt = f"""查询: {query}

检索结果:
{chr(10).join(items)}

逐条判断语义相关性。严格输出JSON数组:
[{{"idx": 0, "relevant": true/false, "score": 0.0-1.0}}, ...]"""
        return prompt

    def evaluate_retrieval_with_llm(
        self,
        test_db: dict,
        adapter: MemoryAdapter = None,
        top_k: int = 10,
        sample_size: int = 50
    ) -> Dict:
        """
        完整的 LLM 评估流程：
        1. 跑检索
        2. 生成 LLM 判断 prompt
        3. 批量调用 LLM（由外部执行）
        4. 汇总结果

        Returns:
            Dict with prompts (待执行) 和 metadata
        """
        adapter = adapter or self.adapter
        if not adapter:
            raise ValueError("需要提供 adapter")

        queries = test_db.get("queries", [])
        if not queries:
            return {"error": "no queries"}

        # 采样
        import random
        random.seed(42)
        sampled = random.sample(queries, min(sample_size, len(queries)))

        prompts = []
        for q in sampled:
            results = adapter.search(q["query_text"], top_k=top_k)
            prompt = self.judge_batch(q["query_text"], results)
            prompts.append({
                "query_id": q.get("query_id", ""),
                "query_text": q["query_text"],
                "query_type": q.get("query_type", ""),
                "expected_ids": q.get("expected_memory_ids", []),
                "prompt": prompt,
                "result_ids": [r.get("memory_id", "") for r in results],
                "result_contents": [r.get("content", "")[:200] for r in results]
            })

        return {
            "total_queries": len(queries),
            "sampled": len(sampled),
            "prompts": prompts,
            "next_step": "批量调用 LLM 执行 prompts 中的判断，汇总 relevant/score"
        }


class LLMAssistedTestSuite(MemoryTestSuite):
    """带 LLM 评估的测试套件"""

    def __init__(self, adapter: MemoryAdapter, llm_evaluator: LLMEvaluator = None):
        super().__init__(adapter)
        self.llm_eval = llm_evaluator or LLMEvaluator(adapter)

    def run_with_llm(self, test_db: dict, sample_size: int = 50) -> dict:
        """先跑标准评测，再跑 LLM 语义评测"""
        # 标准评测
        standard_report = self.run(test_db)

        # LLM 评测
        llm_result = self.llm_eval.evaluate_retrieval_with_llm(
            test_db, self.adapter, sample_size=sample_size
        )

        standard_report["llm_evaluation"] = llm_result
        return standard_report


if __name__ == "__main__":
    print("LLM Evaluator for MemTest")
    print("Usage: integrate with NoesisAdapter + LLM call")
