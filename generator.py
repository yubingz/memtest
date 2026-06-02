"""MemTest 程序化生成器 — 生成测试数据库

旧架构兼容存根。新架构使用 pipeline_v4.py + extractor.py + relation_builder.py + query_builder.py。
"""

import json
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List


def _make_versions(content: str, person: str, location: str, time_abs: str) -> List[Dict[str, Any]]:
    """生成3个语义差异化版本"""
    v1 = content
    
    # v2: 实体化补全
    v2 = content
    if person and not v2.startswith(person):
        v2 = f"{person}：{v2}"
    if time_abs and time_abs not in v2:
        v2 = f"【{time_abs}】{v2}"
    if location and location not in v2:
        v2 = f"【地点：{location}】{v2}"
    
    # v3: 口语化简化
    v3 = content
    replacements = [
        (r"乃是", "是"), (r"亦即", "就是"), (r"便", "就"),
        (r"之", "的"), (r"遂", "于是"), (r"然", "但是"),
    ]
    for pattern, repl in replacements:
        v3 = v3.replace(pattern, repl)
    if len(v3) > 30:
        v3 = v3[:int(len(v3) * 0.85)]
        if v3[-1] not in "。！？；，":
            v3 += "…"
    
    return [
        {"version_id": "v1", "style": "客观叙述", "content": v1},
        {"version_id": "v2", "style": "实体化补全", "content": v2},
        {"version_id": "v3", "style": "口语化简化", "content": v3},
    ]


def build_database(count: int = 50, output_path: str = None) -> Dict[str, Any]:
    """程序化生成测试数据库（兼容旧接口）"""
    
    # 预设人物、地点、事件模板
    persons = ["刘备", "关羽", "张飞", "诸葛亮", "曹操", "孙权", "赵云", "黄忠"]
    locations = ["涿县", "新野", "赤壁", "荆州", "益州", "汉中", "许昌", "建业"]
    event_templates = [
        "{person}在{location}{action}",
        "{person}与{partner}在{location}{action}",
        "{location}之战，{person}{action}",
    ]
    actions = ["大败敌军", "商议军机", "招募兵马", "修缮城池", "宴请宾客", "巡视边防"]
    
    # 预生成时间（用于 expected_time）
    base_date = datetime(2024, 1, 1)
    
    memories = []
    for i in range(count):
        person = random.choice(persons)
        partner = random.choice([p for p in persons if p != person]) if random.random() > 0.5 else ""
        location = random.choice(locations)
        action = random.choice(actions)
        template = random.choice(event_templates)
        content = template.format(person=person, partner=partner, location=location, action=action)
        
        # 生成时间
        time_offset = random.randint(-365, 365)
        event_time = base_date + timedelta(days=time_offset)
        time_abs = event_time.strftime("%Y-%m-%d")
        
        mem = {
            "memory_id": f"MEM{i+1:06d}",
            "content": content,
            "person": {"name": person, "partner_name": partner, "identity": "", "relation": ""},
            "time": {"absolute": time_abs, "relative": None, "fuzzy": None},
            "location": {"city": location, "place": "", "landmark": ""},
            "event": {"type": "军事", "action": action, "product": ""},
            "source": "三国演义",
            "tags": [],
            "category": "检索功能测试集",
            "difficulty": random.choice(["简单", "中等", "困难"]),
            "weight": 1.0,
            "versions": _make_versions(content, person, location, time_abs),
        }
        memories.append(mem)
    
    # 构建 memory_id -> content 映射（先定义，供查询使用）
    mem_id_to_content = {m["memory_id"]: m["content"] for m in memories}
    
    # 生成多维度查询
    queries = []
    dimensions = [
        ("人物检索", "{target}做了什么？", lambda p: p["person"]["name"]),
        ("地点检索", "在{target}发生了什么？", lambda p: p["location"]["city"]),
        ("事件检索", "关于{target}的记录有哪些？", lambda p: p["event"]["action"]),
        ("时间检索", "{target}有什么事件？", lambda p: p["time"]["absolute"]),
        ("组合检索", "{target}", lambda p: f"{p['person']['name']}在{p['location']['city']}"),
    ]
    
    # 正样本查询 — 确保数量充足，不严格去重（不同维度可重复）
    used_targets = {}  # (target, dim_name) -> count
    max_per_target_dim = 3
    for i in range(min(count * 4, 500)):
        dim_name, template, extract = random.choice(dimensions)
        mem = random.choice(memories)
        target = extract(mem)
        key = (target, dim_name)
        if used_targets.get(key, 0) >= max_per_target_dim:
            continue
        used_targets[key] = used_targets.get(key, 0) + 1
        
        text = template.format(target=target)
        expected = [m["memory_id"] for m in memories if target in m["content"] or target in m.get("person", {}).get("name", "") or target in m.get("location", {}).get("city", "") or target in m.get("event", {}).get("action", "") or target == m.get("time", {}).get("absolute", "")]
        
        if not expected:
            continue  # 跳过无匹配的正样本
        
        # expected_answer 使用 dict 格式
        expected_answer = {mid: {"text": mem_id_to_content.get(mid, ""), "score": 1} for mid in expected[:5]}
        # expected_answer_text 用于文本匹配场景
        expected_answer_text = " | ".join(mem_id_to_content.get(mid, "") for mid in expected[:3])
        # acceptable_answers 用于兼容旧测试
        acceptable_answers = [mem_id_to_content.get(mid, "") for mid in expected[:5]]
        
        # 时间查询的 expected_time
        expected_time = None
        if dim_name == "时间检索":
            expected_time = {"absolute": target, "fuzzy": None}
        
        queries.append({
            "query_id": f"Q{(i+1):04d}",
            "query_text": text,
            "query_type": dim_name,
            "test_dimension": dim_name,
            "expected_memory_ids": expected[:5],
            "expected_answer": expected_answer,
            "expected_answer_text": expected_answer_text,
            "acceptable_answers": acceptable_answers,
            "expected_time": expected_time,
            "difficulty": random.choice(["简单", "中等", "困难"]),
            "search_depth": "中层",
            "is_negative": False,
        })
    
    # 负样本查询 — 按比例生成（目标15-25%）
    neg_target_ratio = 0.20
    neg_target_count = max(8, int(len(queries) * neg_target_ratio / (1 - neg_target_ratio)))
    negative_names_pool = [
        "孙悟空", "猪八戒", "林黛玉", "贾宝玉", "宋江", "武松", "唐僧", "白骨精",
        "貂蝉", "西施", "王昭君", "杨玉环", "鲁智深", "李逵", "林冲", "秦明",
        "哪吒", "杨戬", "雷震子", "姜子牙", "周瑜", "司马懿", "吕布", "董卓",
        "花木兰", "穆桂英", "樊梨花", "梁红玉", "扈三娘", "孙二娘", "顾大嫂",
        "秦琼", "尉迟恭", "程咬金", "罗成", "薛仁贵", "郭子仪", "岳飞", "文天祥",
        "包拯", "狄仁杰", "海瑞", "于谦", "郑和", "玄奘", "鉴真", "六祖慧能",
    ]
    used_neg = set()
    corpus_names = set()
    for m in memories:
        corpus_names.add(m["person"]["name"])
        if m["person"]["partner_name"]:
            corpus_names.add(m["person"]["partner_name"])
    
    neg_idx = len(queries)
    for name in negative_names_pool:
        if len(used_neg) >= neg_target_count:
            break
        if name not in corpus_names and name not in used_neg:
            used_neg.add(name)
            queries.append({
                "query_id": f"Q{(neg_idx+1):04d}",
                "query_text": f"{name}做了什么？",
                "query_type": "人物检索",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "expected_answer_text": "",
                "acceptable_answers": [],
                "expected_time": None,
                "difficulty": "中等",
                "search_depth": "中层",
                "is_negative": True,
            })
            neg_idx += 1
    
    # 构建 memory_id -> content 映射（用于 expected_answer）
    mem_id_to_content = {m["memory_id"]: m["content"] for m in memories}
    
    # 重新填充 expected_answer 中的 content
    for q in queries:
        if not q.get("is_negative") and isinstance(q.get("expected_answer"), dict):
            for mid in list(q["expected_answer"].keys()):
                q["expected_answer"][mid] = {
                    "text": mem_id_to_content.get(mid, ""),
                    "score": 1
                }
    
    # 确保至少5个维度
    dim_counts = {}
    for q in queries:
        dim = q["test_dimension"]
        dim_counts[dim] = dim_counts.get(dim, 0) + 1
    
    # 补充维度
    extra_dims = [
        ("因果推理", "为什么{target}{action}？"),
        ("时序推理", "{target}之前发生了什么？"),
        ("对比推理", "{target}和{partner}有什么不同？"),
        ("别名查询", "{target}的别名叫什么？"),
    ]
    
    while len(dim_counts) < 5 and extra_dims:
        dim_name, template = extra_dims.pop(0)
        mem = random.choice(memories)
        target = mem["person"]["name"]
        partner = mem["person"]["partner_name"] or random.choice(persons)
        action = mem["event"]["action"]
        text = template.format(target=target, partner=partner, action=action)
        
        queries.append({
            "query_id": f"Q{(len(queries)+1):04d}",
            "query_text": text,
            "query_type": dim_name,
            "test_dimension": dim_name,
            "expected_memory_ids": [mem["memory_id"]],
            "expected_answer": {mem["memory_id"]: {"text": mem["content"], "score": 1}},
            "expected_time": None,
            "difficulty": "困难",
            "search_depth": "深层",
            "is_negative": False,
        })
        dim_counts[dim_name] = dim_counts.get(dim_name, 0) + 1
    
    # 收集类别信息
    categories = {}
    for m in memories:
        cat = m.get("category", "未分类")
        categories[cat] = categories.get(cat, 0) + 1
    
    # 重新编号
    for i, q in enumerate(queries):
        q["query_id"] = f"Q{(i+1):04d}"
    
    db = {
        "database_info": {
            "name": "程序化生成测试数据库",
            "version": "4.0.0",
            "description": "兼容旧接口的程序化生成数据库",
            "source": "generator.py",
            "total_count": len(memories),
            "total_memories": len(memories),
            "total_queries": len(queries),
            "categories": list(categories.keys()),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "memories": memories,
        "queries": queries,
    }
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    
    return db
