#!/usr/bin/env python3
"""
MemTest 测试数据库生成器 — 零依赖，纯程序化合成
生成 6 大类记忆测试数据 + 配套查询，输出标准 JSON。
输出可直接喂给任意 MemoryAdapter 做评测。

用法:
    python generator.py             # 生成 sample_db_100.json + sample_queries.json
    python generator.py --full      # 生成全量 test_db_10000.json
    python generator.py --size 500  # 自定义规模
"""

import json
import random
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any

random.seed(42)  # 可复现

# ====== 数据池 ======
CITIES = [
    "北京","上海","深圳","广州","杭州","成都","武汉","西安","南京","苏州",
    "天津","重庆","青岛","长沙","郑州","东莞","佛山","宁波","无锡","济南",
    "合肥","福州","厦门","沈阳","大连","哈尔滨","长春","南昌","昆明","贵阳",
    "石家庄","太原","呼和浩特","兰州","银川","西宁","乌鲁木齐","海口","三亚","拉萨",
    "珠海","中山","惠州","汕头","江门","湛江","茂名","肇庆","清远","潮州",
    "柳州","桂林","梧州","北海","钦州","贵港","玉林","百色","河池","来宾",
    "绵阳","德阳","南充","宜宾","泸州","达州","乐山","内江","遂宁","自贡",
    "昆山","常熟","张家港","太仓","江阴","宜兴","邳州","新沂","溧阳","句容",
    "慈溪","余姚","义乌","东阳","永康","诸暨","海宁","桐乡","平湖","瑞安",
    "温岭","玉环","龙港","乐清","苍南","晋江","石狮","南安","惠安","安溪"
]

PLACES = [
    "星巴克","肯德基","麦当劳","海底捞","全聚德","外婆家","绿茶餐厅","西贝莜面村",
    "瑞幸咖啡","喜茶","奈雪的茶","一点点","CoCo都可","蜜雪冰城",
    "万达广场","万象城","太古里","ifs国金中心","大悦城","龙湖天街","来福士",
    "盒马鲜生","永辉超市","山姆会员店","麦德龙","家乐福","沃尔玛","大润发",
    "故宫","长城","颐和园","西湖","黄山","泰山","兵马俑","外滩","东方明珠",
    "公司办公室","会议室A","会议室B","茶水间","休息室","健身房","停车场"
]

LANDMARKS = [
    "CBD核心区","科技园区","创业大厦","金融中心","商业综合体","居民小区",
    "大学校园","中学门口","小学门口","幼儿园","医院大厅","社区卫生站",
    "银行网点","ATM机","地铁站","公交站","高铁站","机场航站楼","加油站",
    "公园入口","体育馆","图书馆","博物馆","剧院","电影院","网吧","棋牌室",
    "健身房","游泳馆"
]

NAMES = [
    "张伟","王芳","李明","刘洋","陈静","杨勇","赵丽","周强","吴敏","郑鹏",
    "孙杰","马超","朱婷","胡磊","郭峰","林雪","何涛","高建","罗欢","梁志",
    "宋雨","唐军","许飞","韩冰","邓伟","冯磊","于娜","董洁","潘阳","蒋伟",
    "蔡明","余涛","杜鹃","苏敏","魏强","卢杰","姜丽","阎峰","薛磊","孟莉",
    "常琪","顾瑶","武毅","贺文","赖勇","邦达","申然","盛天","牛博","洪峰",
    "师倩","於洋","龚伟","祁坚","缪磊","施雨","孔祥","曹华","严军","苏醒",
    "单丹","乔磊","楚雷","楚雨","楚阳","钱伟","储勇","焦强","籍磊","窦莉",
    "章娜","麦朵","庄潇","柴明","蒙杰","桂峰","聂攀","晁哲","哈丹","元华",
    "卜顾","孟平","谷梁","谭勋","官恩","荆孝","巫丹","仇嵩","栾朵","戚谢",
    "邹游","储梅","喻理","柏林","和水","窦章","桑菜","应华","宗政","蒲团"
]

IDENTITIES = [
    "项目经理","软件工程师","产品经理","设计师","销售经理","市场专员","财务主管",
    "HR经理","运营总监","客户经理","数据分析师","算法工程师","测试工程师","架构师",
    "CTO","CEO","COO","CFO","总监","大学教授","中学老师","医生","律师","咨询师"
]

RELATIONS = [
    "同事","上级","下属","平级","朋友","闺蜜","兄弟","同学","客户","合作伙伴"
]

EVENT_TYPES = {
    "交易": ["购买","出售","投资","转账","退款"],
    "会议": ["召开","参加","主持","复盘"],
    "决策": ["批准","否决","确认"],
    "日常": ["上班","出差","加班","拜访","接待"],
    "技术": ["开发","测试","上线","发布"],
    "情感": ["庆祝","感谢","祝福"]
}

PRODUCTS = [
    "茅台","五粮液","苹果股票","特斯拉","比亚迪","宁德时代","腾讯","阿里",
    "字节跳动","京东","美团","百度","小米","华为","比特币","以太坊","黄金"
]

# ====== 时间生成 ======
def time_desc(days_ago: int) -> str:
    if days_ago == 0: return "刚刚"
    if days_ago == 1: return "昨天"
    if days_ago < 7: return f"{days_ago}天前"
    if days_ago < 30: return f"{days_ago//7}周前"
    if days_ago < 365: return f"{days_ago//30}个月前"
    return f"{days_ago//365}年前"

def fuzzy_time(days_ago: int) -> str:
    opts = {0:"今天",1:"昨天",3:"前几天",7:"上周",14:"两周前",30:"上个月",
            60:"两个月前",90:"三个月前",180:"半年前",365:"去年",730:"很久以前"}
    fuzz = "以前"
    for d, opt in sorted(opts.items(), reverse=True):
        if days_ago >= d: fuzz = opt; break
    return fuzz

# ====== 版本生成 ======
def make_versions(base: dict) -> list:
    dt = base["base_time"]
    return [
        {"version_id": "v1", "style": "标准叙述",
         "content": f"{base['person1']}在{base['city']}{base['place']}{base['action']}了{base['product']}，数量{base['quantity']}"},
        {"version_id": "v2", "style": "详细描述",
         "content": f"{dt.strftime('%Y年%m月%d日 %H时%M分')}，{base['person1']}（{base['identity1']}）在{base['city']}市{base['place']}进行{base['action']}操作，涉及{base['product']}，交易数量{base['quantity']}股，单价{base['price']}元"},
        {"version_id": "v3", "style": "口语化",
         "content": f"在{base['city']}出差的{base['person1']}，{dt.day}号那天{base['action']}了{base['product']}，搞了{base['quantity']}份"}
    ]

# ====== 记忆生成器 ======
class MemoryGenerator:
    def __init__(self):
        self.memory_id = 0

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
            "versions": make_versions(base), "tags": [],
            "cluster_id": None, "reasoning_chain": None, "chain_position": None,
            "decay": {"level": None, "access_count": 0}, **extra
        }

    def gen_storage(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["24h","7d","30d","90d","1y","fuzzy"]))
            result.append(self._build("存储正确性测试集", diff, base, tags=["存储测试", diff, str(base["days_ago"])+"d"]))
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
                                             "semantic_distance": random.choice(["near", "mid", "far"])},
                                      tags=["深度检索", diff]))
        return result

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

def generate_queries(memories: list, count: int = 100) -> list:
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

# ====== 主入口 ======
def build_database(size: int = 100) -> dict:
    gen = MemoryGenerator()
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
    queries = generate_queries(all_mems, max(30, size // 2))
    return {
        "database_info": {
            "name": "MemTest Database", "version": "1.0.0",
            "total_count": len(all_mems), "categories": cats,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "memories": all_mems, "queries": queries
    }

if __name__ == "__main__":
    import sys
    full = "--full" in sys.argv
    size = 100
    for a in sys.argv:
        if a.startswith("--size="): size = int(a.split("=")[1])
    if full: size = 10000
    db = build_database(size)
    db_file = f"test_db_{size}.json" if full or size > 100 else "sample_db_100.json"
    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"Generated {db_file}: {len(db['memories'])} memories, {len(db['queries'])} queries")
    qs = {"queries_info": {"total_count": len(db["queries"]), "query_types": list(QUERY_TEMPLATES.keys())},
          "queries": db["queries"]}
    with open("sample_queries.json", "w", encoding="utf-8") as f:
        json.dump(qs, f, ensure_ascii=False, indent=2)
    print(f"Generated sample_queries.json")
