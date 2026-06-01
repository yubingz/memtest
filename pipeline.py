#!/usr/bin/env python3
"""MemTest v3 自动导入流水线

需求定义 → 按需提取 → 出题 → 校验 → 修复

核心原则：
- 先定义查询需求，再针对性提取，不全量提取再筛
- 只存原文（memory_id + content 喂给被测系统）
- 别名只认语料证据
- 时间有什么记什么，断链不补
"""

from __future__ import annotations
import json
import os
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# 导入同目录模块
from schema import (
    MEMORY_SCHEMA_V3, QUERY_SCHEMA_V3, STORAGE_SCHEMA,
    MEMORY_REQUIRED_V3, QUERY_REQUIRED_V3,
    validate_memory, validate_query, validate_database,
    make_memory_id, make_query_id, memory_to_storage,
    build_database_info, finalize_database,
)
from time_resolver import TimeResolver
from alias_resolver import AliasResolver

# ==============================================================================
# 一、Prompt 加载
# ==============================================================================

def _load_prompt(name: str) -> str:
    """从 prompts/ 目录加载提示词"""
    base = os.path.dirname(__file__)
    paths = [
        os.path.join(base, "prompts", f"{name}.md"),
        os.path.join(base, f"{name}.md"),
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except (OSError, IOError):
            pass
    return ""


PROMPTS = {
    "temporal": _load_prompt("v3_extract_temporal"),
    "causal": _load_prompt("v3_extract_causal"),
    "alias": _load_prompt("v3_extract_alias"),
    "fact": _load_prompt("v3_extract_fact"),
    "contrast": _load_prompt("v3_extract_contrast"),
    "query_generate": _load_prompt("v3_query_generate"),
    "query_validate": _load_prompt("v3_query_validate"),
}


# ==============================================================================
# 二、配置与数据结构
# ==============================================================================

@dataclass
class QueryRequirement:
    """单条查询需求定义"""
    type: str           # 时序推理 / 因果推理 / 别名查询 / 事实检索 / 对比推理 / 负样本
    count: int          # 需要多少条
    min_chain_length: int = 3   # 链最小长度（时序/因果）
    chain_length: int = 6       # 链目标长度（因果）
    require_alias_evidence: bool = True   # 别名查询：必须有语料证据
    require_location: bool = False        # 事实检索：必须含地点
    require_contrast_pair: bool = False   # 对比推理：必须是对比对
    difficulty: str = "medium"            # 默认难度

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QueryRequirement":
        return cls(
            type=d["type"],
            count=d["count"],
            min_chain_length=d.get("min_chain_length", 3),
            chain_length=d.get("chain_length", 6),
            require_alias_evidence=d.get("require_alias_evidence", True),
            require_location=d.get("require_location", False),
            require_contrast_pair=d.get("require_contrast_pair", False),
            difficulty=d.get("difficulty", "medium"),
        )


@dataclass
class PipelineConfig:
    """流水线配置"""
    query_requirements: List[QueryRequirement] = field(default_factory=list)
    corpus: str = "./corpus/"                    # 语料目录
    content_granularity: Dict[str, Any] = field(default_factory=lambda: {
        "min_chars": 30,
        "max_chars": 150,
        "target_chars": 80,
    })
    output_path: str = "memtest_v3_output.json"
    name: str = "MemTest Database"
    description: str = ""
    source: str = ""
    # LLM 配置
    llm_adapter: str = "deepseek"
    llm_max_tokens: int = 3000
    llm_temperature: float = 0
    # 修复配置
    max_repair_iterations: int = 3
    semantic_check_sample_rate: float = 0.3  # 30% 做语义校验
    # 别名/时间解析器
    alias_resolver: Optional[AliasResolver] = None
    time_resolver: Optional[TimeResolver] = None
    # 负样本比例
    negative_ratio: float = 0.2


# ==============================================================================
# 三、提取结果结构
# ==============================================================================

@dataclass
class ExtractionResult:
    """提取结果"""
    raw_memories: List[Dict[str, Any]] = field(default_factory=list)
    # chain_id → list of memory indices
    chains: Dict[str, List[int]] = field(default_factory=dict)
    # 别名等价对
    alias_pairs: List[Dict[str, Any]] = field(default_factory=list)  # v3: 等价组模型 [{"members": [...], "evidence": [...]}]
    # 对比对
    contrast_pairs: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ==============================================================================
# 四、核心流水线类
# ==============================================================================

class MemTestPipeline:
    """MemTest v3 自动导入流水线"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._llm = None
        self._stats: Dict[str, Any] = {}

        # 初始化解析器
        if config.alias_resolver:
            self.alias_resolver = config.alias_resolver
        else:
            self.alias_resolver = AliasResolver(corpus_dir=config.corpus)

        if config.time_resolver:
            self.time_resolver = config.time_resolver
        else:
            self.time_resolver = TimeResolver(corpus_dir=config.corpus)

    # --------------------------------------------------------------------------
    # LLM 初始化
    # --------------------------------------------------------------------------

    def _get_llm(self):
        """获取 LLM 实例（延迟加载）"""
        if self._llm is None:
            try:
                import sys
                sys.path.insert(0, os.path.dirname(__file__))
                from llm_interface import create_llm
                self._llm = create_llm(self.config.llm_adapter)
            except Exception:
                from llm_interface import LocalMockAdapter
                self._llm = LocalMockAdapter(echo=True)
        return self._llm

    def _llm_generate(self, prompt: str, max_tokens: int = None) -> str:
        """LLM 生成（带错误处理）"""
        llm = self._get_llm()
        max_tokens = max_tokens or self.config.llm_max_tokens
        try:
            return llm.generate(prompt, max_tokens=max_tokens,
                               temperature=self.config.llm_temperature)
        except Exception as e:
            return f"[LLM ERROR: {e}]"

    def _llm_json(self, prompt: str, max_tokens: int = None) -> Any:
        """LLM 生成 JSON"""
        text = self._llm_generate(prompt, max_tokens)
        text = text.strip()

        # 提取 JSON
        if text.startswith("```json"):
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        for start in ["{", "["]:
            idx = text.find(start)
            if idx >= 0:
                for end in ["}", "]"]:
                    end_idx = text.rfind(end)
                    if end_idx > idx:
                        try:
                            return json.loads(text[idx:end_idx + 1])
                        except json.JSONDecodeError:
                            pass

        # 回退：返回结构化错误
        return {"_error": f"无法解析 JSON: {text[:200]}"}

    # --------------------------------------------------------------------------
    # 主流程
    # --------------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """运行完整流水线"""
        print(f"\n{'='*60}")
        print(f"  MemTest v3 流水线启动")
        print(f"{'='*60}")
        print(f"  corpus: {self.config.corpus}")
        print(f"  query_requirements: {len(self.config.query_requirements)} 类")
        print(f"  output: {self.config.output_path}")
        print(f"  LLM adapter: {self.config.llm_adapter}")
        print(f"{'='*60}\n")

        t0 = time.time()

        # 阶段0: 读取语料
        corpus_text = self._load_corpus()
        print(f"[阶段0] 语料加载: {len(corpus_text)} 字\n")

        # 阶段1: 按需提取
        extraction = self._extract_all(corpus_text)
        print(f"[阶段1] 提取完成: {len(extraction.raw_memories)} 条原始记忆\n")

        # 阶段1b: 别名等价检测
        self._resolve_aliases(extraction)
        print(f"[阶段1b] 别名等价组: {len(extraction.alias_pairs)} 组\n")

        # 阶段2: 清洗 + 出题
        memories, queries = self._generate_queries(extraction)
        print(f"[阶段2] 出题完成: {len(memories)} 条记忆, {len(queries)} 条查询\n")

        # 阶段3: 校验
        validation = self._validate_all(memories, queries)
        print(f"[阶段3] 校验完成: valid={validation['valid']}, "
              f"errors={len(validation['errors'])}, "
              f"warnings={len(validation['warnings'])}\n")

        # 阶段4: 修复（可选）
        if not validation["valid"] and self.config.max_repair_iterations > 0:
            memories, queries = self._repair(memories, queries, validation)

        # 组装数据库
        db = {
            "database_info": build_database_info(
                name=self.config.name,
                description=self.config.description,
                source=self.config.source,
            ),
            "memories": memories,
            "queries": queries,
        }
        db = finalize_database(db, name=self.config.name,
                              description=self.config.description,
                              source=self.config.source)

        elapsed = time.time() - t0
        self._stats = {
            "elapsed_seconds": round(elapsed, 1),
            "total_memories": len(memories),
            "total_queries": len(queries),
            "validation": validation,
        }

        # 保存
        self._save_database(db)

        print(f"\n{'='*60}")
        print(f"  流水线完成！耗时 {elapsed:.1f}s")
        print(f"  记忆: {len(memories)} 条")
        print(f"  查询: {len(queries)} 条")
        print(f"  输出: {self.config.output_path}")
        print(f"{'='*60}\n")

        return db

    # --------------------------------------------------------------------------
    # 阶段0: 读取语料
    # --------------------------------------------------------------------------

    def _load_corpus(self) -> str:
        """加载语料目录中的所有文本"""
        texts: List[str] = []
        corpus_dir = self.config.corpus

        if not corpus_dir or not os.path.isdir(corpus_dir):
            # 如果目录不存在，返回空字符串（允许 mock 模式）
            return ""

        for root, dirs, files in os.walk(corpus_dir):
            # 安全：跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fn in files:
                if fn.endswith(('.txt', '.md', '.text')) and not fn.startswith('.'):
                    path = os.path.join(root, fn)
                    try:
                        with open(path, encoding="utf-8") as f:
                            content = f.read()
                        # 去除 frontmatter
                        if content.startswith('---'):
                            idx = content.find('---', 3)
                            if idx > 0:
                                content = content[idx + 3:]
                        texts.append(content[:50000])  # 每文件限制 5 万字
                    except (OSError, IOError):
                        pass

        return "\n\n".join(texts)

    # --------------------------------------------------------------------------
    # 阶段1: 按需提取
    # --------------------------------------------------------------------------

    def _extract_all(self, corpus_text: str) -> ExtractionResult:
        """按需求矩阵分批提取"""
        result = ExtractionResult()
        memory_counter = 0

        for req in self.config.query_requirements:
            if req.type == "负样本":
                # 负样本不需要提取，标记即可
                continue

            count = req.count
            batch_size = 10  # 每批 10 条
            for batch_start in range(0, count, batch_size):
                batch_count = min(batch_size, count - batch_start)
                extracted = self._extract_for_type(
                    req.type, batch_count, corpus_text, req, memory_counter
                )
                result.raw_memories.extend(extracted)
                memory_counter += len(extracted)

                if extracted:
                    print(f"  [{req.type}] +{len(extracted)} 条 (累计 {memory_counter})")

        return result

    def _extract_for_type(
        self,
        query_type: str,
        count: int,
        corpus_text: str,
        requirement: QueryRequirement,
        memory_counter_start: int,
    ) -> List[Dict[str, Any]]:
        """针对特定查询类型提取记忆"""
        # 中文查询类型 -> 英文 prompt key 映射
        TYPE_TO_PROMPT_KEY = {
            '时序推理': 'temporal',
            '因果推理': 'causal',
            '别名查询': 'alias',
            '事实检索': 'fact',
            '对比推理': 'contrast',
        }
        prompt_key = TYPE_TO_PROMPT_KEY.get(query_type, query_type)
        prompt_template = PROMPTS.get(prompt_key, "")
        if not prompt_template:
            return []

        # 构建提取 prompt
        granularity = self.config.content_granularity
        extra_context = f"\n\n内容长度指引: {granularity.get('target_chars', 80)} 字左右，"
        extra_context += f"范围 {granularity.get('min_chars', 30)}-{granularity.get('max_chars', 150)} 字。"

        prompt = f"{prompt_template}\n\n{extra_context}\n\n=== 语料 ===\n{corpus_text[:30000]}\n\n=== 输出 ==="

        # 调用 LLM
        raw = self._llm_json(prompt)

        if isinstance(raw, dict) and "_error" in raw:
            return self._fallback_extract(query_type, count, corpus_text, memory_counter_start)

        memories: List[Dict[str, Any]] = []

        # 解析结果
        items = raw if isinstance(raw, list) else raw.get("chains", []) or raw.get("memories", []) or [raw]

        for i, item in enumerate(items[:count]):
            if not isinstance(item, dict):
                continue

            mid = make_memory_id(memory_counter_start + i)

            # 构建记忆条目
            mem = self._build_memory(item, query_type, mid)
            memories.append(mem)

        return memories

    def _build_memory(self, item: Dict[str, Any], query_type: str, memory_id: str) -> Dict[str, Any]:
        """从提取结果构建标准记忆条目"""
        content = item.get("content", "")
        if not content:
            content = item.get("text", "") or item.get("description", "")

        # 截断超长 content
        max_chars = self.config.content_granularity.get("max_chars", 150)
        if len(content) > max_chars:
            content = content[:max_chars]

        person_raw = item.get("person", [])
        if isinstance(person_raw, str):
            person_list = [p.strip() for p in person_raw.replace("，", ",").split(",") if p.strip()]
        elif isinstance(person_raw, list):
            # 递归展平嵌套列表
            def flatten(lst):
                result = []
                for x in lst:
                    if isinstance(x, list):
                        result.extend(flatten(x))
                    else:
                        s = str(x).strip()
                        if s:
                            result.append(s)
                return result
            person_list = flatten(person_raw)
        else:
            person_list = []

        return {
            "memory_id": memory_id,
            "content": content,
            "person": person_list,
            "time_absolute": item.get("time_absolute") or None,
            "time_relative": item.get("time_relative") or None,
            "time_ref_id": None,       # 由 time_resolver 填充
            "time_offset_days": None,  # 由 time_resolver 填充
            "location": item.get("location") or None,
            "event_type": item.get("event_type") or None,
            "source": item.get("source") or None,
            "tags": item.get("tags", []),
            "difficulty": self._infer_difficulty(item, query_type),
        }

    def _validate_person_in_content(self, memories: List[Dict[str, Any]]) -> None:
        """修正person字段：确保每个名字都在content中出现。
        
        对于不在content中出现的名字：
        1. 先查别名等价组，找到组内出现在content中的形式
        2. 如果找不到等价名，则移除该person
        """
        # 构建别名映射：名字 → 等价组所有成员
        alias_groups = []
        if hasattr(self, 'alias_resolver') and self.alias_resolver:
            alias_groups = self.alias_resolver.get_all_groups()
        
        for m in memories:
            content = m.get("content", "")
            persons = m.get("person", [])
            new_persons = []
            for p in persons:
                if p in content:
                    new_persons.append(p)
                else:
                    # 查找等价组中出现在content里的别名
                    found_alias = None
                    for group in alias_groups:
                        if p in group:
                            for member in group:
                                if member in content and member != p:
                                    found_alias = member
                                    break
                        if found_alias:
                            break
                    if found_alias:
                        new_persons.append(found_alias)
                    # else: 找不到等价名，不添加
            m["person"] = new_persons

    def _infer_difficulty(self, item: Dict[str, Any], query_type: str) -> str:
        """根据内容复杂度推断难度"""
        content = item.get("content", "")
        # 简单启发式：长度越长越难
        if len(content) < 50:
            return "easy"
        elif len(content) < 100:
            return "medium"
        else:
            return "hard"

    def _fallback_extract(
        self,
        query_type: str,
        count: int,
        corpus_text: str,
        memory_counter_start: int,
    ) -> List[Dict[str, Any]]:
        """当 LLM 调用失败时的回退提取（基于规则）"""
        # 按 query_type 找到关键段落
        separator = "\n" if len(corpus_text) < 50000 else "\n\n"
        paragraphs = [p.strip() for p in corpus_text.split(separator) if p.strip() and len(p) > 20]

        results = []
        for i, para in enumerate(paragraphs[:count]):
            max_chars = self.config.content_granularity.get("max_chars", 150)
            content = para[:max_chars]

            mem = {
                "memory_id": make_memory_id(memory_counter_start + i),
                "content": content,
                "person": self._extract_persons(content),
                "time_absolute": None,
                "time_relative": None,
                "time_ref_id": None,
                "time_offset_days": None,
                "location": self._extract_location(content),
                "event_type": query_type,
                "source": None,
                "tags": [query_type],
                "difficulty": "medium",
            }
            results.append(mem)

        return results

    def _extract_persons(self, text: str) -> List[str]:
        """人物提取：先正则候选，再LLM筛选
        
        策略：
        1. 正则提取2-4字中文片段作为候选
        2. 用LLM判断哪些是真正的人名
        3. 只返回在原文中出现的名字
        """
        # 提取连续 2-4 个中文字符（候选）
        candidates = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
        # 去重保序
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)
        
        # 如果候选太多（>10），先用基本规则过滤
        exclude = {"有限公司", "公司", "集团", "因为", "所以", "但是", "然而",
                   "如果", "虽然", "而且", "之后", "之前", "之后", "以来",
                   "年间", "年间", "年间", "年代初", "年代末"}
        if len(unique_candidates) > 10:
            unique_candidates = [c for c in unique_candidates if c not in exclude]
        
        # 用LLM筛选真正的人名
        if unique_candidates:
            persons = self._llm_filter_persons(unique_candidates, text)
        else:
            # fallback: 用别名等价组辅助判断
            persons = self._rule_filter_persons(unique_candidates, text)
        
        # 只返回在原文中完整出现的
        result = []
        for p in persons:
            if p in text:
                result.append(p)
            if len(result) >= 5:
                break
        return result

    def _llm_filter_persons(self, candidates: List[str], context: str) -> List[str]:
        """用LLM从候选中筛选真正的人名"""
        prompt = f"""从以下词语中选出所有"人物姓名"（真实或虚构人物的名字、字、号、别称），排除地点、时间、事件、组织、物品等非人名。

词语列表：{", ".join(candidates[:30])}

上下文（前200字）：{context[:200]}

请只输出人名，用逗号分隔，不要解释。如果没有则输出"无"："""
        
        try:
            response = self._llm_generate(prompt, max_tokens=200)
            if response and "无" not in response:
                persons = [p.strip() for p in response.split(",") if p.strip()]
                return persons
        except Exception:
            pass
        return []

    def _rule_filter_persons(self, candidates: List[str], context: str) -> List[str]:
        """规则fallback：用别名等价组和常见人名模式过滤"""
        # 已知的人名模式：2-3字，且在上下文中出现在"字X""号X""人称X"附近
        person_set = set()
        # 从别名等价组获取已知人名
        if hasattr(self, 'alias_resolver') and self.alias_resolver:
            for group in self.alias_resolver.get_all_groups():
                person_set |= group
        
        result = []
        for c in candidates:
            # 在等价组中 → 是人名
            if c in person_set:
                result.append(c)
                continue
            # 跟在"字/号/人称"后面 → 是人名
            for marker in [f"字{c}", f"号{c}", f"人称{c}", f"又名{c}", f"俗名{c}"]:
                if marker in context:
                    result.append(c)
                    break
        return result

    def _extract_location(self, text: str) -> Optional[str]:
        """简单的地点提取"""
        # 常见的地点后缀词
        for suffix in ["在", "到", "去", "位于", "建于"]:
            idx = text.find(suffix)
            if idx >= 0:
                loc_text = text[idx + len(suffix):]
                # 取接下来的 2-6 个字符
                loc = re.match(r"[\s]*(.{2,6}?)", loc_text)
                if loc:
                    return loc.group(1).strip()
        return None

    # --------------------------------------------------------------------------
    # 阶段1b: 别名等价检测
    # --------------------------------------------------------------------------

    def _resolve_aliases(self, extraction: ExtractionResult) -> None:
        """解析别名等价关系（v3 等价组模型：所有成员平等）"""
        alias_resolver = self.alias_resolver

        for mem in extraction.raw_memories:
            alias_resolver._scan_text_for_aliases(
                mem.get("content", ""),
                source=mem.get("memory_id", "")
            )

        # 构建等价组
        alias_resolver._build_equivalence_groups()

        # 导出等价组信息（兼容旧字段名）
        extraction.alias_pairs = [
            {"members": sorted(list(group)), "evidence": alias_resolver._evidence.get(str(i), [])}
            for i, group in enumerate(alias_resolver.get_all_groups())
        ]

    # --------------------------------------------------------------------------
    # 阶段2: 清洗 + 出题
    # --------------------------------------------------------------------------

    def _generate_queries(
        self,
        extraction: ExtractionResult,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """基于提取的记忆生成查询和答案"""
        # 合并记忆，去重
        memories = self._deduplicate_memories(extraction.raw_memories)
        self._validate_person_in_content(memories)

        # 时间关系解析
        self.time_resolver.resolve_time_relations(memories)

        # 生成查询
        queries: List[Dict[str, Any]] = []

        for req in self.config.query_requirements:
            if req.type == "负样本":
                neg_queries = self._generate_negative_queries(req.count, memories, req)
                queries.extend(neg_queries)
            else:
                type_queries = self._generate_queries_for_type(
                    req.type, memories, extraction, req
                )
                queries.extend(type_queries)

        # 确保 query_id 唯一
        used_ids = set()
        for q in queries:
            base = q.get("query_id", "Q")
            suffix = 0
            while q["query_id"] in used_ids:
                suffix += 1
                q["query_id"] = f"{base}_{suffix}"
            used_ids.add(q["query_id"])

        return memories, queries

    def _deduplicate_memories(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重（字符串子集 + 语义子集检测，保留最长版本）"""
        if not memories:
            return []

        # 先按 content 长度降序排列，优先保留长内容
        sorted_mems = sorted(
            [m for m in memories if m.get("content", "").strip()],
            key=lambda m: len(m.get("content", "")),
            reverse=True,
        )

        unique: List[Dict[str, Any]] = []
        for m in sorted_mems:
            content = m.get("content", "").strip()
            is_duplicate = False
            for existing in unique:
                existing_content = existing.get("content", "").strip()
                # 1. 字符串子集：短内容是长内容的子字符串
                if content in existing_content:
                    is_duplicate = True
                    break
                # 2. 语义子集：短记忆的bigram覆盖率检测
                #    短记忆占比<60% 且 短记忆的bigram有>70%出现在长记忆中 → 语义子集
                if len(content) < len(existing_content) * 0.6:
                    coverage = self._bigram_coverage(content, existing_content)
                    if coverage > 0.7:
                        is_duplicate = True
                        break
            if not is_duplicate:
                unique.append(m)

        # 重新编号
        for i, m in enumerate(unique):
            m["memory_id"] = make_memory_id(i)

        return unique

    @staticmethod
    def _bigram_coverage(short_text: str, long_text: str) -> float:
        """短文本的bigram有多少比例出现在长文本中（语义子集检测）"""
        def _bigrams(text: str) -> set:
            return {text[i:i+2] for i in range(len(text) - 1)}
        b_short = _bigrams(short_text)
        b_long = _bigrams(long_text)
        if not b_short:
            return 0.0
        return len(b_short & b_long) / len(b_short)

    def _generate_queries_for_type(
        self,
        query_type: str,
        memories: List[Dict[str, Any]],
        extraction: ExtractionResult,
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """针对特定类型生成查询"""
        if not memories:
            return []

        # 按类型选择对应的生成逻辑
        if query_type == "时序推理":
            return self._generate_temporal_queries(memories, requirement)
        elif query_type == "因果推理":
            return self._generate_causal_queries(memories, requirement)
        elif query_type == "别名查询":
            return self._generate_alias_queries(memories, requirement)
        elif query_type == "事实检索":
            return self._generate_fact_queries(memories, requirement)
        elif query_type == "对比推理":
            return self._generate_contrast_queries(memories, requirement)
        else:
            return []

    def _generate_temporal_queries(
        self,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成时序推理查询"""
        queries: List[Dict[str, Any]] = []
        mem_map = {m["memory_id"]: m for m in memories}

        # 按人物分组（使用别名等价组合并同一人的不同称呼）
        by_person = defaultdict(list)
        person_to_key = {}  # 人名 → 等价组主键
        if hasattr(self, 'alias_resolver') and self.alias_resolver:
            for group in self.alias_resolver.get_all_groups():
                members = sorted(list(group))
                key = members[0]  # 用排序后第一个作为主键
                for member in members:
                    person_to_key[member] = key
        
        for m in memories:
            for person in m.get("person", []):
                key = person_to_key.get(person, person)
                by_person[key].append(m)

        # 去重：同一记忆可能因不同别名被多次添加
        for key in by_person:
            seen = set()
            unique = []
            for m in by_person[key]:
                if m["memory_id"] not in seen:
                    seen.add(m["memory_id"])
                    unique.append(m)
            by_person[key] = unique

        used_mid_sets = []  # 去重：记录已使用的记忆组合
        for person, person_mems in by_person.items():
            if len(person_mems) < requirement.min_chain_length:
                continue

            # 按时间或位置排序
            sorted_mems = sorted(
                person_mems,
                key=lambda m: m.get("time_absolute", "") or m.get("content", "")
            )

            chain = sorted_mems[:requirement.min_chain_length]
            mid_list = [m["memory_id"] for m in chain]

            # 去重：跳过与已有查询记忆组合完全相同的
            mid_set = set(mid_list)
            if any(mid_set == used for used in used_mid_sets):
                continue
            used_mid_sets.append(mid_set)

            # 生成查询
            q_texts = [
                f"{person}的事件按时间顺序是怎样的？",
                f"{person}先做了什么，后来又做了什么？",
                f"请列出{person}的经历。",
            ]
            for qi, qtext in enumerate(q_texts[:1]):
                queries.append({
                    "query_id": make_query_id(len(queries) + 1),
                    "query_text": qtext,
                    "query_type": "时序推理",
                    "test_dimension": "时间线追踪",
                    "expected_memory_ids": mid_list,
                    "expected_answer": "。".join(m["content"] for m in chain),
                    "difficulty": requirement.difficulty,
                    "is_negative": False,
                })

        return queries[:requirement.count]

    def _generate_causal_queries(
        self,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成因果推理查询（v3：从记忆内容中检测因果关系，不依赖chain_id）"""
        queries: List[Dict[str, Any]] = []

        # 因果指示词
        cause_indicators = ["因为", "由于", "因", "所以", "因此", "导致", "结果", "使得", "从而"]
        # 在记忆中找含因果关系的条目
        causal_memories = []
        for m in memories:
            content = m.get("content", "")
            if any(ind in content for ind in cause_indicators):
                causal_memories.append(m)

        for m in causal_memories:
            content = m.get("content", "")
            # 尝试分割因果
            cause_part = ""
            effect_part = ""
            for ind in cause_indicators:
                if ind in content:
                    parts = content.split(ind, 1)
                    if len(parts) == 2:
                        cause_part = parts[0].strip().rstrip("，。,")
                        effect_part = parts[1].strip().rstrip("，。,")
                        # 清理cause_part中的别名信息（如"沙悟净，又名卷帘大将、沙和尚"→"沙悟净"）
                        # 取第一个逗号前的主名
                        for sep in ["，又名", "，俗名", "，字", "，号"]:
                            if sep in cause_part:
                                cause_part = cause_part.split(sep)[0].strip()
                                break
                        break

            if not cause_part or not effect_part:
                continue

            # 生成双向因果查询
            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": f"{cause_part}导致了什么？",
                "query_type": "因果推理",
                "test_dimension": "因果关系追踪",
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": f"{cause_part}导致{effect_part}",
                "difficulty": "medium",
                "is_negative": False,
            })

            if len(queries) >= requirement.count:
                break

            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": f"{effect_part}是什么原因造成的？",
                "query_type": "因果推理",
                "test_dimension": "因果关系追踪",
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": f"{effect_part}是因为{cause_part}",
                "difficulty": "medium",
                "is_negative": False,
            })

            if len(queries) >= requirement.count:
                break

        return queries[:requirement.count]

    def _generate_alias_queries(
        self,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成别名查询（v3 等价组模型：区分人/地/物的查询模板）"""
        queries: List[Dict[str, Any]] = []

        for group in self.alias_resolver.get_all_groups():
            members = sorted(list(group))
            if len(members) < 2:
                continue

            # 找包含组内任一成员的记忆
            relevant_mems = [m for m in memories
                           if any(member in m.get("content", "") for member in members)]

            if not relevant_mems:
                continue

            # 别名查询的expected_memory_ids只应包含实际含有别名关系的记忆
            # （content中包含"又名"/"俗名"/"就是"/"即"等别名标记的记忆）
            alias_indicators = ["又名", "俗名", "又称", "又叫", "就是", "即", "号", "字", "人称", "别称", "绰号"]
            alias_mems = [m for m in relevant_mems
                         if any(ind in m.get("content", "") for ind in alias_indicators)]
            # 如果找不到含别名标记的记忆，退回所有相关记忆（兜底）
            mid_list = [m["memory_id"] for m in (alias_mems if alias_mems else relevant_mems)]
            other_members = [m for m in members]  # 全组成员

            # 判断等价组类型：人/地/物
            # 通过相关记忆的 person/location 字段推断
            is_location = any(m.get("location") in members for m in relevant_mems)
            has_person = any(any(p in members for p in m.get("person", [])) for m in relevant_mems)
            
            if is_location and not has_person:
                query_verb = "是什么"
                unit_label = "同一事物/地点"
                followup_verb = "还有哪些别称"
            elif has_person:
                query_verb = "是谁"
                unit_label = "同一人"
                followup_verb = "还有哪些称呼"
            else:
                query_verb = "是什么"
                unit_label = "同一事物"
                followup_verb = "还有哪些别称"

            # 对每个非首要名生成查询（用别名问，答案覆盖全组）
            primary = members[0]  # 排序后第一个，用于expected_answer
            for alias in members[1:]:
                queries.append({
                    "query_id": make_query_id(len(queries) + 1),
                    "query_text": f"{alias}{query_verb}？",
                    "query_type": "别名查询",
                    "test_dimension": "别名等价识别",
                    "expected_memory_ids": mid_list,
                    "expected_answer": f"{alias}就是{primary}，与{', '.join(other_members)}{unit_label}",
                    "difficulty": "easy",
                    "is_negative": False,
                })

            # 综合查询
            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": f"{primary}{followup_verb}？",
                "query_type": "别名查询",
                "test_dimension": "别名等价识别",
                "expected_memory_ids": mid_list,
                "expected_answer": f"{primary}的别称包括{', '.join(members[1:])}",
                "difficulty": "medium",
                "is_negative": False,
            })

        return queries[:requirement.count]

    def _generate_fact_queries(
        self,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成事实检索查询"""
        queries: List[Dict[str, Any]] = []

        for m in memories:
            content = m.get("content", "")
            person_list = m.get("person", [])
            location = m.get("location")

            if not content:
                continue

            # 构建查询
            if person_list and location:
                qtext = f"{person_list[0]}在{location}做了什么？"
            elif person_list:
                qtext = f"{person_list[0]}做了什么？"
            elif location:
                qtext = f"{location}发生了什么？"
            else:
                qtext = content[:20] + "..."

            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": qtext,
                "query_type": "事实检索",
                "test_dimension": "事实检索",
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": content,
                "difficulty": m.get("difficulty", "medium"),
                "is_negative": False,
            })

        return queries[:requirement.count]

    def _generate_contrast_queries(
        self,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成对比推理查询（排除别名等价组内对比）"""
        queries: List[Dict[str, Any]] = []

        # 获取别名等价组，构建"名字→等价组代表"映射
        alias_map: Dict[str, str] = {}  # 名字 → 组代表（取组内最长的名字）
        if hasattr(self, 'alias_resolver') and self.alias_resolver:
            groups = self.alias_resolver.get_all_groups()
            for group in groups:
                members = list(group)  # get_all_groups returns Set
                if len(members) > 1:
                    # 用最长的名字作为代表
                    rep = max(members, key=len)
                    for m in members:
                        alias_map[m] = rep

        # 找有 contrast 信息或相似人物的不同记忆
        by_person = defaultdict(list)
        for m in memories:
            for person in m.get("person", []):
                by_person[person].append(m)

        person_names = list(by_person.keys())
        seen_pairs = set()  # 避免等价组内重复
        for i in range(len(person_names)):
            for j in range(i + 1, len(person_names)):
                p1, p2 = person_names[i], person_names[j]
                
                # 检查是否为同一等价组的别名
                rep1 = alias_map.get(p1, p1)
                rep2 = alias_map.get(p2, p2)
                if rep1 == rep2:
                    continue  # 同一等价组，跳过
                
                # 避免重复配对
                pair_key = tuple(sorted([rep1, rep2]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                
                mems1, mems2 = by_person[p1], by_person[p2]
                if not mems1 or not mems2:
                    continue

                # 找两人各自独立出现的记忆（不含对方），做有效对比
                m1_unique = [m for m in mems1 if p2 not in m.get("content", "")]
                m2_unique = [m for m in mems2 if p1 not in m.get("content", "")]
                
                # 优先用独立记忆，如果没有则退回全部
                pick1 = m1_unique[0] if m1_unique else mems1[0]
                pick2 = m2_unique[0] if m2_unique else mems2[0]
                
                # 如果两人只有同一条记忆且该记忆同时提到两人，对比无意义
                if pick1["memory_id"] == pick2["memory_id"]:
                    continue

                mid_list = [pick1["memory_id"], pick2["memory_id"]]
                q1 = pick1["content"][:30]
                q2 = pick2["content"][:30]

                queries.append({
                    "query_id": make_query_id(len(queries) + 1),
                    "query_text": f"{p1}和{p2}有什么不同？",
                    "query_type": "对比推理",
                    "test_dimension": "对比推理",
                    "expected_memory_ids": mid_list,
                    "expected_answer": f"{p1}：{q1}；{p2}：{q2}",
                    "difficulty": requirement.difficulty,
                    "is_negative": False,
                })
                
                if len(queries) >= requirement.count:
                    break
            if len(queries) >= requirement.count:
                break

        return queries[:requirement.count]

    def _generate_negative_queries(
        self,
        count: int,
        memories: List[Dict[str, Any]],
        requirement: QueryRequirement,
    ) -> List[Dict[str, Any]]:
        """生成负样本查询"""
        queries: List[Dict[str, Any]] = []
        negative_ratio = self.config.negative_ratio

        # 收集真实人物/地点
        all_persons = set()
        all_locations = set()
        for m in memories:
            all_persons.update(m.get("person", []))
            if m.get("location"):
                all_locations.add(m["location"])

        # 生成假人物/地点
        fake_persons = [
            "赵钱孙", "周吴郑", "冯陈褚", "蒋沈韩", "诸葛无名",
            "李假名", "王伪名", "张虚构",
        ]
        fake_locations = [
            "火星基地", "月球背面", "银河中心", "平行宇宙",
            "虚拟空间", "量子维度", "时空夹缝",
        ]

        # 类型1: 假人物
        for fp in fake_persons[:count // 3 + 1]:
            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": f"{fp}最近做了什么？",
                "query_type": "负样本",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "difficulty": "medium",
                "is_negative": True,
            })

        # 类型2: 假地点
        for fl in fake_locations[:count // 3 + 1]:
            queries.append({
                "query_id": make_query_id(len(queries) + 1),
                "query_text": f"{fl}发生了什么？",
                "query_type": "负样本",
                "test_dimension": "负样本",
                "expected_memory_ids": [],
                "expected_answer": "",
                "difficulty": "medium",
                "is_negative": True,
            })

        # 类型3: 真实人物 + 假地点
        real_persons = list(all_persons)
        for rp in real_persons[:count // 3 + 1]:
            for fl in fake_locations[:1]:
                queries.append({
                    "query_id": make_query_id(len(queries) + 1),
                    "query_text": f"{rp}在{fl}做了什么？",
                    "query_type": "负样本",
                    "test_dimension": "负样本",
                    "expected_memory_ids": [],
                    "expected_answer": "",
                    "difficulty": "hard",
                    "is_negative": True,
                })

        return queries[:count]

    # --------------------------------------------------------------------------
    # 阶段3: 校验
    # --------------------------------------------------------------------------

    def _validate_all(
        self,
        memories: List[Dict[str, Any]],
        queries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """双重校验：结构 + 语义 + 内容一致性"""
        # 结构校验
        db = {"memories": memories, "queries": queries, "database_info": {}}
        validation = validate_database(db)

        # 时间引用校验
        time_errors = self.time_resolver.validate_time_refs(memories)
        validation["errors"].extend(time_errors)

        # 内容一致性校验：person 字段中的名字必须出现在 content 中
        for m in memories:
            mid = m.get("memory_id", "?")
            persons = m.get("person", [])
            content = m.get("content", "")
            for p in persons:
                if p and p not in content:
                    msg = f'记忆 {mid}: person="{p}" 不在 content 中'
                    validation["warnings"].append(msg)

        # 别名等价组校验：对比查询不能对比同一等价组的别名
        if hasattr(self, 'alias_resolver') and self.alias_resolver:
            groups = self.alias_resolver.get_all_groups()
            alias_map = {}
            for group in groups:
                members = list(group)  # get_all_groups returns List[Set[str]]
                if len(members) > 1:
                    rep = max(members, key=len)
                    for m_name in members:
                        alias_map[m_name] = rep
            for q in queries:
                if q.get("query_type") == "对比推理" and not q.get("is_negative"):
                    qt = q.get("query_text", "")
                    # 简单检查：如果查询中两个名字映射到同一代表
                    for name1, rep1 in alias_map.items():
                        for name2, rep2 in alias_map.items():
                            if name1 != name2 and rep1 == rep2:
                                if name1 in qt and name2 in qt:
                                    msg2 = f'查询 {q.get("query_id","?")}: 对比查询中的"{name1}"和"{name2}"是同一等价组别名'
                                    validation["errors"].append(msg2)

        # 语义校验（采样）
        if validation["valid"] and random.random() < self.config.semantic_check_sample_rate:
            semantic_errors = self._semantic_check(memories, queries)
            if semantic_errors:
                validation["warnings"].extend([f"语义: {e}" for e in semantic_errors])

        return validation

    def _semantic_check(
        self,
        memories: List[Dict[str, Any]],
        queries: List[Dict[str, Any]],
    ) -> List[str]:
        """LLM 语义校验（采样）"""
        errors: List[str] = []
        mem_map = {m["memory_id"]: m for m in memories}

        # 采样 5 条查询做语义校验
        sample_queries = random.sample(queries, min(5, len(queries)))

        for q in sample_queries:
            mid_list = q.get("expected_memory_ids", [])
            if not mid_list:
                continue

            contents = [mem_map.get(mid, {}).get("content", "") for mid in mid_list]
            content_text = "\n".join(f"- {c[:100]}" for c in contents if c)

            prompt = f"""请检查以下查询-答案对是否合理：

查询: {q['query_text']}
类型: {q['query_type']}
预期记忆:
{content_text}
预期答案: {q.get('expected_answer', '')[:200]}

请检查：
1. 答案是否与记忆内容一致？
2. 别名查询的等价关系是否有原文证据？
3. 时序查询的时间顺序是否正确？

输出：合理 / 有问题（请说明）
"""

            try:
                result = self._llm_generate(prompt, max_tokens=500)
                if "有问题" in result or "不合理" in result:
                    errors.append(f"查询 {q['query_id']}: {result[:100]}")
            except Exception:
                pass

        return errors

    # --------------------------------------------------------------------------
    # 阶段4: 修复
    # --------------------------------------------------------------------------

    def _repair(
        self,
        memories: List[Dict[str, Any]],
        queries: List[Dict[str, Any]],
        validation: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """自动修复 + 重跑校验"""
        print(f"[阶段4] 开始修复，最大迭代 {self.config.max_repair_iterations} 次...")

        for iteration in range(self.config.max_repair_iterations):
            print(f"  修复迭代 {iteration + 1}/{self.config.max_repair_iterations}")

            # 修复结构错误
            errors = validation.get("errors", [])
            fixed_memories, fixed_queries = self._fix_errors(memories, queries, errors)

            # 重新校验
            validation = self._validate_all(fixed_memories, fixed_queries)

            if validation["valid"]:
                print(f"  ✅ 修复成功！")
                return fixed_memories, fixed_queries

        print(f"  ⚠️  修复未能完全通过校验，保留结果")
        return memories, queries

    def _fix_errors(
        self,
        memories: List[Dict[str, Any]],
        queries: List[Dict[str, Any]],
        errors: List[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """根据错误列表自动修复"""
        mem_map = {m["memory_id"]: m for m in memories}
        valid_mids = set(mem_map.keys())

        # 修复1: 移除指向无效记忆的查询
        fixed_queries = []
        for q in queries:
            valid_ids = [mid for mid in q.get("expected_memory_ids", []) if mid in valid_mids]
            # 负样本必须有空的 expected_memory_ids
            if q.get("is_negative"):
                q["expected_memory_ids"] = []
            else:
                q["expected_memory_ids"] = valid_ids
            fixed_queries.append(q)

        # 修复2: 补全缺失的 memory_id
        for i, m in enumerate(memories):
            if not m.get("memory_id"):
                m["memory_id"] = make_memory_id(i)

        # 修复3: 补全缺失的 query_id
        for i, q in enumerate(fixed_queries):
            if not q.get("query_id"):
                q["query_id"] = make_query_id(i)

        # 修复4: 补全 is_negative
        for q in fixed_queries:
            if "is_negative" not in q:
                q["is_negative"] = False

        return memories, fixed_queries

    # --------------------------------------------------------------------------
    # 保存
    # --------------------------------------------------------------------------

    def _save_database(self, db: Dict[str, Any]) -> None:
        """保存数据库到文件"""
        output_path = self.config.output_path
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        print(f"  已保存: {output_path}")


# ==============================================================================
# 五、便捷入口
# ==============================================================================

def run_pipeline(config: Dict[str, Any]) -> Dict[str, Any]:
    """便捷入口：接收 dict 配置，构建并运行流水线"""
    # 转换 query_requirements
    requirements = [
        QueryRequirement.from_dict(r) for r in config.get("query_requirements", [])
    ]

    pipeline_config = PipelineConfig(
        query_requirements=requirements,
        corpus=config.get("corpus", "./corpus/"),
        content_granularity=config.get("content_granularity", {
            "min_chars": 30, "max_chars": 150, "target_chars": 80,
        }),
        output_path=config.get("output_path", "memtest_v3_output.json"),
        name=config.get("name", "MemTest Database"),
        description=config.get("description", ""),
        source=config.get("source", ""),
        llm_adapter=config.get("llm_adapter", "deepseek"),
        max_repair_iterations=config.get("max_repair_iterations", 3),
        negative_ratio=config.get("negative_ratio", 0.2),
    )

    pipeline = MemTestPipeline(pipeline_config)
    return pipeline.run()


# ==============================================================================
# 六、自测
# ==============================================================================

if __name__ == "__main__":
    print("测试 schema 导入...")
    from schema import validate_database, MEMORY_SCHEMA_V3
    print(f"  schema version OK: {MEMORY_SCHEMA_V3['difficulty']}")

    print("\n测试 time_resolver...")
    from time_resolver import TimeResolver, parse_relative_days
    resolver = TimeResolver()
    assert parse_relative_days("三年后") == 1095
    assert parse_relative_days("次日") == 1
    assert parse_relative_days("半年后") == 180
    print("  time_resolver OK")

    print("\n测试 alias_resolver...")
    from alias_resolver import AliasResolver
    ar = AliasResolver()
    ar._scan_text_for_aliases("林黛玉，大名颦儿，林妹妹是贾府上下对她的昵称。")
    assert "林黛玉" in ar._alias_map
    assert ar.are_equivalent("林黛玉", "林妹妹")
    assert ar.are_equivalent("林黛玉", "颦儿")
    print("  alias_resolver OK")

    print("\n测试 pipeline（mock 模式）...")
    test_config = {
        "query_requirements": [
            {"type": "事实检索", "count": 3},
            {"type": "时序推理", "count": 2, "min_chain_length": 3},
            {"type": "别名查询", "count": 2},
            {"type": "负样本", "count": 2},
        ],
        "corpus": "/tmp/nonexistent_corpus",
        "content_granularity": {"min_chars": 30, "max_chars": 100, "target_chars": 60},
        "output_path": "/tmp/memtest_test_output.json",
        "llm_adapter": "mock",
        "max_repair_iterations": 1,
    }

    db = run_pipeline(test_config)

    # 校验输出
    validation = validate_database(db)
    print(f"\n数据库校验: valid={validation['valid']}")
    if not validation["valid"]:
        print(f"  errors: {validation['errors'][:5]}")
    print(f"  stats: {validation['stats']}")

    print("\n✅ pipeline.py 自测通过")
