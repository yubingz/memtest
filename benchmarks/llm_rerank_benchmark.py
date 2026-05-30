#!/usr/bin/env python3
"""
LLM Reranking Benchmark: Uses Coze session API (our own large model) to rerank TF-IDF candidates.
Pipeline: TF-IDF top-50 → LLM rerank → top-20 → evaluate
"""
import sqlite3, json, re, random, sys, gc, time, subprocess, os
from collections import defaultdict
import numpy as np

# --- Security: paths from env, never hardcode absolute paths ---
DB_PATH = os.getenv("MEMTEST_DB_PATH", "./noesis.db")
OUTPUT_DIR = os.getenv("MEMTEST_OUTPUT_DIR", "./data")

SAMPLE_SIZE = 100   # Use 100 queries for LLM reranking (speed)
TOP_K = 20          # Final top-K for evaluation
CANDIDATE_K = 50    # TF-IDF retrieves top-50 candidates for LLM to rerank
BATCH_SIZE = 5      # Queries per LLM call
PARALLEL_SESSIONS = 4  # Run this many sessions in parallel

_MAX_SESSION_ID_LEN = 128
_SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')

def _validate_session_id(sid):
    """Validate session_id to prevent command injection."""
    if not sid or len(sid) > _MAX_SESSION_ID_LEN:
        raise ValueError(f"Invalid session_id length: {len(sid) if sid else 0}")
    if not _SESSION_ID_RE.match(sid):
        raise ValueError(f"Invalid session_id characters: {sid[:20]}")
    return sid

def _safe_json_loads(raw, max_size=5*1024*1024):
    """Parse JSON with size guard to avoid DoS from huge payloads."""
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
    by_novel = defaultdict(list)
    for m in memories:
        if m['person']: by_person[m['person']].append(m['memory_id'])
        if m['location'] and m['location'] not in ('不详', '待考证'): by_location[m['location']].append(m['memory_id'])
        if m['event'] and m['event'] not in ('event',): by_event[m['event']].append(m['memory_id'])
        if m['dynasty']: by_dynasty[m['dynasty']].append(m['memory_id'])
        by_novel[m['novel']].append(m['memory_id'])
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

def compute_metrics(retrieved_list, eval_queries, entity_index):
    results = {"total": 0,
               "precision_sum": 0.0, "recall_sum": 0.0, "mrr_sum": 0.0,
               "by_type": defaultdict(lambda: {"total": 0, "precision_sum": 0.0, "recall_sum": 0.0, "mrr_sum": 0.0}),
               "by_novel": defaultdict(lambda: {"total": 0, "precision_sum": 0.0, "recall_sum": 0.0, "mrr_sum": 0.0})}
    for i, q in enumerate(eval_queries):
        retrieved = retrieved_list[i]
        entity = q['target_entity']
        relevant = entity_index.get(entity, set())
        hits = [1 if mid in relevant else 0 for mid in retrieved]
        precision = sum(hits) / len(retrieved) if retrieved else 0
        recall = sum(hits) / min(len(relevant), TOP_K) if relevant else 0
        mrr = 0
        for rank, hit in enumerate(hits, 1):
            if hit: mrr = 1.0 / rank; break
        results["total"] += 1
        results["precision_sum"] += precision
        results["recall_sum"] += recall
        results["mrr_sum"] += mrr
        results["by_type"][q['query_type']]["total"] += 1
        results["by_type"][q['query_type']]["precision_sum"] += precision
        results["by_type"][q['query_type']]["recall_sum"] += recall
        results["by_type"][q['query_type']]["mrr_sum"] += mrr
        results["by_novel"][q['novel']]["total"] += 1
        results["by_novel"][q['novel']]["precision_sum"] += precision
        results["by_novel"][q['novel']]["recall_sum"] += recall
        results["by_novel"][q['novel']]["mrr_sum"] += mrr
    n = results["total"]
    results["avg_precision"] = results["precision_sum"] / n if n else 0
    results["avg_recall"] = results["recall_sum"] / n if n else 0
    results["avg_mrr"] = results["mrr_sum"] / n if n else 0
    for key in ["by_type", "by_novel"]:
        for k in results[key]:
            t = results[key][k]["total"]
            results[key][k]["avg_precision"] = results[key][k]["precision_sum"] / t if t else 0
            results[key][k]["avg_recall"] = results[key][k]["recall_sum"] / t if t else 0
            results[key][k]["avg_mrr"] = results[key][k]["mrr_sum"] / t if t else 0
    return results

def run_tfidf_topk(memories, eval_queries, mem_ids, mem_texts, topk=CANDIDATE_K):
    """Run TF-IDF and return top-k candidate IDs for each query."""
    import jieba
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as cos_sim
    def tokenize(text):
        return [w for w in jieba.lcut(text) if len(w) > 1]
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, max_features=50000)
    tfidf_matrix = vectorizer.fit_transform(mem_texts)
    query_texts = [q['query'] for q in eval_queries]
    query_matrix = vectorizer.transform(query_texts)
    all_candidates = []
    for i in range(len(eval_queries)):
        sims = cos_sim(query_matrix[i], tfidf_matrix)[0]
        if hasattr(sims, 'toarray'): sims = sims.toarray()[0]
        else: sims = np.asarray(sims).flatten()
        top_indices = np.argsort(sims)[::-1][:topk]
        candidates = []
        for idx in top_indices:
            candidates.append({
                'rank_in_tfidf': int(np.where(top_indices == idx)[0][0]) + 1,
                'memory_id': mem_ids[idx],
                'content': memories[idx]['content'][:80],
                'score': float(sims[idx])
            })
        all_candidates.append(candidates)
    return all_candidates

def create_session():
    """Create a new Coze session and return its ID."""
    result = subprocess.run(
        ['coze', 'session', 'create', '--format', 'json'],
        capture_output=True, text=True, timeout=15,
        # Security: fixed args, no shell; cwd not needed here
    )
    if result.returncode != 0:
        raise RuntimeError(f"coze session create failed: {result.stderr[:200]}")
    data = _safe_json_loads(result.stdout)
    sid = data.get('session_id', '')
    return _validate_session_id(sid)

def send_message(session_id, message):
    """Send a message to a session (non-blocking)."""
    _validate_session_id(session_id)
    proc = subprocess.Popen(
        ['coze', 'session', 'message', '-s', session_id, '--format', 'json'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )
    try:
        stdout, stderr = proc.communicate(input=message, timeout=20)
        data = _safe_json_loads(stdout)
        return data.get('status') == 'accepted', data.get('message_id')
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, None

def read_last_reply(session_id):
    """Read the last bot reply from a session."""
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
                reply = inner.get('message_data', {}).get('reply', {}).get('content', '')
                return reply
            except (json.JSONDecodeError, ValueError):
                return content
    return None

def build_rerank_prompt(batch_queries, batch_candidates):
    """Build a reranking prompt for a batch of queries."""
    prompt_lines = [
        "你是一个记忆检索重排助手。以下有多个查询，每个查询有若干候选记忆。",
        "请对每个查询，从候选记忆中选出与查询相关的记忆编号，按相关度从高到低排列。",
        "只返回编号列表，用逗号分隔。每个查询一行，格式：Q编号:编号1,编号2,...",
        ""
    ]
    for i, (q, candidates) in enumerate(zip(batch_queries, batch_candidates)):
        prompt_lines.append(f"Q{i+1}: {q['query']}")
        prompt_lines.append(f"候选记忆:")
        for j, c in enumerate(candidates[:30]):  # Limit to 30 candidates per query
            prompt_lines.append(f"  {j+1}. {c['content']}")
        prompt_lines.append("")
    
    prompt_lines.append("请返回每个查询的相关记忆编号：")
    for i in range(len(batch_queries)):
        prompt_lines.append(f"Q{i+1}: ")
    
    return '\n'.join(prompt_lines)

def parse_rerank_response(response, batch_queries, batch_candidates):
    """Parse the LLM's reranking response into lists of memory IDs."""
    results = []
    lines = response.strip().split('\n')
    
    # Build a mapping from response lines to query indices
    for i, q in enumerate(batch_queries):
        found = False
        for line in lines:
            line = line.strip()
            # Look for lines starting with Q1:, Q2:, etc.
            prefix = f"Q{i+1}:"
            if line.upper().startswith(prefix.upper()):
                nums_str = line[len(prefix):].strip()
                # Parse comma-separated numbers
                try:
                    nums = [int(x.strip()) for x in nums_str.split(',') if x.strip().isdigit()]
                except ValueError:
                    nums = []
                # Convert candidate indices to memory IDs
                mem_ids = []
                candidates = batch_candidates[i][:30]
                for n in nums:
                    if 1 <= n <= len(candidates):
                        mem_ids.append(candidates[n-1]['memory_id'])
                results.append(mem_ids[:TOP_K])
                found = True
                break
        
        if not found:
            # Fallback: try to find numbers in the response
            results.append([])  # Empty result for this query
    
    return results

def run_llm_rerank(eval_queries, all_candidates):
    """Run LLM reranking on all queries."""
    print(f"\n=== LLM Reranking ({len(eval_queries)} queries) ===", flush=True)
    
    n_batches = (len(eval_queries) + BATCH_SIZE - 1) // BATCH_SIZE
    all_reranked = [None] * len(eval_queries)
    
    # Process in parallel waves
    for wave_start in range(0, n_batches, PARALLEL_SESSIONS):
        wave_end = min(wave_start + PARALLEL_SESSIONS, n_batches)
        wave_sessions = []
        
        # Create sessions and send messages
        for batch_idx in range(wave_start, wave_end):
            start_q = batch_idx * BATCH_SIZE
            end_q = min(start_q + BATCH_SIZE, len(eval_queries))
            batch_queries = eval_queries[start_q:end_q]
            batch_candidates = all_candidates[start_q:end_q]
            
            prompt = build_rerank_prompt(batch_queries, batch_candidates)
            
            # Create session and send
            try:
                session_id = create_session()
                ok, msg_id = send_message(session_id, prompt)
                if ok:
                    wave_sessions.append({
                        'session_id': session_id,
                        'batch_idx': batch_idx,
                        'start_q': start_q,
                        'end_q': end_q,
                        'batch_queries': batch_queries,
                        'batch_candidates': batch_candidates,
                        'send_time': time.time()
                    })
                    print(f"  Batch {batch_idx+1}/{n_batches}: sent to session {session_id}", flush=True)
                else:
                    print(f"  Batch {batch_idx+1}/{n_batches}: FAILED to send", flush=True)
            except Exception as e:
                print(f"  Batch {batch_idx+1}/{n_batches}: ERROR {e}", flush=True)
        
        # Poll for responses with max total timeout instead of fixed sleep
        if wave_sessions:
            max_wait = 120  # seconds total timeout per wave
            poll_interval = 5
            deadline = time.time() + max_wait
            pending = {ws['session_id']: ws for ws in wave_sessions}
            while pending and time.time() < deadline:
                for sid in list(pending.keys()):
                    try:
                        reply = read_last_reply(sid)
                        if reply:
                            ws = pending.pop(sid)
                            reranked = parse_rerank_response(reply, ws['batch_queries'], ws['batch_candidates'])
                            for j, mem_ids in enumerate(reranked):
                                q_idx = ws['start_q'] + j
                                if q_idx < len(all_reranked):
                                    all_reranked[q_idx] = mem_ids
                            print(f"  Batch {ws['batch_idx']+1}: got reply ({len(reply)} chars)", flush=True)
                    except Exception as e:
                        print(f"  Batch {pending[sid]['batch_idx']+1}: poll error {e}", flush=True)
                if pending:
                    time.sleep(poll_interval)
            # Fallback for any still-pending sessions
            for ws in pending.values():
                print(f"  Batch {ws['batch_idx']+1}: NO REPLY (timeout)", flush=True)
                for j in range(ws['start_q'], ws['end_q']):
                    if j < len(all_reranked) and all_reranked[j] is None:
                        all_reranked[j] = [c['memory_id'] for c in all_candidates[j][:TOP_K]]
    
    # Fill any remaining None with TF-IDF top-20
    for i in range(len(all_reranked)):
        if all_reranked[i] is None:
            all_reranked[i] = [c['memory_id'] for c in all_candidates[i][:TOP_K]]
    
    return all_reranked

def print_results(name, results):
    print(f"\n{name}:", flush=True)
    print(f"  Precision@{TOP_K}: {results['avg_precision']:.1%}", flush=True)
    print(f"  Recall@{TOP_K}:    {results['avg_recall']:.1%}", flush=True)
    print(f"  MRR@{TOP_K}:       {results['avg_mrr']:.3f}", flush=True)
    for qt in sorted(results['by_type']):
        r = results['by_type'][qt]
        print(f"  {qt}: P={r['avg_precision']:.1%} R={r['avg_recall']:.1%} MRR={r['avg_mrr']:.3f}", flush=True)
    for nv in sorted(results['by_novel']):
        r = results['by_novel'][nv]
        print(f"  {nv}: P={r['avg_precision']:.1%} R={r['avg_recall']:.1%} MRR={r['avg_mrr']:.3f}", flush=True)

def main():
    print("=== LLM Reranking Benchmark ===", flush=True)
    start_time = time.time()
    
    # Load data
    conn = sqlite3.connect(DB_PATH)
    memories = load_memories(conn)
    conn.close()
    print(f"Loaded {len(memories)} unique memories", flush=True)
    
    id_to_mem = {m['memory_id']: m for m in memories}
    queries = generate_queries(memories)
    print(f"Generated {len(queries)} queries", flush=True)
    
    eval_queries = random.sample(queries, min(SAMPLE_SIZE, len(queries)))
    print(f"Evaluating {len(eval_queries)} queries", flush=True)
    
    mem_ids = [m['memory_id'] for m in memories]
    mem_texts = [m['structured'] for m in memories]
    
    # Build entity index
    print("Building entity index...", flush=True)
    all_entities = list(set(q['target_entity'] for q in queries))
    entity_index = build_entity_index(id_to_mem, all_entities)
    
    # Step 1: TF-IDF top-50 candidates
    print("Running TF-IDF retrieval (top-50)...", flush=True)
    all_candidates = run_tfidf_topk(memories, eval_queries, mem_ids, mem_texts, CANDIDATE_K)
    
    # Also compute TF-IDF top-20 metrics for comparison
    tfidf_top20 = [[c['memory_id'] for c in candidates[:TOP_K]] for candidates in all_candidates]
    tfidf_results = compute_metrics(tfidf_top20, eval_queries, entity_index)
    print_results("TF-IDF top-20 (baseline)", tfidf_results)
    
    # Step 2: LLM reranking
    reranked = run_llm_rerank(eval_queries, all_candidates)
    llm_results = compute_metrics(reranked, eval_queries, entity_index)
    print_results("LLM Reranked top-20", llm_results)
    
    # Save results
    output = {
        "config": {
            "sample_size": SAMPLE_SIZE, "top_k": TOP_K, "candidate_k": CANDIDATE_K,
            "batch_size": BATCH_SIZE, "parallel_sessions": PARALLEL_SESSIONS,
            "total_memories": len(memories), "total_queries": len(queries),
            "llm_method": "Coze session (own large model)"
        },
        "tfidf_top20": tfidf_results,
        "llm_rerank": llm_results
    }
    with open(f"{OUTPUT_DIR}/llm_rerank_benchmark.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    
    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*70}", flush=True)
    print(f"COMPARISON ({elapsed:.0f}s total)", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"{'Method':<30} {'P@20':<10} {'R@20':<10} {'MRR':<8}", flush=True)
    print("-"*60, flush=True)
    print(f"{'jieba+LIKE':<30} {'~2%':<10} {'~2%':<10} {'N/A':<8}", flush=True)
    print(f"{'TF-IDF+jieba':<30} {tfidf_results['avg_precision']:.1%}{'':<5} {tfidf_results['avg_recall']:.1%}{'':<5} {tfidf_results['avg_mrr']:.3f}", flush=True)
    print(f"{'ST(MiniLM)':<30} {'9.1%':<10} {'12.4%':<10} {'0.201':<8}", flush=True)
    print(f"{'LLM Rerank(TF-IDF→LLM)':<30} {llm_results['avg_precision']:.1%}{'':<5} {llm_results['avg_recall']:.1%}{'':<5} {llm_results['avg_mrr']:.3f}", flush=True)

if __name__ == "__main__":
    main()
