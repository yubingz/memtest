#!/usr/bin/env python3
"""MemTest v4 记忆提取器

从语料中提取结构化记忆。只在这一步使用LLM，其余步骤纯规则。

用法:
    from extractor import MemoryExtractor
    from llm_interface import create_llm

    llm = create_llm()  # 需要 DEEPSEEK_API_KEY 或 OPENAI_API_KEY
    extractor = MemoryExtractor(llm)
    memories = extractor.extract("./my_corpus/", default_source="我的语料")

无 LLM 时：
    会使用规则提取（段落分割 + 正则提取人物/别名），质量较低但能跑。
    建议生产环境务必使用 LLM。
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

# 尝试导入LLM接口
try:
    from llm_interface import create_llm, DeepSeekAdapter
except ImportError:
    create_llm = None
    DeepSeekAdapter = None

# 常见中文姓氏（用于规则提取人名）
COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵堪汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程"
    "嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗"
    "山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶"
    "郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳"
    "逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连"
    "茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚"
    "越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾母沙乜养鞠须丰巢关蒯相查后荆红"
)

# 别名检测正则
ALIAS_PATTERNS = [
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]?\s*(?:人称|又名|又称|又叫|即|也就是|便是)\s*([\u4e00-\u9fff]{1,20})"), "称谓"),
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]\s*(?:俗名|绰号|号|字|别号|雅号|昵称)\s*([\u4e00-\u9fff]{1,20})"), "字號"),
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*(?:就是|便是|即是|等于)\s*([\u4e00-\u9fff]{1,20})"), "等价"),
]

# 别名噪音过滤
NOISE_WORDS = {"指的", "这种", "那个", "这是", "也就是", "的", "了", "在", "是", "有", "和", "与", "被", "把"}

# LLM提取提示词
EXTRACT_PROMPT = """从以下文本中提取所有有意义的记忆片段。

每条记忆输出一行JSON，格式：
{"content": "记忆原文", "person": ["人物1", "人物2"], "location": "地点", "time_absolute": "绝对时间", "time_relative": "相对时间", "event_type": "事件类型"}

要求：
1. content必须是原文中的句子或段落，不要改写
2. person是人物列表，包括所有提到的人物
3. 如果有别名关系（如"刘备，字玄德"），在person中同时列出两个名字
4. location可为空字符串
5. time_absolute: 有明确年月日的写日期，没有的留空
6. time_relative: 只有相对时间表述（如"三年后"）时填写
7. event_type: 如"战争""外交""出生""日常"等

输出纯JSON数组，不要其他内容。"""


# ==============================================================================
# 提取器
# ==============================================================================

class MemoryExtractor:
    """从语料提取结构化记忆（v4格式）"""

    def __init__(self, llm_adapter=None, seed=42):
        self.llm = llm_adapter
        self.seed = seed
        if llm_adapter is None:
            print("⚠️  未提供LLM适配器，将使用规则提取（质量较低，建议配置API key）")

    def extract(self, corpus_dir: str, default_source: str = None) -> List[Dict[str, Any]]:
        """从语料目录提取结构化记忆

        Args:
            corpus_dir: 语料目录路径或单个文件路径
            default_source: 默认来源名（如"三国演义"），用于填充source字段

        Returns:
            v4格式记忆列表
        """
        corpus_text = self._load_corpus(corpus_dir)
        if not corpus_text:
            print(f"⚠️  语料为空: {corpus_dir}")
            return []

        if default_source is None:
            default_source = self._infer_source(corpus_dir)

        # LLM or rule-based extraction
        if self.llm:
            memories = self._llm_extract(corpus_text)
        else:
            memories = self._rule_extract(corpus_text)

        # Post-process
        memories = self._postprocess(memories)

        # Fill missing source
        if default_source:
            for m in memories:
                if not m.get("source"):
                    m["source"] = default_source

        return memories

    # --------------------------------------------------------------------------
    # 语料加载
    # --------------------------------------------------------------------------

    def _load_corpus(self, corpus_dir: str) -> str:
        """加载语料文件"""
        if os.path.isfile(corpus_dir):
            with open(corpus_dir, "r", encoding="utf-8") as f:
                return f.read()

        if not os.path.isdir(corpus_dir):
            print(f"⚠️  路径不存在: {corpus_dir}")
            return ""

        chunks = []
        for fname in sorted(os.listdir(corpus_dir)):
            if fname.endswith((".md", ".txt")):
                fpath = os.path.join(corpus_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    chunks.append(f.read())

        if not chunks:
            print(f"⚠️  目录中没有 .md/.txt 文件: {corpus_dir}")
            return ""

        return "\n\n".join(chunks)

    def _infer_source(self, corpus_dir: str) -> str:
        """从目录名/文件名推断来源"""
        name_map = {
            "xiyouji": "西游记", "xi_you_ji": "西游记",
            "sgyy": "三国演义", "sanguo_yanyi": "三国演义",
            "hongloumeng": "红楼梦", "hong_lou_meng": "红楼梦",
            "jinyong": "金庸小说",
            "shuihu": "水浒传", "shuihu_zhuan": "水浒传",
        }

        if os.path.isdir(corpus_dir):
            for fname in os.listdir(corpus_dir):
                base = os.path.splitext(fname)[0].lower()
                if base in name_map:
                    return name_map[base]

        # Try directory name
        dirname = os.path.basename(os.path.normpath(corpus_dir)).lower()
        return name_map.get(dirname, dirname)

    # --------------------------------------------------------------------------
    # LLM 提取
    # --------------------------------------------------------------------------

    def _llm_extract(self, corpus_text: str) -> List[Dict[str, Any]]:
        """使用LLM提取记忆"""
        # Split into chunks
        chunks = self._split_chunks(corpus_text, max_chars=3000)
        all_memories = []

        for i, chunk in enumerate(chunks):
            prompt = f"{EXTRACT_PROMPT}\n\n=== 文本 ===\n{chunk}\n\n=== 输出 ==="
            print(f"  [Chunk {i+1}/{len(chunks)}] Extracting... ({len(chunk)} chars)", flush=True)

            try:
                raw_text = self.llm.generate(prompt, max_tokens=4000)
                memories = self._parse_llm_output(raw_text)
                all_memories.extend(memories)
            except Exception as e:
                print(f"  ⚠️  Chunk {i+1} LLM error: {e}")
                # Fallback to rule extraction for this chunk
                rule_mems = self._rule_extract_from_text(chunk)
                all_memories.extend(rule_mems)

        return all_memories

    def _split_chunks(self, text: str, max_chars: int = 3000) -> List[str]:
        """将长文本按段落分块"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > max_chars and current:
                chunks.append(current)
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current:
            chunks.append(current)

        return chunks if chunks else [text[:max_chars]]

    def _parse_llm_output(self, raw_text: str) -> List[Dict[str, Any]]:
        """解析LLM输出的JSON"""
        # Try to find JSON array
        json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if json_match:
            try:
                items = json.loads(json_match.group())
                if isinstance(items, list):
                    return [self._normalize_memory(m) for m in items if isinstance(m, dict)]
            except json.JSONDecodeError:
                pass

        # Try line-by-line JSON
        memories = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    m = json.loads(line.rstrip(","))
                    if isinstance(m, dict):
                        memories.append(self._normalize_memory(m))
                except json.JSONDecodeError:
                    continue

        return memories

    def _normalize_memory(self, m: dict) -> dict:
        """归一化为v4格式"""
        content = m.get("content", "")
        if not content:
            return {}

        person_raw = m.get("person", [])
        if isinstance(person_raw, str):
            person_list = [person_raw] if person_raw else []
        elif isinstance(person_raw, list):
            person_list = person_raw
        else:
            person_list = []

        return {
            "content": content,
            "person": person_list,
            "time_absolute": m.get("time_absolute", "") or "",
            "time_relative": m.get("time_relative", "") or "",
            "time_ref_id": None,
            "time_offset_days": None,
            "location": m.get("location", "") or "",
            "event_type": m.get("event_type", "") or "",
            "source": m.get("source", "") or "",
            "tags": [],
            "difficulty": "medium",
        }

    # --------------------------------------------------------------------------
    # 规则提取（fallback）
    # --------------------------------------------------------------------------

    def _rule_extract(self, corpus_text: str) -> List[Dict[str, Any]]:
        """不依赖LLM的规则提取（质量较低）"""
        return self._rule_extract_from_text(corpus_text)

    def _rule_extract_from_text(self, text: str) -> List[Dict[str, Any]]:
        """从文本中用规则提取记忆"""
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and len(p.strip()) > 20]
        memories = []

        for para in paragraphs:
            persons = self._extract_persons_rule(para)
            alias_evidence = self._extract_aliases_rule(para)

            mem = {
                "content": para[:500],
                "person": persons,
                "time_absolute": "",
                "time_relative": "",
                "time_ref_id": None,
                "time_offset_days": None,
                "location": "",
                "event_type": "日常",
                "source": "",
                "tags": [],
                "difficulty": "medium",
                "alias_evidence": alias_evidence,
            }
            memories.append(mem)

        return memories

    def _extract_persons_rule(self, text: str) -> List[str]:
        """规则提取人名：2-3字中文，首字是常见姓氏"""
        candidates = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        persons = []
        seen = set()
        for c in candidates:
            if c in seen:
                continue
            if len(c) >= 2 and c[0] in COMMON_SURNAMES:
                if c not in ("有限公司", "公司集团", "这是", "那就是"):
                    persons.append(c)
                    seen.add(c)
                    if len(persons) >= 5:
                        break
        return persons

    def _extract_aliases_rule(self, text: str) -> List[Dict[str, str]]:
        """规则检测别名证据"""
        results = []
        for pattern, ptype in ALIAS_PATTERNS:
            for match in pattern.finditer(text):
                entity = match.group(1).strip()
                alias = match.group(2).strip()
                evidence = match.group(0)
                if (entity and alias and len(entity) >= 2 and len(alias) >= 2
                    and entity not in NOISE_WORDS and alias not in NOISE_WORDS):
                    results.append({
                        "entity": entity,
                        "alias": alias,
                        "evidence": evidence,
                    })
        return results

    # --------------------------------------------------------------------------
    # 后处理
    # --------------------------------------------------------------------------

    def _postprocess(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """后处理：分配ID、去重、补全字段"""
        # 分配memory_id
        for i, m in enumerate(memories):
            if not m:
                continue
            m["memory_id"] = f"MEM{(i+1):06d}"

        # 去重（按content前50字）
        seen_content = set()
        unique = []
        for m in memories:
            if not m:
                continue
            key = m.get("content", "")[:50]
            if key not in seen_content:
                seen_content.add(key)
                unique.append(m)

        # 补全缺失字段
        for m in unique:
            m.setdefault("person", [])
            m.setdefault("time_absolute", "")
            m.setdefault("time_relative", "")
            m.setdefault("time_ref_id", None)
            m.setdefault("time_offset_days", None)
            m.setdefault("location", "")
            m.setdefault("event_type", "")
            m.setdefault("source", "")
            m.setdefault("tags", [])
            m.setdefault("difficulty", "medium")

        return unique


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MemTest v4 记忆提取器")
    parser.add_argument("corpus_dir", help="语料目录或文件路径")
    parser.add_argument("-o", "--output", default="extracted_memories.json", help="输出文件")
    parser.add_argument("--source", default=None, help="来源名（如'三国演义'）")
    args = parser.parse_args()

    # Try to create LLM
    llm = None
    if create_llm:
        try:
            llm = create_llm()
            print("✅ LLM适配器已加载")
        except Exception as e:
            print(f"⚠️  LLM加载失败: {e}")
            print("   将使用规则提取（质量较低）")

    extractor = MemoryExtractor(llm)
    memories = extractor.extract(args.corpus_dir, default_source=args.source)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 提取完成: {len(memories)} 条记忆 → {args.output}")
