#!/usr/bin/env python3
"""
MemTest LLM 数据生成器 — 运行时调用 DeepSeek API 生成高质量中文数据

用法:
    export DEEPSEEK_API_KEY=sk-xxx
    python generate_llm.py > sample_db.json          # 默认 100 条
    python generate_llm.py --size 1000 > big_db.json   # 自定义规模
    python generate_llm.py --model flash              # 指定模型（默认 flash）
    python generate_llm.py --dry-run                  # 不调用 API，打印 prompt 预览

环境变量:
    DEEPSEEK_API_KEY — API密钥（必须）
    DEEPSEEK_BASE_URL — 可选，默认 https://api.deepseek.com
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta

# 导入 httpx 或 requests
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    try:
        import requests
        HAS_REQUESTS = True
    except ImportError:
        print("Error: 需要 httpx 或 requests。pip install httpx", file=sys.stderr)
        sys.exit(1)

# ========== 配置 ==========
DEFAULT_MODEL = "deepseek-chat"  # flash 级别
DEFAULT_SIZE = 100
API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# 人物池
PEOPLE_POOL = [
    ("张伟", "创业者"), ("李明", "金融分析师"), ("王芳", "科技投资人"),
    ("刘洋", "健身教练"), ("陈静", "个人投资者"), ("赵磊", "职业交易员"),
    ("李娜", "天使投资人"), ("孙强", "医生"), ("周梅", "护士"),
    ("吴昊", "律师"), ("郑欣", "法官"), ("黄丽", "教师"),
]

CITIES = ["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "西安", "南京", "苏州"]
EVENT_TYPES = ["投资", "购买", "学习", "研究", "开发", "建设", "培训", "参观", "签约", "发布"]


def call_llm(messages: list, model: str = None, temperature: float = 0.7, max_retries: int = 3) -> str:
    """调用 DeepSeek API。"""
    model = model or DEFAULT_MODEL
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 800
    }
    
    for attempt in range(max_retries):
        try:
            if HAS_HTTPX:
                r = httpx.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=60)
            else:
                r = requests.post(f"{API_BASE}/chat/completions", json=payload, headers=headers, timeout=60)
            
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return ""


def extract_json_array(text: str) -> list:
    """从LLM响应中提取JSON数组，支持markdown代码块。"""
    import re
    
    # 1. 尝试完整解析
    text = text.strip()
    try:
        return json.loads(text)
    except:
        pass
    
    # 2. 尝试从 ```json ... ``` 提取
    match = re.search(r'```(?:json)?\s*\n?(\[.*?\])\s*\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    
    # 3. 尝试找第一个 [ 到最后一个 ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except:
            pass
    
    # 4. 尝试逐行找JSON数组开头
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith('['):
            try:
                # 尝试从这一行开始解析到文件末尾
                candidate = '\n'.join(lines[i:])
                end_idx = candidate.rfind(']')
                if end_idx != -1:
                    return json.loads(candidate[:end_idx+1])
            except:
                pass
    
    return []


def generate_memory_batch(count: int, model: str) -> list:
    """用 LLM 批量生成记忆种子数据。"""
    
    prompt = f"""你是 MemTest 评测数据生成专家。请生成 {count} 条符合以下格式的中文记忆数据。

要求：
1. 每条记忆是一个JSON对象，包含自然流畅的中文事件描述
2. 人物、地点、动作、对象必须语义搭配合理
3. 时间跨度要合理（2020-2024年）
4. 避免语法错误，如"进行了健身运动了旅游服务"

输出严格JSON数组格式，不要任何解释文字：

[
  {{
    "person": "张伟",
    "identity": "创业者",
    "city": "北京",
    "place": "中关村创业大街",
    "landmark": "创业孵化器",
    "action": "启动",
    "product": "新能源汽车项目",
    "event_type": "创业",
    "quantity": 1,
    "price": 0,
    "timestamp": "2024-01-15 09:30:00",
    "tags": ["推理测试", "中等"]
  }},
  ...
]

人物池（12人）：张伟(创业者)、李明(金融分析师)、王芳(科技投资人)、刘洋(健身教练)、陈静(个人投资者)、赵磊(职业交易员)、李娜(天使投资人)、孙强(医生)、周梅(护士)、吴昊(律师)、郑欣(法官)、黄丽(教师)

城市池：北京、上海、深圳、广州、杭州、成都、武汉、西安、南京、苏州

事件类型：投资、购买、学习、研究、开发、建设、培训、参观、签约、发布

动作与产品搭配示例：
- 启动 + 新能源汽车项目
- 购买 + 公寓 / 股票 / 课程
- 研究 + 病毒基因序列 / 神经网络
- 开发 + APP / 系统
- 建设 + 数据中心 / 智慧园区
- 培训 + 团队 / 学员
- 参观 + 展览 / 工厂
- 签约 + 合作协议 / 投资协议
- 发布 + 新产品 / 研究成果

请生成 {count} 条，确保：
1. 动作和产品自然搭配
2. 不重复已有搭配组合
3. 时间分布均匀覆盖2020-2024年
4. 每条包含丰富细节"""
    
    response = call_llm([{"role": "user", "content": prompt}], model=model, temperature=0.8)
    
    return extract_json_array(response)


def generate_chain_with_llm(person: str, identity: str, city: str, 
                             chain_type: str, length: int, model: str) -> list:
    """用 LLM 生成一条连贯的推理链。"""
    
    type_desc = {
        "时序": "时间先后关系，前一件事导致后一件事发生",
        "因果": "因果关系，前因后果",
        "对比": "同一主题下不同人物/方案的对照",
        "包含": "整体项目包含多个子事件",
        "推导": "从观察→分析→判断→验证的逻辑推导"
    }
    
    prompt = f"""生成一条{chain_type}推理链，{length}个节点。

人物：{person}（{identity}）
城市：{city}
链类型：{type_desc.get(chain_type, chain_type)}

要求：
1. 每个节点是一个事件，动作+产品搭配自然
2. 节点之间有清晰的{chain_type}关系
3. 时间按顺序排列
4. 输出严格JSON数组

格式示例（时序链）：
[
  {{"action": "启动", "product": "新能源汽车项目", "event_type": "创业", "place": "创业大街", "landmark": "孵化器", "quantity": 1, "price": 0, "days_offset": 0}},
  {{"action": "调研", "product": "消费者需求", "event_type": "市场", "place": "调研中心", "landmark": "商业综合体", "quantity": 2000, "price": 0, "days_offset": 65}},
  {{"action": "完成", "product": "原型车", "event_type": "研发", "place": "开发区", "landmark": "工业设计园", "quantity": 3, "price": 500000, "days_offset": 146}},
  {{"action": "申请", "product": "电池技术专利", "event_type": "知识产权", "place": "知识产权局", "landmark": "专利大厅", "quantity": 5, "price": 0, "days_offset": 202}},
  {{"action": "量产", "product": "新能源汽车", "event_type": "生产", "place": "制造基地", "landmark": "智能工厂", "quantity": 500, "price": 150000, "days_offset": 260}}
]

注意：
- action 必须是动词（启动、调研、完成、申请、量产）
- product 是名词短语
- 不能用"进行"+产品 这种无意义搭配
- days_offset 是相对于第一条的天数差"""
    
    response = call_llm([{"role": "user", "content": prompt}], model=model, temperature=0.7)
    
    return extract_json_array(response)


def seed_to_memory(seed: dict, mem_id: int) -> dict:
    """将LLM生成的种子转换为完整记忆结构。"""
    ts_str = seed.get("timestamp", "2024-01-01 10:00:00")
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    now = datetime(2025, 7, 1)
    days = (now - dt).days
    
    p = seed["person"]
    i = seed.get("identity", "")
    c = seed["city"]
    pl = seed.get("place", "")
    act = seed["action"]
    prod = seed["product"]
    qty = seed.get("quantity", 1)
    price = seed.get("price", 0)
    
    v1 = f"{p}在{c}{pl}{act}了{prod}"
    if qty > 1:
        v1 += f"，数量{qty}"
    
    v2 = f"{p}回忆道：当时在{c}的{pl}，作为{i}的{p}{act}了{prod}"
    if qty > 1:
        v2 += f"，总共{qty}"
    if price > 0:
        v2 += f"，花费{price}元"
    
    v3 = f"据知情人士透露，{p}在{c}那边{act}了{prod}，具体情况还在核实中"
    
    diff = "简单" if days < 365 else ("中等" if days < 730 else "困难")
    
    return {
        "memory_id": f"MEM{mem_id:06d}",
        "category": seed.get("tags", ["LLM生成"])[0] + "测试集",
        "difficulty": diff,
        "weight": {"简单": 0.5, "中等": 1.0, "困难": 1.5}.get(diff, 1.0),
        "time": {
            "absolute": ts_str,
            "relative": f"{days//365}年前" if days > 365 else f"{days//30}个月前",
            "fuzzy": "去年" if days > 365 else "半年前" if days > 180 else "本月",
            "timestamp": int(dt.timestamp())
        },
        "location": {
            "city": c,
            "place": pl,
            "landmark": seed.get("landmark", "")
        },
        "person": {
            "name": p,
            "identity": i,
            "partner_name": seed.get("partner", ""),
            "partner_identity": seed.get("partner_id", ""),
            "relation": seed.get("relation", "")
        },
        "event": {
            "type": seed.get("event_type", ""),
            "action": act,
            "product": prod,
            "quantity": qty,
            "price": price
        },
        "versions": [
            {"version_id": "v1", "style": "客观叙述", "content": v1},
            {"version_id": "v2", "style": "主观视角", "content": v2},
            {"version_id": "v3", "style": "第三方转述", "content": v3}
        ],
        "tags": seed.get("tags", ["LLM生成", "中等"]),
        "decay": {"level": None, "access_count": 0}
    }


def build_queries_llm(memories: list, model: str) -> list:
    """用 LLM 为生成的记忆设计查询。"""
    
    # 抽取关键信息传给 LLM
    mem_summary = []
    for m in memories[:30]:  # 只传前30条避免太长
        mem_summary.append({
            "id": m["memory_id"],
            "person": m["person"]["name"],
            "city": m["location"]["city"],
            "action": m["event"]["action"],
            "product": m["event"]["product"],
            "time": m["time"]["absolute"],
            "tags": m["tags"]
        })
    
    prompt = f"""基于以下记忆数据，生成测试查询。

记忆数据（前30条摘要）：
{json.dumps(mem_summary, ensure_ascii=False, indent=2)}

要求：
1. 生成10-15条查询，覆盖不同测试维度
2. 查询必须基于真实存在的记忆（人物、地点、事件都在上面的列表里）
3. 包含2-3条负样本（查询不存在的事件）
4. 每条查询格式：

{{
  "query_id": "Q0001",
  "query_text": "张伟在北京启动了什么项目？",
  "query_type": "精确检索",
  "test_dimension": "精确检索",
  "expected_memory_ids": ["MEM000001"],
  "expected_answer_text": "张伟在北京中关村创业大街启动了新能源汽车项目",
  "acceptable_answers": ["张伟在北京中关村创业大街启动了新能源汽车项目"],
  "is_negative": false,
  "difficulty": "简单"
}}

负样本示例：
{{
  "query_id": "Q0010",
  "query_text": "张三在火星购买了房产",
  "query_type": "负样本",
  "test_dimension": "负样本",
  "expected_memory_ids": [],
  "expected_answer_text": "",
  "acceptable_answers": [],
  "is_negative": true,
  "difficulty": "简单"
}}

输出严格JSON数组，不要解释。"""
    
    response = call_llm([{"role": "user", "content": prompt}], model=model, temperature=0.5)
    
    queries = extract_json_array(response)
    if queries:
        return queries
    
    print(f"Warning: 查询生成失败。响应: {response[:200]}", file=sys.stderr)
    return []


def main():
    parser = argparse.ArgumentParser(description="MemTest LLM 数据生成器")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"生成记忆数量（默认{DEFAULT_SIZE}）")
    parser.add_argument("--model", default="deepseek-chat", help="模型名称（默认 deepseek-chat）")
    parser.add_argument("--chains", type=int, default=5, help="推理链数量（默认5）")
    parser.add_argument("--chain-length", type=int, default=5, help="每条链长度（默认5）")
    parser.add_argument("--clusters", type=int, default=3, help="聚类数量（默认3）")
    parser.add_argument("--dry-run", action="store_true", help="打印prompt预览，不调用API")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    
    random.seed(args.seed)
    
    if not API_KEY:
        print("Error: 请设置环境变量 DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)
    
    if args.dry_run:
        print("=== Prompt 预览（第一条链）===")
        print(generate_chain_with_llm("张伟", "创业者", "北京", "时序", 5, args.model))
        return
    
    print(f"开始生成 {args.size} 条记忆...", file=sys.stderr)
    
    memories = []
    mem_id = 1
    
    # 1. 生成推理链（用 LLM）
    chain_types = ["时序", "因果", "对比", "包含", "推导"]
    for i in range(args.chains):
        person, identity = random.choice(PEOPLE_POOL)
        city = random.choice(CITIES)
        ctype = chain_types[i % len(chain_types)]
        
        print(f"  生成 {ctype} 链: {person} @ {city}...", file=sys.stderr)
        chain_nodes = generate_chain_with_llm(person, identity, city, ctype, args.chain_length, args.model)
        
        if not chain_nodes:
            print(f"  链生成失败，跳过", file=sys.stderr)
            continue
        
        base_time = datetime(2023, 1, 1) + timedelta(days=random.randint(0, 365))
        chain_id = f"CHAIN_{ctype}_{mem_id:04d}"
        
        for j, node in enumerate(chain_nodes):
            ts = base_time + timedelta(days=node.get("days_offset", j * 60))
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            
            seed = {
                "person": person,
                "identity": identity,
                "city": city,
                "place": node.get("place", ""),
                "landmark": node.get("landmark", ""),
                "action": node["action"],
                "product": node["product"],
                "event_type": node.get("event_type", "事件"),
                "quantity": node.get("quantity", 1),
                "price": node.get("price", 0),
                "timestamp": ts_str,
                "tags": ["推理测试", "中等" if ctype != "因果" else "困难", ctype]
            }
            
            mem = seed_to_memory(seed, mem_id)
            mem["reasoning_chain"] = chain_id
            mem["chain_position"] = j + 1
            mem["chain_total"] = len(chain_nodes)
            mem["chain_hop"] = j + 1
            mem["chain_prev"] = f"MEM{mem_id-1:06d}" if j > 0 else ""
            mem["chain_next"] = f"MEM{mem_id+1:06d}" if j < len(chain_nodes) - 1 else ""
            mem["chain_relation"] = ctype
            if ctype in ["因果", "推导"]:
                mem["logic"] = {"type": ctype}
            
            memories.append(mem)
            mem_id += 1
    
    # 2. 生成独立记忆（用 LLM 批量）
    remaining = args.size - len(memories)
    if remaining > 0:
        batch_size = min(20, remaining)
        batches = (remaining + batch_size - 1) // batch_size
        
        for b in range(batches):
            count = min(batch_size, remaining - b * batch_size)
            print(f"  批量生成独立记忆 {b+1}/{batches}（{count}条）...", file=sys.stderr)
            
            seeds = generate_memory_batch(count, args.model)
            for seed in seeds:
                mem = seed_to_memory(seed, mem_id)
                mem["tags"] = seed.get("tags", ["LLM生成", "中等"])
                mem["retrieval_keywords"] = [
                    seed["person"], seed["city"], 
                    seed.get("event_type", ""), seed["action"], seed["product"]
                ]
                memories.append(mem)
                mem_id += 1
    
    # 3. 生成查询（用 LLM）
    print(f"  生成查询...", file=sys.stderr)
    queries = build_queries_llm(memories, args.model)
    
    # 如果 LLM 查询生成失败，用简单规则生成
    if not queries:
        print("  查询生成失败，回退到规则生成", file=sys.stderr)
        queries = generate_fallback_queries(memories)
    
    # 4. 组装数据库
    categories = {}
    for m in memories:
        cat = m["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    db = {
        "database_info": {
            "name": "MemTest Database (LLM Generated)",
            "version": "3.0.0",
            "total_count": len(memories),
            "categories": categories,
            "generated_by": "llm",
            "model": args.model,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "memories": memories,
        "queries": queries
    }
    
    # 所有状态信息只输出到stderr，stdout只有纯JSON
    sys.stdout.write(json.dumps(db, ensure_ascii=False, indent=2))
    sys.stdout.write('\n')
    sys.stdout.flush()
    print(f"生成完成: {len(memories)} 条记忆, {len(queries)} 条查询", file=sys.stderr)


def generate_fallback_queries(memories: list) -> list:
    """LLM 查询生成失败时的回退方案。"""
    queries = []
    qid = 1
    
    # 从链中取时序查询
    chain_mems = [m for m in memories if m.get("reasoning_chain")]
    if chain_mems:
        chain_ids = list(set(m["reasoning_chain"] for m in chain_mems))
        for cid in chain_ids[:3]:
            mems = sorted([m for m in memories if m.get("reasoning_chain") == cid], 
                         key=lambda x: x.get("chain_position", 0))
            if len(mems) >= 2:
                p = mems[0]["person"]["name"]
                c = mems[0]["location"]["city"]
                act = mems[0]["event"]["action"]
                prod = mems[0]["event"]["product"]
                ids = [m["memory_id"] for m in mems]
                parts = [f"{m['person']['name']}在{m['location']['city']}{m['event']['action']}了{m['event']['product']}" for m in mems]
                ans = " → ".join(parts)
                
                queries.append({
                    "query_id": f"Q{qid:04d}",
                    "query_text": f"{p}在{c}{act}了{prod}，后续事件依次是什么？",
                    "query_type": "时序推理链",
                    "test_dimension": "时序推理",
                    "expected_memory_ids": ids,
                    "expected_answer_text": ans,
                    "acceptable_answers": [ans],
                    "is_negative": False,
                    "difficulty": "中等"
                })
                qid += 1
    
    # 精确检索
    for m in memories[:5]:
        p = m["person"]["name"]
        c = m["location"]["city"]
        act = m["event"]["action"]
        prod = m["event"]["product"]
        
        queries.append({
            "query_id": f"Q{qid:04d}",
            "query_text": f"{p}在{c}做了什么？",
            "query_type": "精确检索",
            "test_dimension": "精确检索",
            "expected_memory_ids": [m["memory_id"]],
            "expected_answer_text": f"{p}在{c}{act}了{prod}",
            "acceptable_answers": [f"{p}在{c}{act}了{prod}"],
            "is_negative": False,
            "difficulty": "简单"
        })
        qid += 1
    
    # 负样本
    queries.append({
        "query_id": f"Q{qid:04d}",
        "query_text": "孙悟空在火星购买了房产",
        "query_type": "负样本",
        "test_dimension": "负样本",
        "expected_memory_ids": [],
        "expected_answer_text": "",
        "acceptable_answers": [],
        "is_negative": True,
        "difficulty": "简单"
    })
    
    return queries


if __name__ == "__main__":
    main()
