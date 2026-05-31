#!/usr/bin/env python3
"""
AI-native MemTest 数据生成器 v2 — 完全取消程序化模板，所有内容预设计。
扩展版：100条记忆，40条查询，12人名，10城市。

用法：python generate_ai_v2.py > sample_db.json
"""
import json
from datetime import datetime

# ====== 预设计的记忆数据（人工设计，中文自然流畅） ======

# 人物扩展：12人
PEOPLE = {
    "张伟": {"identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴"},
    "李明": {"identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问"},
    "王芳": {"identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人"},
    "刘洋": {"identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事"},
    "陈静": {"identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手"},
    "赵磊": {"identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手"},
    "李娜": {"identity": "天使投资人", "partner": "张伟", "partner_id": "创业者", "relation": "合作伙伴"},
    "孙强": {"identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事"},
    "周梅": {"identity": "护士", "partner": "孙强", "partner_id": "医生", "relation": "同事"},
    "吴昊": {"identity": "律师", "partner": "郑欣", "partner_id": "法官", "relation": "合作"},
    "郑欣": {"identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作"},
    "黄丽": {"identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级"},
}

CITIES = ["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "西安", "南京", "苏州"]
PLACES = ["创业大街", "金融中心", "科技园", "体育馆", "医院", "学校", "法院", "商场", "公园", "餐厅"]
LANDMARKS = ["创业孵化器", "交易大厅", "研发中心", "健身中心", "门诊部", "教学楼", "审判庭", "购物中心", "景观区", "美食街"]

# 时序链1：张伟-北京-新能源汽车（5跳）
TEMPORAL_1 = [
    {"id": "MEM000001", "ts": "2024-01-15 09:30:00", "days": 500, "city": "北京", "place": "中关村创业大街", "landmark": "创业孵化器", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "启动项目", "action": "启动", "product": "新能源汽车", "qty": 1, "price": 0, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_时序_0001", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000002", "ts": "2024-03-20 14:00:00", "days": 436, "city": "北京", "place": "三里屯调研中心", "landmark": "商业综合体", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "市场调研", "action": "调研", "product": "消费者需求", "qty": 2000, "price": 0, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_时序_0001", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000003", "ts": "2024-06-10 10:00:00", "days": 355, "city": "北京", "place": "亦庄开发区", "landmark": "工业设计园", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "原型设计", "action": "完成", "product": "原型车", "qty": 3, "price": 500000, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_时序_0001", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000004", "ts": "2024-08-05 16:30:00", "days": 300, "city": "北京", "place": "国家知识产权局", "landmark": "专利大厅", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "申请专利", "action": "申请", "product": "电池技术专利", "qty": 5, "price": 0, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_时序_0001", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000005", "ts": "2024-10-01 08:00:00", "days": 243, "city": "北京", "place": "顺义制造基地", "landmark": "智能工厂", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "量产", "action": "量产", "product": "新能源汽车", "qty": 500, "price": 150000, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_时序_0001", "tags": ["推理测试", "中等", "时序"]},
]

# 时序链2：李明-上海-房产（5跳）
TEMPORAL_2 = [
    {"id": "MEM000006", "ts": "2023-05-10 10:00:00", "days": 755, "city": "上海", "place": "陆家嘴房产中心", "landmark": "金融区", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "购买房产", "action": "购买", "product": "公寓", "qty": 1, "price": 8500000, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_时序_0002", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000007", "ts": "2023-07-15 09:00:00", "days": 689, "city": "上海", "place": "浦东装修市场", "landmark": "建材城", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "装修", "action": "装修", "product": "房屋", "qty": 1, "price": 500000, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_时序_0002", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000008", "ts": "2023-09-01 15:00:00", "days": 642, "city": "上海", "place": "世纪公园小区", "landmark": "住宅区", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "搬家", "action": "搬入", "product": "新居", "qty": 1, "price": 0, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_时序_0002", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000009", "ts": "2023-11-20 18:00:00", "days": 558, "city": "上海", "place": "新天地会所", "landmark": "社交中心", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "乔迁", "action": "举办", "product": "乔迁派对", "qty": 1, "price": 30000, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_时序_0002", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000010", "ts": "2024-01-10 11:00:00", "days": 507, "city": "上海", "place": "智能家居展厅", "landmark": "科技体验馆", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "安装", "action": "安装", "product": "智能家居", "qty": 20, "price": 80000, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_时序_0002", "tags": ["推理测试", "中等", "时序"]},
]

# 时序链3：孙强-武汉-医疗设备（5跳）
TEMPORAL_3 = [
    {"id": "MEM000011", "ts": "2024-02-01 08:00:00", "days": 484, "city": "武汉", "place": "协和医院", "landmark": "门诊部", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "诊断", "action": "诊断", "product": "新型病毒", "qty": 1, "price": 0, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_时序_0003", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000012", "ts": "2024-02-15 14:00:00", "days": 470, "city": "武汉", "place": "医学实验室", "landmark": "研发中心", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "研究", "action": "研究", "product": "病毒基因序列", "qty": 1, "price": 0, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_时序_0003", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000013", "ts": "2024-03-01 09:00:00", "days": 455, "city": "武汉", "place": "制药公司", "landmark": "生产车间", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "合作", "action": "合作", "product": "疫苗研发", "qty": 1, "price": 10000000, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_时序_0003", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000014", "ts": "2024-03-20 10:00:00", "days": 436, "city": "武汉", "place": "临床试验中心", "landmark": "试验基地", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "试验", "action": "开展", "product": "临床试验", "qty": 1000, "price": 0, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_时序_0003", "tags": ["推理测试", "中等", "时序"]},
    {"id": "MEM000015", "ts": "2024-04-10 11:00:00", "days": 415, "city": "武汉", "place": "医院注射室", "landmark": "接种中心", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "接种", "action": "接种", "product": "疫苗", "qty": 5000, "price": 200, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_时序_0003", "tags": ["推理测试", "中等", "时序"]},
]

# 因果链1：王芳-深圳-AI公司（5跳）
CAUSAL_1 = [
    {"id": "MEM000016", "ts": "2024-02-01 09:00:00", "days": 484, "city": "深圳", "place": "南山科技园", "landmark": "创新大厦", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "投资", "action": "投资", "product": "AI初创公司", "qty": 1, "price": 5000000, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_因果_0001", "tags": ["推理测试", "困难", "因果"]},
    {"id": "MEM000017", "ts": "2024-04-15 14:00:00", "days": 412, "city": "深圳", "place": "技术研究院", "landmark": "实验室", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "技术瓶颈", "action": "遭遇", "product": "算法优化难题", "qty": 1, "price": 0, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_因果_0001", "tags": ["推理测试", "困难", "因果"]},
    {"id": "MEM000018", "ts": "2024-06-20 10:00:00", "days": 346, "city": "深圳", "place": "猎头公司", "landmark": "人才中心", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "招聘", "action": "聘请", "product": "顶尖工程师", "qty": 3, "price": 1200000, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_因果_0001", "tags": ["推理测试", "困难", "因果"]},
    {"id": "MEM000019", "ts": "2024-08-30 16:00:00", "days": 275, "city": "深圳", "place": "研发中心", "landmark": "技术总部", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "技术突破", "action": "突破", "product": "核心算法", "qty": 1, "price": 0, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_因果_0001", "tags": ["推理测试", "困难", "因果"]},
    {"id": "MEM000020", "ts": "2024-11-10 11:00:00", "days": 203, "city": "深圳", "place": "创投大厦", "landmark": "融资中心", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "融资", "action": "获得", "product": "B轮融资", "qty": 1, "price": 20000000, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_因果_0001", "tags": ["推理测试", "困难", "因果"]},
]

# 因果链2：刘洋-杭州-健身房（5跳）
CAUSAL_2 = [
    {"id": "MEM000021", "ts": "2023-03-05 08:00:00", "days": 818, "city": "杭州", "place": "西湖区商业街", "landmark": "购物中心", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "开店", "action": "开设", "product": "健身房", "qty": 1, "price": 3000000, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_因果_0002", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000022", "ts": "2023-05-20 19:00:00", "days": 741, "city": "杭州", "place": "社区广场", "landmark": "宣传点", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "推广", "action": "吸引", "product": "会员", "qty": 500, "price": 2000, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_因果_0002", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000023", "ts": "2023-08-10 09:00:00", "days": 660, "city": "杭州", "place": "滨江新城", "landmark": "商业区", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "扩展", "action": "开设", "product": "分店", "qty": 2, "price": 5000000, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_因果_0002", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000024", "ts": "2023-10-25 15:00:00", "days": 584, "city": "杭州", "place": "体育学院", "landmark": "训练基地", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "人才引进", "action": "引进", "product": "专业教练", "qty": 10, "price": 800000, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_因果_0002", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000025", "ts": "2024-01-15 12:00:00", "days": 502, "city": "杭州", "place": "总部办公室", "landmark": "财务中心", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "盈利", "action": "实现", "product": "利润翻倍", "qty": 1, "price": 0, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_因果_0002", "tags": ["推理测试", "中等", "因果"]},
]

# 因果链3：郑欣-西安-法律案件（5跳）
CAUSAL_3 = [
    {"id": "MEM000026", "ts": "2024-01-10 09:00:00", "days": 511, "city": "西安", "place": "法院", "landmark": "审判庭", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "立案", "action": "受理", "product": "知识产权案件", "qty": 1, "price": 0, "chain_pos": 1, "chain_total": 5, "chain_id": "CHAIN_因果_0003", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000027", "ts": "2024-02-20 14:00:00", "days": 470, "city": "西安", "place": "证据中心", "landmark": "调查部", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "调查", "action": "调取", "product": "关键证据", "qty": 1, "price": 0, "chain_pos": 2, "chain_total": 5, "chain_id": "CHAIN_因果_0003", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000028", "ts": "2024-03-25 10:00:00", "days": 436, "city": "西安", "place": "律师事务所", "landmark": "会议厅", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "庭审", "action": "主持", "product": "法庭辩论", "qty": 1, "price": 0, "chain_pos": 3, "chain_total": 5, "chain_id": "CHAIN_因果_0003", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000029", "ts": "2024-04-30 16:00:00", "days": 400, "city": "西安", "place": "司法鉴定中心", "landmark": "专家室", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "鉴定", "action": "委托", "product": "技术鉴定", "qty": 1, "price": 50000, "chain_pos": 4, "chain_total": 5, "chain_id": "CHAIN_因果_0003", "tags": ["推理测试", "中等", "因果"]},
    {"id": "MEM000030", "ts": "2024-06-10 11:00:00", "days": 355, "city": "西安", "place": "法院", "landmark": "宣判庭", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "判决", "action": "宣判", "product": "赔偿决定", "qty": 1, "price": 1000000, "chain_pos": 5, "chain_total": 5, "chain_id": "CHAIN_因果_0003", "tags": ["推理测试", "中等", "因果"]},
]

# 对比链：陈静 vs 赵磊 - 成都 - 股票（4跳）
CONTRAST = [
    {"id": "MEM000031", "ts": "2024-03-01 10:00:00", "days": 457, "city": "成都", "place": "证券交易所", "landmark": "交易大厅", "person": "陈静", "identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手", "event_type": "交易", "action": "购买", "product": "科技股", "qty": 1000, "price": 150, "chain_pos": 1, "chain_total": 4, "chain_id": "CHAIN_对比_0001", "tags": ["推理测试", "简单", "对比"]},
    {"id": "MEM000032", "ts": "2024-03-01 10:05:00", "days": 457, "city": "成都", "place": "证券交易所", "landmark": "交易大厅", "person": "赵磊", "identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手", "event_type": "交易", "action": "出售", "product": "科技股", "qty": 2000, "price": 148, "chain_pos": 2, "chain_total": 4, "chain_id": "CHAIN_对比_0001", "tags": ["推理测试", "简单", "对比"]},
    {"id": "MEM000033", "ts": "2024-05-10 14:00:00", "days": 387, "city": "成都", "place": "投资咨询室", "landmark": "分析中心", "person": "陈静", "identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手", "event_type": "加仓", "action": "增持", "product": "仓位", "qty": 500, "price": 160, "chain_pos": 3, "chain_total": 4, "chain_id": "CHAIN_对比_0001", "tags": ["推理测试", "简单", "对比"]},
    {"id": "MEM000034", "ts": "2024-05-10 14:05:00", "days": 387, "city": "成都", "place": "投资咨询室", "landmark": "分析中心", "person": "赵磊", "identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手", "event_type": "清仓", "action": "清仓", "product": "持仓", "qty": 0, "price": 0, "chain_pos": 4, "chain_total": 4, "chain_id": "CHAIN_对比_0001", "tags": ["推理测试", "简单", "对比"]},
]

# 包含链：张伟-北京-智慧城市（4跳）
INCLUSION = [
    {"id": "MEM000035", "ts": "2023-01-10 09:00:00", "days": 872, "city": "北京", "place": "市政规划院", "landmark": "规划中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "规划", "action": "规划", "product": "智慧城市项目", "qty": 1, "price": 50000000, "chain_pos": 1, "chain_total": 4, "chain_id": "CHAIN_包含_0001", "tags": ["推理测试", "困难", "包含"]},
    {"id": "MEM000036", "ts": "2023-03-15 10:00:00", "days": 808, "city": "北京", "place": "交通管理局", "landmark": "控制中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "子系统", "action": "部署", "product": "交通管理系统", "qty": 1, "price": 8000000, "chain_pos": 2, "chain_total": 4, "chain_id": "CHAIN_包含_0001", "tags": ["推理测试", "困难", "包含"]},
    {"id": "MEM000037", "ts": "2023-05-20 14:00:00", "days": 742, "city": "北京", "place": "数据中心", "landmark": "机房楼", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "子系统", "action": "建设", "product": "数据中心", "qty": 1, "price": 12000000, "chain_pos": 3, "chain_total": 4, "chain_id": "CHAIN_包含_0001", "tags": ["推理测试", "困难", "包含"]},
    {"id": "MEM000038", "ts": "2023-08-01 08:00:00", "days": 669, "city": "北京", "place": "公共安全局", "landmark": "监控中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "子系统", "action": "安装", "product": "监控系统", "qty": 500, "price": 3000000, "chain_pos": 4, "chain_total": 4, "chain_id": "CHAIN_包含_0001", "tags": ["推理测试", "困难", "包含"]},
]

# 推导链：李明-上海-在线教育（4跳）
DEDUCTION = [
    {"id": "MEM000039", "ts": "2024-01-05 10:00:00", "days": 511, "city": "上海", "place": "教育研究院", "landmark": "趋势分析室", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "观察", "action": "观察", "product": "在线教育趋势", "qty": 1, "price": 0, "chain_pos": 1, "chain_total": 4, "chain_id": "CHAIN_推导_0001", "tags": ["推理测试", "中等", "推导"]},
    {"id": "MEM000040", "ts": "2024-02-10 14:00:00", "days": 476, "city": "上海", "place": "市场调研公司", "landmark": "数据分析部", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "分析", "action": "分析", "product": "市场需求", "qty": 1, "price": 0, "chain_pos": 2, "chain_total": 4, "chain_id": "CHAIN_推导_0001", "tags": ["推理测试", "中等", "推导"]},
    {"id": "MEM000041", "ts": "2024-03-20 09:00:00", "days": 438, "city": "上海", "place": "课程设计室", "landmark": "产品开发部", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "判断", "action": "判断", "product": "课程方向", "qty": 1, "price": 0, "chain_pos": 3, "chain_total": 4, "chain_id": "CHAIN_推导_0001", "tags": ["推理测试", "中等", "推导"]},
    {"id": "MEM000042", "ts": "2024-05-01 11:00:00", "days": 396, "city": "上海", "place": "创业孵化器", "landmark": "商业模式实验室", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "验证", "action": "验证", "product": "商业模式", "qty": 1, "price": 500000, "chain_pos": 4, "chain_total": 4, "chain_id": "CHAIN_推导_0001", "tags": ["推理测试", "中等", "推导"]},
]

# 推导链2：黄丽-南京-教育改革（4跳）
DEDUCTION_2 = [
    {"id": "MEM000043", "ts": "2024-02-01 08:00:00", "days": 484, "city": "南京", "place": "教育局", "landmark": "政策研究室", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "观察", "action": "观察", "product": "学生成绩下滑", "qty": 1, "price": 0, "chain_pos": 1, "chain_total": 4, "chain_id": "CHAIN_推导_0002", "tags": ["推理测试", "简单", "推导"]},
    {"id": "MEM000044", "ts": "2024-03-01 14:00:00", "days": 455, "city": "南京", "place": "学校", "landmark": "教研组", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "分析", "action": "分析", "product": "教学方法", "qty": 1, "price": 0, "chain_pos": 2, "chain_total": 4, "chain_id": "CHAIN_推导_0002", "tags": ["推理测试", "简单", "推导"]},
    {"id": "MEM000045", "ts": "2024-04-01 09:00:00", "days": 425, "city": "南京", "place": "培训中心", "landmark": "教师进修", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "判断", "action": "判断", "product": "改革方案", "qty": 1, "price": 0, "chain_pos": 3, "chain_total": 4, "chain_id": "CHAIN_推导_0002", "tags": ["推理测试", "简单", "推导"]},
    {"id": "MEM000046", "ts": "2024-05-01 11:00:00", "days": 396, "city": "南京", "place": "学校", "landmark": "实验班", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "验证", "action": "验证", "product": "改革效果", "qty": 1, "price": 0, "chain_pos": 4, "chain_total": 4, "chain_id": "CHAIN_推导_0002", "tags": ["推理测试", "简单", "推导"]},
]

# 聚类1：人物-张伟（跨城市）
CLUSTER_1 = [
    {"id": "MEM000047", "ts": "2024-06-15 09:00:00", "days": 351, "city": "北京", "place": "国际会议中心", "landmark": "峰会场馆", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "参会", "action": "参加", "product": "行业峰会", "qty": 1, "price": 0, "cluster_id": "CLUSTER_人物_张伟", "chain": None, "tags": ["整理测试", "简单", "人物", "张伟"]},
    {"id": "MEM000048", "ts": "2024-07-20 14:00:00", "days": 316, "city": "深圳", "place": "签约大厅", "landmark": "商务中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "签约", "action": "签署", "product": "合作协议", "qty": 1, "price": 0, "cluster_id": "CLUSTER_人物_张伟", "chain": None, "tags": ["整理测试", "简单", "人物", "张伟"]},
    {"id": "MEM000049", "ts": "2024-08-25 10:00:00", "days": 280, "city": "杭州", "place": "电商产业园", "landmark": "调研中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "考察", "action": "考察", "product": "市场前景", "qty": 1, "price": 0, "cluster_id": "CLUSTER_人物_张伟", "chain": None, "tags": ["整理测试", "简单", "人物", "张伟"]},
]

# 聚类2：事件-医疗
CLUSTER_2 = [
    {"id": "MEM000050", "ts": "2024-09-10 08:00:00", "days": 264, "city": "深圳", "place": "三甲医院", "landmark": "体检中心", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "体检", "action": "预约", "product": "健康体检", "qty": 1, "price": 3000, "cluster_id": "CLUSTER_事件_医疗", "chain": None, "tags": ["整理测试", "简单", "事件", "医疗"]},
    {"id": "MEM000051", "ts": "2024-10-05 09:00:00", "days": 239, "city": "杭州", "place": "保险公司", "landmark": "业务大厅", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "保险", "action": "购买", "product": "医疗保险", "qty": 1, "price": 8000, "cluster_id": "CLUSTER_事件_医疗", "chain": None, "tags": ["整理测试", "简单", "事件", "医疗"]},
    {"id": "MEM000052", "ts": "2024-11-01 10:00:00", "days": 212, "city": "成都", "place": "专科门诊", "landmark": "专家诊室", "person": "陈静", "identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手", "event_type": "咨询", "action": "咨询", "product": "专家门诊", "qty": 1, "price": 500, "cluster_id": "CLUSTER_事件_医疗", "chain": None, "tags": ["整理测试", "简单", "事件", "医疗"]},
]

# 聚类3：地点-北京
CLUSTER_3 = [
    {"id": "MEM000053", "ts": "2024-06-20 15:00:00", "days": 346, "city": "北京", "place": "投资大厦", "landmark": "资本中心", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "拜访", "action": "拜访", "product": "投资人", "qty": 3, "price": 0, "cluster_id": "CLUSTER_地点_北京", "chain": None, "tags": ["整理测试", "简单", "地点", "北京"]},
    {"id": "MEM000054", "ts": "2024-07-15 09:00:00", "days": 321, "city": "北京", "place": "学术报告厅", "landmark": "会议中心", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "参会", "action": "出席", "product": "学术会议", "qty": 1, "price": 0, "cluster_id": "CLUSTER_地点_北京", "chain": None, "tags": ["整理测试", "简单", "地点", "北京"]},
    {"id": "MEM000055", "ts": "2024-08-01 14:00:00", "days": 304, "city": "北京", "place": "创业咖啡馆", "landmark": "交流空间", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "交流", "action": "参加", "product": "创业分享会", "qty": 1, "price": 0, "cluster_id": "CLUSTER_地点_北京", "chain": None, "tags": ["整理测试", "简单", "地点", "北京"]},
]

# 聚类4：人物-李娜（投资活动）
CLUSTER_4 = [
    {"id": "MEM000056", "ts": "2024-03-10 10:00:00", "days": 447, "city": "深圳", "place": "投资大厦", "landmark": "资本中心", "person": "李娜", "identity": "天使投资人", "partner": "张伟", "partner_id": "创业者", "relation": "合作伙伴", "event_type": "投资", "action": "投资", "product": "人工智能项目", "qty": 1, "price": 3000000, "cluster_id": "CLUSTER_人物_李娜", "chain": None, "tags": ["整理测试", "简单", "人物", "李娜"]},
    {"id": "MEM000057", "ts": "2024-05-20 14:00:00", "days": 377, "city": "广州", "place": "创业大赛", "landmark": "比赛场馆", "person": "李娜", "identity": "天使投资人", "partner": "张伟", "partner_id": "创业者", "relation": "合作伙伴", "event_type": "评审", "action": "评审", "product": "创业项目", "qty": 1, "price": 0, "cluster_id": "CLUSTER_人物_李娜", "chain": None, "tags": ["整理测试", "简单", "人物", "李娜"]},
    {"id": "MEM000058", "ts": "2024-07-15 09:00:00", "days": 321, "city": "苏州", "place": "科技园区", "landmark": "研发中心", "person": "李娜", "identity": "天使投资人", "partner": "张伟", "partner_id": "创业者", "relation": "合作伙伴", "event_type": "考察", "action": "考察", "product": "科技企业", "qty": 1, "price": 0, "cluster_id": "CLUSTER_人物_李娜", "chain": None, "tags": ["整理测试", "简单", "人物", "李娜"]},
]

# 存储正确性测试（扩展到10条）
STORAGE = [
    {"id": "MEM000059", "ts": "2024-12-01 10:00:00", "days": 182, "city": "成都", "place": "教育中心", "landmark": "培训机构", "person": "陈静", "identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手", "event_type": "学习", "action": "购买", "product": "数据分析课程", "qty": 1, "price": 5000, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000060", "ts": "2024-11-15 09:00:00", "days": 197, "city": "广州", "place": "证券公司", "landmark": "交易大厅", "person": "赵磊", "identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手", "event_type": "投资", "action": "投资", "product": "新能源股票", "qty": 5000, "price": 50, "chain": None, "cluster": None, "tags": ["存储测试", "中等"]},
    {"id": "MEM000061", "ts": "2024-10-20 08:00:00", "days": 224, "city": "深圳", "place": "体检中心", "landmark": "健康管理", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "体检", "action": "预约", "product": "全身体检", "qty": 1, "price": 5000, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000071", "ts": "2024-09-15 14:00:00", "days": 259, "city": "杭州", "place": "电商仓库", "landmark": "物流中心", "person": "周梅", "identity": "护士", "partner": "孙强", "partner_id": "医生", "relation": "同事", "event_type": "购物", "action": "购买", "product": "医疗用品", "qty": 50, "price": 200, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000072", "ts": "2024-08-20 10:00:00", "days": 285, "city": "北京", "place": "书店", "landmark": "文化中心", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "阅读", "action": "购买", "product": "法律书籍", "qty": 5, "price": 300, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000073", "ts": "2024-07-10 09:00:00", "days": 326, "city": "上海", "place": "健身房", "landmark": "健身中心", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "健身", "action": "购买", "product": "私教课程", "qty": 10, "price": 5000, "chain": None, "cluster": None, "tags": ["存储测试", "中等"]},
    {"id": "MEM000074", "ts": "2024-06-05 14:00:00", "days": 361, "city": "南京", "place": "学校", "landmark": "教学楼", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "教学", "action": "购买", "product": "教学设备", "qty": 20, "price": 10000, "chain": None, "cluster": None, "tags": ["存储测试", "中等"]},
]

# 深度检索测试（扩展到8条）
DEEP = [
    {"id": "MEM000062", "ts": "2022-06-01 09:00:00", "days": 1095, "city": "北京", "place": "清华大学", "landmark": "计算机系", "person": "张伟", "identity": "学生", "partner": "导师", "partner_id": "教授", "relation": "师生", "event_type": "研究", "action": "研究", "product": "神经网络", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["深度检索", "困难"], "depth": {"layers": 5, "associations": 4, "semantic_distance": "远"}},
    {"id": "MEM000063", "ts": "2022-09-15 14:00:00", "days": 990, "city": "北京", "place": "教授办公室", "landmark": "科研楼", "person": "张伟", "identity": "学生", "partner": "导师", "partner_id": "教授", "relation": "师生", "event_type": "推荐", "action": "获得", "product": "创业项目推荐", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["深度检索", "困难"], "depth": {"layers": 4, "associations": 3, "semantic_distance": "中"}},
    {"id": "MEM000064", "ts": "2023-01-20 10:00:00", "days": 862, "city": "北京", "place": "天使投资机构", "landmark": "融资中心", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "融资", "action": "获得", "product": "天使投资", "qty": 1, "price": 2000000, "chain": None, "cluster": None, "tags": ["深度检索", "困难"], "depth": {"layers": 3, "associations": 2, "semantic_distance": "近"}},
    {"id": "MEM000075", "ts": "2021-03-10 09:00:00", "days": 1178, "city": "武汉", "place": "医院", "landmark": "门诊部", "person": "孙强", "identity": "实习生", "partner": "导师", "partner_id": "主任医师", "relation": "师生", "event_type": "实习", "action": "学习", "product": "诊断技术", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["深度检索", "困难"], "depth": {"layers": 5, "associations": 3, "semantic_distance": "远"}},
    {"id": "MEM000076", "ts": "2021-06-20 14:00:00", "days": 1077, "city": "武汉", "place": "医学实验室", "landmark": "科研中心", "person": "孙强", "identity": "实习生", "partner": "导师", "partner_id": "主任医师", "relation": "师生", "event_type": "实验", "action": "完成", "product": "第一篇论文", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["深度检索", "困难"], "depth": {"layers": 4, "associations": 2, "semantic_distance": "中"}},
]

# 遗忘测试（扩展到8条）
FORGET = [
    {"id": "MEM000065", "ts": "2020-01-10 09:00:00", "days": 1998, "city": "武汉", "place": "武汉大学", "landmark": "创业学院", "person": "张伟", "identity": "大学生", "partner": "同学", "partner_id": "学生", "relation": "同学", "event_type": "比赛", "action": "参加", "product": "创业比赛", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["遗忘测试", "简单", "低频记忆"], "decay": {"level": "低频记忆", "access_count": 3}},
    {"id": "MEM000066", "ts": "2020-05-20 14:00:00", "days": 1872, "city": "武汉", "place": "互联网公司", "landmark": "实习基地", "person": "张伟", "identity": "实习生", "partner": "主管", "partner_id": "经理", "relation": "上下级", "event_type": "实习", "action": "开发", "product": "第一个APP", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["遗忘测试", "简单", "低频记忆"], "decay": {"level": "低频记忆", "access_count": 2}},
    {"id": "MEM000067", "ts": "2020-08-15 10:00:00", "days": 1785, "city": "武汉", "place": "创业咖啡厅", "landmark": "交流空间", "person": "张伟", "identity": "大学生", "partner": "同学", "partner_id": "学生", "relation": "同学", "event_type": "结识", "action": "结识", "product": "技术合伙人", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["遗忘测试", "简单", "低频记忆"], "decay": {"level": "低频记忆", "access_count": 1}},
    {"id": "MEM000077", "ts": "2019-09-01 08:00:00", "days": 2104, "city": "西安", "place": "大学", "landmark": "图书馆", "person": "郑欣", "identity": "学生", "partner": "同学", "partner_id": "学生", "relation": "同学", "event_type": "学习", "action": "准备", "product": "司法考试", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["遗忘测试", "简单", "低频记忆"], "decay": {"level": "低频记忆", "access_count": 2}},
    {"id": "MEM000078", "ts": "2019-12-20 14:00:00", "days": 1994, "city": "西安", "place": "法院", "landmark": "实习基地", "person": "郑欣", "identity": "实习生", "partner": "导师", "partner_id": "法官", "relation": "师生", "event_type": "实习", "action": "观摩", "product": "庭审过程", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["遗忘测试", "简单", "低频记忆"], "decay": {"level": "低频记忆", "access_count": 1}},
]

# 检索功能测试（扩展到8条）
RETRIEVAL = [
    {"id": "MEM000068", "ts": "2024-06-01 10:00:00", "days": 365, "city": "广州", "place": "餐厅", "landmark": "美食街", "person": "吴昊", "identity": "律师", "partner": "郑欣", "partner_id": "法官", "relation": "合作", "event_type": "聚餐", "action": "组织", "product": "团队聚餐", "qty": 1, "price": 3000, "chain": None, "cluster": None, "tags": ["检索测试", "中等"]},
    {"id": "MEM000069", "ts": "2024-05-15 14:00:00", "days": 381, "city": "西安", "place": "学校", "landmark": "教学楼", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "教学", "action": "开展", "product": "公开课", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
    {"id": "MEM000070", "ts": "2024-04-20 09:00:00", "days": 406, "city": "南京", "place": "体育馆", "landmark": "健身中心", "person": "李娜", "identity": "天使投资人", "partner": "张伟", "partner_id": "创业者", "relation": "合作伙伴", "event_type": "运动", "action": "参加", "product": "马拉松", "qty": 1, "price": 0, "chain": None, "cluster": None, "tags": ["检索测试", "中等"]},
    {"id": "MEM000079", "ts": "2024-03-15 10:00:00", "days": 442, "city": "苏州", "place": "园林", "landmark": "景观区", "person": "周梅", "identity": "护士", "partner": "孙强", "partner_id": "医生", "relation": "同事", "event_type": "旅游", "action": "游览", "product": "古典园林", "qty": 1, "price": 100, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
    {"id": "MEM000080", "ts": "2024-02-28 14:00:00", "days": 458, "city": "成都", "place": "茶馆", "landmark": "休闲区", "person": "赵磊", "identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手", "event_type": "休闲", "action": "品尝", "product": "成都茶", "qty": 1, "price": 50, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
]

# 额外存储测试（再增加5条）
STORAGE_EXTRA = [
    {"id": "MEM000081", "ts": "2024-06-20 09:00:00", "days": 346, "city": "深圳", "place": "手机店", "landmark": "数码城", "person": "王芳", "identity": "科技投资人", "partner": "刘洋", "partner_id": "技术合伙人", "relation": "合伙人", "event_type": "购物", "action": "购买", "product": "最新款手机", "qty": 1, "price": 8000, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000082", "ts": "2024-05-10 14:00:00", "days": 386, "city": "杭州", "place": "电脑城", "landmark": "科技市场", "person": "刘洋", "identity": "健身教练", "partner": "陈静", "partner_id": "会员经理", "relation": "同事", "event_type": "购物", "action": "购买", "product": "运动手表", "qty": 1, "price": 2000, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000083", "ts": "2024-04-15 10:00:00", "days": 411, "city": "广州", "place": "家具城", "landmark": "家居中心", "person": "陈静", "identity": "个人投资者", "partner": "赵磊", "partner_id": "交易员", "relation": "对手", "event_type": "装修", "action": "购买", "product": "办公桌椅", "qty": 10, "price": 5000, "chain": None, "cluster": None, "tags": ["存储测试", "中等"]},
    {"id": "MEM000084", "ts": "2024-03-20 08:00:00", "days": 436, "city": "南京", "place": "书店", "landmark": "文化中心", "person": "黄丽", "identity": "教师", "partner": "林峰", "partner_id": "校长", "relation": "上下级", "event_type": "采购", "action": "购买", "product": "教学参考书", "qty": 30, "price": 1500, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
    {"id": "MEM000085", "ts": "2024-02-28 14:00:00", "days": 458, "city": "成都", "place": "超市", "landmark": "购物中心", "person": "赵磊", "identity": "职业交易员", "partner": "陈静", "partner_id": "个人投资者", "relation": "对手", "event_type": "购物", "action": "购买", "product": "进口食品", "qty": 20, "price": 800, "chain": None, "cluster": None, "tags": ["存储测试", "简单"]},
]

# 额外检索测试（再增加5条）
RETRIEVAL_EXTRA = [
    {"id": "MEM000086", "ts": "2024-07-01 10:00:00", "days": 335, "city": "北京", "place": "机场", "landmark": "航站楼", "person": "张伟", "identity": "创业者", "partner": "李娜", "partner_id": "投资人", "relation": "合作伙伴", "event_type": "出行", "action": "乘坐", "product": "航班", "qty": 1, "price": 2000, "chain": None, "cluster": None, "tags": ["检索测试", "中等"]},
    {"id": "MEM000087", "ts": "2024-06-15 09:00:00", "days": 351, "city": "上海", "place": "酒店", "landmark": "商务区", "person": "李明", "identity": "金融分析师", "partner": "王芳", "partner_id": "房产顾问", "relation": "顾问", "event_type": "住宿", "action": "预订", "product": "商务酒店", "qty": 1, "price": 800, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
    {"id": "MEM000088", "ts": "2024-05-20 14:00:00", "days": 377, "city": "武汉", "place": "博物馆", "landmark": "展览中心", "person": "孙强", "identity": "医生", "partner": "周梅", "partner_id": "护士", "relation": "同事", "event_type": "参观", "action": "参观", "product": "历史展览", "qty": 1, "price": 50, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
    {"id": "MEM000089", "ts": "2024-04-10 08:00:00", "days": 416, "city": "西安", "place": "餐厅", "landmark": "美食街", "person": "郑欣", "identity": "法官", "partner": "吴昊", "partner_id": "律师", "relation": "合作", "event_type": "用餐", "action": "品尝", "product": "陕西面食", "qty": 1, "price": 30, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
    {"id": "MEM000090", "ts": "2024-03-05 10:00:00", "days": 452, "city": "苏州", "place": "园林", "landmark": "景观区", "person": "周梅", "identity": "护士", "partner": "孙强", "partner_id": "医生", "relation": "同事", "event_type": "旅游", "action": "游览", "product": "拙政园", "qty": 1, "price": 80, "chain": None, "cluster": None, "tags": ["检索测试", "简单"]},
]

ALL_SEEDS = (TEMPORAL_1 + TEMPORAL_2 + TEMPORAL_3 + 
             CAUSAL_1 + CAUSAL_2 + CAUSAL_3 +
             CONTRAST + INCLUSION + DEDUCTION + DEDUCTION_2 +
             CLUSTER_1 + CLUSTER_2 + CLUSTER_3 + CLUSTER_4 +
             STORAGE + STORAGE_EXTRA + DEEP + FORGET + RETRIEVAL + RETRIEVAL_EXTRA)


def _relative_time(days: int) -> str:
    if days <= 1: return "刚刚"
    if days <= 7: return f"{days}天前"
    if days <= 30: return f"{days//7}周前"
    if days <= 90: return f"{days//30}个月前"
    if days <= 365: return f"{days//30}个月前"
    return f"{days//365}年前"


def _fuzzy_time(days: int) -> str:
    if days <= 1: return "今天"
    if days <= 7: return "本周"
    if days <= 14: return "上周"
    if days <= 30: return "本月"
    if days <= 60: return "上个月"
    if days <= 180: return "半年前"
    if days <= 365: return "去年"
    if days <= 730: return "前年"
    return "多年前"


def _difficulty(days: int) -> str:
    if days > 730: return "困难"
    if days > 365: return "中等"
    return "简单"


def _weight(diff: str) -> float:
    return {"简单": 0.5, "中等": 1.0, "困难": 1.5}.get(diff, 1.0)


def build_memory(seed: dict, prev_id: str = "", next_id: str = "") -> dict:
    """将种子数据转换为完整的记忆结构。"""
    p = seed["person"]
    p2 = seed.get("partner", "")
    i1 = seed["identity"]
    i2 = seed.get("partner_id", "")
    c = seed["city"]
    pl = seed["place"]
    act = seed["action"]
    prod = seed["product"]
    qty = seed["qty"]
    price = seed["price"]
    dt = datetime.strptime(seed["ts"], "%Y-%m-%d %H:%M:%S")
    days = seed["days"]
    diff = _difficulty(days)

    # 3个版本
    v1 = f"{p}在{c}{pl}{act}了{prod}"
    if qty > 1 and seed.get("chain") is None:
        v1 += f"，数量{qty}"

    import random
    random.seed(hash(seed["id"]))
    feelings = ["觉得是个难得的机会", "认为值得全力以赴", "想趁窗口期推进", "认为这是正确方向"]
    feeling = random.choice(feelings)
    v2 = f"{p}回忆道：当时在{c}的{pl}，{p}（{i1}）{act}了{prod}，{feeling}"
    if qty > 1 and seed.get("chain") is None:
        v2 += f"，总共{qty}"
    if price > 0:
        v2 += f"，单价{price}元"

    fillers = ["听说", "据说", "好像"]
    hedges = ["大概", "差不多", "左右"]
    filler = random.choice(fillers)
    hedge = random.choice(hedges)
    v3 = f"{p2}说{p}在{c}那边{act}了{prod}，{filler}{hedge}"
    if qty > 1 and seed.get("chain") is None:
        v3 += f"{qty}"
    else:
        v3 += "有这回事"
    v3 += "，具体细节不太清楚"

    mem = {
        "memory_id": seed["id"],
        "category": seed["tags"][0] + "测试集",
        "difficulty": diff,
        "weight": _weight(diff),
        "time": {
            "absolute": seed["ts"],
            "relative": _relative_time(days),
            "fuzzy": _fuzzy_time(days),
            "timestamp": int(dt.timestamp())
        },
        "location": {
            "city": c,
            "place": pl,
            "landmark": seed.get("landmark", "")
        },
        "person": {
            "name": p,
            "identity": i1,
            "partner_name": p2,
            "partner_identity": i2,
            "relation": seed.get("relation", "")
        },
        "event": {
            "type": seed["event_type"],
            "action": act,
            "product": prod,
            "quantity": qty,
            "price": price
        },
        "versions": [
            {"version_id": "v1", "style": "客观叙述", "content": v1},
            {"version_id": "v2", "style": "主观视角", "content": v2},
            {"version_id": "v3", "style": "第三方转述", "content": v3}
        ],
        "tags": seed["tags"],
        "cluster_id": seed.get("cluster_id"),
        "reasoning_chain": seed.get("chain_id"),
        "chain_position": seed.get("chain_pos"),
        "decay": seed.get("decay", {"level": None, "access_count": 0}),
    }

    # 链式字段
    if seed.get("chain_id"):
        mem["chain_hop"] = seed["chain_pos"]
        mem["chain_total"] = seed["chain_total"]
        mem["chain_relation"] = seed["tags"][2]
        mem["chain_prev"] = prev_id
        mem["chain_next"] = next_id
        if mem["chain_relation"] in ["因果", "推导"]:
            mem["logic"] = {"type": mem["chain_relation"]}
    
    if "depth" in seed:
        mem["depth"] = seed["depth"]
    
    if not seed.get("chain_id") and not seed.get("cluster_id"):
        mem["retrieval_keywords"] = [p, c, seed["event_type"], act, prod]

    return mem


def build_chain_queries(chain_seeds: list, chain_type: str, qid: str) -> dict:
    """为一条链生成查询。"""
    first = chain_seeds[0]
    ids = [s["id"] for s in chain_seeds]
    
    p = first["person"]
    c = first["city"]
    act = first["action"]
    prod = first["product"]
    
    if chain_type == "时序":
        qtext = f"{p}在{c}{act}了{prod}，后续事件依次是什么？"
        parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in chain_seeds]
        ans = " → ".join(parts)
        qtype = "时序推理链"
        dim = "时序推理"
    elif chain_type == "因果":
        qtext = f"因为{p}在{c}{act}了{prod}，后续导致了哪些事件？"
        parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in chain_seeds]
        ans = " → ".join(parts)
        qtype = "因果推理链"
        dim = "因果推理"
    elif chain_type == "对比":
        persons = list(dict.fromkeys([s["person"] for s in chain_seeds]))
        qtext = f"{persons[0]}在{c}{act}了{prod}，和{persons[1] if len(persons)>1 else '其他人'}的做法有什么不同？"
        parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in chain_seeds]
        ans = " → ".join(parts)
        qtype = "对比推理链"
        dim = "对比推理"
    elif chain_type == "包含":
        qtext = f"{p}在{c}{act}了{prod}，这件事包含了哪些子事件？"
        parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in chain_seeds]
        ans = " → ".join(parts)
        qtype = "包含推理链"
        dim = "包含推理"
    elif chain_type == "推导":
        qtext = f"从{p}在{c}{act}了{prod}出发，能推导出什么？"
        parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in chain_seeds]
        ans = " → ".join(parts)
        qtype = "推导推理链"
        dim = "推导推理"
    else:
        qtext = f"关于{p}在{c}的事件"
        ans = ""
        qtype = "链式查询"
        dim = "链式推理"
    
    return {
        "query_id": qid, "query_text": qtext, "query_type": qtype,
        "test_dimension": dim, "expected_memory_ids": ids,
        "expected_answer_text": ans, "acceptable_answers": [ans],
        "is_negative": False, "difficulty": "中等"
    }


def build_cluster_queries(cluster_seeds: list, cluster_type: str, qid: str) -> dict:
    """为一个聚类生成查询。"""
    ids = [s["id"] for s in cluster_seeds]
    
    if cluster_type == "人物":
        p = cluster_seeds[0]["person"]
        qtext = f"{p}的活动记录有哪些"
    elif cluster_type == "事件":
        evt = cluster_seeds[0]["event_type"]
        qtext = f"关于{evt}的事件有哪些"
    elif cluster_type == "地点":
        c = cluster_seeds[0]["city"]
        qtext = f"在{c}发生的事件有哪些"
    else:
        qtext = "相关事件"
    
    parts = [f"{s['person']}在{s['city']}{s['action']}了{s['product']}" for s in cluster_seeds]
    ans = "；".join(parts)
    
    return {
        "query_id": qid, "query_text": qtext, "query_type": "聚类检索",
        "test_dimension": "聚类检索", "expected_memory_ids": ids,
        "expected_answer_text": ans, "acceptable_answers": [ans],
        "is_negative": False, "difficulty": "简单"
    }


def build_simple_query(seed: dict, qtype: str, qid: str) -> dict:
    """为基础记忆生成简单查询。"""
    p = seed["person"]
    c = seed["city"]
    act = seed["action"]
    prod = seed["product"]
    
    if qtype == "人物检索":
        qtext = f"{p}做了什么"
        dim = "精确检索"
    elif qtype == "地点检索":
        qtext = f"在{c}发生过什么"
        dim = "精确检索"
    elif qtype == "事件检索":
        qtext = f"关于{prod}的事件有哪些"
        dim = "精确检索"
    elif qtype == "组合检索":
        qtext = f"{p}在{c}的{act}记录"
        dim = "组合检索"
    elif qtype == "跨版本":
        qtext = f"关于{p}在{c}{act}了{prod}的详情，多说点"
        dim = "跨版本"
    elif qtype == "深度检索":
        qtext = f"{p}的早期经历对后续发展有什么影响"
        dim = "深度检索"
    elif qtype == "遗忘":
        qtext = f"{p}在武汉期间有什么经历"
        dim = "遗忘功能"
    else:
        qtext = f"{p}在{c}的事件"
        dim = "精确检索"
    
    ans = f"{p}在{c}{act}了{prod}"
    if seed["qty"] > 1 and seed.get("chain") is None:
        ans += f"，数量{seed['qty']}"
    
    return {
        "query_id": qid, "query_text": qtext,
        "query_type": qtype if qtype != "深度检索" else "深度推理",
        "test_dimension": dim, "expected_memory_ids": [seed["id"]],
        "expected_answer_text": ans, "acceptable_answers": [ans],
        "is_negative": False, "difficulty": _difficulty(seed["days"])
    }


def main():
    memories = []
    queries = []
    q_counter = 1

    def add_chain(chain_seeds, chain_type):
        nonlocal q_counter
        for i, seed in enumerate(chain_seeds):
            prev = chain_seeds[i-1]["id"] if i > 0 else ""
            next_id = chain_seeds[i+1]["id"] if i < len(chain_seeds)-1 else ""
            memories.append(build_memory(seed, prev, next_id))
        queries.append(build_chain_queries(chain_seeds, chain_type, f"Q{q_counter:04d}"))
        q_counter += 1

    def add_cluster(cluster_seeds, cluster_type):
        nonlocal q_counter
        for seed in cluster_seeds:
            memories.append(build_memory(seed))
        queries.append(build_cluster_queries(cluster_seeds, cluster_type, f"Q{q_counter:04d}"))
        q_counter += 1

    def add_simple(seed, qtype):
        nonlocal q_counter
        memories.append(build_memory(seed))
        queries.append(build_simple_query(seed, qtype, f"Q{q_counter:04d}"))
        q_counter += 1

    # 链式记忆
    add_chain(TEMPORAL_1, "时序")
    add_chain(TEMPORAL_2, "时序")
    add_chain(TEMPORAL_3, "时序")
    add_chain(CAUSAL_1, "因果")
    add_chain(CAUSAL_2, "因果")
    add_chain(CAUSAL_3, "因果")
    add_chain(CONTRAST, "对比")
    add_chain(INCLUSION, "包含")
    add_chain(DEDUCTION, "推导")
    add_chain(DEDUCTION_2, "推导")

    # 聚类
    add_cluster(CLUSTER_1, "人物")
    add_cluster(CLUSTER_2, "事件")
    add_cluster(CLUSTER_3, "地点")
    add_cluster(CLUSTER_4, "人物")

    # 存储测试 + 跨版本查询
    for seed in STORAGE + STORAGE_EXTRA:
        memories.append(build_memory(seed))
    q_cross = build_simple_query(STORAGE[0], "跨版本", f"Q{q_counter:04d}")
    mem_cross = next(m for m in memories if m["memory_id"] == STORAGE[0]["id"])
    q_cross["acceptable_answers"] = [v["content"] for v in mem_cross["versions"]]
    queries.append(q_cross)
    q_counter += 1

    # 深度检索
    for seed in DEEP:
        memories.append(build_memory(seed))
    queries.append(build_simple_query(DEEP[0], "深度检索", f"Q{q_counter:04d}"))
    q_counter += 1

    # 遗忘测试
    for seed in FORGET:
        memories.append(build_memory(seed))
    queries.append(build_simple_query(FORGET[0], "遗忘", f"Q{q_counter:04d}"))
    q_counter += 1

    # 检索功能测试
    for seed in RETRIEVAL + RETRIEVAL_EXTRA:
        memories.append(build_memory(seed))
    queries.append(build_simple_query(RETRIEVAL[0], "人物检索", f"Q{q_counter:04d}"))
    q_counter += 1
    queries.append(build_simple_query(RETRIEVAL[1], "地点检索", f"Q{q_counter:04d}"))
    q_counter += 1
    queries.append(build_simple_query(RETRIEVAL[2], "事件检索", f"Q{q_counter:04d}"))
    q_counter += 1

    # 基础精确检索（从链中取）
    queries.append(build_simple_query(TEMPORAL_1[0], "人物检索", f"Q{q_counter:04d}"))
    q_counter += 1
    queries.append(build_simple_query(TEMPORAL_1[0], "地点检索", f"Q{q_counter:04d}"))
    q_counter += 1
    queries.append(build_simple_query(TEMPORAL_1[0], "事件检索", f"Q{q_counter:04d}"))
    q_counter += 1
    queries.append(build_simple_query(TEMPORAL_1[0], "组合检索", f"Q{q_counter:04d}"))
    q_counter += 1

    # 负样本（多样化：地点不存在、人物不存在、产品不存在、时间不存在）
    negative_queries = [
        {"query_id": f"Q{q_counter:04d}", "query_text": "张三在火星购买了房产", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
        {"query_id": f"Q{q_counter+1:04d}", "query_text": "李四在月球开设了餐厅", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
        {"query_id": f"Q{q_counter+2:04d}", "query_text": "王五在木星投资了股票", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
        {"query_id": f"Q{q_counter+3:04d}", "query_text": "孙悟空在北京参加了行业峰会", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
        {"query_id": f"Q{q_counter+4:04d}", "query_text": "张伟在成都会见了外星人", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
        {"query_id": f"Q{q_counter+5:04d}", "query_text": "李明在2028年购买了房产", "query_type": "负样本", "test_dimension": "负样本", "expected_memory_ids": [], "expected_answer_text": "", "acceptable_answers": [], "is_negative": True, "difficulty": "简单"},
    ]
    queries.extend(negative_queries)
    q_counter += 6

    # 统计类别
    categories = {}
    for m in memories:
        cat = m["category"]
        categories[cat] = categories.get(cat, 0) + 1

    db = {
        "database_info": {
            "name": "MemTest Database",
            "version": "2.0.0",
            "total_count": len(memories),
            "categories": categories,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "memories": memories,
        "queries": queries
    }

    print(json.dumps(db, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
