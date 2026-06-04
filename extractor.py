#!/usr/bin/env python3
"""MemTest v4 记忆提取器

唯一使用LLM的环节：从语料提取结构化记忆。
一次调用提取完整记忆，不按类型分别提取。

输出格式：v2完整schema（兼容现有runner.py和quality_check.py）
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from llm_interface import DeepSeekAdapter, create_llm


# ==============================================================================
# 常量
# ==============================================================================

EXTRACT_PROMPT = """从以下文本中提取所有有意义的记忆片段。

每条记忆包含以下字段：
- content: 原文片段（尽量保留原文措辞，30-150字）
- person: 出现的人物姓名列表（包括别名和称呼，如"凤姐"也要列出来）
- time: 时间信息，格式 {"absolute": "具体日期或null", "relative": "相对时间词或null", "fuzzy": "模糊时间词或null"}
- location: 地点（字符串或null）
- event_type: 事件类型标签（如：交易/会议/决策/日常/冲突/情感/技术/发现）
- event_action: 具体动作（如：购买/召开/誓死不从/初见）
- event_product: 涉及的事物（如：通灵宝玉/金锁/琉璃盏）
- dynasty: 朝代或时期（如：东晋/贞观年间），无则为null
- source: 来源作品名或null
- alias_evidence: 人物的名字和称呼（如"宋江"、"宋公明"、"宋押司"、"及时雨"）。注意：不包括代称（如"我"、"你"、"洒家"、"小可"、"小人"、"阿哥"、"这个"）。如果文本中有别名证据，列出等价对，格式 [{"entity": "全称", "alias": "称呼", "evidence": "原文证据"}]

注意：
1. person 必须包含文中出现的所有人名，包括简称（如"黛玉"和"林黛玉"都要列）
2. alias_evidence 只提取名字和称呼，不要提取代称（我/你/他/洒家/小可/小人/阿哥/这个等）
3. content 保留原文，不要改写
4. 一段话如果包含多个独立事件，拆成多条记忆

输出JSON数组，不要其他内容。"""

# 常见姓氏（用于规则fallback的人名提取）
COMMON_SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾母沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"

# 别名检测模式
ALIAS_PATTERNS = [
    # "人称X"、"又名X"、"即X"、"也就是X"
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]?\s*(?:人称|又名|又称|又叫|即|也就是|便是)\s*([\u4e00-\u9fff]{1,20})"), "explicit"),
    # "X是Y之Z，人称W"
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*[,，]\s*(?:俗名|绰号|号|字|别号|雅号|昵称)\s*([\u4e00-\u9fff]{1,20})"), "formal"),
    # "X，就是Y" / "X，便是Y"
    (re.compile(r"([\u4e00-\u9fff]{2,10})\s*(?:就是|便是|即是|等于)\s*([\u4e00-\u9fff]{1,20})"), "equivalence"),
]


# ==============================================================================
# 提取器
# ==============================================================================

class MemoryExtractor:
    """从语料提取结构化记忆（v2格式）"""

    def __init__(self, llm_adapter=None, seed=42):
        self.llm = llm_adapter
        self.seed = seed

    # --------------------------------------------------------------------------
    # 主入口
    # --------------------------------------------------------------------------

    def extract(self, corpus_dir: str, default_source: str = None) -> List[Dict[str, Any]]:
        """从语料目录提取结构化记忆
        
        Args:
            corpus_dir: 语料目录路径
            default_source: 默认来源名（如"三国演义"），用于填充LLM未返回source的记忆
        """
        corpus_text = self._load_corpus(corpus_dir)
        if not corpus_text:
            return []

        # 如果未指定default_source，从目录名/文件名推断
        if default_source is None:
            default_source = self._infer_source(corpus_dir)

        # 尝试LLM提取
        if self.llm:
            memories = self._llm_extract(corpus_text)
        else:
            memories = self._rule_extract(corpus_text)

        # 后处理
        memories = self._postprocess(memories)

        # 填充缺失的source
        if default_source:
            for m in memories:
                if not m.get("source"):
                    m["source"] = default_source

        return memories

    # --------------------------------------------------------------------------
    # 语料加载
    # --------------------------------------------------------------------------

    def _infer_source(self, corpus_dir: str) -> str:
        """从目录名/文件名推断来源作品名"""
        # 文件名映射
        name_map = {
            "xiyouji": "西游记", "sgyy": "三国演义", "hongloumeng": "红楼梦",
            "jinyong": "金庸小说", "shuihu": "水浒传", "sanguo": "三国演义",
        }
        
        # 检查目录内文件名
        if os.path.isdir(corpus_dir):
            for root, dirs, files in os.walk(corpus_dir):
                for fn in files:
                    basename = os.path.splitext(fn)[0].lower()
                    for key, name in name_map.items():
                        if key in basename:
                            return name
        
        # 检查目录名本身
        dirname = os.path.basename(os.path.normpath(corpus_dir)).lower()
        for key, name in name_map.items():
            if key in dirname:
                return name
        
        # 如果是单文件，用文件名
        if os.path.isfile(corpus_dir):
            basename = os.path.splitext(os.path.basename(corpus_dir))[0].lower()
            for key, name in name_map.items():
                if key in basename:
                    return name
        
        return None

    def _load_corpus(self, corpus_dir: str) -> str:
        """加载语料目录中的所有文本"""
        texts = []
        if not os.path.isdir(corpus_dir):
            return ""

        for root, dirs, files in os.walk(corpus_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fn in sorted(files):
                if fn.endswith(('.txt', '.md', '.text')) and not fn.startswith('.'):
                    path = os.path.join(root, fn)
                    try:
                        with open(path, encoding='utf-8') as f:
                            content = f.read()
                        if content.startswith('---'):
                            idx = content.find('---', 3)
                            if idx > 0:
                                content = content[idx + 3:]
                        texts.append(content.strip())
                    except (OSError, IOError):
                        pass

        return "\n\n".join(texts)

    # --------------------------------------------------------------------------
    # LLM提取
    # --------------------------------------------------------------------------

    def _llm_extract(self, corpus_text: str) -> List[Dict[str, Any]]:
        """用LLM一次提取所有结构化记忆"""
        # 长文本分段处理
        chunks = self._split_corpus(corpus_text, max_chars=3000)
        all_memories = []

        for i, chunk in enumerate(chunks):
            prompt = f"{EXTRACT_PROMPT}\n\n=== 文本 ===\n{chunk}\n\n=== 输出 ==="
            print(f"  [Chunk {i+1}/{len(chunks)}] Prompt size: {len(prompt)} chars, chunk: {len(chunk)} chars", flush=True)
            # 用generate而不是generate_json，手动解析更robust
            raw_text = self.llm.generate(prompt, max_tokens=4000)
            print(f"  [Chunk {i+1}/{len(chunks)}] API response: {len(raw_text)} chars", flush=True)
            raw = self._robust_json_parse(raw_text)

            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = raw.get("memories", []) or raw.get("items", []) or [raw]
            else:
                items = []

            for item in items:
                if not isinstance(item, dict):
                    continue
                mem = self._parse_llm_item(item)
                if mem and mem.get("content"):
                    all_memories.append(mem)

            # Progress logging
            if (i + 1) % 10 == 0 or i == len(chunks) - 1:
                print(f"  Extracted chunk {i+1}/{len(chunks)} -> {len(all_memories)} memories total", flush=True)

        return all_memories

    def _robust_json_parse(self, text: str):
        """Robust JSON解析：处理code block、截断等情况"""
        import json as _json
        # 去掉markdown code block
        if "```json" in text:
            text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
        
        text_stripped = text.strip()
        # 尝试直接解析
        try:
            return _json.loads(text_stripped)
        except (_json.JSONDecodeError, ValueError):
            pass
        
        # 找[...]或{...}
        for start_char, end_char in [('[', ']'), ('{', '}')]:
            start = text_stripped.find(start_char)
            end = text_stripped.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return _json.loads(text_stripped[start:end+1])
                except (_json.JSONDecodeError, ValueError):
                    pass
        
        # 最后尝试：逐步缩小范围（处理截断）—— 使用步长1避免跳过有效位置
        for start_char in ['[']:
            start = text_stripped.find(start_char)
            if start >= 0:
                # 从end往前找，逐步尝试（步长1，不跳过任何位置）
                for end_pos in range(len(text_stripped)-1, start, -1):
                    if text_stripped[end_pos] in ']}':
                        try:
                            candidate = text_stripped[start:end_pos+1]
                            # 如果截断，尝试补全
                            if candidate.count('[') > candidate.count(']'):
                                candidate += ']'
                            if candidate.count('{') > candidate.count('}'):
                                candidate += '}'
                            return _json.loads(candidate)
                        except (_json.JSONDecodeError, ValueError):
                            continue
        
        return {}
        
        return {}

    def _split_corpus(self, text: str, max_chars: int = 3000) -> List[str]:
        """按段落边界分段，每段不超过max_chars"""
        paragraphs = text.split('\n\n')
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) + 2 > max_chars:
                if current:
                    chunks.append(current)
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current:
            chunks.append(current)

        return chunks

    def _parse_llm_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """将LLM输出解析为v2格式记忆"""
        content = item.get("content", "")
        if not content:
            content = item.get("text", "") or item.get("description", "")
        if not content:
            return None

        # person: 统一为list
        person_raw = item.get("person", [])
        if isinstance(person_raw, str):
            person_list = [p.strip() for p in person_raw.replace("，", ",").split(",") if p.strip()]
        elif isinstance(person_raw, list):
            person_list = [str(p).strip() for p in person_raw if str(p).strip()]
        else:
            person_list = []

        # time: 统一为v2嵌套格式
        time_raw = item.get("time", {})
        if isinstance(time_raw, str):
            time_data = {"absolute": time_raw, "relative": None, "fuzzy": None}
        elif isinstance(time_raw, dict):
            time_data = {
                "absolute": time_raw.get("absolute") or None,
                "relative": time_raw.get("relative") or None,
                "fuzzy": time_raw.get("fuzzy") or None,
            }
        else:
            time_data = {"absolute": None, "relative": None, "fuzzy": None}

        # location: 统一为v2嵌套格式
        loc_raw = item.get("location")
        if isinstance(loc_raw, str) and loc_raw:
            location = {"city": loc_raw, "place": "", "landmark": ""}
        elif isinstance(loc_raw, dict):
            location = loc_raw
        else:
            location = {"city": "", "place": "", "landmark": ""}

        # event
        event_type = item.get("event_type") or "日常"
        event_action = item.get("event_action") or ""
        event_product = item.get("event_product") or ""

        # alias evidence
        alias_evidence = item.get("alias_evidence", [])
        if isinstance(alias_evidence, dict):
            alias_evidence = [alias_evidence]

        return {
            "content": content.strip(),
            "person": {"name": person_list[0] if person_list else "",
                       "identity": "",
                       "partner_name": person_list[1] if len(person_list) > 1 else "",
                       "relation": ""},
            "person_list": person_list,  # 内部用，出题参考
            "time": time_data,
            "location": location,
            "event": {"type": event_type, "action": event_action, "product": event_product},
            "dynasty": item.get("dynasty"),
            "source": item.get("source"),
            "alias_evidence": alias_evidence,
            "tags": [],
            "category": "检索功能测试集",  # 默认，后续由relation_builder调整
            "difficulty": "中等",
            "weight": 1.0,
        }

    # --------------------------------------------------------------------------
    # 规则fallback提取（无LLM时使用）
    # --------------------------------------------------------------------------

    def _rule_extract(self, corpus_text: str) -> List[Dict[str, Any]]:
        """不依赖LLM的规则提取"""
        paragraphs = [p.strip() for p in corpus_text.split('\n\n') if p.strip() and len(p.strip()) > 20]
        memories = []

        for para in paragraphs:
            persons = self._extract_persons_rule(para)
            alias_evidence = self._extract_aliases_rule(para)

            mem = {
                "content": para[:200],
                "person": {"name": persons[0] if persons else "",
                           "identity": "",
                           "partner_name": persons[1] if len(persons) > 1 else "",
                           "relation": ""},
                "person_list": persons,
                "time": {"absolute": None, "relative": None, "fuzzy": None},
                "location": {"city": "", "place": "", "landmark": ""},
                "event": {"type": "日常", "action": "", "product": ""},
                "dynasty": None,
                "source": None,
                "alias_evidence": alias_evidence,
                "tags": [],
                "category": "检索功能测试集",
                "difficulty": "中等",
                "weight": 1.0,
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
                # 排除明显的非人名
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
                if entity and alias and len(entity) >= 2 and len(alias) >= 2:
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
            m["memory_id"] = f"MEM{(i+1):06d}"

        # 去重（按content前50字）
        seen_content = set()
        deduped = []
        for m in memories:
            key = m["content"][:50]
            if key not in seen_content:
                seen_content.add(key)
                deduped.append(m)

        # 如果person_list里有人名但person.name为空，补上
        for m in deduped:
            pl = m.get("person_list", [])
            if pl and not m["person"]["name"]:
                m["person"]["name"] = pl[0]
                if len(pl) > 1:
                    m["person"]["partner_name"] = pl[1]

        # 过滤代称（不是人物名字，而是指代或自称）
        PRONOUNS = {"我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们", "自己", "本人", "俺", "咱", "洒家", "小可", "小人", "在下", "鄙人", "愚", "不才", "不肖", "奴才", "老奴", "臣", "本官", "本府", "本县", "老夫", "老身", "妾", "妾身", "奴家", "奴婢", "小的", "小的们", "阿哥", "大姐", "这个", "那个", "这位", "那位", "此人", "那人", "这厮", "那厮", "这汉子", "那汉子", "这和尚", "那和尚", "这道士", "那道士", "这先生", "那先生", "这妇人", "那妇人", "这女子", "那女子", "这老儿", "那老儿", "这老者", "那老者", "这公公", "那公公", "这婆婆", "那婆婆", "这妈妈", "那妈妈", "这小二", "那小二", "这店家", "那店家", "这主人", "那主人", "这庄客", "那庄客", "这庄主", "那庄主", "这员外", "那员外"}
        
        # 过滤官名/身份（单独出现是官名，与姓名组合才是别名，如"鲁提辖"保留，"提辖"过滤）
        PURE_TITLES = {"提辖", "知县", "都头", "押司", "教头", "制使", "都监", "巡检", "县尉", "指挥", "统制", "将军", "元帅", "先锋", "参谋", "节级", "孔目", "节帅", "节度使", "观察", "防御使", "团练使", "刺史", "太守", "知府", "知州", "通判", "推官", "主簿", "县丞", "典史", "捕快", "差役", "牢头", "狱卒", "仵作", "门子", "管家", "账房", "师爷", "员外", "财主", "地主", "庄主", "寨主", "大王", "头领", "首领", "喽啰", "清客", "幕宾", "门客", "宾客", "客人", "旅客", "过客", "游人", "闲人", "高人", "异人", "奇人", "怪人", "强人", "好汉", "壮士", "勇士", "武夫", "武士", "剑客", "刀客", "枪手", "弓手", "弩手", "炮手", "骑手", "马夫", "车夫", "船夫", "艄公", "渔夫", "猎户", "樵夫", "农夫", "牧童", "书童", "丫鬟", "侍女", "婢女", "仆妇", "老妈", "老嬷", "嬷嬷", "乳母", "奶妈", "养娘", "干娘", "姨娘", "婶娘", "伯娘", "姑母", "姑奶奶", "舅母", "舅奶奶", "姨母", "姨奶奶", "婶母", "伯母", "叔母", "嫂嫂", "弟妹", "弟媳", "侄媳", "侄媳妇", "孙媳", "孙媳妇", "外孙媳", "外甥媳", "表嫂", "表弟媳", "堂弟媳", "堂弟媳妇"}
        
        # 过滤通用占位名（如"张三"作为具体人物别名通常是错误）
        GENERIC_NAMES = {"张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十", "郑十一", "王十二", "某人", "有人", "那人", "这人"}
        
        def _is_valid_alias(entity: str, alias: str, person_list: list) -> bool:
            """校验别名是否有效：不是代称、不是纯官名、不是通用占位名"""
            e, a = (entity or "").strip(), (alias or "").strip()
            if not e or not a:
                return False
            if e in PRONOUNS or a in PRONOUNS:
                return False
            if e in PURE_TITLES or a in PURE_TITLES:
                return False
            if e in GENERIC_NAMES or a in GENERIC_NAMES:
                return False
            return True
        
        for m in deduped:
            alias_evidence = m.get("alias_evidence", [])
            filtered = []
            person_list = m.get("person_list", [])
            for ae in alias_evidence:
                entity = (ae.get("entity") or "").strip()
                alias = (ae.get("alias") or "").strip()
                if _is_valid_alias(entity, alias, person_list):
                    filtered.append(ae)
            m["alias_evidence"] = filtered

        # 规则检测别名（补充LLM可能遗漏的）
        for m in deduped:
            if not m.get("alias_evidence"):
                m["alias_evidence"] = self._extract_aliases_rule(m["content"])
                # 再次过滤规则提取的别名
                alias_evidence = m.get("alias_evidence", [])
                filtered = []
                person_list = m.get("person_list", [])
                for ae in alias_evidence:
                    entity = (ae.get("entity") or "").strip()
                    alias = (ae.get("alias") or "").strip()
                    if _is_valid_alias(entity, alias, person_list):
                        filtered.append(ae)
                m["alias_evidence"] = filtered

        # 重新编号
        for i, m in enumerate(deduped):
            m["memory_id"] = f"MEM{(i+1):06d}"

        return deduped


# ==============================================================================
# CLI
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MemTest v4 记忆提取器")
    parser.add_argument("corpus_dir", help="语料目录")
    parser.add_argument("-o", "--output", default="extracted_memories.json", help="输出文件")
    parser.add_argument("--no-llm", action="store_true", help="不使用LLM，纯规则提取")
    args = parser.parse_args()

    if args.no_llm:
        extractor = MemoryExtractor(llm_adapter=None)
    else:
        llm = create_llm("deepseek")
        extractor = MemoryExtractor(llm_adapter=llm)

    memories = extractor.extract(args.corpus_dir)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)

    print(f"提取完成: {len(memories)} 条记忆")
    for m in memories[:5]:
        print(f"  [{m['memory_id']}] person={m['person_list']} | {m['content'][:40]}...")
    if len(memories) > 5:
        print(f"  ... 还有 {len(memories)-5} 条")
