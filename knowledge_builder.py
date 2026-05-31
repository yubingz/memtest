#!/usr/bin/env python3
"""MemTest Knowledge Builder — 从任意中文/英文长文本生成评测数据库

输入: MD 文章目录 (经典书籍、知乎文章、百科等)
输出: 标准 MemTest JSON 评测数据库 (带 facts + chains + queries)

依赖: LLM 接口 (llm_interface.py)，默认 DeepSeek，可替换为任意模型

用法:
    python knowledge_builder.py ./my_books/ output.json
    python knowledge_builder.py ./my_books/ output.json --merge   # 增量追加
    python knowledge_builder.py existing_db.json --clean           # 清洗已有数据库

流程:
    1. LLM 事实提取 (content/person/location/time/dynasty/event_type)
    2. LLM 字段分类校验 (dynasty vs location vs concept)
    3. 标准化 + 推理链构建
    4. 数据清洗 (去重 + 人物平衡 + 跨视角去重)
    5. 6 类均衡查询生成 + 人物平衡
    6. LLM 预解析缓存 (查询→结构化检索参数)
"""

import json, os, sys, time, random, re
from collections import defaultdict, Counter

# 导入统一 LLM 接口
try:
    from llm_interface import create_llm, LLMInterface
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from llm_interface import create_llm, LLMInterface

random.seed(42)

# ====== 配置 ======
BATCH = 3
QUERIES_PER_TYPE = 25
MAX_CHAIN_DEPTH = 6

# 相对时间词映射表（偏移天数）
RELATIVE_TIME_WORDS = {
    '次日': 1, '第二天': 1, '隔天': 1, '翌日': 1,
    '三天后': 3, '三日后': 3,
    '一周后': 7, '七天后': 7, '七日后': 7,
    '半个月后': 15, '半月后': 15,
    '一个月后': 30, '一月后': 30, '三十天后': 30,
    '两个月后': 60, '两月后': 60, '六十天后': 60,
    '三个月后': 90, '三月后': 90, '九十天后': 90,
    '半年后': 180, '六个月后': 180,
    '一年后': 365, '次年': 365, '第二年': 365,
    '两年后': 730, '二年后': 730,
    '三年后': 1095, '三年后': 1095,
    '十年后': 3650, '十年后': 3650,
    '许久之后': 9999, '很久以后': 9999, '之后': 1,
    '随后': 1, '接着': 1, '然后': 1, '后来': 1,
    '不久': 2, '几天后': 3, '几日后': 3,
}

# 清洗配置
PERSON_CAP_KEY = 60       # 关键人物每人物最多记忆条数
PERSON_CAP_OTHER = 30     # 非关键人物上限
QUERY_PERSON_CAP = 8      # 每人物最多查询条数
DEDUP_SIM_THRESHOLD = 0.6 # 跨视角去重相似度阈值 (0-1)


# ====== 加载提示词 ======
def _load_prompt(name: str) -> str:
    """从 prompts/ 目录加载提示词。"""
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
    return _INLINE_PROMPTS.get(name, "")


_INLINE_PROMPTS = {
    "fact_extract": """从文本提取所有独立事实。严格遵守字段规则:

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
""",
}


# ====== 安全 ======
def _safe_json_loads(raw, max_size=2*1024*1024):
    """Parse JSON with size guard to avoid DoS from huge payloads."""
    if isinstance(raw, str) and len(raw) > max_size:
        raise ValueError(f"JSON payload too large: {len(raw)} bytes > {max_size}")
    if isinstance(raw, bytes) and len(raw) > max_size:
        raise ValueError(f"JSON payload too large: {len(raw)} bytes > {max_size}")
    return json.loads(raw)

def _validate_corpus_dir(articles_dir):
    """Prevent path traversal via .. or symlinks outside the intended tree."""
    abs_dir = os.path.realpath(os.path.abspath(articles_dir))
    blocked_prefixes = ['/etc', '/usr', '/bin', '/sbin', '/lib', '/dev', '/proc', '/sys', '/root']
    for prefix in blocked_prefixes:
        if abs_dir.startswith(prefix + os.sep) or abs_dir == prefix:
            raise ValueError(f"Corpus directory points to a system path: {abs_dir}")
    return abs_dir


# ====== LLM 接口实例 ======
_llm_instance = None

def get_llm() -> LLMInterface:
    """获取或创建 LLM 实例（单例）。"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = create_llm("deepseek")
    return _llm_instance

def llm(prompt: str, max_tokens: int = 3000) -> str:
    """向后兼容的 LLM 调用函数，内部使用统一接口。"""
    return get_llm().generate(prompt, max_tokens=max_tokens, temperature=0)

def llm_json(prompt: str, max_tokens: int = 3000) -> dict:
    """调用 LLM 并解析为 JSON。"""
    return get_llm().generate_json(prompt, max_tokens=max_tokens, temperature=0)


# ====== 阶段1: 事实提取 ======
EXTRACT_PROMPT = _load_prompt("fact_extract")


def extract_facts(articles_dir, existing_facts=None, done_files=None):
    if existing_facts is None: existing_facts = []
    if done_files is None: done_files = set()

    abs_dir = _validate_corpus_dir(articles_dir)
    todo = []
    for root, dirs, files in os.walk(abs_dir):
        # Security: skip symlinks that point outside the validated tree
        if os.path.islink(root) and not os.path.realpath(root).startswith(abs_dir + os.sep):
            continue
        for fn in files:
            if fn.endswith('.md') and fn not in done_files:
                todo.append((os.path.basename(root), os.path.join(root, fn)))

    if not todo:
        print(f'[{time.strftime("%H:%M")}] All files processed')
        return existing_facts, done_files

    print(f'[{time.strftime("%H:%M")}] {len(existing_facts)} existing, {len(todo)} files remaining')

    for bi in range(0, len(todo), BATCH):
        batch = todo[bi:bi + BATCH]
        
        # 批量读取文章内容
        batch_contents = []
        batch_meta = []
        for dname, path in batch:
            fn = os.path.basename(path)
            with open(path, encoding='utf-8') as fh:
                t = fh.read()
            if t.startswith('---'):
                idx = t.find('---', 3)
                if idx > 0: t = t[idx + 3:]
            if len(t) < 500: 
                continue
            batch_contents.append(t[:3000])
            batch_meta.append((dname, fn))
        
        if not batch_contents:
            continue
        
        # 批量LLM调用：一次处理多篇文章
        if len(batch_contents) == 1:
            # 单篇文章：直接调用（保持兼容性）
            prompts = [EXTRACT_PROMPT + batch_contents[0]]
        else:
            # 多篇文章：构建批量提示词
            prompts = []
            for idx, content in enumerate(batch_contents):
                prompts.append(f"""=== 文章{idx+1} ===
{EXTRACT_PROMPT}
{content}
""")
        
        try:
            # 使用batch_generate批量处理
            if len(prompts) == 1:
                results = [llm(prompts[0], 3000)]
            else:
                # 尝试使用batch_generate，如果不可用则逐条调用
                llm_inst = get_llm()
                if hasattr(llm_inst, 'batch_generate'):
                    results = llm_inst.batch_generate(prompts, max_tokens=3000, temperature=0)
                else:
                    results = [llm_inst.generate(p, max_tokens=3000, temperature=0) for p in prompts]
            
            # 解析每篇文章的结果
            for idx, (c, (dname, fn)) in enumerate(zip(results, batch_meta)):
                n = 0
                try:
                    arr = _safe_json_loads(c)
                    if isinstance(arr, list):
                        for item in arr:
                            if isinstance(item, dict):
                                # 标记来源文章
                                item['_source'] = f"{dname}/{fn}"
                                existing_facts.append(item); n += 1
                except (json.JSONDecodeError, ValueError):
                    for l in c.split('\n'):
                        l = l.strip().rstrip(',')
                        if l.startswith('{') and l.endswith('}'):
                            try:
                                fact = _safe_json_loads(l)
                                fact['_source'] = f"{dname}/{fn}"
                                existing_facts.append(fact)
                                n += 1
                            except (json.JSONDecodeError, ValueError):
                                pass
                print(f'  [{time.strftime("%H:%M")}] +{n:4d} | {dname}/{fn[:35]}', flush=True)
                done_files.add(fn)
        except Exception as e:
            # 批量失败时，逐条重试
            print(f'  [{time.strftime("%H:%M")}] Batch failed ({type(e).__name__}), retrying individually...', flush=True)
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
                        arr = _safe_json_loads(c)
                        if isinstance(arr, list):
                            for item in arr:
                                if isinstance(item, dict):
                                    item['_source'] = f"{dname}/{fn}"
                                    existing_facts.append(item); n += 1
                    except (json.JSONDecodeError, ValueError):
                        for l in c.split('\n'):
                            l = l.strip().rstrip(',')
                            if l.startswith('{') and l.endswith('}'):
                                try:
                                    fact = _safe_json_loads(l)
                                    fact['_source'] = f"{dname}/{fn}"
                                    existing_facts.append(fact)
                                    n += 1
                                except (json.JSONDecodeError, ValueError):
                                    pass
                    print(f'  [{time.strftime("%H:%M")}] +{n:4d} | {dname}/{fn[:35]} (retry)', flush=True)
                    done_files.add(fn)
                except Exception as e2:
                    print(f'  [{time.strftime("%H:%M")}] {type(e2).__name__} | {dname}/{fn[:35]}', flush=True)

    return existing_facts, done_files


# ====== 阶段2: 字段分类校验 ======
def classify_fields(facts):
    """字段分类校验 — 批量LLM处理。

    优化：使用batch_generate并行处理多个批次，而非逐条调用。
    """
    locs = sorted(set(f.get('location', '') for f in facts
                      if f.get('location', '') and f.get('location') != '未知'))
    times = sorted(set(f.get('time', '') for f in facts
                       if f.get('time', '') and f.get('time') not in ('未知', '未知时间', '')))
    print(f'[{time.strftime("%H:%M")}] Classifying {len(locs)} locations, {len(times)} times')

    # 批量处理location分类
    loc_map = {}
    loc_batches = [locs[i:i+30] for i in range(0, len(locs), 30)]
    if loc_batches:
        loc_prompts = []
        for batch in loc_batches:
            prompt = '分类每个词: dynasty(朝代/政权/时期) | place(实体地点) | concept(抽象/建筑非地点)。返回JSON:{"词":"类别"}\n' + '\n'.join(batch)
            loc_prompts.append(prompt)
        
        try:
            llm_inst = get_llm()
            if hasattr(llm_inst, 'batch_generate') and len(loc_prompts) > 1:
                loc_results = llm_inst.batch_generate(loc_prompts, max_tokens=1000, temperature=0)
            else:
                loc_results = [llm_inst.generate(p, max_tokens=1000, temperature=0) for p in loc_prompts]
            
            for result in loc_results:
                try:
                    parsed = _safe_json_loads(result)
                    if isinstance(parsed, dict): loc_map.update(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
        except Exception as e:
            print(f'  [{time.strftime("%H:%M")}] Location batch failed: {type(e).__name__}, falling back...', flush=True)
            # Fallback to individual calls
            for batch in loc_batches:
                prompt = '分类每个词: dynasty(朝代/政权/时期) | place(实体地点) | concept(抽象/建筑非地点)。返回JSON:{"词":"类别"}\n' + '\n'.join(batch)
                try:
                    result = _safe_json_loads(llm(prompt, 1000))
                    if isinstance(result, dict): loc_map.update(result)
                except (json.JSONDecodeError, ValueError):
                    pass
        print(f'  [{time.strftime("%H:%M")}] Locations classified: {len(loc_map)}/{len(locs)}', flush=True)

    # 批量处理time拆分
    time_map = {}
    compound = [t for t in times if '，' in t or ',' in t]
    time_batches = [compound[i:i+30] for i in range(0, len(compound), 30)]
    if time_batches:
        time_prompts = []
        for batch in time_batches:
            prompt = '拆分复合时间。返回JSON:{"原值":{"time":"年份","dynasty":"朝代"}}\n' + '\n'.join(batch)
            time_prompts.append(prompt)
        
        try:
            llm_inst = get_llm()
            if hasattr(llm_inst, 'batch_generate') and len(time_prompts) > 1:
                time_results = llm_inst.batch_generate(time_prompts, max_tokens=1000, temperature=0)
            else:
                time_results = [llm_inst.generate(p, max_tokens=1000, temperature=0) for p in time_prompts]
            
            for result in time_results:
                try:
                    parsed = _safe_json_loads(result)
                    if isinstance(parsed, dict): time_map.update(parsed)
                except (json.JSONDecodeError, ValueError):
                    pass
        except Exception as e:
            print(f'  [{time.strftime("%H:%M")}] Time batch failed: {type(e).__name__}, falling back...', flush=True)
            for batch in time_batches:
                prompt = '拆分复合时间。返回JSON:{"原值":{"time":"年份","dynasty":"朝代"}}\n' + '\n'.join(batch)
                try:
                    result = _safe_json_loads(llm(prompt, 1000))
                    if isinstance(result, dict): time_map.update(result)
                except (json.JSONDecodeError, ValueError):
                    pass
        print(f'  [{time.strftime("%H:%M")}] Times classified: {len(time_map)}/{len(compound)}', flush=True)

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


def _extract_relative_time(content):
    """从文本中提取相对时间词，返回偏移天数（相对于前一件事）
    如果没有匹配到，返回None
    """
    if not content:
        return None
    for word, offset in RELATIVE_TIME_WORDS.items():
        if word in content:
            return offset
    return None


def _parse_time_to_int(time_str):
    """将时间字符串解析为可排序的整数（简单版本）
    支持：YYYY, YYYY-MM, YYYY-MM-DD, 或纯数字
    """
    if not time_str:
        return 0
    # 提取数字
    digits = re.findall(r'\d+', time_str)
    if not digits:
        return 0
    # 取第一个数字组，填充为 YYYYMMDD 格式
    t = digits[0]
    if len(t) == 4:  # 年份
        return int(t) * 10000
    elif len(t) == 6:  # 年月
        return int(t) * 100
    elif len(t) == 8:  # 年月日
        return int(t)
    elif len(t) == 12:  # 年月日时分
        return int(t[:8])
    elif len(t) == 14:  # 年月日时分秒
        return int(t[:8])
    else:
        return int(t)


def _sort_chain_by_time(memories):
    """按时间排序chain中的记忆。支持绝对时间+相对时间混合。

    排序策略（优先级）：
    1. 有绝对时间：按绝对时间排序
    2. 无绝对时间但有相对时间：按相对时间偏移累计排序
    3. 两者都有：用相对时间校准绝对时间（如果矛盾，以相对时间偏移为主）
    """
    if not memories:
        return memories

    # 第一步：提取每个记忆的时间信息
    items = []
    for m in memories:
        abs_time = m['time'].get('absolute', '') or ''
        rel_offset = _extract_relative_time(m['versions'][0].get('content', ''))
        items.append({
            'memory': m,
            'abs_time': abs_time,
            'abs_int': _parse_time_to_int(abs_time),
            'rel_offset': rel_offset,
        })

    # 第二步：判断哪种排序策略
    has_abs = sum(1 for it in items if it['abs_int'] > 0)
    has_rel = sum(1 for it in items if it['rel_offset'] is not None)

    if has_abs >= 2 and has_rel >= 2:
        # 两者都有：以绝对时间为主排序，相对时间保留但不干预排序
        # 矛盾检测由被测记忆系统自行判断
        items_sorted = sorted(items, key=lambda x: x['abs_int'])
        return [it['memory'] for it in items_sorted]

    elif has_abs >= 2:
        # 只有绝对时间：直接排序
        items_sorted = sorted(items, key=lambda x: x['abs_int'])
        return [it['memory'] for it in items_sorted]

    elif has_rel >= 2:
        # 只有相对时间：按相对偏移排序（累计）
        # 相对时间是相对于前一件事的偏移，所以原顺序就是时序
        # 如果LLM给了chain_position，优先用那个
        has_chain_pos = any(it['memory'].get('chain_position', 0) for it in items)
        if has_chain_pos:
            items_sorted = sorted(items, key=lambda x: x['memory'].get('chain_position', 0) or 0)
        else:
            # 按相对偏移排序（简单方式：偏移小的在前）
            items_sorted = sorted(items, key=lambda x: x['rel_offset'] or 0)
        return [it['memory'] for it in items_sorted]

    else:
        # 没有时间信息：保持原顺序或按chain_position
        has_chain_pos = any(it['memory'].get('chain_position', 0) for it in items)
        if has_chain_pos:
            items_sorted = sorted(items, key=lambda x: x['memory'].get('chain_position', 0) or 0)
        else:
            items_sorted = items
        return [it['memory'] for it in items_sorted]


# ====== 阶段3: 标准化 + 建链 ======
def build_memories(facts):
    """标准化事实为记忆 + 构建推理链。

    链构建策略（优先级）：
    1. LLM提取的chain_id：如果事实包含chain_id，按chain_id分组构建链
    2. 人物分组：chain_id为空时，按人物分组构建链（3条以上）
    """
    memories = []
    for i, f in enumerate(facts):
        pid = f'MEM{10000 + i:06d}'
        c = f.get('content', '')
        pn = f.get('person', '') or '未知'
        loc = f.get('location', '') or ''
        t = f.get('time', '') or ''
        era = f.get('dynasty', '') or ''
        ep = f.get('event_type', '事件')
        chain_id = f.get('chain_id', '')  # LLM提取的链ID
        chain_pos = f.get('chain_position', 0)  # LLM提取的位置
        memories.append({
            'memory_id': pid, 'category': 'knowledge', 'weight': 0.7,
            'person': {'name': pn.split(',')[0] if ',' in pn else pn, 'identity': ''},
            'location': {'city': loc.split(',')[0] if ',' in loc else loc, 'place': '', 'landmark': ''},
            'time': {'absolute': t, 'era': era, 'relative': '', 'fuzzy': ''},
            'event': {'type': 'event', 'product': ep[:30], 'action': c[:20]},
            'chain_id': chain_id,  # 保留原始chain_id用于调试
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

    # 链构建策略1：优先使用LLM提取的chain_id
    chain_groups = defaultdict(list)
    unchained = []  # 没有chain_id的记忆
    for m in memories:
        cid = m.get('chain_id', '')
        if cid:
            chain_groups[cid].append(m)
        else:
            unchained.append(m)

    # 处理LLM链：按chain_id分组，每组最多MAX_CHAIN_DEPTH条
    cid = 1
    for ch_id, ms in chain_groups.items():
        if len(ms) >= 2:  # 至少2条才算链
            ch = f'CHAIN_{cid:05d}'
            # 使用混合时间排序（支持绝对时间+相对时间）
            ms_sorted = _sort_chain_by_time(ms)[:MAX_CHAIN_DEPTH]
            for pos, m in enumerate(ms_sorted):
                m['reasoning_chain'] = ch
                m['chain_position'] = pos + 1
                # 设置链连接
                m['chain_hop'] = pos + 1
                m['chain_total'] = min(len(ms), MAX_CHAIN_DEPTH)
                # 设置链关系类型
                m['chain_relation'] = '时序' if any(it['time']['absolute'] for it in ms_sorted) else '因果'
            cid += 1

    # 链构建策略2：无chain_id的记忆，按人物分组
    bp = defaultdict(list)
    for m in unchained:
        pn = m['person']['name']
        if pn and pn != '未知': bp[pn].append(m)
    for pn, ms in bp.items():
        if len(ms) >= 3:
            ch = f'CHAIN_{cid:05d}'
            # 使用混合时间排序
            ms_sorted = _sort_chain_by_time(ms)[:MAX_CHAIN_DEPTH]
            for pos, m in enumerate(ms_sorted):
                m['reasoning_chain'] = ch
                m['chain_position'] = pos + 1
                m['chain_hop'] = pos + 1
                m['chain_total'] = min(len(ms), MAX_CHAIN_DEPTH)
                m['chain_relation'] = '时序' if any(it['time']['absolute'] for it in ms_sorted) else '关联'
            cid += 1

    # 设置链连接（prev/next）
    chain_map = defaultdict(list)
    for m in memories:
        ch = m.get('reasoning_chain', '')
        if ch:
            chain_map[ch].append(m)
    for ch, ms in chain_map.items():
        ms_sorted = sorted(ms, key=lambda x: x['chain_position'])
        for i, m in enumerate(ms_sorted):
            m['chain_prev'] = ms_sorted[i-1]['memory_id'] if i > 0 else ''
            m['chain_next'] = ms_sorted[i+1]['memory_id'] if i < len(ms_sorted) - 1 else ''

    n_llm_chains = sum(1 for m in memories if m.get('chain_id') and m.get('reasoning_chain'))
    n_person_chains = sum(1 for m in memories if m.get('reasoning_chain') and not m.get('chain_id'))
    print(f'[{time.strftime("%H:%M")}] {len(memories)} mems, chains: {n_llm_chains}(LLM) + {n_person_chains}(person) = {n_llm_chains + n_person_chains}')
    return memories


# ====== 阶段4: 数据清洗 ======
def _get_content_field(mem):
    """从不同格式的记忆中提取content文本"""
    if 'content' in mem and isinstance(mem['content'], str):
        return mem['content']
    if 'versions' in mem and isinstance(mem['versions'], list) and mem['versions']:
        return mem['versions'][0].get('content', '')
    return ''


def _get_person_field(mem):
    """从不同格式的记忆中提取person名称"""
    if 'person' in mem:
        if isinstance(mem['person'], dict):
            return mem['person'].get('name', '')
        return mem['person']
    return ''


def _content_similarity(c1, c2):
    """基于关键词Jaccard相似度，忽略通用词。支持中英文混合文本。"""
    generic_en = {'that','this','with','from','they','were','been','have','their','them',
                  'about','would','could','should','when','where','what','which','while',
                  'after','before','during','between','through','around','another','other',
                  'than','some','into','also','very','just','even','still','only','once',
                  'back','over','down','upon','such'}
    generic_cn = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
    
    # 英文词提取（4字母以上）
    w1_en = set(re.findall(r'[a-z]{4,}', c1.lower())) - generic_en
    w2_en = set(re.findall(r'[a-z]{4,}', c2.lower())) - generic_en
    
    # 中文词提取（连续2-6个汉字作为词）
    w1_cn = set(re.findall(r'[\u4e00-\u9fff]{2,6}', c1)) - generic_cn
    w2_cn = set(re.findall(r'[\u4e00-\u9fff]{2,6}', c2)) - generic_cn
    
    w1 = w1_en | w1_cn
    w2 = w2_en | w2_cn
    
    if not w1 or not w2:
        return 0
    return len(w1 & w2) / len(w1 | w2)


def _select_diverse(mems, cap):
    """按event_type+book分层采样，保证多样性"""
    if len(mems) <= cap:
        return mems
    groups = defaultdict(list)
    for m in mems:
        et = m.get('event_type', m.get('event', {}).get('product', 'narrative'))
        book = m.get('book', m.get('time', {}).get('era', 'unknown'))
        groups[f"{et}|{book}"].append(m)
    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]))
    selected = []
    for key, group in sorted_groups:
        selected.append(group[0])
    remaining = cap - len(selected)
    if remaining <= 0:
        return selected[:cap]
    random.seed(42)
    leftovers = []
    for key, group in sorted_groups:
        leftovers.extend(group[1:])
    random.shuffle(leftovers)
    selected.extend(leftovers[:remaining])
    return selected[:cap]


def deduplicate_memories(memories):
    """
    三步去重:
    1. 完全重复: content完全相同则去重
    2. 跨视角重复: 不同人物描述同一事件，关键词重叠>阈值则合并
    3. 人物平衡: 每人物记忆上限，超出部分按多样性采样

    Returns: (cleaned_memories, stats_dict)
    """
    stats = {'original': len(memories), 'exact_dup': 0, 'cross_person_dup': 0, 'person_capped': 0}

    # Step 1: 去完全重复
    seen = {}
    deduped = []
    for m in memories:
        content = _get_content_field(m).strip().lower()
        if content not in seen:
            seen[content] = m
            deduped.append(m)
        else:
            stats['exact_dup'] += 1

    # Step 2: 跨视角去重 (不同人物描述同一事件)
    # 按 event_type 分组，组内检测不同人物的高重叠记忆
    groups = defaultdict(list)
    for m in deduped:
        et = m.get('event_type', m.get('event', {}).get('product', ''))
        book = m.get('book', '')
        groups[f"{book}|{et}"].append(m)

    marked_remove = set()
    for gkey, mems in groups.items():
        # 用union-find聚类
        parent = list(range(len(mems)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb: parent[ra] = rb

        for i in range(len(mems)):
            for j in range(i + 1, len(mems)):
                # 同一人物不判跨视角重复
                if _get_person_field(mems[i]) == _get_person_field(mems[j]):
                    continue
                sim = _content_similarity(
                    _get_content_field(mems[i]),
                    _get_content_field(mems[j])
                )
                if sim > DEDUP_SIM_THRESHOLD:
                    union(i, j)

        # 每个连通分量保留最详细的1条
        clusters = defaultdict(list)
        for i in range(len(mems)):
            clusters[find(i)].append(i)

        for root, indices in clusters.items():
            if len(indices) > 1:
                best = max(indices, key=lambda i: len(_get_content_field(mems[i])))
                for i in indices:
                    if i != best:
                        marked_remove.add(id(mems[i]))
                        stats['cross_person_dup'] += 1

    deduped = [m for m in deduped if id(m) not in marked_remove]

    # Step 3: 人物平衡
    person_mems = defaultdict(list)
    for m in deduped:
        person_mems[_get_person_field(m)].append(m)

    # 识别关键人物 (记忆数量前20%的人物)
    counts = sorted(len(ms) for ms in person_mems.values())
    threshold = counts[int(len(counts) * 0.8)] if counts else 0
    key_persons = {p for p, ms in person_mems.items() if len(ms) >= threshold}

    balanced = []
    for person, ms in person_mems.items():
        cap = PERSON_CAP_KEY if person in key_persons else PERSON_CAP_OTHER
        if len(ms) <= cap:
            balanced.extend(ms)
        else:
            balanced.extend(_select_diverse(ms, cap))
            stats['person_capped'] += len(ms) - cap

    stats['final'] = len(balanced)
    print(f'[{time.strftime("%H:%M")}] Cleaned: {stats["original"]} → {stats["final"]} '
          f'(exact_dup={stats["exact_dup"]}, cross_dup={stats["cross_person_dup"]}, '
          f'capped={stats["person_capped"]})')
    return balanced, stats


# ====== 阶段5: 生成查询 ======
def _format_answer_structured_kb(m: dict) -> dict:
    """将记忆格式化为结构化答案（knowledge_builder 版）。"""
    return {
        "person": m.get('person', {}).get('name', ''),
        "location": f"{m.get('location', {}).get('city', '')}{m.get('location', {}).get('place', '')}",
        "action": m.get('event', {}).get('action', ''),
        "product": m.get('event', {}).get('product', ''),
        "time": m.get('time', {}).get('absolute', m.get('time', {}).get('relative', ''))
    }


def _format_answer_text_kb(m: dict) -> str:
    """格式化答案为字段化文本（knowledge_builder 版）。"""
    person = m.get('person', {}).get('name', '')
    city = m.get('location', {}).get('city', '')
    place = m.get('location', {}).get('place', '')
    action = m.get('event', {}).get('action', '')
    product = m.get('event', {}).get('product', '')
    time = m.get('time', {}).get('absolute', m.get('time', {}).get('relative', ''))
    return f"人物：{person}，地点：{city}{place}，动作：{action}，对象：{product}，时间：{time}"


def generate_queries(memories):
    """生成查询（含20%负样本）。

    正样本：5类查询 + 链式查询
    负样本：人物不存在/地点不存在/事件不存在/组合矛盾
    """
    queries = []
    # 收集所有实体用于负样本构造
    all_persons = list(set(m['person']['name'] for m in memories if m['person']['name'] != '未知'))
    all_cities = list(set(m['location']['city'] for m in memories if m['location']['city']))
    all_products = list(set(m['event']['product'] for m in memories if m['event']['product']))
    all_eras = list(set(m['time'].get('era', '') for m in memories if m['time'].get('era', '')))
    
    # 用于生成负样本的假实体池
    fake_persons = ['赵钱孙', '周吴郑', '冯陈褚', '卫蒋沈', '韩杨朱', '秦尤许', '何吕施', '张孔曹', '严华金', '魏陶姜', '戚谢邹', '喻柏水', '窦章云', '苏潘葛', '范彭郎', '鲁韦昌', '马苗凤', '花方俞', '任袁柳', '酆鲍史']
    fake_cities = ['火星', '月球', '水星', '金星', '木星', '土星', '冥王星', '开普勒', '比邻星', '泰坦星', '谷神星', '妊神星', '鸟神星', '阋神星', '齐娜星']
    fake_events = ['时光旅行', '量子跃迁', '黑洞探索', '星际战争', '外星殖民', '维度穿越', '时空折叠', '虫洞穿越', '超光速飞行', '暗物质研究', '反物质引擎', '引力波通讯', '戴森球建设', '基因飞升', '机械飞升']

    # ===== 正样本查询 =====
    # 按评测维度平衡：精确检索、组合检索、时序推理、因果推理、负样本
    # 计算各类记忆数量，按比例分配查询配额
    n_memories = len(memories)
    dim_quotas = {
        '精确检索': max(3, int(n_memories * 0.15)),
        '组合检索': max(3, int(n_memories * 0.15)),
        '时序推理': max(3, int(n_memories * 0.10)),
        '因果推理': max(3, int(n_memories * 0.10)),
        '对比推理': max(2, int(n_memories * 0.05)),
        '包含推理': max(2, int(n_memories * 0.05)),
        '推导推理': max(2, int(n_memories * 0.05)),
        '聚类检索': max(2, int(n_memories * 0.05)),
        '跨版本': max(2, int(n_memories * 0.03)),
    }
    
    # 精确检索：人物/地点/事件（用相对时间或自然表达，不用时间戳原文）
    with_time = [m for m in memories if m['time']['absolute'] and m['person']['name'] != '未知']
    for i, m in enumerate(random.sample(with_time, min(dim_quotas['精确检索'], len(with_time)))):
        queries.append({
            'query_id': f'Q{len(queries)+1:04d}',
            'query_text': f'{m["time"]["relative"] or "那天"} {m["person"]["name"]}做了什么',
            'query_type': '时间检索',
            'test_dimension': '精确检索',
            'expected_memory_ids': [m['memory_id']],
            'expected_answer': _format_answer_structured_kb(m),
            'expected_answer_text': _format_answer_text_kb(m),
            'acceptable_answers': [v['content'] for v in m.get('versions', [])],
            'expected_time': m['time']['absolute'],
            'difficulty': m.get('difficulty', '中等')})

    with_loc = [m for m in memories if m['location']['city']]
    for i, m in enumerate(random.sample(with_loc, min(dim_quotas['精确检索'], len(with_loc)))):
        queries.append({
            'query_id': f'Q{len(queries)+1:04d}',
            'query_text': f'在{m["location"]["city"]}发生过什么',
            'query_type': '地点检索',
            'test_dimension': '精确检索',
            'expected_memory_ids': [m['memory_id']],
            'expected_answer': _format_answer_structured_kb(m),
            'expected_answer_text': _format_answer_text_kb(m),
            'acceptable_answers': [v['content'] for v in m.get('versions', [])],
            'expected_time': m['time']['absolute'],
            'difficulty': m.get('difficulty', '中等')})

    with_person = [m for m in memories if m['person']['name'] != '未知']
    for i, m in enumerate(random.sample(with_person, min(dim_quotas['精确检索'], len(with_person)))):
        queries.append({
            'query_id': f'Q{len(queries)+1:04d}',
            'query_text': f'{m["person"]["name"]}做了什么',
            'query_type': '人物检索',
            'test_dimension': '精确检索',
            'expected_memory_ids': [m['memory_id']],
            'expected_answer': _format_answer_structured_kb(m),
            'expected_answer_text': _format_answer_text_kb(m),
            'acceptable_answers': [v['content'] for v in m.get('versions', [])],
            'expected_time': m['time']['absolute'],
            'difficulty': m.get('difficulty', '中等')})

    for i, m in enumerate(random.sample(with_person, min(dim_quotas['精确检索'], len(with_person)))):
        queries.append({
            'query_id': f'Q{len(queries)+1:04d}',
            'query_text': f'{m["person"]["name"]}关于{m["event"]["product"]}有什么经历',
            'query_type': '事件检索',
            'test_dimension': '精确检索',
            'expected_memory_ids': [m['memory_id']],
            'expected_answer': _format_answer_structured_kb(m),
            'expected_answer_text': _format_answer_text_kb(m),
            'acceptable_answers': [v['content'] for v in m.get('versions', [])],
            'expected_time': m['time']['absolute'],
            'difficulty': m.get('difficulty', '中等')})

    # 组合检索
    with_all = [m for m in memories if m['time']['absolute'] and m['person']['name'] != '未知' and m['location']['city']]
    for i, m in enumerate(random.sample(with_all, min(dim_quotas['组合检索'], len(with_all)))):
        queries.append({
            'query_id': f'Q{len(queries)+1:04d}',
            'query_text': f'{m["time"]["relative"] or "那天"} {m["person"]["name"]}在{m["location"]["city"]}发生了什么',
            'query_type': '组合检索',
            'test_dimension': '组合检索',
            'expected_memory_ids': [m['memory_id']],
            'expected_answer': _format_answer_structured_kb(m),
            'expected_answer_text': _format_answer_text_kb(m),
            'acceptable_answers': [v['content'] for v in m.get('versions', [])],
            'expected_time': m['time']['absolute'],
            'difficulty': m.get('difficulty', '中等')})

    # 链式查询（按维度分类）
    cs = set()
    chain_idx = 0
    for m in memories:
        ch = m.get('reasoning_chain', '')
        if ch and ch not in cs:
            cs.add(ch)
            members = sorted([x for x in memories if x['reasoning_chain'] == ch], key=lambda x: x['chain_position'])
            if len(members) >= 3:
                chain_idx += 1
                # 判断链类型
                chain_relation = members[0].get('chain_relation', '')
                if chain_relation == '时序':
                    test_dim = '时序推理'
                elif chain_relation == '因果':
                    test_dim = '因果推理'
                elif chain_relation == '对比':
                    test_dim = '对比推理'
                elif chain_relation == '包含':
                    test_dim = '包含推理'
                elif chain_relation == '推导':
                    test_dim = '推导推理'
                else:
                    test_dim = '组合推理'
                
                # 多跳链式查询，根据链类型生成不同模板
                if len(members) >= 2:
                    # 按 chain_relation 选择多跳模板
                    cr = chain_relation or '关联'
                    if cr == '时序':
                        # 时序链：问"之后发生了什么"
                        if len(members) >= 3:
                            mid = len(members) // 2
                            mid_mem = members[mid]
                            prev_mem = members[mid - 1] if mid > 0 else members[0]
                            qtext = f'在{prev_mem["person"]["name"]}{prev_mem["event"]["action"]}了{prev_mem["event"]["product"]}之后，{mid_mem["person"]["name"]}又做了什么？'
                        else:
                            qtext = f'请梳理{members[0]["person"]["name"]}的完整时间线'
                    elif cr == '因果':
                        # 因果链：问"为什么/导致什么"
                        if len(members) >= 3:
                            cause_mem = members[0]
                            effect_mem = members[1]
                            qtext = f'因为{cause_mem["person"]["name"]}{cause_mem["event"]["action"]}了{cause_mem["event"]["product"]}，后面导致{effect_mem["person"]["name"]}做了什么？'
                        else:
                            qtext = f'{members[0]["person"]["name"]}的{m["event"]["action"]}导致了什么？'
                    elif cr == '对比':
                        # 对比链：问"有什么不同"
                        if len(members) >= 2:
                            a_mem = members[0]
                            b_mem = members[1] if len(members) > 1 else members[0]
                            qtext = f'{a_mem["person"]["name"]}{a_mem["event"]["action"]}了{a_mem["event"]["product"]}，而{b_mem["person"]["name"]}做了什么不同的？'
                        else:
                            qtext = f'和{members[0]["person"]["name"]}的{m["event"]["action"]}相比，有什么不同的做法？'
                    elif cr == '包含':
                        # 包含链：问"里面有什么"
                        if len(members) >= 2:
                            parent = members[0]
                            child = members[1] if len(members) > 1 else members[0]
                            qtext = f'{parent["person"]["name"]}{parent["event"]["action"]}了{parent["event"]["product"]}，这件事里面包含了{child["person"]["name"]}的什么行为？'
                        else:
                            qtext = f'{members[0]["person"]["name"]}的{m["event"]["action"]}里面包含了哪些细节？'
                    elif cr == '推导':
                        # 推导链：问"能推导出什么"
                        if len(members) >= 2:
                            obs = members[0]
                            conc = members[1] if len(members) > 1 else members[0]
                            qtext = f'从{obs["person"]["name"]}{obs["event"]["action"]}了{obs["event"]["product"]}出发，能推导出{conc["person"]["name"]}做了什么？'
                        else:
                            qtext = f'从{members[0]["person"]["name"]}的{m["event"]["action"]}出发，能推导出什么？'
                    else:
                        qtext = f'请梳理{members[0]["person"]["name"]}的完整经历脉络'
                    
                    # 链式答案：包含所有成员的摘要（结构化）
                    chain_summary = '；'.join([
                        f'{i+1}. {x["person"]["name"]}{x["event"]["action"]}了{x["event"]["product"]}（{x["time"]["absolute"] or x["time"]["relative"]}）'
                        for i, x in enumerate(members)
                    ])
                    # 链式结构化答案：取所有成员的汇总
                    chain_structured = {
                        "chain_type": cr,
                        "members": [
                            {
                                "person": x["person"]["name"],
                                "action": x["event"]["action"],
                                "product": x["event"]["product"],
                                "time": x["time"]["absolute"] or x["time"]["relative"]
                            }
                            for x in members
                        ]
                    }
                    
                    queries.append({
                        'query_id': f'Q{len(queries) + 1:04d}',
                        'query_text': qtext,
                        'query_type': '组合推理',
                        'test_dimension': test_dim,
                        'expected_memory_ids': [x['memory_id'] for x in members],
                        'expected_answer': chain_structured,
                        'expected_answer_text': chain_summary,
                        'expected_time': members[0]['time']['absolute'],
                        'difficulty': '中等'})

    # ===== 负样本查询（20%） =====
    n_positive = len(queries)
    n_negative = max(1, int(n_positive * 0.25))  # 约20%负样本
    
    for i in range(n_negative):
        neg_type = random.choice(['人物不存在', '地点不存在', '事件不存在', '组合矛盾', '微妙错误'])
        if neg_type == '人物不存在' and all_persons:
            query_text = random.choice([
                f'{random.choice(fake_persons)}做了什么',
                f'{random.choice(fake_persons)}在{random.choice(all_cities)}做了什么',
                f'{random.choice(fake_persons)}关于{random.choice(all_products)}有什么经历',
            ]) if all_cities else f'{random.choice(fake_persons)}做了什么'
        elif neg_type == '地点不存在' and all_cities:
            query_text = random.choice([
                f'在{random.choice(fake_cities)}发生了什么',
                f'{random.choice(all_persons)}在{random.choice(fake_cities)}做了什么',
            ]) if all_persons else f'在{random.choice(fake_cities)}发生了什么'
        elif neg_type == '事件不存在' and all_products:
            query_text = random.choice([
                f'关于{random.choice(fake_events)}的事件有哪些',
                f'{random.choice(all_persons)}关于{random.choice(fake_events)}有什么经历',
            ]) if all_persons else f'关于{random.choice(fake_events)}的事件有哪些'
        elif neg_type == '微妙错误' and all_persons and all_cities:
            # 真实人物 + 真实地点 + 不存在的动作
            real_person = random.choice(all_persons)
            real_city = random.choice(all_cities)
            fake_actions = ['打篮球', '游泳', '跳舞', '画画', '唱歌']
            query_text = f'{real_person}在{real_city}{random.choice(fake_actions)}'
        else:  # 组合矛盾
            if all_persons and all_cities and all_products:
                query_text = f'{random.choice(all_persons)}在{random.choice(fake_cities)}购买了{random.choice(all_products)}'
            elif all_persons and all_cities:
                query_text = f'{random.choice(all_persons)}在{random.choice(fake_cities)}做了什么'
            else:
                query_text = f'关于{random.choice(fake_events)}的记录'
        
        queries.append({
            'query_id': f'NEG{i+1:04d}',
            'query_text': query_text,
            'query_type': '负样本',
            'test_dimension': '负样本',
            'expected_memory_ids': [],
            'expected_answer': '',
            'difficulty': '困难',
            'search_depth': '浅层',
            'is_negative': True,
        })

    # 查询人物平衡（正样本）
    mem_map = {m['memory_id']: m for m in memories}
    by_person = defaultdict(list)
    for q in queries:
        if q.get('is_negative'):
            continue  # 负样本不参与人物平衡
        eids = q.get('expected_memory_ids', [])
        person = mem_map[eids[0]]['person']['name'] if eids and eids[0] in mem_map else '未知'
        by_person[person].append(q)

    balanced_queries = []
    for person, qs in by_person.items():
        cap = QUERY_PERSON_CAP
        if len(qs) <= cap:
            balanced_queries.extend(qs)
        else:
            # 按查询类型多样性采样
            by_type = defaultdict(list)
            for q in qs:
                by_type[q['query_type']].append(q)
            sampled = []
            for qt, type_qs in by_type.items():
                per_type = max(1, cap // len(by_type))
                sampled.extend(type_qs[:per_type])
            if len(sampled) > cap:
                random.seed(42)
                sampled = random.sample(sampled, cap)
            balanced_queries.extend(sampled)

    # 加入负样本（不参与人物平衡）
    neg_queries = [q for q in queries if q.get('is_negative')]
    balanced_queries.extend(neg_queries)

    random.shuffle(balanced_queries)
    tc = defaultdict(int)
    for q in balanced_queries: tc[q['query_type']] += 1
    print(f'[{time.strftime("%H:%M")}] Queries: {dict(tc)} total={len(balanced_queries)} (neg={len(neg_queries)})')
    return balanced_queries


# ====== 阶段6: LLM预解析缓存 ======
def build_llm_cache(queries):
    """LLM预解析缓存 — 批量处理查询。

    优化：使用batch_generate并行处理多个批次，提升3-5x速度。
    """
    cache = {}
    batch_size = 15
    query_batches = [queries[i:i+batch_size] for i in range(0, len(queries), batch_size)]
    
    if not query_batches:
        return cache
    
    # 构建所有批次的prompts
    all_prompts = []
    batch_indices = []
    for batch in query_batches:
        bq = '\n'.join(f'{i}: {q["query_text"]}' for i, q in enumerate(batch))
        prompt = '对每个查询解析为JSON。字段: person_name,location_city,event_product,time_start,dynasty_era。缺失字段省略。严格按序号:JSON格式每行。\n\n' + bq + '\n输出:\n0: {"person_name":"X"}\n1: {"location_city":"Y"}'
        all_prompts.append(prompt)
        batch_indices.append(batch)
    
    try:
        llm_inst = get_llm()
        if hasattr(llm_inst, 'batch_generate') and len(all_prompts) > 1:
            all_results = llm_inst.batch_generate(all_prompts, max_tokens=len(all_prompts[0]) * 80, temperature=0)
        else:
            all_results = [llm_inst.generate(p, max_tokens=len(p) * 5, temperature=0) for p in all_prompts]
        
        for batch, result in zip(batch_indices, all_results):
            for line in result.split('\n'):
                mm = re.match(r'(\d+):\s*(\{.+\})', line.strip())
                if mm:
                    idx = int(mm.group(1))
                    if idx < len(batch):
                        try:
                            cache[batch[idx]['query_text']] = _safe_json_loads(mm.group(2))
                        except (json.JSONDecodeError, ValueError):
                            pass
        print(f'[{time.strftime("%H:%M")}] Cache: {len(cache)}/{len(queries)} queries parsed (batch)')
    except Exception as e:
        print(f'[{time.strftime("%H:%M")}] Batch cache failed ({type(e).__name__}), falling back...', flush=True)
        # Fallback to original sequential processing
        for start in range(0, len(queries), batch_size):
            batch = queries[start:start + batch_size]
            bq = '\n'.join(f'{i}: {q["query_text"]}' for i, q in enumerate(batch))
            prompt = '对每个查询解析为JSON。字段: person_name,location_city,event_product,time_start,dynasty_era。缺失字段省略。严格按序号:JSON格式每行。\n\n' + bq + '\n输出:\n0: {"person_name":"X"}\n1: {"location_city":"Y"}'
            try:
                c = llm(prompt, len(batch) * 80)
                for line in c.split('\n'):
                    mm = re.match(r'(\d+):\s*(\{.+\})', line.strip())
                    if mm:
                        idx = int(mm.group(1))
                        if idx < len(batch):
                            try:
                                cache[batch[idx]['query_text']] = _safe_json_loads(mm.group(2))
                            except (json.JSONDecodeError, ValueError):
                                pass
            except (Exception):
                pass
            if (start + batch_size) % 60 == 0:
                print(f'  cache {min(start + batch_size, len(queries))}/{len(queries)}', flush=True)
        print(f'[{time.strftime("%H:%M")}] Cache: {len(cache)}/{len(queries)} queries parsed (fallback)')
    return cache


# ====== 清洗已有数据库 (不重新提取) ======
def clean_existing_db(db_path, output_path=None):
    """对已有数据库执行去重+人物平衡，不重新LLM提取"""
    if output_path is None:
        base, ext = os.path.splitext(db_path)
        output_path = f'{base}_cleaned{ext}'

    with open(db_path, encoding='utf-8') as f:
        db = json.load(f)

    memories = db.get('memories', [])
    queries = db.get('queries', [])

    print(f'[{time.strftime("%H:%M")}] Cleaning {db_path}: {len(memories)} memories, {len(queries)} queries')

    # 清洗记忆
    cleaned_memories, stats = deduplicate_memories(memories)

    # 更新查询中的expected_memory_ids
    valid_ids = set(m['memory_id'] for m in cleaned_memories)
    valid_ids.update(m.get('memory_id', '') for m in cleaned_memories)

    cleaned_queries = []
    for q in queries:
        eids_key = None
        for key in ['expected_memory_ids', 'relevant_memory_ids']:
            if key in q:
                eids_key = key
                break
        if eids_key is None:
            cleaned_queries.append(q)
            continue

        valid = [eid for eid in q[eids_key] if eid in valid_ids]
        if valid:
            q[eids_key] = valid
            cleaned_queries.append(q)

    # 查询人物平衡
    mem_map = {}
    for m in cleaned_memories:
        mid = m.get('memory_id', '')
        if mid:
            mem_map[mid] = m

    by_person = defaultdict(list)
    for q in cleaned_queries:
        eids_key = None
        for key in ['expected_memory_ids', 'relevant_memory_ids']:
            if key in q:
                eids_key = key
                break
        if eids_key:
            eids = q.get(eids_key, [])
            person = '未知'
            if eids and eids[0] in mem_map:
                person = _get_person_field(mem_map[eids[0]])
            by_person[person].append(q)
        else:
            by_person['未知'].append(q)

    balanced_queries = []
    for person, qs in by_person.items():
        cap = QUERY_PERSON_CAP + 2  # 清洗模式稍宽松
        if len(qs) <= cap:
            balanced_queries.extend(qs)
        else:
            balanced_queries.extend(qs[:cap])

    # 保存
    db['memories'] = cleaned_memories
    db['queries'] = balanced_queries
    db['clean_stats'] = stats
    db['clean_time'] = time.strftime('%Y-%m-%d %H:%M')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f'[{time.strftime("%H:%M")}] Saved: {output_path} ({len(cleaned_memories)} mems, {len(balanced_queries)} queries)')
    return output_path


# ====== Main ======
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法:")
        print("  python knowledge_builder.py <文章目录> [输出.json] [--merge]  # 从文本生成")
        print("  python knowledge_builder.py <数据库.json> --clean [输出.json]  # 清洗已有数据库")
        sys.exit(1)

    # 清洗模式
    if '--clean' in sys.argv:
        db_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else None
        clean_existing_db(db_path, output_path)
        sys.exit(0)

    # 生成模式
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
    memories, _ = deduplicate_memories(memories)  # 清洗
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
