#!/usr/bin/env python3
"""
LLM Reranking Benchmark at multiple K values (5, 10, 15, 20).
TF-IDF top-50 → LLM ranks all candidates → evaluate at K=5,10,15,20.
"""
import sqlite3, json, re, random, sys, gc, time, subprocess, os
from collections import defaultdict
import numpy as np

# --- Security: paths from env, never hardcode absolute paths ---
DB_PATH = os.getenv("MEMTEST_DB_PATH", "./noesis.db")
OUTPUT_DIR = os.getenv("MEMTEST_OUTPUT_DIR", "./data")

SAMPLE_SIZE = 100
CANDIDATE_K = 50
BATCH_SIZE = 3       # 3 queries per LLM call (more candidates per query now)
PARALLEL_SESSIONS = 4
K_VALUES = [5, 10, 15, 20]

_MAX_SESSION_ID_LEN = 128
_SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')

def _validate_session_id(sid):
    if not sid or len(sid) > _MAX_SESSION_ID_LEN:
        raise ValueError(f"Invalid session_id length: {len(sid) if sid else 0}")
    if not _SESSION_ID_RE.match(sid):
        raise ValueError(f"Invalid session_id characters: {sid[:20]}")
    return sid

def _safe_json_loads(raw, max_size=5*1024*1024):
    if isinstance(raw, str) and len(raw) > max_size:
        raise ValueError(f"JSON payload too large: {len(raw)} bytes > {max_size}")
    if isinstance(raw, bytes) and len(raw) > max_size:
        raise ValueError(f"JSON payload too large: {len(raw)} bytes > {max_size}")
    return json.loads(raw)

random.seed(42)

def get_novel(mid_num):
    if mid_num < 13850: return "红楼梦"
    if mid_num < 15988: return "西游记"
    if mid_num < 18088: return "水浒传"
    return "三国演义"

def parse_content(content):
    result = {"person": None, "location": None, "time": None, "dynasty": None, "event": None}
    m = re.search(r'\[(.+)\]$', content)
    if m:
        meta = m.group(1)
        for field, key in [("人物", "person"), ("地点", "location"), ("时间", "time"), ("朝代", "dynasty"), ("事件", "event")]:
            fm = re.search(rf'{field}:([^\s\]]+)', meta)
            if fm: result[key] = fm.group(1)
    text_match = re.match(r'^(.+?)(?:\s*\[)', content)
    result['text'] = text_match.group(1).strip() if text_match else content[:60]
    return result

def load_memories(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, summary, content FROM ltm_nodes WHERE summary GLOB 'MEM[0-9]*' ORDER BY summary")
    seen = set()
    memories = []
    for row in cur.fetchall():
        mid = row[1]
        if mid in seen: continue
        seen.add(mid)
        try: mid_num = int(mid.replace("MEM", ""))
        except ValueError: continue
        parsed = parse_content(row[2])
        parts = []
        if parsed['person']: parts.append(parsed['person'])
        if parsed['event'] and parsed['event'] not in ('event',): parts.append(parsed['event'])
        if parsed['location'] and parsed['location'] not in ('不详', '待考证'): parts.append(parsed['location'])
        if parsed['dynasty']: parts.append(parsed['dynasty'])
        if parsed['time'] and parsed['time'] not in ('不详',): parts.append(parsed['time'])
        text_match = re.match(r'^(.+?)(?:\s*\[)', row[2])
        raw_text = text_match.group(1).strip()[:60] if text_match else row[2][:60]
        parts.append(raw_text)
        structured = ' '.join(parts)
        memories.append({"memory_id": mid, "id_num": mid_num, "content": row[2],
                         "structured": structured, "novel": get_novel(mid_num), **parsed})
    return memories

def generate_queries(memories):
    by_person = defaultdict(list)
    by_location = defaultdict(list)
    by_event = defaultdict(list)
    by_dynasty = defaultdict(list)
    for m in memories:
        if m['person']: by_person[m['person']].append(m['memory_id'])
        if m['location'] and m['location'] not in ('不详', '待考证'): by_location[m['location']].append(m['memory_id'])
        if m['event'] and m['event'] not in ('event',): by_event[m['event']].append(m['memory_id'])
        if m['dynasty']: by_dynasty[m['dynasty']].append(m['memory_id'])
    queries = []
    for person, mids in sorted(by_person.items(), key=lambda x: -len(x[1])):
        if len(mids) >= 3:
            queries.append({"query": f"{person}的事迹言行", "query_type": "人物检索",
                            "target_entity": person, "novel": get_novel(int(mids[0].replace("MEM","")))})
    for loc, mids in sorted(by_location.items(), key=lambda x: -len(x[1])):
        if len(mids) >= 3:
            queries.append({"query": f"在{loc}发生的事情", "query_type": "地点检索",
                            "target_entity": loc, "novel": get_novel(int(mids[0].replace("MEM","")))})
    for evt, mids in sorted(by_event.items(), key=lambda x: -len(x[1])):
        if len(mids) >= 3 and evt not in ('event', 'events'):
            queries.append({"query": f"{evt}的经过", "query_type": "事件检索",
                            "target_entity": evt, "novel": get_novel(int(mids[0].replace("MEM","")))})
    for dyn, mids in sorted(by_dynasty.items(), key=lambda x: -len(x[1])):
        if len(mids) >= 5:
            queries.append({"query": f"{dyn}的故事", "query_type": "时间检索",
                            "target_entity": dyn, "novel": get_novel(int(mids[0].replace("MEM","")))})
    for person in list(by_person.keys())[:20]:
        person_mems = [m for m in memories if m['person'] == person and m['location'] and m['location'] not in ('不详', '待考证')]
        if person_mems:
            loc = person_mems[0]['location']
            queries.append({"query": f"{person}在{loc}", "query_type": "组合检索",
                            "target_entity": person, "novel": person_mems[0]['novel']})
    novel_names = {"红楼梦": "贾府的故事", "西游记": "取经路上", "水浒传": "梁山好汉", "三国演义": "三国战争"}
    for novel, query_text in novel_names.items():
        queries.append({"query": query_text, "query_type": "组合检索", "target_entity": novel, "novel": novel})
    return queries

def build_entity_index(id_to_mem, all_entities):
    index = defaultdict(set)
    entity_list = list(all_entities)
    for mid, mem in id_to_mem.items():
        content = mem['content']
        for entity in entity_list:
            if entity in content:
                index[entity].add(mid)
    return dict(index)

def compute_metrics_at_k(retrieved_full, eval_queries, entity_index, k):
    """Compute metrics at a specific K value from a full ranking."""
    total = len(eval_queries)
    p_sum = r_sum = mrr_sum = 0.0
    for i, q in enumerate(eval_queries):
        retrieved = retrieved_full[i][:k]
        entity = q['target_entity']
        relevant = entity_index.get(entity, set())
        hits = [1 if mid in relevant else 0 for mid in retrieved]
        precision = sum(hits) / len(retrieved) if retrieved else 0
        recall = sum(hits) / min(len(relevant), k) if relevant else 0
        mrr = 0
        for rank, hit in enumerate(hits, 1):
            if hit: mrr = 1.0 / rank; break
        p_sum += precision
        r_sum += recall
        mrr_sum += mrr
    return {
        "precision": p_sum / total if total else 0,
        "recall": r_sum / total if total else 0,
        "mrr": mrr_sum / total if total else 0
    }

def run_tfidf_fullranking(memories, eval_queries, mem_ids, mem_texts):
    """Run TF-IDF and return full ranked list (all memories sorted by similarity)."""
    import jieba
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim
    def tokenize(text):
        return [w for w in jieba.lcut(text) if len(w) > 1]
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, max_features=50000)
    tfidf_matrix = vectorizer.fit_transform(mem_texts)
    query_texts = [q['query'] for q in eval_queries]
    query_matrix = vectorizer.transform(query_texts)
    all_ranked = []
    for i in range(len(eval_queries)):
        sims = cos_sim(query_matrix[i], tfidf_matrix)[0]
        if hasattr(sims, 'toarray'): sims = sims.toarray()[0]
        else: sims = np.asarray(sims).flatten()
        ranked_indices = np.argsort(sims)[::-1]
        all_ranked.append([mem_ids[idx] for idx in ranked_indices])
    return all_ranked

def create_session():
    result = subprocess.run(
        ['coze', 'session', 'create', '--format', 'json'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        raise RuntimeError(f"coze session create failed: {result.stderr[:200]}")
    data = _safe_json_loads(result.stdout)
    sid = data.get('session_id', '')
    return _validate_session_id(sid)

def send_message(session_id, message):
    _validate_session_id(session_id)
    proc = subprocess.Popen(
        ['coze', 'session', 'message', '-s', session_id, '--format', 'json'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        stdout, _ = proc.communicate(input=message, timeout=20)
        data = _safe_json_loads(stdout)
        return data.get('status') == 'accepted'
    except subprocess.TimeoutExpired:
        proc.kill()
        return False

def read_last_reply(session_id):
    _validate_session_id(session_id)
    result = subprocess.run(
        ['coze', 'agent', 'message', 'list', '--project-id', session_id, '--json', '--size', '3'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return None
    data = _safe_json_loads(result.stdout)
    msgs = data.get('data', {}).get('messages', [])
    for msg in msgs:
        if msg.get('source') == 2 and msg.get('message_type') == 'reply':
            content = msg.get('content', '')
            try:
                inner = _safe_json_loads(content)
                return inner.get('message_data', {}).get('reply', {}).get('content', '')
            except (json.JSONDecodeError, ValueError):
                return content
    return None

def build_rank_prompt(batch_queries, batch_candidates):
    """Build prompt asking LLM to rank ALL candidates by relevance."""
    lines = [
        "你是记忆检索重排助手。以下有多个查询，每个查询有若干候选记忆。",
        "请将每个查询的候选记忆按与查询的相关度从高到低排列，返回所有候选的编号。",
        "格式：每行一个查询，Q编号:编号1,编号2,编号3,...（按相关度降序）",
        ""
    ]
    for i, (q, candidates) in enumerate(zip(batch_queries, batch_candidates)):
        lines.append(f"Q{i+1}: {q['query']}")
        lines.append("候选记忆:")
        for j, c in enumerate(candidates[:30]):
            lines.append(f"  {j+1}. {c['content']}")
        lines.append("")
    
    lines.append("请返回每个查询的所有候选记忆排序：")
    return '\n'.join(lines)

def parse_rank_response(response, batch_queries, batch_candidates):
    """Parse ranking response into full ordered memory ID lists."""
    results = []
    lines = response.strip().split('\n')
    for i in range(len(batch_queries)):
        found = False
        for line in lines:
            line = line.strip()
            prefix = f"Q{i+1}:"
            if line.upper().startswith(prefix.upper()):
                nums_str = line[len(prefix):].strip()
                try:
                    nums = [int(x.strip()) for x in re.findall(r'\d+', nums_str)]
                except:
                    nums = []
                mem_ids = []
                candidates = batch_candidates[i][:30]
                for n in nums:
                    if 1 <= n <= len(candidates):
                        mem_ids.append(candidates[n-1]['memory_id'])
                # Append any candidates not in LLM ranking (LLM missed them)
                ranked_set = set(mem_ids)
                for c in candidates:
                    if c['memory_id'] not in ranked_set:
                        mem_ids.append(c['memory_id'])
                results.append(mem_ids)
                found = True
                break
        if not found:
            # Fallback to TF-IDF order
            results.append([c['memory_id'] for c in batch_candidates[i][:30]])
    return results

def main():
    print("=== LLM Reranking Multi-K Benchmark ===", flush=True)
    start_time = time.time()
    
    conn = sqlite3.connect(DB_PATH)
    memories = load_memories(conn)
    conn.close()
    print(f"Loaded {len(memories)} unique memories", flush=True)
    
    id_to_mem = {m['memory_id']: m for m in memories}
    queries = generate_queries(memories)
    eval_queries = random.sample(queries, min(SAMPLE_SIZE, len(queries)))
    print(f"Evaluating {len(eval_queries)} queries", flush=True)
    
    mem_ids = [m['memory_id'] for m in memories]
    mem_texts = [m['structured'] for m in memories]
    
    # Build entity index
    print("Building entity index...", flush=True)
    all_entities = list(set(q['target_entity'] for q in queries))
    entity_index = build_entity_index(id_to_mem, all_entities)
    
    # Step 1: TF-IDF full ranking
    print("Running TF-IDF full ranking...", flush=True)
    tfidf_ranked = run_tfidf_fullranking(memories, eval_queries, mem_ids, mem_texts)
    
    # Step 2: TF-IDF top-50 candidates for LLM
    tfidf_top50 = [ranked[:CANDIDATE_K] for ranked in tfidf_ranked]
    all_candidates = []
    for i, ranked_ids in enumerate(tfidf_top50):
        candidates = []
        for mid in ranked_ids:
            mem = id_to_mem[mid]
            candidates.append({'memory_id': mid, 'content': mem['content'][:80]})
        all_candidates.append(candidates)
    
    # Step 3: LLM reranking (rank all candidates)
    print(f"\n=== LLM Reranking ({len(eval_queries)} queries) ===", flush=True)
    n_batches = (len(eval_queries) + BATCH_SIZE - 1) // BATCH_SIZE
    llm_ranked = [None] * len(eval_queries)
    
    for wave_start in range(0, n_batches, PARALLEL_SESSIONS):
        wave_end = min(wave_start + PARALLEL_SESSIONS, n_batches)
        wave_sessions = []
        
        for batch_idx in range(wave_start, wave_end):
            start_q = batch_idx * BATCH_SIZE
            end_q = min(start_q + BATCH_SIZE, len(eval_queries))
            bq = eval_queries[start_q:end_q]
            bc = all_candidates[start_q:end_q]
            prompt = build_rank_prompt(bq, bc)
            
            try:
                session_id = create_session()
                ok = send_message(session_id, prompt)
                if ok:
                    wave_sessions.append({
                        'session_id': session_id, 'batch_idx': batch_idx,
                        'start_q': start_q, 'end_q': end_q,
                        'batch_queries': bq, 'batch_candidates': bc,
                        'send_time': time.time()
                    })
                    print(f"  Batch {batch_idx+1}/{n_batches}: sent", flush=True)
            except Exception as e:
                print(f"  Batch {batch_idx+1}: ERROR {e}", flush=True)
        
        # Poll for responses with max total timeout instead of fixed sleep
        if wave_sessions:
            max_wait = 120
            poll_interval = 5
            deadline = time.time() + max_wait
            pending = {ws['session_id']: ws for ws in wave_sessions}
            while pending and time.time() < deadline:
                for sid in list(pending.keys()):
                    try:
                        reply = read_last_reply(sid)
                        if reply:
                            ws = pending.pop(sid)
                            ranked = parse_rank_response(reply, ws['batch_queries'], ws['batch_candidates'])
                            for j, mem_ids_list in enumerate(ranked):
                                q_idx = ws['start_q'] + j
                                if q_idx < len(llm_ranked):
                                    llm_ranked[q_idx] = mem_ids_list
                            print(f"  Batch {ws['batch_idx']+1}: OK ({len(reply)} chars)", flush=True)
                    except Exception as e:
                        print(f"  Batch {pending[sid]['batch_idx']+1}: poll error {e}", flush=True)
                if pending:
                    time.sleep(poll_interval)
            # Fallback for any still-pending sessions
            for ws in pending.values():
                print(f"  Batch {ws['batch_idx']+1}: NO REPLY (timeout)", flush=True)
                for j in range(ws['start_q'], ws['end_q']):
                    if llm_ranked[j] is None:
                        llm_ranked[j] = [c['memory_id'] for c in all_candidates[j]]
    
    # Fill None
    for i in range(len(llm_ranked)):
        if llm_ranked[i] is None:
            llm_ranked[i] = [c['memory_id'] for c in all_candidates[i]]
    
    # Step 4: Compute metrics at all K values
    print("\n=== Results ===", flush=True)
    print(f"{'Method':<20} {'K':<5} {'P@K':<10} {'R@K':<10} {'MRR@K':<10}", flush=True)
    print("-" * 55, flush=True)
    
    results = {"tfidf": {}, "llm_rerank": {}}
    
    for k in K_VALUES:
        tfidf_m = compute_metrics_at_k(tfidf_ranked, eval_queries, entity_index, k)
        llm_m = compute_metrics_at_k(llm_ranked, eval_queries, entity_index, k)
        results["tfidf"][k] = tfidf_m
        results["llm_rerank"][k] = llm_m
        print(f"{'TF-IDF':<20} {k:<5} {tfidf_m['precision']:.1%}{'':<5} {tfidf_m['recall']:.1%}{'':<5} {tfidf_m['mrr']:.3f}", flush=True)
        print(f"{'LLM Rerank':<20} {k:<5} {llm_m['precision']:.1%}{'':<5} {llm_m['recall']:.1%}{'':<5} {llm_m['mrr']:.3f}", flush=True)
        print(f"{'Δ (LLM-TFIDF)':<20} {k:<5} {llm_m['precision']-tfidf_m['precision']:+.1%}{'':<4} {llm_m['recall']-tfidf_m['recall']:+.1%}{'':<4} {llm_m['mrr']-tfidf_m['mrr']:+.3f}", flush=True)
        print(flush=True)
    
    # Save
    output = {"config": {"sample_size": SAMPLE_SIZE, "candidate_k": CANDIDATE_K,
                          "k_values": K_VALUES, "total_memories": len(memories),
                          "total_queries": len(queries)}, "results": results}
    with open(f"{OUTPUT_DIR}/llm_rerank_multik.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    
    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.0f}s", flush=True)

if __name__ == "__main__":
    main()
