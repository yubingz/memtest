#!/usr/bin/env python3
"""
MemTest Knowledge Builder — 从任意中英文长文本生成评测数据库

输入: MD 文章目录 (经典书籍、知乎文章、百科等)
输出: 标准 MemTest JSON 评测数据库 (带 facts + chains + queries)

依赖: DeepSeek API (或其他 OpenAI-compatible API)

用法:
    python knowledge_builder.py ./my_books/ output.json
    python knowledge_builder.py ./my_books/ output.json --lang zh
    python knowledge_builder.py ./my_books/ output.json --lang en
    python knowledge_builder.py ./my_books/ output.json --merge  # 增量追加
    python knowledge_builder.py ./my_books/ output.json --lang en --merge

语料要求:
    - 格式: 仅支持 .md 文件 (其他格式需先转换)
    - 语言: 支持中文(zh)和英文(en)，可通过 --lang 指定，默认自动检测
    - 文件大小: 每个文件需 >= 500 字符 (过短跳过), 前 3000 字符参与提取
    - 长文本建议拆分为章节级 .md 文件, 每个文件 500-3000 字效果最佳
    - 目录名会作为分类标签使用

API 配置:
    在项目根目录或上级目录创建 .env 文件:
        echo "DEEPSEEK_API_KEY=sk-your-key-here" > .env
    也支持其他 OpenAI-compatible API, 修改 llm() 函数中的 endpoint 即可

流程:
    1. LLM 事实提取 (content/person/location/time/era/event_type)
    2. LLM 字段分类校验 (era vs location vs concept)
    3. 标准化 + 推理链构建
    4. 6 类均衡查询生成
    5. LLM 预解析缓存 (查询→结构化检索参数)

质量建议:
    - 叙事类文本 (小说、传记) 提取效果最好
    - 技术文档可用但 person/location 字段可能较少
    - 超长文件 (>3000字) 会截断, 建议拆分
    - 生成后建议人工抽查字段分类准确性
"""

import json, os, sys, time, random, re
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections import defaultdict

random.seed(42)

# ====== 配置 ======
BATCH = 3
QUERIES_PER_TYPE = 25
MAX_CHAIN_DEPTH = 6

# ====== 语言配置 ======
LANG_CONFIG = {
    'zh': {
        # 阶段1: 事实提取
        'extract_prompt': """从文本提取所有独立事实。严格遵守字段规则:

字段定义:
- content: 简洁事实陈述(15-40字)
- person: 人物姓名(非人物留空)
- location: 实体地理地点(城市/建筑/地区)。朝代/时期/政权名/概念词不要放这里！
- time: 具体时间(年份/日期)。朝代/时期放era字段！
- era: 朝代/时期/政权名(如东晋、西汉、战国、贞观年间)
- event_type: 事件类型简短标签

规则:
1. location只放实体地点(沧州、红岸基地、丞相府)，朝代(东晋、西汉)和概念(别墅、实验室)不放
2. era与time分开: "383年"→time, "东晋"→era, 不合并
3. 每人每事每地分别提取
4. 同一人物的连续事件按chain_id串联(position 1-6)
5. 输出纯JSON数组，每行一个对象

文本:
""",
        # 阶段2: 字段分类
        'classify_loc_prompt': '分类每个词: era(朝代/政权/时期) | place(实体地点) | concept(抽象/建筑非地点)。返回JSON:{"词":"类别"}\n',
        'classify_time_prompt': '拆分复合时间。返回JSON:{"原值":{"time":"年份","era":"朝代"}}\n',
        # 阶段3: 标准化
        'unknown_person': '未知',
        'default_event': '事件',
        'style_standard': '标准叙述',
        'style_detail': '详细描述',
        'style_colloquial': '口语化',
        'detail_template': '{time}{era_bracket} {person}在{location}{event_type}：{content}',
        'colloquial_template': '据记载，{person}：{time}，{content}',
        # 阶段4: 查询生成
        'query_time': '{time} {person}做了什么',
        'query_location': '在{location}发生过什么',
        'query_person': '{person}做了什么',
        'query_event': '{person}关于{event}有什么经历',
        'query_composite': '{time} {person}在{location}发生了什么',
        'query_chain': '请梳理{person}的完整经历脉络',
        'qtype_time': '时间检索',
        'qtype_location': '地点检索',
        'qtype_person': '人物检索',
        'qtype_event': '事件检索',
        'qtype_composite': '组合检索',
        'qtype_chain': '组合推理',
        'difficulty_medium': '中等',
        # 阶段5: 预解析
        'cache_prompt': '对每个查询解析为JSON。字段: person_name,location_city,event_product,time_start,era。缺失字段省略。严格按序号:JSON格式每行。\n\n',
    },
    'en': {
        # 阶段1: 事实提取
        'extract_prompt': """Extract all independent facts from the text. Strictly follow field rules:

Field definitions:
- content: concise fact statement (10-30 words)
- person: character/person name (leave empty for non-person entities)
- location: physical geographic location (city/building/region). Do NOT put era/period/concept here!
- time: specific time (year/date/season). Put era/period in the era field!
- era: historical era/period (e.g., Victorian era, Medieval period, 1990s, First Wizarding War)
- event_type: short event type label (e.g., discovery, battle, betrayal, learning, rescue)

Rules:
1. location only for physical places (Hogwarts, London, Ministry of Magic), NOT eras or concepts
2. era and time are separate: "1997" → time, "1990s" → era, do not merge
3. Extract each person/event/location separately
4. Chain consecutive events for the same character with chain_id (position 1-6)
5. Output pure JSON array, one object per line

Text:
""",
        # 阶段2: 字段分类
        'classify_loc_prompt': 'Classify each term: era(historical period/era) | place(physical location) | concept(abstract/non-location). Return JSON: {"term":"category"}\n',
        'classify_time_prompt': 'Split compound time expressions. Return JSON: {"original":{"time":"year/date","era":"period"}}\n',
        # 阶段3: 标准化
        'unknown_person': 'Unknown',
        'default_event': 'event',
        'style_standard': 'Standard',
        'style_detail': 'Detailed',
        'style_colloquial': 'Colloquial',
        'detail_template': '{time}{era_bracket} {person} at {location} — {event_type}: {content}',
        'colloquial_template': 'According to records, {person}: {time}, {content}',
        # 阶段4: 查询生成
        'query_time': 'What did {person} do in {time}?',
        'query_location': 'What happened at {location}?',
        'query_person': 'What did {person} do?',
        'query_event': "What was {person}'s involvement with {event}?",
        'query_composite': 'What happened with {person} at {location} in {time}?',
        'query_chain': "Trace {person}'s complete story arc",
        'qtype_time': 'Time Retrieval',
        'qtype_location': 'Location Retrieval',
        'qtype_person': 'Person Retrieval',
        'qtype_event': 'Event Retrieval',
        'qtype_composite': 'Composite Retrieval',
        'qtype_chain': 'Chain Reasoning',
        'difficulty_medium': 'Medium',
        # 阶段5: 预解析
        'cache_prompt': 'Parse each query into JSON. Fields: person_name, location_city, event_product, time_start, era. Omit missing fields. Strictly follow index number: JSON format per line.\n\n',
    }
}


def detect_lang(text):
    """检测文本语言：统计中文字符占比"""
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total = max(len(text), 1)
    return 'zh' if cn_chars / total > 0.1 else 'en'


# ====== API Key ======
KEY = ''
for p in [os.path.join(os.path.dirname(__file__) if os.path.dirname(__file__) else '.', '.env'),
          os.path.join(os.path.dirname(__file__) if os.path.dirname(__file__) else '.', '..', '.env'), '.env']:
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
def extract_facts(articles_dir, lang='auto', existing_facts=None, done_files=None):
    if existing_facts is None: existing_facts = []
    if done_files is None: done_files = set()

    todo = []
    for root, dirs, files in os.walk(articles_dir):
        for fn in files:
            if fn.endswith('.md') and fn not in done_files:
                todo.append((os.path.basename(root), os.path.join(root, fn)))

    if not todo:
        print(f'[{time.strftime("%H:%M")}] All files processed')
        return existing_facts, done_files, lang if lang != 'auto' else 'zh'

    # 自动检测语言：取第一个文件样本
    if lang == 'auto':
        sample_path = todo[0][1]
        with open(sample_path, encoding='utf-8') as fh:
            sample = fh.read(2000)
        lang = detect_lang(sample)
        print(f'[{time.strftime("%H:%M")}] Auto-detected language: {lang}')

    cfg = LANG_CONFIG[lang]
    extract_prompt = cfg['extract_prompt']

    print(f'[{time.strftime("%H:%M")}] {len(existing_facts)} existing, {len(todo)} files remaining, lang={lang}')

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
                c = llm(extract_prompt + t[:3000])
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

    return existing_facts, done_files, lang


# ====== 阶段2: 字段分类校验 ======
def classify_fields(facts, lang='zh'):
    cfg = LANG_CONFIG[lang]
    locs = sorted(set(f.get('location', '') for f in facts
                      if f.get('location', '') and f.get('location') not in ('未知', 'Unknown', '')))
    times = sorted(set(f.get('time', '') for f in facts
                       if f.get('time', '') and f.get('time') not in ('未知', '未知时间', 'Unknown', '')))
    print(f'[{time.strftime("%H:%M")}] Classifying {len(locs)} locations, {len(times)} times')

    loc_map = {}
    for start in range(0, len(locs), 30):
        batch = locs[start:start + 30]
        prompt = cfg['classify_loc_prompt'] + '\n'.join(batch)
        try:
            result = json.loads(llm(prompt, 1000))
            if isinstance(result, dict): loc_map.update(result)
        except: pass
        print(f'  loc {min(start + 30, len(locs))}/{len(locs)}', flush=True)

    time_map = {}
    sep = '，' if lang == 'zh' else ','
    compound = [t for t in times if sep in t]
    for start in range(0, len(compound), 30):
        batch = compound[start:start + 30]
        prompt = cfg['classify_time_prompt'] + '\n'.join(batch)
        try:
            result = json.loads(llm(prompt, 1000))
            if isinstance(result, dict): time_map.update(result)
        except: pass
        print(f'  time {min(start + 30, len(compound))}/{len(compound)}', flush=True)

    # era 字段名兼容：同时接受 dynasty 和 era
    era_key = 'era'
    fix_count = 0
    for f in facts:
        loc = f.get('location', '')
        if loc in loc_map:
            cat = loc_map[loc]
            if cat in ('dynasty', 'era'):
                f[era_key] = (f.get(era_key, '') or f.get('dynasty', '')) + ',' + loc
                f[era_key] = f[era_key].strip(',')
                f['location'] = ''; fix_count += 1
            elif cat == 'concept':
                f['location'] = ''; fix_count += 1
        t = f.get('time', '')
        if t in time_map:
            new = time_map[t]
            if new.get('time'): f['time'] = new['time']
            era_val = new.get('era') or new.get('dynasty', '')
            if era_val:
                f[era_key] = (f.get(era_key, '') or f.get('dynasty', '') + ',' + era_val).strip(',')
                fix_count += 1
        # 统一 era 字段：如果只有 dynasty 没有 era，迁移过来
        if 'dynasty' in f and era_key not in f:
            f[era_key] = f.pop('dynasty')
        elif 'dynasty' in f and era_key in f:
            # 合并
            combined = (f.get(era_key, '') + ',' + f.get('dynasty', '')).strip(',')
            f[era_key] = combined
            del f['dynasty']
    print(f'[{time.strftime("%H:%M")}] Classified: {fix_count} fixes applied')
    return facts


# ====== 阶段3: 标准化 + 建链 ======
def build_memories(facts, lang='zh'):
    cfg = LANG_CONFIG[lang]
    unknown = cfg['unknown_person']
    default_evt = cfg['default_event']
    memories = []
    for i, f in enumerate(facts):
        pid = f'MEM{10000 + i:06d}'
        c = f.get('content', '')
        pn = f.get('person', '') or unknown
        loc = f.get('location', '') or ''
        t = f.get('time', '') or ''
        era = f.get('era', '') or ''
        ep = f.get('event_type', default_evt)

        # 构建详细描述版本
        era_bracket = f'({era})' if era else ''
        detail = cfg['detail_template'].format(
            time=t, era_bracket=era_bracket, person=pn,
            location=loc, event_type=ep, content=c)
        colloquial = cfg['colloquial_template'].format(
            person=pn, time=t, content=c)

        memories.append({
            'memory_id': pid, 'category': 'knowledge', 'weight': 0.7,
            'person': {'name': pn.split(',')[0] if ',' in pn else pn, 'identity': ''},
            'location': {'city': loc.split(',')[0] if ',' in loc else loc, 'place': '', 'landmark': ''},
            'time': {'absolute': t, 'era': era, 'relative': '', 'fuzzy': ''},
            'event': {'type': 'event', 'product': ep[:30], 'action': c[:20]},
            'reasoning_chain': '', 'chain_position': 0, 'cluster_id': None,
            'decay': {'level': None, 'access_count': 0},
            'versions': [
                {'version_id': 'v1', 'style': cfg['style_standard'], 'content': c},
                {'version_id': 'v2', 'style': cfg['style_detail'], 'content': detail},
                {'version_id': 'v3', 'style': cfg['style_colloquial'], 'content': colloquial},
            ],
            'tags': ['knowledge', ep] if ep else ['knowledge'],
            'difficulty': cfg['difficulty_medium'],
            'lang': lang
        })

    bp = defaultdict(list)
    for m in memories:
        pn = m['person']['name']
        if pn and pn != unknown: bp[pn].append(m)
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
def generate_queries(memories, lang='zh'):
    cfg = LANG_CONFIG[lang]
    unknown = cfg['unknown_person']
    queries = []

    with_time = [m for m in memories if m['time']['absolute'] and m['person']['name'] != unknown]
    for m in random.sample(with_time, min(QUERIES_PER_TYPE, len(with_time))):
        queries.append({
            'query_text': cfg['query_time'].format(time=m['time']['absolute'], person=m['person']['name']),
            'query_type': cfg['qtype_time'], 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', cfg['difficulty_medium'])})

    with_loc = [m for m in memories if m['location']['city']]
    for m in random.sample(with_loc, min(QUERIES_PER_TYPE, len(with_loc))):
        queries.append({
            'query_text': cfg['query_location'].format(location=m['location']['city']),
            'query_type': cfg['qtype_location'], 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', cfg['difficulty_medium'])})

    with_person = [m for m in memories if m['person']['name'] != unknown]
    for m in random.sample(with_person, min(QUERIES_PER_TYPE, len(with_person))):
        queries.append({
            'query_text': cfg['query_person'].format(person=m['person']['name']),
            'query_type': cfg['qtype_person'], 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', cfg['difficulty_medium'])})

    for m in random.sample(with_person, min(QUERIES_PER_TYPE, len(with_person))):
        queries.append({
            'query_text': cfg['query_event'].format(person=m['person']['name'], event=m['event']['product']),
            'query_type': cfg['qtype_event'], 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', cfg['difficulty_medium'])})

    with_all = [m for m in memories if m['time']['absolute'] and m['person']['name'] != unknown and m['location']['city']]
    for m in random.sample(with_all, min(QUERIES_PER_TYPE, len(with_all))):
        queries.append({
            'query_text': cfg['query_composite'].format(time=m['time']['absolute'], person=m['person']['name'], location=m['location']['city']),
            'query_type': cfg['qtype_composite'], 'expected_memory_ids': [m['memory_id']],
            'expected_answer': m['versions'][0]['content'], 'difficulty': m.get('difficulty', cfg['difficulty_medium'])})

    cs = set()
    for m in memories:
        ch = m['reasoning_chain']
        if ch and ch not in cs:
            cs.add(ch)
            members = sorted([x for x in memories if x['reasoning_chain'] == ch], key=lambda x: x['chain_position'])
            if len(members) >= 3:
                queries.append({
                    'query_text': cfg['query_chain'].format(person=members[0]['person']['name']),
                    'query_type': cfg['qtype_chain'],
                    'expected_memory_ids': [x['memory_id'] for x in members],
                    'expected_answer': f"{members[0]['person']['name']}'s story arc",
                    'difficulty': cfg['difficulty_medium']})

    random.shuffle(queries)
    tc = defaultdict(int)
    for q in queries: tc[q['query_type']] += 1
    print(f'[{time.strftime("%H:%M")}] Queries: {dict(tc)} total={len(queries)}')
    return queries


# ====== 阶段5: LLM预解析缓存 ======
def build_llm_cache(queries, lang='zh'):
    cfg = LANG_CONFIG[lang]
    cache = {}
    for start in range(0, len(queries), 15):
        batch = queries[start:start + 15]
        bq = '\n'.join(f'{i}: {q["query_text"]}' for i, q in enumerate(batch))
        prompt = cfg['cache_prompt'] + bq + '\nOutput:\n0: {"person_name":"X"}\n1: {"location_city":"Y"}'
        try:
            c = llm(prompt, len(batch) * 80)
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
    import argparse
    parser = argparse.ArgumentParser(description='MemTest Knowledge Builder')
    parser.add_argument('source_dir', help='Corpus directory containing .md files')
    parser.add_argument('output', nargs='?', default='test_db_knowledge.json', help='Output JSON file')
    parser.add_argument('--lang', choices=['zh', 'en', 'auto'], default='auto',
                        help='Language: zh=Chinese, en=English, auto=auto-detect (default: auto)')
    parser.add_argument('--merge', action='store_true', help='Merge into existing database (incremental)')
    args = parser.parse_args()

    src_dir = args.source_dir
    out_file = args.output
    merge = args.merge
    lang = args.lang

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

    facts, done_files, resolved_lang = extract_facts(src_dir, lang=lang, existing_facts=old_mems or [], done_files=done_files)
    facts = classify_fields(facts, lang=resolved_lang)

    with open('facts_all.json', 'w', encoding='utf-8') as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    with open(done_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(done_files)))

    memories = build_memories(facts, lang=resolved_lang)
    queries = generate_queries(memories, lang=resolved_lang)
    cache = build_llm_cache(queries, lang=resolved_lang)

    cache_path = os.path.join(os.path.dirname(out_file), '_parsed_text.json') if os.path.dirname(out_file) else '_parsed_text.json'
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)

    out = {
        'generated': time.strftime('%Y-%m-%d %H:%M'),
        'source': os.path.basename(src_dir),
        'lang': resolved_lang,
        'memories': memories, 'queries': queries,
        'total': len(memories)
    }
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n[{time.strftime("%H:%M")}] Done: {out_file} ({len(memories)} mems, {len(queries)} queries, lang={resolved_lang})')
