#!/usr/bin/env python3
"""MemTest 测试数据库生成器 — 支持纯程序化合成 和 LLM增强生成

模式:
  --mock (默认): 纯程序化，零依赖，秒级生成
  --llm:          LLM增强生成，记忆文本更自然，查询更多样

用法:
    python generator.py              # 程序化生成 sample_db_100.json
    python generator.py --llm        # LLM增强生成（需要 DEEPSEEK_API_KEY）
    python generator.py --size=500   # 自定义规模
    python generator.py --full        # 生成10000条（程序化）
"""

import json, random, os, sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict

random.seed(42)

# ====== 数据池 ======
CITIES = ["北京","上海","深圳","广州","杭州","成都","武汉","西安","南京","苏州"]
PLACES = ["星巴克","肯德基","海底捞","全聚德","万达广场","太古里","公司办公室"]
LANDMARKS = ["CBD核心区","科技园区","金融中心","地铁站"]
NAMES = ["张伟","王芳","李明","刘洋","陈静","杨勇","赵丽","周强"]
IDENTITIES = ["项目经理","软件工程师","产品经理","设计师","销售经理"]
RELATIONS = ["同事","上级","下属","朋友","客户","合作伙伴"]
EVENT_TYPES = {"交易":["购买","出售","投资","转账"],"会议":["召开","参加","主持"],"日常":["上班","出差","拜访"]}
PRODUCTS = ["茅台","苹果股票","特斯拉","比亚迪","宁德时代","腾讯","阿里"]


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载提示词模板。"""
    paths = [
        f"prompts/{name}.md",
        os.path.join(os.path.dirname(__file__), "prompts", f"{name}.md"),
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except (OSError, IOError):
            pass
    # Fallback: 返回内联提示词
    return _INLINE_PROMPTS.get(name, "")


# ====== 内联提示词（当 prompts/ 目录不可用时回退） ======
_INLINE_PROMPTS = {
    "memory_enhance": """给定以下结构化记忆，生成同一事件的3种不同表达风格。

输入: {"person": "{person}", "identity": "{identity}", "location": "{location}", "event": "{event}", "time": "{time}"}

输出JSON格式: {"versions": [{"style":"标准叙述","content":"..."},{"style":"详细描述","content":"..."},{"style":"口语化","content":"..."}]}

规则：
1. 三种风格描述同一事件，核心事实一致
2. 不要编造未提供的信息
3. 每种版本30-120字，中文""",

    "query_generate": """给定以下记忆，生成5种查询方式。

输入: {"person": "{person}", "location": "{location}", "event": "{event}", "time": "{time}"}

输出JSON格式: {"queries": [{"query_type":"人物检索","query_text":"...","difficulty":"简单"}, ...]}

查询类型: 人物检索、地点检索、时间检索、事件检索、组合检索
难度: 简单(单一维度)、中等(两个维度)、困难(3+维度)
不要直接复制原文，要换一种表达""",
}


def _prompt_from_template(template_name: str, **kwargs) -> str:
    """用kwargs填充提示词模板中的占位符。"""
    prompt = load_prompt(template_name)
    for key, val in kwargs.items():
        prompt = prompt.replace("{" + key + "}", str(val))
    return prompt


# ====== 时间生成 ======
def time_desc(days_ago: int) -> str:
    if days_ago == 0: return "刚刚"
    if days_ago == 1: return "昨天"
    if days_ago < 7: return f"{days_ago}天前"
    if days_ago < 30: return f"{days_ago//7}周前"
    if days_ago < 365: return f"{days_ago//30}个月前"
    return f"{days_ago//365}年前"

def fuzzy_time(days_ago: int) -> str:
    opts = {0:"今天",1:"昨天",3:"前几天",7:"上周",30:"上个月",90:"三个月前",180:"半年前",365:"去年"}
    fuzz = "以前"
    for d, opt in sorted(opts.items(), reverse=True):
        if days_ago >= d: fuzz = opt; break
    return fuzz


# ====== 版本生成 ======
def make_versions_programmatic(base: dict) -> list:
    """程序化生成3种表达（默认，零依赖）。"""
    dt = base["base_time"]
    return [
        {"version_id": "v1", "style": "标准叙述",
         "content": f"{base['person1']}在{base['city']}{base['place']}{base['action']}了{base['product']}，数量{base['quantity']}"},
        {"version_id": "v2", "style": "详细描述",
         "content": f"{dt.strftime('%Y年%m月%d日 %H时%M分')}，{base['person1']}（{base['identity1']}）在{base['city']}市{base['place']}进行{base['action']}操作，涉及{base['product']}，交易数量{base['quantity']}股，单价{base['price']}元"},
        {"version_id": "v3", "style": "口语化",
         "content": f"在{base['city']}出差的{base['person1']}，{dt.day}号那天{base['action']}了{base['product']}，搞了{base['quantity']}份"}
    ]

def make_versions_llm(base: dict, llm) -> list:
    """LLM增强生成3种表达（更自然，需要API key）。"""
    prompt = _prompt_from_template(
        "memory_enhance",
        person=base["person1"],
        identity=base["identity1"],
        location=f"{base['city']} {base['place']}",
        event=f"{base['action']} {base['product']} {base['quantity']}股",
        time=base["base_time"].strftime("%Y-%m-%d"),
    )
    result = llm.generate_json(prompt, max_tokens=1500, temperature=0.3)
    versions = result.get("versions", [])
    if not versions:
        # LLM失败，回退到程序化
        return make_versions_programmatic(base)
    # 标准化
    for i, v in enumerate(versions):
        v["version_id"] = f"v{i+1}"
    return versions


# ====== 查询生成 ======
QUERY_TEMPLATES = {
    "时间检索": lambda m: [
        f"查找{m['time']['relative']}发生的事情",
        f"查询{m['time']['fuzzy']}在{m['location']['city']}的相关记录",
    ],
    "地点检索": lambda m: [
        f"在{m['location']['city']}{m['location']['place']}发生过什么",
        f"查询{m['location']['landmark']}的相关记忆",
    ],
    "人物检索": lambda m: [
        f"{m['person']['name']}最近做了什么",
        f"查询{m['person']['name']}的{m['person']['identity']}相关活动",
    ],
    "事件检索": lambda m: [
        f"关于{m['event']['product']}的事件有哪些",
        f"查询{m['event']['action']}相关的记录",
    ],
    "组合检索": lambda m: [
        f"{m['person']['name']}在{m['location']['city']}的{m['event']['action']}记录",
        f"查询{m['time']['relative']}{m['person']['name']}在{m['location']['place']}的{m['event']['type']}事件",
    ]
}

def generate_queries_programmatic(memories: list, count: int = 100) -> list:
    """程序化生成查询（默认）。"""
    queries = []
    selected = random.sample(memories, min(count, len(memories)))
    for i, m in enumerate(selected):
        qtype = random.choice(list(QUERY_TEMPLATES.keys()))
        templates = QUERY_TEMPLATES[qtype](m)
        queries.append({
            "query_id": f"Q{i+1:04d}",
            "query_text": random.choice(templates),
            "query_type": qtype,
            "expected_memory_ids": [m["memory_id"]],
            "expected_answer": m["versions"][0]["content"],
            "difficulty": m["difficulty"],
            "search_depth": random.choice(["浅层","中层","深层"])
        })
    return queries

def generate_queries_llm(memories: list, count: int = 100, llm=None) -> list:
    """LLM增强生成查询（更自然多样，需要API key）。"""
    if llm is None:
        return generate_queries_programmatic(memories, count)
    queries = []
    selected = random.sample(memories, min(count, len(memories)))

    for i, m in enumerate(selected):
        prompt = _prompt_from_template(
            "query_generate",
            person=m["person"]["name"],
            location=f"{m['location']['city']} {m['location']['place']}",
            event=f"{m['event']['action']} {m['event']['product']}",
            time=m["time"]["relative"],
        )
        result = llm.generate_json(prompt, max_tokens=1200, temperature=0.3)
        qs = result.get("queries", [])
        if not qs:
            # LLM失败，回退程序化
            qtype = random.choice(list(QUERY_TEMPLATES.keys()))
            templates = QUERY_TEMPLATES[qtype](m)
            queries.append({
                "query_id": f"Q{i+1:04d}",
                "query_text": random.choice(templates),
                "query_type": qtype,
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": m["versions"][0]["content"],
                "difficulty": m["difficulty"],
                "search_depth": random.choice(["浅层","中层","深层"])
            })
            continue

        for q in qs:
            queries.append({
                "query_id": f"Q{i+1:04d}",
                "query_text": q.get("query_text", ""),
                "query_type": q.get("query_type", "组合检索"),
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": m["versions"][0]["content"],
                "difficulty": q.get("difficulty", "中等"),
                "search_depth": random.choice(["浅层","中层","深层"])
            })

    return queries


# ====== 记忆生成器 ======
class MemoryGenerator:
    def __init__(self, use_llm: bool = False, llm=None):
        self.memory_id = 0
        self.use_llm = use_llm
        self.llm = llm

    def _id(self) -> str:
        self.memory_id += 1
        return f"MEM{self.memory_id:06d}"

    def _weight(self, difficulty: str) -> float:
        return {"简单": 0.5, "中等": 1.0, "困难": 1.5}.get(difficulty, 1.0)

    def _base(self, time_period: str) -> dict:
        ranges = {"24h":(1,1),"7d":(1,7),"30d":(7,30),"90d":(30,90),"1y":(90,365),"fuzzy":(365,730)}
        lo, hi = ranges.get(time_period, (1,30))
        days = random.randint(lo, hi)
        base_time = datetime.now() - timedelta(days=days)
        p1, p2 = random.sample(NAMES, 2)
        i1, i2 = random.sample(IDENTITIES, 2)
        etype = random.choice(list(EVENT_TYPES.keys()))
        return {
            "base_time": base_time, "days_ago": days,
            "city": random.choice(CITIES), "place": random.choice(PLACES),
            "landmark": random.choice(LANDMARKS),
            "person1": p1, "person2": p2, "identity1": i1, "identity2": i2,
            "relation": random.choice(RELATIONS),
            "event_type": etype, "action": random.choice(EVENT_TYPES[etype]),
            "product": random.choice(PRODUCTS),
            "quantity": random.randint(1, 1000) * (10 if random.random() > 0.5 else 1),
            "price": random.randint(10, 10000)
        }

    def _make_versions(self, base: dict) -> list:
        if self.use_llm and self.llm:
            return make_versions_llm(base, self.llm)
        return make_versions_programmatic(base)

    def _build(self, category: str, difficulty: str, base: dict, **extra) -> dict:
        return {
            "memory_id": self._id(), "category": category, "difficulty": difficulty,
            "weight": self._weight(difficulty),
            "time": {"absolute": base["base_time"].strftime("%Y-%m-%d %H:%M:%S"),
                     "relative": time_desc(base["days_ago"]),
                     "fuzzy": fuzzy_time(base["days_ago"]),
                     "timestamp": int(base["base_time"].timestamp())},
            "location": {"city": base["city"], "place": base["place"], "landmark": base["landmark"]},
            "person": {"name": base["person1"], "identity": base["identity1"],
                       "partner_name": base["person2"], "partner_identity": base["identity2"],
                       "relation": base["relation"]},
            "event": {"type": base["event_type"], "action": base["action"],
                      "product": base["product"], "quantity": base["quantity"], "price": base["price"]},
            "versions": self._make_versions(base), "tags": [],
            "cluster_id": None, "reasoning_chain": None, "chain_position": None,
            "decay": {"level": None, "access_count": 0}, **extra
        }

    def gen_storage(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["24h","7d","30d","90d","1y","fuzzy"]))
            result.append(self._build("存储正确性测试集", diff, base,
                                      tags=["存储测试", diff, str(base["days_ago"])+"d"]))
        return result

    def gen_retrieval(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["24h","7d","30d","90d","1y","fuzzy"]))
            keywords = [base["person1"], base["city"], base["event_type"], base["action"], base["product"]]
            result.append(self._build("检索功能测试集", diff, base, retrieval_keywords=keywords,
                                      tags=["检索测试", diff, str(base["days_ago"])+"d"]))
        return result

    def gen_organization(self, count: int) -> list:
        result = []
        for i in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["7d","30d","90d","1y"]))
            result.append(self._build("记忆整理测试集", diff, base, cluster_id=f"CLUSTER{(i//10)+1:04d}",
                                      tags=["整理测试", diff, base["event_type"]]))
        return result

    def gen_forgetting(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["24h","7d","30d","90d","1y"]))
            decay_level = random.choice(["高频记忆","中等频率","低频记忆","偶发事件"])
            result.append(self._build("遗忘功能测试集", diff, base,
                                      decay={"level": decay_level, "access_count": random.randint(0, 100)},
                                      tags=["遗忘测试", diff, decay_level]))
        return result

    def gen_reasoning(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["7d","30d","90d","1y"]))
            logic_type = random.choice(["因果","时序","对比","包含","推导"])
            result.append(self._build("逻辑推理测试集", diff, base, logic={"type": logic_type},
                                      tags=["推理测试", diff, logic_type]))
        return result

    def gen_deep(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["1y","fuzzy"]))
            result.append(self._build("长期记忆深度检索测试集", diff, base,
                                      depth={"layers": random.randint(3,7), "associations": random.randint(2,5),
                                             "semantic_distance": random.choice(["近", "中", "远"])},
                                      tags=["深度检索", diff]))
        return result


# ====== 主入口 ======
def build_database(size: int = 100, use_llm: bool = False, llm=None) -> dict:
    gen = MemoryGenerator(use_llm=use_llm, llm=llm)
    ratios = {"storage":0.17,"retrieval":0.17,"org":0.17,"forget":0.17,"reason":0.16,"deep":0.16}
    storage = gen.gen_storage(max(1, int(size * ratios["storage"])))
    retrieval = gen.gen_retrieval(max(1, int(size * ratios["retrieval"])))
    org = gen.gen_organization(max(1, int(size * ratios["org"])))
    forget = gen.gen_forgetting(max(1, int(size * ratios["forget"])))
    reason = gen.gen_reasoning(max(1, int(size * ratios["reason"])))
    deep = gen.gen_deep(max(1, int(size * ratios["deep"])))
    all_mems = storage + retrieval + org + forget + reason + deep
    random.shuffle(all_mems)
    cats = {}
    for m in all_mems: cats[m["category"]] = cats.get(m["category"], 0) + 1

    if use_llm and llm:
        queries = generate_queries_llm(all_mems, max(30, size // 2), llm)
    else:
        queries = generate_queries_programmatic(all_mems, max(30, size // 2))

    return {
        "database_info": {
            "name": "MemTest Database", "version": "1.0.0",
            "total_count": len(all_mems), "categories": cats,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "memories": all_mems, "queries": queries
    }


if __name__ == "__main__":
    full = "--full" in sys.argv
    use_llm = "--llm" in sys.argv
    size = 100
    for a in sys.argv:
        if a.startswith("--size="): size = int(a.split("=")[1])
    if full: size = 10000

    llm = None
    if use_llm:
        try:
            from llm_interface import create_llm
            llm = create_llm("deepseek")
            print(f"[LLM模式] 使用 DeepSeek API")
        except Exception as e:
            print(f"[警告] LLM初始化失败: {e}，回退到程序化模式")
            use_llm = False

    db = build_database(size, use_llm=use_llm, llm=llm)
    db_file = f"test_db_{size}.json" if full or size > 100 else "sample_db_100.json"
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"Generated {db_file}: {len(db['memories'])} memories, {len(db['queries'])} queries")
