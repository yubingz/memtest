#!/usr/bin/env python3
"""
MemTest Knowledge Builder — 从任意中文长文本生成评测数据库

输入: MD 文章目录 (经典书籍、知乎文章、百科等)
输出: 标准 MemTest JSON 评测数据库 (带 facts + chains + queries)

依赖: DeepSeek API (或其他 OpenAI-compatible API)

用法:
    python knowledge_builder.py ./my_books/ output.json
    python knowledge_builder.py ./my_books/ output.json --merge  # 增量追加

流程:
    1. LLM 事实提取 (content/person/location/time/dynasty/event_type)
    2. LLM 字段分类校验 (dynasty vs location vs concept)
    3. 标准化 + 推理链构建
    4. 6 类均衡查询生成
    5. LLM 预解析缓存 (查询→结构化检索参数)
"""

import json, os, sys, time, random
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections import defaultdict

random.seed(42)

# ====== 配置 ======
BATCH = 3
QUERIES_PER_TYPE = 25
MAX_CHAIN_DEPTH = 6

# ====== API Key ======
KEY = ''
for p in [os.path.join(os.path.dirname(__file__), '.env'),
          os.path.join(os.path.dirname(__file__), '..', '.env'), '.env']:
    try:
        with open(p, encoding='utf-8') as f:
            for l in f:
                if l.startswith('DEEPSEEK_API_KEY='):
                    KEY = l.split('=', 1)[1].strip().strip('"')
                    break
    except:
        pass
    if KEY: break


def llm(prompt, max_tokens=3000):
    d = json.dumps({
        'model': 'deepseek-chat',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens, 'temperature': 0
    }).encode()
    r = urlopen(Request(
        'https://api.deepseek.com/v1/chat/completions', data=d,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}
    ), timeout=60)
    c = json.loads(r.read())['choices'][0]['message']['content'].strip()
    if c.startswith('```'):
        c = '\n'.join(c.split('\n')[1:-1])
    return c.strip()


# ====== 阶段1: 事实提取 ======
EXTRACT_PROMPT = """从文本提取所有独立事实。严格遵守字段规则:

字段定义:
- content: 简洁事实陈述(15-40字)
- person: 人物姓名(非人物留空)
- location: 实体地理地点(城市/建筑/地区)。朝代/时期/政权名/概念词不要放这里！
- time: 具体时间(年份/日期)。朝代/时期放dynasty字段！
- dynasty: 朝代/时期/政权名(如东晋、西汉、战国、贞观年间)
- event_type: 事件类型简短标签

规则:
1. location只放实体地点(沧州、红岸基地、丞相府)，朝代(东晋、西汉)和概念(别墅、实验室)不放
2. dynasty与time分开: "383年"→time, "东晋"→dynasty, 不合并
3. 每人每事每地分别提取
4. 同一人物的连续事件按chain_id串联(position 1-6)
5. 输出纯JSON数组，每行一个对象

文本:
"""


def extract_facts(articles_dir, existing_facts=None, done_files=None):
    if existing_facts is None: existing_facts = []
    if done_files is None: done_files = set()

    todo = []
    for root, dirs, files in os.walk(articles_dir):
        for fn in files:
            if fn.endswith('.md') and fn not in done_files:
                todo.append((os.path.basename(root), os.path.join(root, fn)))

    if not todo:
        print(f'[{time.strftime("%H:%M")}] All files processed')
        return existing_facts, done_files

    print(f'[{time.strftime("%H:%M")}] {len(existing_facts)} existing, {len(todo)} files remaining')

    for bi in range(0, len(todo), BATCH):
        batch = todo[bi:bi + BATCH]
        for dname, path in batch:
            fn = os.path.basename(path)
            with open(path, encoding='utf-8') as fh:
                t = fh.read()
            if t.startswith('---'):
                idx = t.find('---', 3)
                if idx > 0: t = t[idx + 3:]
            if len(t) < 500: continue
            try:
                c = llm(EXTRACT_PROMPT + t[:3000])
                n = 0
                try:
                    arr = json.loads(c)
                    if isinstance(arr, list):
                        for item in arr:
                            if isinstance(item, dict):
                                existing_facts.append(item); n += 1
                except:
                    for l in c.split('\n'):
                        l = l.strip().rstrip(',')
                        if l.startswith('{') and l.endswith('}'):
                            try: existing_facts.append(json.loads(l)); n += 1
                            except: pass
                print(f'  [{time.strftime("%H:%M")}] +{n:4d} | {dname}/{fn[:35]}', flush=True)
                done_files.add(fn)
            except HTTPError as e:
                print(f'  [{time.strftime("%H:%M")}] HTTP{e.code} | {dname}/{fn[:35]}', flush=True)
            except Exception as e:
                print(f'  [{time.strftime("%H:%M")}] {type(e).__name__} | {dname}/{fn[:35]}', flush=True)

    return existing_facts, done_files


# ====== 阶段2: 字段分类校验 ======
def classify_fields(facts):
    locs = sorted(set(f.get('location', '') for f in facts
                      if f.get('location', '') and f.get('location') != '未知'))
    times = sorted(set(f.get('time', '') for f in facts
                       if f.get('time', '') and f.get('time') not in ('未知', '未知时间', '')))
    print(f'[{time.strftime("%H:%M")}] Classifying {len(locs)} locations, {len(times)} times')

    loc_map = {}
    for start in range(0, len(locs), 30):
        batch = locs[start:start + 30]
        prompt = '分类每个词: dynasty(朝代/政权/时期) | place(实体地点) | concept(抽象/建筑非地点)。返回JSON:{"词":"类别"}\n' + '\n'.join(batch)
        try:
            result = json.loads(llm(prompt, 1000))
            if isinstance(result, dict): loc_map.update(result)
        except: pass
        print(f'  loc {min(start + 30, len(locs))}/{len(locs)}', flush=True)

    time_map = {}
    compound = [t for t in times if '，' in t or ',' in t]
    for start in range(0, len(compound), 30):
        batch = compound[start:start + 30]
        prompt = '拆分复合时间。返回JSON:{"原值":{"time":"年份","dynasty":"朝代"}}\n' + '\n'.join(batch)
        try:
            result = json.loads(llm(prompt, 1000))
            if isinstance(result, dict): time_map.update(result)
        except: pass
        print(f'  time {min(start + 30, len(compound))}/{len(compound)}', flush=True)

    fix_count = 0
    for f in facts:
        loc = f.get('location', '')
        if loc in loc_map:
            cat = loc_map[loc]
            if cat == 'dynasty':
                f['dynasty'] = (f.get('dynasty', '') + ',' + loc).strip(',')
                f['location'] = ''; fix_count += 1
            elif cat == 'concept':
                f['location'] = ''; fix_count += 1
        t = f.get('time', '')
        if t in time_map:
            new = time_map[t]
            if new.get('time'): f['time'] = new['time']
            if new.get('dynasty'): f['dynasty'] = (f.get('dynasty', '') + ',' + new['dynasty']).strip(',')
            fix_count += 1
    print(f'[{time.strftime("%H:%M")}] Classified: {fix_count} fixes applied')
    return facts


# ====== 阶段3: 标准化 + 建链 ======
def build_memories(facts):
    memories = []
    for i, f in enumerate(facts):
        pid = f'MEM{10000 + i:06d}'
        c = f.get('content', '')
        pn = f.get('person', '') or '未知'
        loc = f.get('location', '') or ''
        t = f.get('time', '') or ''
        era = f.get('dynasty', '') or ''
        ep = f.get('event_type', '事件')
        memories.append({
            'memory_id': pid, 'category': 'knowledge', 'weight': 0.7,
            'person': {'name': pn.split(',')[0] if ',' in pn else pn, 'identity': ''},
            'location': {'city': loc.split(',')[0] if ',' in loc else loc, 'place': '', 'landmark': ''},
            'time': {'absolute': t, 'era': era, 'relative': '', 'fuzzy': ''},
            'event': {'type': 'event', 'product': ep[:30], 'action': c[:20]},
            'reasoning_chain': '', 'chain_position': 0, 'cluster_id': None,
            'decay': {'level': None, 'access_count': 0},
            'versions': [
                {'version_id': 'v1', 'style': '标准叙述', 'content': c},
                {'version_id': 'v2', 'style': '详细描述',
                 'content': f'{t}{"(" + era + ")" if era else ""} {pn}在{loc}{ep}：{c}'},
                {'version_id': 'v3', 'style': '口语化',
                 'content': f'据记载，{pn}：{t}，{c}'}
            ],
            'tags': ['knowledge', ep] if ep else ['knowledge'],
            'difficulty': '中等'
        })

    bp = defaultdict(list)
    for m in memories:
        pn = m['person']['name']
        if pn and pn != '未知': bp[pn].append(m)
    cid = 1
    for pn, ms in bp.items():
        if len(ms) >= 3:
            ch = f'CHAIN_{cid:05d}'
            for pos, m in enumerate(ms[:MAX_CHAIN_DEPTH]):
                m['reasoning_chain'] = ch; m['chain_position'] = pos + 1
            cid += 1
    n_chains = sum(1 for m in memories if m['reasoning_chain'])
    print(f'[{time.strftime("%H:%M")}] {len(memories)} mems, {n_chains} in chains')
    return memories


# ====== 阶段4: 生成查询 ======
def generate_queries(memories):
    queries = []
    with_time = [m for m in memories if m['time']['absolute'] and m['person']['name'] != '未知']
    for m in random.sample(with_time, min(QUERIES_PER_TYPE, len(with_time))):
        queries.append({
            'query_text': f'{m["time"]["absolute"]} {m["person"]["name"]}做了什么',
            'query_type': '时间检索', 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', '中等')})

    with_loc = [m for m in memories if m['location']['city']]
    for m in random.sample(with_loc, min(QUERIES_PER_TYPE, len(with_loc))):
        queries.append({
            'query_text': f'在{m["location"]["city"]}发生过什么',
            'query_type': '地点检索', 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', '中等')})

    with_person = [m for m in memories if m['person']['name'] != '未知']
    for m in random.sample(with_person, min(QUERIES_PER_TYPE, len(with_person))):
        queries.append({
            'query_text': f'{m["person"]["name"]}做了什么',
            'query_type': '人物检索', 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', '中等')})

    for m in random.sample(with_person, min(QUERIES_PER_TYPE, len(with_person))):
        queries.append({
            'query_text': f'{m["person"]["name"]}关于{m["event"]["product"]}有什么经历',
            'query_type': '事件检索', 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', '中等')})

    with_all = [m for m in memories if m['time']['absolute'] and m['person']['name'] != '未知' and m['location']['city']]
    for m in random.sample(with_all, min(QUERIES_PER_TYPE, len(with_all))):
        queries.append({
            'query_text': f'{m["time"]["absolute"]} {m["person"]["name"]}在{m["location"]["city"]}发生了什么',
            'query_type': '组合检索', 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', '中等')})

    cs = set()
    for m in memories:
        ch = m['reasoning_chain']
        if ch and ch not in cs:
            cs.add(ch)
            members = sorted([x for x in memories if x['reasoning_chain'] == ch], key=lambda x: x['chain_position'])
            if len(members) >= 3:
                queries.append({
                    'query_text': f'请梳理{members[0]["person"]["name"]}的完整经历脉络',
                    'query_type': '组合推理',
                    'expected_memory_ids': [x['memory_id'] for x in members],
                    'expected_answer': f'{members[0]["person"]["name"]}的经历脉络',
                    'difficulty': '中等'})

    random.shuffle(queries)
    tc = defaultdict(int)
    for q in queries: tc[q['query_type']] += 1
    print(f'[{time.strftime("%H:%M")}] Queries: {dict(tc)} total={len(queries)}')
    return queries


# ====== 阶段5: LLM预解析缓存 ======
def build_llm_cache(queries):
    cache = {}
    for start in range(0, len(queries), 15):
        batch = queries[start:start + 15]
        bq = '\n'.join(f'{i}: {q["query_text"]}' for i, q in enumerate(batch))
        prompt = '对每个查询解析为JSON。字段: person_name,location_city,event_product,time_start,dynasty_era。缺失字段省略。严格按序号:JSON格式每行。\n\n' + bq + '\n输出:\n0: {"person_name":"X"}\n1: {"location_city":"Y"}'
        try:
            c = llm(prompt, len(batch) * 80)
            import re
            for line in c.split('\n'):
                mm = re.match(r'(\d+):\s*(\{.+\})', line.strip())
                if mm:
                    idx = int(mm.group(1))
                    if idx < len(batch):
                        try: cache[batch[idx]['query_text']] = json.loads(mm.group(2))
                        except: pass
        except: pass
        if (start + 15) % 60 == 0:
            print(f'  cache {min(start + 15, len(queries))}/{len(queries)}', flush=True)
    print(f'[{time.strftime("%H:%M")}] Cache: {len(cache)}/{len(queries)} queries parsed')
    return cache


# ====== Main ======
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python knowledge_builder.py <文章目录> [输出.json] [--merge]")
        print("  --merge: 合并到已有数据库(增量)")
        sys.exit(1)

    src_dir = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else 'test_db_knowledge.json'
    merge = '--merge' in sys.argv

    if merge and os.path.exists(out_file):
        with open(out_file, encoding='utf-8') as f:
            d = json.load(f)
        old_mems = d.get('memories', []); old_queries = d.get('queries', [])
    else:
        old_mems = []; old_queries = []

    done_path = '_extract_done.txt'
    done_files = set()
    if os.path.exists(done_path):
        with open(done_path, encoding='utf-8') as f:
            done_files = set(f.read().splitlines())

    facts, done_files = extract_facts(src_dir, old_mems or [], done_files)
    facts = classify_fields(facts)

    with open('facts_all.json', 'w', encoding='utf-8') as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    with open(done_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(done_files)))

    memories = build_memories(facts)
    queries = generate_queries(memories)
    cache = build_llm_cache(queries)

    cache_path = os.path.join(os.path.dirname(out_file), '_parsed_text.json') if os.path.dirname(out_file) else '_parsed_text.json'
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

    out = {
        'generated': time.strftime('%Y-%m-%d %H:%M'),
        'source': os.path.basename(src_dir),
        'memories': memories, 'queries': queries,
        'total': len(memories)
    }
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n[{time.strftime("%H:%M")}] Done: {out_file} ({len(memories)} mems, {len(queries)} queries)')
