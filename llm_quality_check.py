#!/usr/bin/env python3
"""用 LLM 检查每条查询和答案的质量"""

import json, sys
from llm_interface import create_llm

def load_db(path="sample_db.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_with_llm(llm, query: dict, memories: dict) -> dict:
    """用 LLM 检查单个查询-答案对。"""
    q = query
    mems = [memories[mid] for mid in q["expected_memory_ids"] if mid in memories]
    
    # 构建记忆文本摘要
    mem_texts = []
    for m in mems:
        mem_texts.append(
            f"- {m['memory_id']}: {m['person']['name']}在{m['location']['city']}{m['event']['action']}了{m['event']['product']}"
        )
    mem_summary = "\n".join(mem_texts) if mem_texts else "（无对应记忆）"
    
    prompt = f"""请检查以下查询-答案对是否合理：

## 查询
ID: {q['query_id']}
类型: {q['query_type']}
文本: {q['query_text']}

## 答案（预期）
{q.get('expected_answer_text', '')}

## 相关记忆
{mem_summary}

## 请检查以下问题并给出评分（1-10）：
1. **查询自然度**: 查询文本是否自然、语法正确？是否有"之后了"这种错误？
2. **答案匹配度**: 答案是否与查询匹配？回答的是查询问的内容吗？
3. **链式完整性**（如果是链式查询）: 查询是否要求系统遍历整条链？答案是否包含整条链？
4. **负样本正确性**（如果是负样本）: 查询是否确实找不到对应记忆？

请用以下格式输出：
```
评分：
- 自然度: X/10
- 匹配度: X/10
- 链式完整性: X/10（非链式填N/A）
- 负样本正确性: X/10（非负样本填N/A）

问题：
- 如果有问题，请列出
- 如果无问题，写"无"

总结：通过/不通过
```
"""
    
    try:
        result = llm.generate(prompt, max_tokens=1000, temperature=0.1)
        return {
            "query_id": q["query_id"],
            "result": result,
            "ok": True
        }
    except Exception as e:
        return {
            "query_id": q["query_id"],
            "result": f"LLM调用失败: {e}",
            "ok": False
        }


def main():
    db = load_db()
    memories = {m["memory_id"]: m for m in db["memories"]}
    queries = db["queries"]
    
    print("初始化 LLM...")
    try:
        llm = create_llm("deepseek")
        print("LLM 就绪")
    except Exception as e:
        print(f"LLM 初始化失败: {e}")
        sys.exit(1)
    
    # 检查所有查询（或采样）
    # 为了效率，先检查所有链式查询和负样本，再随机抽查其他
    chain_types = ["时序推理链", "因果推理链", "对比推理链", "包含推理链", "推导推理链"]
    priority_queries = []
    other_queries = []
    
    for q in queries:
        if q.get("is_negative") or q.get("query_type") in chain_types:
            priority_queries.append(q)
        else:
            other_queries.append(q)
    
    # 检查优先查询（全部）
    print(f"\n检查 {len(priority_queries)} 个优先查询（链式+负样本）...")
    results = []
    for q in priority_queries:
        r = check_with_llm(llm, q, memories)
        results.append(r)
        print(f"\n{'='*60}")
        print(f"Q: {q['query_text']}")
        print(f"A: {q.get('expected_answer_text', '')[:80]}")
        print(f"\nLLM 评估:\n{r['result']}")
    
    # 抽查其他查询（10个）
    import random
    random.seed(42)
    sample = random.sample(other_queries, min(10, len(other_queries)))
    print(f"\n\n检查 {len(sample)} 个抽查查询...")
    for q in sample:
        r = check_with_llm(llm, q, memories)
        results.append(r)
        print(f"\n{'='*60}")
        print(f"Q: {q['query_text']}")
        print(f"A: {q.get('expected_answer_text', '')[:80]}")
        print(f"\nLLM 评估:\n{r['result']}")
    
    # 汇总
    print(f"\n\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    ok_count = sum(1 for r in results if r["ok"])
    print(f"总计检查: {len(results)} 条查询")
    print(f"LLM 调用成功: {ok_count}")
    print(f"LLM 调用失败: {len(results) - ok_count}")


if __name__ == "__main__":
    main()
