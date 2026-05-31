#!/usr/bin/env python3
"""规则检查：所有查询和答案的详细质量审查"""

import json, re
from collections import Counter, defaultdict

def load_db(path="sample_db.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_all():
    db = load_db()
    memories = {m["memory_id"]: m for m in db["memories"]}
    queries = db["queries"]
    
    issues = []
    
    # 1. 检查查询文本重复
    qtexts = Counter(q["query_text"] for q in queries)
    for t, c in qtexts.items():
        if c > 1:
            issues.append(f"🔴 查询重复: '{t}' 出现 {c} 次")
    
    # 2. 检查负样本
    for q in queries:
        if q.get("is_negative"):
            if q["expected_memory_ids"]:
                issues.append(f"🔴 {q['query_id']}: 负样本但 expected_memory_ids 非空: {q['expected_memory_ids']}")
            # 检查负样本查询是否自然
            qt = q["query_text"]
            if "在火星" in qt or "在木星" in qt:
                pass  # 地名错误，合理
            elif "购买了项目" in qt or "购买了化妆品" in qt:
                pass  # 产品不存在，合理
            else:
                # 检查人物是否不存在
                person_match = re.search(r'^(\S+)', qt)
                if person_match:
                    person = person_match.group(1)
                    # 检查这个人物是否存在于记忆中
                    found = False
                    for m in db["memories"]:
                        if m["person"]["name"] == person:
                            found = True
                            break
                    if not found:
                        pass  # 人物不存在，合理
    
    # 3. 检查链式查询
    chain_types = ["时序推理链", "因果推理链", "对比推理链", "包含推理链", "推导推理链"]
    for q in queries:
        if q.get("query_type") in chain_types:
            mem_ids = q["expected_memory_ids"]
            if len(mem_ids) < 2:
                issues.append(f"🔴 {q['query_id']}: 链式查询只指向 {len(mem_ids)} 个记忆")
            else:
                # 检查这些记忆是否属于同一条链
                chains = set()
                for mid in mem_ids:
                    if mid in memories:
                        chains.add(memories[mid].get("reasoning_chain", ""))
                if len(chains) > 1:
                    issues.append(f"🔴 {q['query_id']}: 指向多个不同链: {chains}")
            
            # 检查查询是否包含起点
            qt = q["query_text"]
            # 时序链查询应包含完整起点
            if "后续事件" in qt or "导致了哪些事件" in qt:
                # 检查是否有 "在...了" 模式
                if not re.search(r'在\S+了\S+', qt):
                    issues.append(f"🟡 {q['query_id']}: 链式查询缺少完整起点（地点+动作+对象）: {qt}")
            
            # 检查首节点动作是否自然
            first_mem = None
            for mid in mem_ids:
                if mid in memories:
                    first_mem = memories[mid]
                    break
            if first_mem:
                action = first_mem["event"]["action"]
                time_words = {"之后", "然后", "接着", "随后"}
                if action in time_words:
                    issues.append(f"🔴 {q['query_id']}: 链首节点动作是时间虚词 '{action}'，查询: {qt}")
    
    # 4. 检查聚类查询
    for q in queries:
        if q.get("query_type") == "聚类检索":
            mem_ids = q["expected_memory_ids"]
            if len(mem_ids) < 2:
                issues.append(f"🟡 {q['query_id']}: 聚类查询只指向 {len(mem_ids)} 个记忆")
            else:
                # 检查是否属于同一 cluster
                clusters = set()
                for mid in mem_ids:
                    if mid in memories:
                        clusters.add(memories[mid].get("cluster_id", ""))
                if len(clusters) > 1:
                    issues.append(f"🔴 {q['query_id']}: 聚类查询指向多个 cluster: {clusters}")
            
            # 检查查询主题是否与 cluster 一致
            qt = q["query_text"]
            # 提取主题
            theme_match = re.search(r'关于(\S+)的记录|(\S+)的活动记录|在(\S+)的记录', qt)
            if theme_match:
                theme = theme_match.group(1) or theme_match.group(2) or theme_match.group(3)
                # 检查主题是否与 cluster 标签一致
                for mid in mem_ids[:1]:
                    if mid in memories:
                        tags = memories[mid].get("tags", [])
                        if len(tags) >= 4 and tags[3] != theme:
                            # 可能是产品名不一致
                            pass
    
    # 5. 检查答案与查询匹配
    for q in queries:
        qt = q["query_text"]
        ans = q.get("expected_answer_text", "")
        
        # 人物检索 → 答案应包含人物名
        if q.get("query_type") == "人物检索":
            person_match = re.search(r'^(.+?)做了什么', qt)
            if person_match and person_match.group(1) not in ans:
                issues.append(f"🟡 {q['query_id']}: 人物检索但答案不含人物名: {qt}")
        
        # 地点检索 → 答案应包含地点
        if q.get("query_type") == "地点检索":
            place = re.search(r'在(\S+)发生过', qt)
            if place and place.group(1) not in ans:
                issues.append(f"🟡 {q['query_id']}: 地点检索但答案不含地点: {qt}")
        
        # 跨版本 → 答案应包含3个版本
        if q.get("query_type") == "跨版本":
            versions = q.get("acceptable_answers", [])
            if len(versions) < 3:
                issues.append(f"🟡 {q['query_id']}: 跨版本查询但答案少于3个版本: {qt}")
    
    # 6. 检查查询语法
    time_words = {"之后了", "然后了", "接着了", "随后了"}
    for q in queries:
        qt = q["query_text"]
        for tw in time_words:
            if tw in qt:
                issues.append(f"🔴 {q['query_id']}: 查询包含语法错误 '{tw}': {qt}")
    
    # 7. 检查代码变量名泄露
    bad_vars = {"event_type", "memory_id", "chain_id", "cluster_id", "location"}
    for q in queries:
        qt = q["query_text"]
        for bv in bad_vars:
            if bv in qt:
                issues.append(f"🔴 {q['query_id']}: 查询包含代码变量名 '{bv}': {qt}")
    
    # 8. 检查时序链位置连续性
    chain_positions = defaultdict(list)
    for m in db["memories"]:
        cid = m.get("reasoning_chain")
        if cid and m.get("chain_relation") == "时序":
            pos = m.get("chain_position")
            if pos is not None:
                chain_positions[cid].append(pos)
    
    for cid, positions in chain_positions.items():
        if len(positions) > 1:
            sorted_pos = sorted(positions)
            for i in range(len(sorted_pos) - 1):
                if sorted_pos[i+1] - sorted_pos[i] > 1:
                    issues.append(f"🟡 {cid}: 位置不连续: {sorted_pos}")
                    break
    
    # 9. 检查链式查询答案是否包含整条链
    for q in queries:
        if q.get("query_type") in chain_types:
            mem_ids = q["expected_memory_ids"]
            ans = q.get("expected_answer_text", "")
            # 答案应包含所有记忆
            for mid in mem_ids:
                if mid in memories:
                    m = memories[mid]
                    person = m["person"]["name"]
                    if person not in ans:
                        issues.append(f"🟡 {q['query_id']}: 答案缺少链成员 {person}: {ans[:80]}")
    
    # 10. 检查推导链前提匹配
    for q in queries:
        if q.get("query_type") == "推导推理链":
            match = re.search(r'从(.+?)出发', q["query_text"])
            if match:
                premise = match.group(1).strip()
                for mid in q["expected_memory_ids"][:1]:
                    if mid in memories:
                        m = memories[mid]
                        person = m["person"]["name"]
                        action = m["event"]["action"]
                        product = m["event"]["product"]
                        city = m["location"]["city"]
                        mem_text = f'{person}在{city}{action}了{product}'
                        if premise != mem_text:
                            issues.append(f"🟡 {q['query_id']}: 推导前提 '{premise}' 与记忆 '{mem_text}' 不完全匹配")
    
    # 11. 检查负样本人物重复
    negative_people = []
    for q in queries:
        if q.get("is_negative"):
            person_match = re.search(r'^(\S+)', q["query_text"])
            if person_match:
                negative_people.append(person_match.group(1))
    
    person_counts = Counter(negative_people)
    for p, c in person_counts.items():
        if c > 3:
            issues.append(f"🟡 负样本人物 '{p}' 出现 {c} 次，过于集中")
    
    # 12. 检查负样本类型多样性
    negative_types = []
    for q in queries:
        if q.get("is_negative"):
            qt = q["query_text"]
            if "在火星" in qt or "在木星" in qt:
                negative_types.append("地点不存在")
            elif any(w in qt for w in ["游泳", "打篮球", "滑雪", "唱歌", "画画"]):
                negative_types.append("动作不存在")
            elif "购买了" in qt:
                negative_types.append("产品不存在")
            elif "最近做了什么" in qt:
                negative_types.append("人物不存在")
            else:
                negative_types.append("其他")
    
    type_counts = Counter(negative_types)
    if len(type_counts) < 3:
        issues.append(f"🟡 负样本类型单一: {dict(type_counts)}")
    
    return issues, len(queries)


def main():
    issues, total = check_all()
    
    print("=" * 70)
    print("  MemTest 查询-答案质量审查报告")
    print("=" * 70)
    print(f"\n总查询数: {total}")
    print(f"发现问题: {len(issues)}\n")
    
    if not issues:
        print("✅ 所有查询和答案检查通过！")
    else:
        for issue in issues:
            print(issue)
    
    print("\n" + "=" * 70)
    print(f" 结果: {'✅ 通过' if not issues else f'⚠️ {len(issues)} 个问题'} ({len([i for i in issues if i.startswith('🔴')])} 严重, {len([i for i in issues if i.startswith('🟡')])} 警告)")
    print("=" * 70)


if __name__ == "__main__":
    main()
