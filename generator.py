#!/usr/bin/env python3
"""MemTest 测试数据库生成器 — 支持纯程序化合成 和 LLM增强生成

模式:
  --mock (默认): 纯程序化，零依赖，秒级生成
  --llm:          LLM增强生成，记忆文本更自然，查询更多样

用法:
    python generator.py              # 程序化生成 sample_db_100.json
    python generator.py --llm        # LLM增强生成（需要 DEEPSEEK_API_KEY）
    python generator.py --size=500   # 自定义规模
    python generator.py --full        # 生成10000条（程序化）
"""

import json, random, os, sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import defaultdict

random.seed(42)

# ====== 数据池（扩展版） ======
CITIES = [
    "北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "西安", "南京", "苏州",
    "天津", "重庆", "青岛", "长沙", "郑州", "东莞", "佛山", "宁波", "无锡", "济南",
    "合肥", "福州", "厦门", "沈阳", "大连", "哈尔滨", "长春", "南昌", "昆明", "贵阳",
    "石家庄", "太原", "呼和浩特", "兰州", "银川", "西宁", "乌鲁木齐", "海口", "三亚", "拉萨",
    "珠海", "中山", "惠州", "汕头", "江门", "湛江", "茂名", "肇庆", "清远", "潮州",
    "威海", "烟台", "潍坊", "淄博", "德州", "聊城", "临沂", "济宁", "泰安", "日照",
    "湖州", "嘉兴", "金华", "绍兴", "衢州", "舟山", "台州", "温州", "丽水", "徐州",
    "扬州", "盐城", "淮安", "镇江", "泰州", "宿迁", "南通", "连云港", "连云港", "连云港",
    "洛阳", "开封", "安阳", "新乡", "焦作", "许昌", "平顶山", "信阳", "南阳", "商丘",
    "岳阳", "常德", "衡阳", "株洲", "湘潭", "邵阳", "益阳", "郴州", "永州", "怀化",
    "桂林", "柳州", "北海", "梧州", "钦州", "贵港", "玉林", "百色", "贺州", "河池",
    "遵义", "六盘水", "安顺", "铜仁", "毕节", "兴义", "凯里", "都匀", "福泉", "仁怀",
]
PLACES = [
    "星巴克", "肯德基", "麦当劳", "海底捞", "全聚德", "外婆家", "绿茶餐厅", "西贝莜面村",
    "瑞幸咖啡", "喜茶", "奈雪的茶", "一点点", "CoCo都可", "蜜雪冰城",
    "万达广场", "万象城", "太古里", "IFS国金中心", "大悦城", "龙湖天街", "来福士",
    "盒马鲜生", "永辉超市", "山姆会员店", "麦德龙", "家乐福", "沃尔玛", "大润发",
    "故宫", "长城", "颐和园", "西湖", "黄山", "泰山", "兵马俑", "外滩", "东方明珠",
    "公司办公室", "会议室A", "会议室B", "茶水间", "休息室", "健身房", "停车场",
    "火车站", "机场", "码头", "港口", "海关", "边检站",
    "幼儿园", "小学", "中学", "大学", "培训机构", "图书馆",
    "医院", "诊所", "药店", "体检中心", "康复中心",
    "银行", "证券公司", "保险公司", "信托公司", "基金公司",
    "法院", "检察院", "公安局", "派出所", "税务局",
    "酒店", "宾馆", "民宿", "青年旅舍", "度假村", "温泉",
    "KTV", "酒吧", "夜店", "网吧", "棋牌室", "桌游吧",
    "电影院", "剧院", "音乐厅", "美术馆", "博物馆", "科技馆",
    "公园", "植物园", "动物园", "游乐场", "水上乐园", "滑雪场",
    "寺庙", "教堂", "清真寺", "道观", "祠堂", "宗祠",
    "健身房", "游泳馆", "羽毛球馆", "篮球馆", "足球场", "网球场",
    "菜市场", "花鸟市场", "古玩市场", "跳蚤市场", "夜市", "大集",
    "加油站", "充电站", "维修站", "4S店", "洗车店", "停车场",
]
LANDMARKS = [
    "CBD核心区", "科技园区", "金融中心", "地铁站", "公交站", "高铁站", "机场航站楼",
    "大学城", "创业孵化园", "经济开发区", "自由贸易区", "保税区",
    "老城区", "新城区", "开发区", "工业区", "物流园区", "仓储中心",
    "滨江带", "河滨公园", "湖畔步道", "山顶观景台", "森林公园入口",
    "商业步行街", "美食一条街", "夜市一条街", "古玩一条街", "酒吧一条街",
    "古镇入口", "古村落", "文化街区", "历史街区", "非遗街区",
    "码头", "渡口", "船闸", "灯塔", "瞭望塔", "观景台",
    "纪念碑", "纪念堂", "纪念馆", "烈士陵园", "英雄广场",
    "体育场馆", "奥林匹克中心", "综合体育馆", "游泳馆", "田径场",
    "会展中心", "会议中心", "博览中心", "展览馆", "展示中心",
]
NAMES = [
    "张伟", "王芳", "李明", "刘洋", "陈静", "杨勇", "赵丽", "周强",
    "吴敏", "郑鹏", "孙杰", "马超", "朱婷", "胡磊", "郭峰", "林雪",
    "何涛", "高建", "罗欢", "梁志", "宋雨", "唐军", "许飞", "韩冰",
    "邓伟", "冯磊", "于娜", "董洁", "潘阳", "蒋伟", "蔡明", "余涛",
    "杜鹃", "苏敏", "魏强", "卢杰", "姜丽", "阎峰", "薛磊", "孟莉",
    "常琪", "顾瑶", "武毅", "贺文", "赖勇", "邦达", "申然", "盛天",
    "牛博", "洪峰", "师倩", "於洋", "龚伟", "祁坚", "缪磊", "施雨",
    "孔祥", "曹华", "严军", "苏醒", "单丹", "乔磊", "楚雷", "楚雨",
    "楚阳", "钱伟", "储勇", "焦强", "籍磊", "窦莉", "章娜", "麦朵",
    "庄潇", "柴明", "蒙杰", "桂峰", "聂攀", "晁哲", "哈丹", "元华",
    "卜顾", "孟平", "谷梁", "谭勋", "官恩", "荆孝", "巫丹", "仇嵩",
    "栾朵", "戚谢", "邹游", "储梅", "喻理", "柏林", "和水", "窦章",
    "桑菜", "应华", "宗政", "蒲团", "司徒", "上官", "欧阳", "司马",
    "东方", "独孤", "慕容", "宇文", "长孙", "轩辕", "令狐", "诸葛",
    "皇甫", "尉迟", "公孙", "仲孙", "孙叔", "叔孙", "季孙", "孟孙",
    "钟离", "宇文", "长孙", "慕容", "鲜于", "闾丘", "司徒", "司空",
    "亓官", "司寇", "仉督", "子车", "颛孙", "端木", "巫马", "公西",
    "漆雕", "乐正", "壤驷", "公良", "拓跋", "夹谷", "宰父", "谷梁",
    "晋楚", "闫法", "汝鄢", "涂钦", "段干", "百里", "东郭", "南门",
    "呼延", "归海", "羊舌", "微生", "岳帅", "缑亢", "况后", "有琴",
    "梁丘", "左丘", "东门", "西门", "商牟", "佘佴", "伯赏", "南宫",
    "墨哈", "谯笪", "年爱", "阳佟", "第五", "言福", "寸贝", "尺素",
]
IDENTITIES = [
    "项目经理", "软件工程师", "产品经理", "设计师", "销售经理", "市场专员", "财务主管",
    "HR经理", "运营总监", "客户经理", "数据分析师", "算法工程师", "测试工程师", "架构师",
    "CTO", "CEO", "COO", "CFO", "总监", "大学教授", "中学老师", "医生", "律师", "咨询师",
    "研究员", "科学家", "工程师", "技术员", "技工", "飞行员", "船长", "司机",
    "厨师", "服务员", "收银员", "保安", "保洁", "园丁", "电工", "水工", "木工",
    "记者", "编辑", "主播", "摄影师", "导演", "演员", "歌手", "舞者",
    "画家", "书法家", "雕塑家", "设计师", "程序员", "作家", "诗人",
    "运动员", "教练", "裁判", "经纪人", "评论员", "解说员",
    "公务员", "警察", "法官", "检察官", "律师", "公证员", "仲裁员",
    "军人", "武警", "消防员", "海关", "边检", "检疫", "安检",
    "护士", "药剂师", "检验师", "放射师", "康复师", "营养师",
    "会计", "出纳", "审计", "税务", "统计", "精算", "估价",
    "经纪人", "中介", "代理", "代表", "经销商", "零售商", "批发商",
    "农民", "渔民", "牧民", "猎人", "花匠", "木匠", "铁匠", "石匠",
    "导游", "翻译", "口译", "笔译", "同传", "交传",
    "司机", "船长", "飞行员", "列车长", "乘务员", "调度员",
    "保安", "保镖", "警卫", "门卫", "巡逻", "监控", "安检",
    "保姆", "月嫂", "育婴师", "养老护理", "家政", "保洁",
    "快递员", "外卖员", "跑腿", "闪送", "代驾", "网约车司机",
]
RELATIONS = [
    "同事", "上级", "下属", "平级", "朋友", "闺蜜", "兄弟", "同学", "客户", "合作伙伴",
    "夫妻", "父子", "母子", "父女", "母女", "兄妹", "姐弟", "表亲", "堂亲", "远亲",
    "邻居", "同乡", "校友", "战友", "狱友", "棋友", "牌友", "球友", "驴友", "跑友",
    "师徒", "师兄弟", "师姐妹", "师兄", "师弟", "师姐", "师妹",
    "甲方", "乙方", "丙方", "丁方", "投资方", "被投资方", "供应商", "采购商",
    "债权人", "债务人", "担保人", "见证人", "中介人", "经纪人", "代理人",
    "房东", "租客", "业主", "物业", "开发商", "中介", "二房东",
    "医生", "患者", "律师", "委托人", "老师", "学生", "教练", "学员",
]
EVENT_TYPES = {
    "交易": ["购买", "出售", "投资", "转账", "退款", "捐赠", "抵押", "拍卖", "收购", "合并"],
    "会议": ["召开", "参加", "主持", "复盘", "筹备", "取消", "延期", "改期", "提前", "推迟"],
    "日常": ["上班", "出差", "加班", "拜访", "接待", "请假", "调休", "值班", "轮班", "打卡"],
    "情感": ["庆祝", "感谢", "祝福", "道歉", "安慰", "鼓励", "批评", "表扬", "奖励", "惩罚"],
    "冲突": ["争吵", "打架", "投诉", "举报", "起诉", "辩护", "调解", "仲裁", "判决", "执行"],
    "发现": ["发现", "发明", "创造", "设计", "构思", "策划", "策划", "实施", "验证", "发布"],
    "转折": ["升职", "降职", "调岗", "离职", "入职", "退休", "复职", "停职", "撤职", "辞职"],
    "意外": ["事故", "故障", "损坏", "丢失", "被盗", "被骗", "受伤", "生病", "死亡", "失踪"],
    "技术": ["开发", "测试", "上线", "发布", "部署", "维护", "升级", "降级", "回滚", "重构"],
    "学习": ["入学", "毕业", "考试", "答辩", "论文", "科研", "实习", "进修", "培训", "认证"],
    "健康": ["体检", "就医", "手术", "住院", "出院", "复查", "康复", "保健", "运动", "减肥"],
    "旅行": ["出发", "到达", "转机", "改签", "退票", "延误", "取消", "改签", "升舱", "降舱"],
    "娱乐": ["看电影", "看演出", "玩游戏", "K歌", "跳舞", "打牌", "下棋", "打球", "游泳", "滑雪"],
    "餐饮": ["订餐", "排队", "等位", "点餐", "上菜", "加菜", "退菜", "打包", "结账", "小费"],
    "购物": ["浏览", "收藏", "加购", "下单", "支付", "发货", "收货", "退货", "换货", "评价"],
    "交通": ["驾车", "乘车", "骑车", "步行", "打车", "拼车", "租车", "停车", "加油", "充电"],
    "居住": ["租房", "买房", "装修", "搬家", "入住", "退房", "续租", "转租", "合租", "独居"],
    "社交": ["聚会", "聚餐", "约会", "相亲", "联谊", "团建", "沙龙", "论坛", "峰会", "展会"],
    "金融": ["存款", "取款", "贷款", "还款", "理财", "保险", "基金", "股票", "债券", "期货"],
    "法律": ["签约", "违约", "解约", "续约", "转让", "继承", "赠与", "遗赠", "公证", "见证"],
}
PRODUCTS = [
    "茅台", "五粮液", "苹果股票", "特斯拉", "比亚迪", "宁德时代", "腾讯", "阿里",
    "字节跳动", "京东", "美团", "百度", "小米", "华为", "比特币", "以太坊", "黄金",
    "白银", "石油", "天然气", "大豆", "玉米", "小麦", "棉花", "白糖", "橡胶", "铜", "铝", "锌", "镍",
    "锂电池", "光伏板", "芯片", "半导体", "人工智能", "云计算", "大数据", "区块链", "物联网", "5G",
    "新能源汽车", "自动驾驶", "无人机", "机器人", "VR", "AR", "元宇宙", "NFT", "DeFi", "Web3",
    "基因编辑", "细胞治疗", "mRNA疫苗", "靶向药", "免疫疗法", "干细胞", "克隆技术", "合成生物学",
    "量子计算", "量子通信", "量子加密", "量子传感器", "量子雷达", "量子导航", "量子测量",
    "核聚变", "可控核聚变", "小型核反应堆", "钍基熔盐堆", "快中子反应堆", "高温气冷堆",
    "空间站", "月球基地", "火星探测器", "小行星采矿", "太空旅游", "卫星互联网", "星链",
    "深海探测", "深海采矿", "海底电缆", "海洋牧场", "海水淡化", "潮汐发电", "波浪发电",
    "碳捕获", "碳封存", "碳交易", "碳中和", "碳达峰", "碳足迹", "碳排放权", "碳税",
    "可控核聚变", "钍基熔盐堆", "快中子反应堆", "高温气冷堆", "核电池",
    "氢能源", "燃料电池", "固态电池", "钠离子电池", "钾离子电池", "钙钛矿电池",
    "石墨烯", "碳纳米管", "富勒烯", "金刚石", "碳纤维", "碳陶瓷", "碳复合材料",
    "超导材料", "拓扑绝缘体", "二维材料", "MXene", "黑磷", "氮化硼", "硅烯",
    "生物材料", "仿生材料", "自愈合材料", "形状记忆合金", "压电材料", "热电材料",
    "光刻胶", "光刻机", "光刻掩膜", "光刻透镜", "光刻光源", "光刻工作台", "光刻对准系统",
    "基因测序", "基因合成", "基因编辑", "基因治疗", "基因诊断", "基因芯片", "基因数据库",
    "脑机接口", "神经芯片", "神经假体", "神经调控", "神经反馈", "神经影像", "神经计算",
    "类脑计算", "神经形态芯片", "脉冲神经网络", " reservoir computing", "忆阻器",
]


def load_prompt(name: str) -> str:
    """从 prompts/ 目录加载提示词模板。"""
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
    # Fallback: 返回内联提示词
    return _INLINE_PROMPTS.get(name, "")


# ====== 内联提示词（当 prompts/ 目录不可用时回退） ======
_INLINE_PROMPTS = {
    "memory_enhance": """给定以下结构化记忆，生成同一事件的3种不同表达风格。

输入: {"person": "{person}", "identity": "{identity}", "location": "{location}", "event": "{event}", "time": "{time}"}

输出JSON格式: {"versions": [{"style":"标准叙述","content":"..."},{"style":"详细描述","content":"..."},{"style":"口语化","content":"..."}]}

规则：
1. 三种风格描述同一事件，核心事实一致
2. 不要编造未提供的信息
3. 每种版本30-120字，中文""",

    "query_generate": """给定以下记忆，生成5种查询方式。

输入: {"person": "{person}", "location": "{location}", "event": "{event}", "time": "{time}"}

输出JSON格式: {"queries": [{"query_type":"人物检索","query_text":"...","difficulty":"简单"}, ...]}

查询类型: 人物检索、地点检索、时间检索、事件检索、组合检索
难度: 简单(单一维度)、中等(两个维度)、困难(3+维度)
不要直接复制原文，要换一种表达""",
}


def _prompt_from_template(template_name: str, **kwargs) -> str:
    """用kwargs填充提示词模板中的占位符。"""
    prompt = load_prompt(template_name)
    for key, val in kwargs.items():
        prompt = prompt.replace("{" + key + "}", str(val))
    return prompt


# ====== 时间生成 ======
def time_desc(days_ago: int) -> str:
    if days_ago == 0: return "刚刚"
    if days_ago == 1: return "昨天"
    if days_ago < 7: return f"{days_ago}天前"
    if days_ago < 30: return f"{days_ago//7}周前"
    if days_ago < 365: return f"{days_ago//30}个月前"
    return f"{days_ago//365}年前"

def fuzzy_time(days_ago: int) -> str:
    opts = {0:"今天",1:"昨天",3:"前几天",7:"上周",30:"上个月",90:"三个月前",180:"半年前",365:"去年"}
    fuzz = "以前"
    for d, opt in sorted(opts.items(), reverse=True):
        if days_ago >= d: fuzz = opt; break
    return fuzz


# ====== 版本生成 ======
def make_versions_programmatic(base: dict) -> list:
    """程序化生成3种表达 — 真正的语义差异：
    v1 客观：标准叙述，完整要素
    v2 主观：从人物1视角，含心理/感受/意图
    v3 转述：第三方视角，含推测/省略/语气词
    """
    dt = base["base_time"]
    p1, p2 = base["person1"], base["person2"]
    i1, i2 = base["identity1"], base["identity2"]
    city, place = base["city"], base["place"]
    action, product = base["action"], base["product"]
    qty, price = base["quantity"], base["price"]
    
    # v1 客观叙述：标准事实，完整要素
    v1 = {
        "version_id": "v1", "style": "客观叙述",
        "content": f"{p1}在{city}{place}{action}了{product}，数量{qty}"
    }
    
    # v2 主观视角：从p1的视角，含心理活动和感受
    feelings = ["觉得是个机会", "认为价格合适", "想试试运气", "觉得有必要",
                "想趁低价入手", "认为值得投入", "考虑再三后决定", "不想错过"]
    v2 = {
        "version_id": "v2", "style": "主观视角",
        "content": f"{p1}回忆道：当时{city}的{place}，{p1}（{i1}）{action}了{product}，{random.choice(feelings)}，总共{qty}，单价{price}元"
    }
    
    # v3 第三方转述：从p2或旁观者的视角，含推测、省略、口语化
    fillers = ["好像", "听说", "大概", "据说", "应该"]
    hedges = ["大概", "差不多", "左右", "可能"]
    v3 = {
        "version_id": "v3", "style": "第三方转述",
        "content": f"{p2}说{p1}在{city}那边{action}了{product}，{random.choice(fillers)}{random.choice(hedges)}{qty}的样子，具体价格不太清楚"
    }
    
    return [v1, v2, v3]

def make_versions_llm(base: dict, llm) -> list:
    """LLM增强生成3种表达（更自然，需要API key）。"""
    prompt = _prompt_from_template(
        "memory_enhance",
        person=base["person1"],
        identity=base["identity1"],
        location=f"{base['city']} {base['place']}",
        event=f"{base['action']} {base['product']} {base['quantity']}股",
        time=base["base_time"].strftime("%Y-%m-%d"),
    )
    result = llm.generate_json(prompt, max_tokens=1500, temperature=0.3)
    versions = result.get("versions", [])
    if not versions:
        # LLM失败，回退到程序化
        return make_versions_programmatic(base)
    # 标准化
    for i, v in enumerate(versions):
        v["version_id"] = f"v{i+1}"
    return versions


# ====== 查询生成 ======
QUERY_TEMPLATES = {
    "时间检索": lambda m: [
        f"查找{m['time']['relative']}发生的事情",
        f"查询{m['time']['fuzzy']}在{m['location']['city']}的相关记录",
        f"{m['time']['relative']}有什么重要的事",
        f"{m['time']['fuzzy']}那段时间发生了什么",
        f"{m['time']['absolute']}前后有什么记录",
        f"{m['time']['relative']}的记忆",
        f"{m['time']['fuzzy']}的事件有哪些",
        f"{m['time']['absolute']}当天发生了什么",
        f"{m['time']['relative']}左右的事情",
        f"{m['time']['fuzzy']}期间{m['person']['name']}在做什么",
    ],
    "地点检索": lambda m: [
        f"在{m['location']['city']}{m['location']['place']}发生过什么",
        f"查询{m['location']['landmark']}的相关记忆",
        f"{m['location']['city']}那边有什么记录",
        f"{m['location']['place']}附近发生过什么事",
        f"{m['location']['city']}市的{m['location']['place']}",
        f"{m['location']['landmark']}附近的事件",
        f"{m['location']['city']}有什么值得关注的事",
        f"{m['location']['place']}的情况",
        f"{m['location']['city']}的记忆",
        f"{m['location']['place']}发生过{m['event']['action']}吗",
    ],
    "人物检索": lambda m: [
        f"{m['person']['name']}最近做了什么",
        f"查询{m['person']['name']}的{m['person']['identity']}相关活动",
        f"{m['person']['name']}有什么新动态",
        f"{m['person']['name']}在{m['time']['relative']}忙什么",
        f"{m['person']['name']}的{m['event']['type']}相关记录",
        f"{m['person']['name']}近期行踪",
        f"{m['person']['name']}在{m['location']['city']}的活动",
        f"{m['person']['name']}和{m['person']['partner_name']}的事",
        f"{m['person']['name']}({m['person']['identity']})的近况",
        f"{m['person']['name']}的{m['event']['action']}记录",
    ],
    "事件检索": lambda m: [
        f"关于{m['event']['product']}的事件有哪些",
        f"查询{m['event']['action']}相关的记录",
        f"{m['event']['product']}的相关信息",
        f"{m['event']['action']}了{m['event']['product']}的情况",
        f"{m['event']['type']}类型的事件",
        f"{m['event']['product']}最新动态",
        f"{m['event']['action']}相关的{m['event']['product']}",
        f"{m['event']['product']}的{m['event']['action']}记录",
        f"{m['event']['type']}类别下的事件",
        f"{m['event']['product']}和{m['person']['name']}的关系",
    ],
    "组合检索": lambda m: [
        f"{m['person']['name']}在{m['location']['city']}的{m['event']['action']}记录",
        f"查询{m['time']['relative']}{m['person']['name']}在{m['location']['place']}的{m['event']['type']}事件",
        f"{m['person']['name']}在{m['time']['relative']}{m['location']['city']}做了什么",
        f"{m['location']['city']}{m['time']['relative']} {m['person']['name']}的活动",
        f"{m['person']['name']}在{m['location']['place']}{m['event']['action']}了{m['event']['product']}",
        f"{m['time']['fuzzy']} {m['person']['name']}在{m['location']['city']}的{m['event']['type']}事",
        f"{m['person']['name']}({m['person']['identity']})在{m['location']['city']}的{m['event']['action']}",
        f"{m['location']['city']}的{m['time']['relative']} {m['person']['name']}发生了什么",
        f"{m['person']['name']}和{m['person']['partner_name']}在{m['location']['city']}的事",
        f"{m['time']['absolute']} {m['location']['city']} {m['person']['name']}的{m['event']['action']}",
    ]
}

# ====== 评测维度定义 ======
TEST_DIMENSIONS = {
    "精确检索": {"description": "单维度精确匹配", "ratio": 0.20, "query_types": ["人物检索", "地点检索", "事件检索"]},
    "组合检索": {"description": "多维度组合查询", "ratio": 0.15, "query_types": ["组合检索"]},
    "时序推理": {"description": "时间先后推理", "ratio": 0.12, "query_types": ["时序链"]},
    "因果推理": {"description": "因果关系推理", "ratio": 0.12, "query_types": ["因果链"]},
    "对比推理": {"description": "对比关系识别", "ratio": 0.08, "query_types": ["对比链"]},
    "包含推理": {"description": "层级包含关系", "ratio": 0.08, "query_types": ["包含链"]},
    "推导推理": {"description": "逻辑推导", "ratio": 0.08, "query_types": ["推导链"]},
    "聚类检索": {"description": "主题聚类检索", "ratio": 0.07, "query_types": ["聚类检索"]},
    "跨版本": {"description": "同一记忆不同表述匹配", "ratio": 0.05, "query_types": ["跨版本"]},
    "负样本": {"description": "不相关查询过滤", "ratio": 0.20, "query_types": ["负样本"]},
}

def _get_memory_dimension(m: dict) -> str:
    """根据记忆特征判断其最适合的评测维度。"""
    if m.get("chain_relation") == "时序":
        return "时序推理"
    elif m.get("chain_relation") == "因果":
        return "因果推理"
    elif m.get("chain_relation") == "对比":
        return "对比推理"
    elif m.get("chain_relation") == "包含":
        return "包含推理"
    elif m.get("chain_relation") == "推导":
        return "推导推理"
    elif m.get("cluster_id"):
        return "聚类检索"
    elif m.get("category") == "存储正确性测试集":
        return "精确检索"
    elif m.get("category") == "长期记忆深度检索测试集":
        return "跨版本"
    else:
        return "组合检索"

def _allocate_queries_by_dimension(memories: list, count: int) -> dict:
    """按评测维度分配查询配额，返回 dimension -> [memories] 映射。"""
    allocations = {}
    for dim_name, dim_cfg in TEST_DIMENSIONS.items():
        n = max(1, int(count * dim_cfg["ratio"]))
        allocations[dim_name] = n
    
    # 按维度分组记忆
    dim_memories = defaultdict(list)
    for m in memories:
        dim = _get_memory_dimension(m)
        dim_memories[dim].append(m)
    
    # 分配查询到记忆
    result = defaultdict(list)
    used_mems = set()
    
    for dim_name, target_count in allocations.items():
        available = [m for m in dim_memories[dim_name] if m["memory_id"] not in used_mems]
        if not available:
            continue
        n = min(target_count, len(available))
        selected = random.sample(available, n)
        for m in selected:
            used_mems.add(m["memory_id"])
        result[dim_name] = selected
    
    return dict(result)

def _format_answer_structured(m: dict) -> dict:
    """将记忆格式化为结构化答案，包含关键字段。"""
    return {
        "person": m["person"]["name"],
        "location": f"{m['location']['city']}{m['location']['place']}",
        "action": m["event"]["action"],
        "product": m["event"]["product"],
        "quantity": m["event"]["quantity"],
        "price": m["event"]["price"],
        "time": m["time"]["absolute"]
    }


def _format_answer_text(m: dict) -> str:
    """格式化答案为字段化文本。"""
    return f"人物：{m['person']['name']}，地点：{m['location']['city']}{m['location']['place']}，动作：{m['event']['action']}，对象：{m['event']['product']}，数量：{m['event']['quantity']}，时间：{m['time']['absolute']}"


def generate_queries_programmatic(memories: list, count: int = 100) -> list:
    """程序化生成查询（默认），含20%负样本，按评测维度平衡分配。"""
    queries = []
    
    # 按维度分配记忆
    dim_allocations = _allocate_queries_by_dimension(memories, count)
    
    # 生成各维度查询
    used_chains = set()  # 每条链只生成一个查询
    for dim_name, mems in dim_allocations.items():
        if dim_name == "负样本":
            continue
        
        for i, m in enumerate(mems):
            if dim_name in ["精确检索", "组合检索", "聚类检索", "跨版本"]:
                qtype = random.choice(TEST_DIMENSIONS[dim_name]["query_types"])
                if qtype == "人物检索":
                    qtext = f'{m["person"]["name"]}做了什么'
                elif qtype == "地点检索":
                    qtext = f'在{m["location"]["city"]}发生过什么'
                elif qtype == "事件检索":
                    qtext = f'关于{m["event"]["product"]}的事件有哪些'
                elif qtype == "组合检索":
                    qtext = f'{m["person"]["name"]}在{m["location"]["city"]}的{m["event"]["action"]}记录'
                elif qtype == "聚类检索":
                    # 使用记忆的产品名或标签中的真实关键词，避免代码变量名
                    theme = m.get("event", {}).get("product", "")
                    if not theme or theme in ["event_type", "location", "memory_id"]:
                        tags = m.get("tags", [])
                        theme = tags[0] if tags else "相关"
                    qtext = f'关于{theme}的记录有哪些'
                elif qtype == "跨版本":
                    # 自然语言提问，不指定风格
                    qtext = f'关于{m["person"]["name"]}在{m["location"]["city"]}{m["event"]["action"]}的详情，多说点'
                else:
                    qtype = "组合检索"
                    qtext = f'{m["person"]["name"]}在{m["location"]["city"]}的{m["event"]["action"]}记录'
                
                # 答案：所有版本作为可接受答案
                acceptable_answers = [v["content"] for v in m.get("versions", [])]
                
                # 结构化答案
                structured_answer = _format_answer_structured(m)
                answer_text = _format_answer_text(m)
                
                queries.append({
                    "query_id": f"Q{len(queries)+1:04d}",
                    "query_text": qtext,
                    "query_type": qtype,
                    "test_dimension": dim_name,
                    "expected_memory_ids": [m["memory_id"]],
                    "expected_answer": structured_answer,
                    "expected_answer_text": answer_text,
                    "acceptable_answers": acceptable_answers,
                    "expected_time": m["time"]["absolute"],
                    "difficulty": m["difficulty"],
                    "search_depth": random.choice(["浅层","中层","深层"])
                })
            
            elif dim_name in ["时序推理", "因果推理", "对比推理", "包含推理", "推导推理"]:
                chain_id = m.get("reasoning_chain", "")
                if chain_id and chain_id in used_chains:
                    continue  # 该链已生成过查询，跳过
                if chain_id:
                    chain_mems = sorted([x for x in memories if x.get("reasoning_chain") == chain_id],
                                        key=lambda x: x.get("chain_position", 0) or 0)
                    if len(chain_mems) >= 2:
                        used_chains.add(chain_id)
                        # 构建链的摘要作为答案
                        chain_summary = []
                        for cm in chain_mems:
                            chain_summary.append(f'{cm["person"]["name"]}在{cm["location"]["city"]}{cm["event"]["action"]}了{cm["event"]["product"]}')
                        chain_text = " → ".join(chain_summary)
                        
                        # 用链中的第一个动作作为查询引子
                        first_mem = chain_mems[0]
                        p_name = first_mem["person"]["name"]
                        p_action = first_mem["event"]["action"]
                        p_product = first_mem["event"]["product"]
                        
                        if dim_name == "时序推理":
                            qtext = f'{p_name}的{p_action}链后续事件依次是什么？'
                        elif dim_name == "因果推理":
                            qtext = f'因为{p_name}{p_action}了{p_product}，导致了哪些后续事件？'
                        elif dim_name == "对比推理":
                            # 对比链：需要链中两个不同人物或不同动作
                            if len(chain_mems) >= 2:
                                qtext = f'{p_name}和{chain_mems[1]["person"]["name"]}在{p_action}了{p_product}方面有什么不同？'
                            else:
                                qtext = f'和{p_name}{p_action}了{p_product}相比，有什么变化？'
                        elif dim_name == "包含推理":
                            qtext = f'{p_name}{p_action}了{p_product}，这件事里包含了哪些子事件？'
                        elif dim_name == "推导推理":
                            # 推导链：前提 = 第一个记忆的实际内容，确保匹配
                            qtext = f'从{p_name}在{p_action}了{p_product}出发，能推导出什么？'
                        else:
                            qtext = f'{p_name}的{p_action}链后续事件依次是什么？'
                        
                        # 答案：整条链的摘要
                        structured_answer = {
                            "chain_type": dim_name,
                            "members": [
                                {
                                    "person": cm["person"]["name"],
                                    "location": cm["location"]["city"],
                                    "action": cm["event"]["action"],
                                    "product": cm["event"]["product"],
                                    "time": cm["time"]["absolute"]
                                }
                                for cm in chain_mems
                            ]
                        }
                        answer_text = f'链式{dim_name}：{chain_text}'
                        
                        # expected_memory_ids = 链中所有成员
                        expected_mem_ids = [cm["memory_id"] for cm in chain_mems]
                        
                        queries.append({
                            "query_id": f"Q{len(queries)+1:04d}",
                            "query_text": qtext,
                            "query_type": f"{dim_name}链",
                            "test_dimension": dim_name,
                            "expected_memory_ids": expected_mem_ids,
                            "expected_answer": structured_answer,
                            "expected_answer_text": answer_text,
                            "acceptable_answers": [chain_text],
                            "expected_time": chain_mems[0]["time"]["absolute"],
                            "difficulty": m["difficulty"],
                            "search_depth": "深层"
                        })
            else:
                qtype = "组合检索"
                qtext = f'{m["person"]["name"]}在{m["location"]["city"]}的{m["event"]["action"]}记录'
                
                # 答案：所有版本作为可接受答案
                acceptable_answers = [v["content"] for v in m.get("versions", [])]
                
                # 结构化答案
                structured_answer = _format_answer_structured(m)
                answer_text = _format_answer_text(m)
                
                queries.append({
                    "query_id": f"Q{len(queries)+1:04d}",
                    "query_text": qtext,
                    "query_type": qtype,
                    "test_dimension": dim_name,
                    "expected_memory_ids": [m["memory_id"]],
                    "expected_answer": structured_answer,
                    "expected_answer_text": answer_text,
                    "acceptable_answers": acceptable_answers,
                    "expected_time": m["time"]["absolute"],
                    "difficulty": m["difficulty"],
                    "search_depth": random.choice(["浅层","中层","深层"])
                })
    
    # 负样本：20% — 确定性生成，避免重复
    n_positive = len(queries)
    n_negative = max(1, int(n_positive * 0.25))
    
    # 收集实体用于微妙错误负样本
    all_persons = list(set(m["person"]["name"] for m in memories if m["person"]["name"]))
    all_cities = list(set(m["location"]["city"] for m in memories if m["location"]["city"]))
    all_products = list(set(m["event"]["product"] for m in memories if m["event"]["product"]))
    
    # 确定性负样本模板池，每个组合唯一
    fake_persons = ['赵钱孙李', '周吴郑王', '冯陈褚卫', '蒋沈韩杨', '朱秦尤许', '何吕施张', '孔曹严华', '金魏陶姜']
    fake_cities = ['火星', '月球', '木星', '土星', '冥王星', '水星', '金星', '海王星']
    fake_events = ['比特币购买', '时光旅行', '量子跃迁', '黑洞探索', '星际战争', '外星殖民', '维度穿越', '时空折叠']
    fake_actions = ['打篮球', '游泳', '跳舞', '画画', '唱歌', '下棋', '钓鱼', '滑雪']
    
    # 构建所有可能的负样本组合（笛卡尔积的子集）
    neg_candidates = []
    
    # 类型1: 人物不存在
    for fp in fake_persons:
        neg_candidates.append(("人物不存在", f"{fp}最近做了什么"))
    
    # 类型2: 地点不存在
    for fc in fake_cities:
        neg_candidates.append(("地点不存在", f"在{fc}发生了什么"))
    
    # 类型3: 事件不存在
    for fe in fake_events:
        neg_candidates.append(("事件不存在", f"关于{fe}的事件有哪些"))
    
    # 类型4: 微妙错误（真实人物 + 真实地点 + 假动作）
    if all_persons and all_cities:
        for pi, person in enumerate(all_persons):
            for ci, city in enumerate(all_cities):
                for ai, action in enumerate(fake_actions):
                    # 用索引组合确保唯一，但限制总量
                    idx = (pi * len(all_cities) + ci) * len(fake_actions) + ai
                    if idx < 200:  # 上限200个微妙错误
                        neg_candidates.append(("微妙错误", f"{person}在{city}{action}"))
    
    # 类型5: 组合矛盾（真实人物 + 假地点 + 真实产品）
    if all_persons and all_products:
        for pi, person in enumerate(all_persons):
            for fi, fc in enumerate(fake_cities):
                for pri, prod in enumerate(all_products):
                    idx = (pi * len(fake_cities) + fi) * len(all_products) + pri
                    if idx < 100:  # 上限100个组合矛盾
                        neg_candidates.append(("组合矛盾", f"{person}在{fc}购买了{prod}"))
    
    # 如果候选不够，补充通用负样本
    while len(neg_candidates) < n_negative:
        idx = len(neg_candidates)
        neg_candidates.append(("通用", f"关于未知事件{idx}的记录"))
    
    # 随机打乱后取前n_negative个，保证多样性
    random.shuffle(neg_candidates)
    selected_negs = neg_candidates[:n_negative]
    
    for i, (neg_type, query_text) in enumerate(selected_negs):
        queries.append({
            "query_id": f"NEG{i+1:04d}",
            "query_text": query_text,
            "query_type": "负样本",
            "test_dimension": "负样本",
            "expected_memory_ids": [],
            "expected_answer": "",
            "expected_time": None,
            "difficulty": "困难",
            "search_depth": "浅层",
            "is_negative": True
        })
    
    return queries

def generate_queries_llm(memories: list, count: int = 100, llm=None) -> list:
    """LLM增强生成查询（更自然多样，需要API key）。"""
    if llm is None:
        return generate_queries_programmatic(memories, count)
    queries = []
    selected = random.sample(memories, min(count, len(memories)))

    for i, m in enumerate(selected):
        prompt = _prompt_from_template(
            "query_generate",
            person=m["person"]["name"],
            location=f"{m['location']['city']} {m['location']['place']}",
            event=f"{m['event']['action']} {m['event']['product']}",
            time=m["time"]["relative"],
        )
        result = llm.generate_json(prompt, max_tokens=1200, temperature=0.3)
        qs = result.get("queries", [])
        if not qs:
            # LLM失败，回退程序化
            qtype = random.choice(list(QUERY_TEMPLATES.keys()))
            templates = QUERY_TEMPLATES[qtype](m)
            test_dim = "精确检索" if qtype in ["人物检索","地点检索","事件检索"] else "组合检索"
            queries.append({
                "query_id": f"Q{i+1:04d}",
                "query_text": random.choice(templates),
                "query_type": qtype,
                "test_dimension": test_dim,
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": _format_answer_structured(m),
                "expected_answer_text": _format_answer_text(m),
                "acceptable_answers": [v["content"] for v in m.get("versions", [])],
                "expected_time": m["time"]["absolute"],
                "difficulty": m["difficulty"],
                "search_depth": random.choice(["浅层","中层","深层"])
            })
            continue

        for q in qs:
            # 根据查询类型判断评测维度
            qtype = q.get("query_type", "组合检索")
            test_dim = "组合检索"
            if qtype in ["人物检索", "地点检索", "事件检索"]:
                test_dim = "精确检索"
            elif qtype in ["时序链", "因果链", "对比链", "包含链", "推导链"]:
                test_dim = qtype.replace("链", "推理")
            elif qtype == "聚类检索":
                test_dim = "聚类检索"
            elif qtype == "跨版本":
                test_dim = "跨版本"
            
            queries.append({
                "query_id": f"Q{i+1:04d}",
                "query_text": q.get("query_text", ""),
                "query_type": qtype,
                "test_dimension": test_dim,
                "expected_memory_ids": [m["memory_id"]],
                "expected_answer": _format_answer_structured(m),
                "expected_answer_text": _format_answer_text(m),
                "acceptable_answers": [v["content"] for v in m.get("versions", [])],
                "expected_time": m["time"]["absolute"],
                "difficulty": q.get("difficulty", "中等"),
                "search_depth": random.choice(["浅层","中层","深层"])
            })

    return queries


# ====== 记忆生成器 ======
class MemoryGenerator:
    def __init__(self, use_llm: bool = False, llm=None, domain: str = "daily", time_distribution: str = "recent"):
        self.memory_id = 0
        self.use_llm = use_llm
        self.llm = llm
        self.domain = domain
        self.time_distribution = time_distribution
        self.domain_data = DOMAINS.get(domain, DOMAINS["daily"])

    def _id(self) -> str:
        self.memory_id += 1
        return f"MEM{self.memory_id:06d}"

    def _weight(self, difficulty: str) -> float:
        return {"简单": 0.5, "中等": 1.0, "困难": 1.5}.get(difficulty, 1.0)

    def _base(self, time_period: str) -> dict:
        """生成基础记忆数据，支持领域和时间分布配置。"""
        # 时间生成策略
        if self.time_distribution == "historical":
            # 历史时间分布：使用真实年份（如1900-2020）
            year = random.randint(1900, 2020)
            month = random.randint(1, 12)
            day = random.randint(1, 28)
            hour = random.randint(0, 23)
            minute = random.randint(0, 59)
            base_time = datetime(year, month, day, hour, minute)
            days_ago = (datetime.now() - base_time).days
        elif self.time_distribution == "uniform":
            # 均匀分布：在1-730天内均匀分布
            days_ago = random.randint(1, 730)
            base_time = datetime.now() - timedelta(days=days_ago)
        else:
            # 默认 recent：近期集中
            ranges = {"24h":(1,1),"7d":(1,7),"30d":(7,30),"90d":(30,90),"1y":(90,365),"fuzzy":(365,730)}
            lo, hi = ranges.get(time_period, (1,30))
            days_ago = random.randint(lo, hi)
            base_time = datetime.now() - timedelta(days=days_ago)
        
        # 从领域数据池中采样
        names = self.domain_data.get("people", NAMES)
        cities = self.domain_data.get("cities", CITIES)
        events = self.domain_data.get("events", list(EVENT_TYPES.keys()))
        products = self.domain_data.get("products", PRODUCTS)
        
        p1, p2 = random.sample(names if len(names) >= 2 else NAMES, 2)
        i1, i2 = random.sample(IDENTITIES, 2)
        etype = random.choice(events) if events else random.choice(list(EVENT_TYPES.keys()))
        actions = EVENT_TYPES.get(etype, ["进行" + etype])
        
        return {
            "base_time": base_time, "days_ago": days_ago,
            "city": random.choice(cities) if cities else random.choice(CITIES),
            "place": random.choice(PLACES),
            "landmark": random.choice(LANDMARKS),
            "person1": p1, "person2": p2, "identity1": i1, "identity2": i2,
            "relation": random.choice(RELATIONS),
            "event_type": etype, "action": random.choice(actions),
            "product": random.choice(products) if products else random.choice(PRODUCTS),
            "quantity": random.randint(1, 1000) * (10 if random.random() > 0.5 else 1),
            "price": random.randint(10, 10000)
        }

    def _make_versions(self, base: dict) -> list:
        if self.use_llm and self.llm:
            return make_versions_llm(base, self.llm)
        return make_versions_programmatic(base)

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
            "versions": self._make_versions(base), "tags": [],
            "cluster_id": None, "reasoning_chain": None, "chain_position": None,
            "decay": {"level": None, "access_count": 0}, **extra
        }

    def gen_storage(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["24h","7d","30d","90d","1y","fuzzy"]))
            result.append(self._build("存储正确性测试集", diff, base,
                                      tags=["存储测试", diff, str(base["days_ago"])+"d"]))
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

    # ====== 聚类配置 ======
    # 生成4-6个不同主题的聚类，每聚类3-8条记忆，确保有相关性
    # 主题维度：人物、地点、产品、时间段、事件类型
    CLUSTER_THEMES = [
        ("person", "张伟"), ("person", "王芳"), ("person", "李明"),
        ("location", "北京"), ("location", "上海"),
        ("product", "茅台"), ("product", "特斯拉"),
        ("event_type", "会议"), ("event_type", "交易"),
    ]

    def _build_clustered(self, theme_type: str, theme_value: str, count: int, cluster_id: str) -> list:
        """生成围绕同一主题的多条记忆，形成聚类。"""
        result = []
        for i in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["7d","30d","90d","1y"]))
            # 将主题维度注入 base
            if theme_type == "person":
                base["person1"] = theme_value
                # 其他人物随机变化，确保有区分度
                base["person2"] = random.choice([n for n in NAMES if n != theme_value])
            elif theme_type == "location":
                base["city"] = theme_value
                base["place"] = random.choice(PLACES)
            elif theme_type == "product":
                base["product"] = theme_value
                base["event_type"] = random.choice(["交易","日常"])
                base["action"] = random.choice(EVENT_TYPES[base["event_type"]])
            elif theme_type == "event_type":
                base["event_type"] = theme_value
                base["action"] = random.choice(EVENT_TYPES[theme_value])
            result.append(self._build("记忆整理测试集", diff, base,
                                      cluster_id=cluster_id,
                                      tags=["整理测试", diff, theme_type, theme_value]))
        return result

    def gen_organization(self, count: int) -> list:
        """生成多主题聚类数据。确保4-6个不同cluster，每cluster 3-8条记忆。"""
        # 选择4-6个不重复的主题
        n_clusters = min(random.randint(4, 6), len(self.CLUSTER_THEMES))
        selected_themes = random.sample(self.CLUSTER_THEMES, n_clusters)
        # 分配记忆数量：每cluster 3-8条，总和尽量接近count
        per_cluster = []
        remaining = count
        for i in range(n_clusters):
            if i == n_clusters - 1:
                per_cluster.append(max(3, min(8, remaining)))
            else:
                c = min(8, max(3, remaining // (n_clusters - i)))
                per_cluster.append(c)
                remaining -= c
        # 生成各cluster
        result = []
        for i, (theme_type, theme_value) in enumerate(selected_themes):
            cid = f"CLUSTER{i+1:04d}"
            result.extend(self._build_clustered(theme_type, theme_value, per_cluster[i], cid))
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
        """生成逻辑推理测试数据 — 包含5种逻辑关系的链式记忆。
        
        时间链作为逻辑关系的一种：
        - 有绝对时间时：按绝对时间排序建立时序链
        - 无绝对时间但有相对时间：按相对时间偏移排序
        - 两者都有：相对时间校准绝对时间
        """
        result = []
        logic_types = ["因果", "时序", "对比", "包含", "推导"]
        
        # 每种类型生成 count // 5 条链，确保总量充足
        chains_per_type = max(3, count // 5)
        
        for logic_type in logic_types:
            for chain_idx in range(chains_per_type):
                chain_id = f"CHAIN_{logic_type}_{self.memory_id:04d}"
                n_hops = random.randint(3, 6)
                
                base = self._base(random.choice(["7d", "30d", "90d", "1y"]))
                person = base["person1"]
                city = base["city"]
                
                chain_mems = []
                for hop in range(n_hops):
                    diff = random.choices(["简单", "中等", "困难"], weights=[0.3, 0.4, 0.3])[0]
                    
                    if logic_type == "因果":
                        if hop == 0:
                            base["action"] = random.choice(["投资", "购买", "决策"])
                        elif hop == 1:
                            base["action"] = random.choice(["导致", "引发", "造成"])
                            base["product"] = random.choice(PRODUCTS)
                        elif hop == 2:
                            base["action"] = random.choice(["产生", "带来", "造成"])
                            base["event_type"] = random.choice(["交易", "冲突", "转折"])
                            base["action"] = random.choice(EVENT_TYPES[base["event_type"]])
                        else:
                            base["action"] = random.choice(["最终", "结果", "导致"])
                            
                    elif logic_type == "时序":
                        # 时序链：利用绝对时间字段排序
                        # 时间向前推进（更近），但时间戳本身已经是绝对时间
                        # 时序链的核心特征：事件按时间先后发生，time.absolute 递增
                        base["days_ago"] = max(0, base.get("days_ago", 30) - random.randint(3, 14))
                        base["base_time"] = datetime.now() - timedelta(days=base["days_ago"])
                        # 更新 time 字段为绝对时间
                        base["time"] = {
                            "absolute": base["base_time"].strftime("%Y-%m-%d %H:%M:%S"),
                            "relative": time_desc(base["days_ago"]),
                            "fuzzy": fuzzy_time(base["days_ago"]),
                            "era": ""
                        }
                        if hop == 0:
                            base["action"] = random.choice(["开始", "启动", "发起"])
                        elif hop == n_hops - 1:
                            base["action"] = random.choice(["完成", "结束", "收尾"])
                        else:
                            base["action"] = random.choice(["随后", "接着", "然后", "之后"])
                            
                    elif logic_type == "对比":
                        if hop % 2 == 0:
                            base["person1"] = person
                            base["action"] = random.choice(["购买", "投资", "支持", "收购", "赞同", "批准"])
                            base["event_type"] = random.choice(["交易", "情感"])
                        else:
                            alt_names = [n for n in NAMES if n != person]
                            base["person1"] = random.choice(alt_names)
                            base["action"] = random.choice(["出售", "撤资", "反对", "否决", "拒绝", "退出"])
                            base["event_type"] = random.choice(["交易", "冲突"])
                        
                    elif logic_type == "包含":
                        if hop == 0:
                            base["action"] = random.choice(["规划", "布局", "涵盖"])
                            base["product"] = random.choice(["项目", "计划", "方案"])
                        elif hop == 1:
                            base["action"] = random.choice(["包含", "涉及", "覆盖"])
                            base["product"] = random.choice(PRODUCTS)
                        elif hop == 2:
                            base["action"] = random.choice(["具体", "细化", "落实"])
                        else:
                            base["action"] = random.choice(["执行", "实施", "完成"])
                            
                    elif logic_type == "推导":
                        if hop == 0:
                            base["action"] = random.choice(["观察", "发现", "注意到"])
                            base["event_type"] = "发现"
                        elif hop == 1:
                            base["action"] = random.choice(["分析", "研究", "推测"])
                            base["event_type"] = "分析"
                        elif hop == 2:
                            base["action"] = random.choice(["推断", "判断", "预测"])
                            base["event_type"] = "推导"
                        else:
                            base["action"] = random.choice(["结论", "证明", "得出"])
                            base["event_type"] = "决策"
                    
                    m = self._build("逻辑推理测试集", diff, base,
                                   logic={"type": logic_type},
                                   reasoning_chain=chain_id,
                                   chain_position=hop + 1,
                                   tags=["推理测试", diff, logic_type])
                    
                    m["chain_hop"] = hop + 1
                    m["chain_total"] = n_hops
                    m["chain_relation"] = logic_type
                    
                    chain_mems.append(m)
                    
                    if hop < n_hops - 1:
                        next_base = self._base(random.choice(["7d", "30d", "90d", "1y"]))
                        if logic_type != "对比":
                            next_base["person1"] = person
                        next_base["city"] = city
                        if logic_type in ["因果", "包含"] and random.random() > 0.5:
                            next_base["product"] = base["product"]
                        if logic_type == "推导":
                            next_base["event_type"] = base["event_type"]
                        base = next_base
                
                # 时序链：按时间重新排序（确保时间递增）
                if logic_type == "时序":
                    chain_mems.sort(key=lambda x: x["time"]["absolute"])
                    for i, m in enumerate(chain_mems):
                        m["chain_position"] = i + 1
                        m["chain_hop"] = i + 1
                
                # 设置链连接（prev/next）
                for i, m in enumerate(chain_mems):
                    m["chain_prev"] = chain_mems[i-1]["memory_id"] if i > 0 else ""
                    m["chain_next"] = chain_mems[i+1]["memory_id"] if i < len(chain_mems) - 1 else ""
                    result.append(m)
        
        return result

    def _build_temporal_chains(self, memories: list) -> list:
        """后处理：对同一人物的记忆按时间排序建立时序链。
        
        时间链作为逻辑关系的一种：
        - 有绝对时间：按时间戳排序
        - 无绝对时间：跳过（保持原顺序）
        """
        # 按人物分组
        person_groups = defaultdict(list)
        for m in memories:
            pn = m.get("person", {}).get("name", "")
            if pn and pn != "未知":
                person_groups[pn].append(m)
        
        chain_counter = 1
        for pn, mems in person_groups.items():
            # 只处理没有已有非时序链关系的记忆（保护 gen_reasoning 生成的因果/对比/推导/包含链）
            eligible = [m for m in mems if not m.get("chain_relation") or m.get("chain_relation") == "时序"]
            # 只处理有绝对时间的记忆
            with_time = [m for m in eligible if m.get("time", {}).get("absolute")]
            if len(with_time) < 3:
                continue
            
            # 按时间排序
            with_time.sort(key=lambda x: x["time"]["absolute"])
            
            # 建立时序链（最多6条）
            chain_id = f"CHAIN_temporal_{chain_counter:04d}"
            for i, m in enumerate(with_time[:6]):
                m["reasoning_chain"] = chain_id
                m["chain_position"] = i + 1
                m["chain_hop"] = i + 1
                m["chain_total"] = min(len(with_time), 6)
                m["chain_relation"] = "时序"
            
            # 设置链连接
            for i, m in enumerate(with_time[:6]):
                m["chain_prev"] = with_time[i-1]["memory_id"] if i > 0 else ""
                m["chain_next"] = with_time[i+1]["memory_id"] if i < len(with_time[:6]) - 1 else ""
            
            chain_counter += 1
        
        return memories

    def gen_deep(self, count: int) -> list:
        result = []
        for _ in range(count):
            diff = random.choices(["简单","中等","困难"], weights=[0.3,0.4,0.3])[0]
            base = self._base(random.choice(["1y","fuzzy"]))
            result.append(self._build("长期记忆深度检索测试集", diff, base,
                                      depth={"layers": random.randint(3,7), "associations": random.randint(2,5),
                                             "semantic_distance": random.choice(["近", "中", "远"])},
                                      tags=["深度检索", diff]))
        return result


# ====== 主入口 ======
DOMAINS = {
    "daily": {
        "people": [
            "张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十",
            "钱十一", "冯十二", "陈十三", "褚十四", "卫十五", "蒋十六", "沈十七", "韩十八",
            "杨十九", "朱二十", "秦二十一", "尤二十二", "许二十三", "何二十四", "吕二十五", "施二十六",
            "张二十七", "孔二十八", "曹二十九", "严三十", "华三十一", "金三十二", "魏三十三", "陶三十四",
        ],
        "cities": [
            "北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉",
            "西安", "重庆", "天津", "苏州", "长沙", "郑州", "青岛", "大连",
            "宁波", "厦门", "济南", "哈尔滨", "沈阳", "长春", "石家庄", "太原",
            "合肥", "南昌", "昆明", "贵阳", "南宁", "兰州", "海口", "乌鲁木齐",
        ],
        "events": [
            "参加会议", "购买商品", "签订合同", "提交报告", "出行旅行",
            "参加面试", "完成项目", "庆祝生日", "拜访客户", "处理投诉",
            "参加活动", "学习课程", "体检就医", "健身运动", "聚餐聚会",
        ],
        "products": [
            "手机", "电脑", "汽车", "房屋", "股票", "基金", "保险", "书籍",
            "服装", "食品", "药品", "电器", "家具", "玩具", "乐器", "珠宝",
            "化妆品", "运动器材", "旅游服务", "教育课程", "医疗服务", "法律服务",
        ],
    },
    "history": {
        "people": [
            "秦始皇", "汉武帝", "唐太宗", "宋太祖", "明成祖", "康熙帝", "乾隆帝", "武则天",
            "曹操", "刘备", "孙权", "诸葛亮", "关羽", "张飞", "赵云", "吕布",
            "李白", "杜甫", "苏轼", "白居易", "王维", "李清照", "辛弃疾", "陆游",
            "岳飞", "文天祥", "于谦", "戚继光", "郑成功", "林则徐", "曾国藩", "李鸿章",
        ],
        "cities": [
            "长安", "洛阳", "金陵", "开封", "临安", "大都", "燕京", "咸阳",
            "邯郸", "临淄", "曲阜", "江陵", "成都", "太原", "大同", "襄阳",
            "扬州", "苏州", "杭州", "福州", "广州", "泉州", "大理", "拉萨",
            "平壤", "高句丽", "西域", "楼兰", "敦煌", "张掖", "武威", "酒泉",
        ],
        "events": [
            "统一天下", "改革变法", "发动战争", "签订条约", "建立王朝",
            "平定叛乱", "出使西域", "编纂典籍", "修建工程", "科举取士",
            "发明创造", "农业生产", "商业贸易", "文化交流", "宗教传播",
        ],
        "products": [
            "兵器", "书籍", "货币", "丝绸", "茶叶", "瓷器", "香料", "马匹",
            "粮食", "药材", "珠宝", "玉器", "青铜器", "铁器", "漆器", "纸张",
            "火药", "指南针", "印刷术", "运河", "长城", "宫殿", "陵墓", "石窟",
        ],
    },
    "scifi": {
        "people": [
            "宇航员", "科学家", "AI", "机器人", "外星生物", "时空旅行者", "基因改造人", "意识上传者",
            "星际指挥官", "舰队司令", "探险家", "考古学家", "物理学家", "生物学家", "数学家", "哲学家",
            "黑客", "赏金猎人", "走私者", "革命者", "外交官", "商人", "牧师", "艺术家",
        ],
        "cities": [
            "空间站", "火星基地", "月球城", "星际飞船", "未来城", "地下城", "轨道电梯", "戴森球",
            "异星殖民地", "虫洞枢纽", "量子网络", "虚拟现实", "平行宇宙", "高维空间", "黑洞边缘", "星云中心",
            "泰坦星", "欧罗巴", "开普勒", "比邻星", "仙女座", "银河系", "太阳系", "宇宙边缘",
        ],
        "events": [
            "时空穿越", "基因改造", "星际战争", "意识上传", "维度跳跃",
            "黑洞探索", "外星接触", "量子跃迁", "暗物质研究", "反物质引擎",
            "戴森球建设", "机械飞升", "基因飞升", "虚拟现实", "平行宇宙",
        ],
        "products": [
            "飞船", "机器人", "全息设备", "量子计算机", "基因编辑器", "意识芯片", "纳米机器人", "反物质引擎",
            "引力波通讯器", "暗物质探测器", "时空折叠器", "虫洞发生器", "戴森球组件", "基因药剂", "虚拟现实头盔",
            "星际传送门", "量子纠缠器", "黑洞炸弹", "维度切割器", "平行宇宙探测器", "宇宙飞船", "太空站", "星际武器",
        ],
    },
    "business": {
        "people": [
            "CEO", "CFO", "CTO", "COO", "投资人", "分析师", "审计师", "律师",
            "银行家", "交易员", "经纪人", "顾问", "经理", "总监", "副总裁", "总裁",
            "董事长", "合伙人", "创始人", "股东", "董事", "监事", "高管", "员工",
        ],
        "cities": [
            "交易所", "总部", "工厂", "仓库", "物流中心", "研发中心", "数据中心", "呼叫中心",
            "分公司", "办事处", "营业部", "门店", "旗舰店", "体验店", "快闪店", "直播间",
            "产业园区", "自贸区", "保税区", "开发区", "高新区", "经济区", "湾区", "都市圈",
        ],
        "events": [
            "并购", "IPO", "财报发布", "融资", "投资", "分红", "裁员", "扩张",
            "合作", "竞争", "诉讼", "仲裁", "破产", "重组", "转型", "创新",
            "上市", "退市", "增发", "回购", "拆分", "合并", "收购", " divestiture",
        ],
        "products": [
            "股票", "债券", "基金", "期货", "期权", "衍生品", "外汇", "黄金",
            "房地产", "保险", "信托", "资管", "私募", "风投", "天使投资", "众筹",
            "加密货币", "NFT", "智能合约", "区块链", "AI模型", "SaaS", "PaaS", "IaaS",
        ],
    },
}


def build_database(size: int = 100, use_llm: bool = False, llm=None, domain: str = "daily", time_distribution: str = "recent") -> dict:
    """
    Build a MemTest database.
    
    Args:
        size: Number of memories to generate
        use_llm: Whether to use LLM for enhanced generation
        llm: LLM interface object (required if use_llm=True)
        domain: Data domain ("daily"|"history"|"scifi"|"business")
        time_distribution: Time distribution mode ("recent"|"uniform"|"historical")
    """
    gen = MemoryGenerator(use_llm=use_llm, llm=llm, domain=domain, time_distribution=time_distribution)
    ratios = {"storage":0.17,"retrieval":0.17,"org":0.17,"forget":0.17,"reason":0.16,"deep":0.16}
    storage = gen.gen_storage(max(1, int(size * ratios["storage"])))
    retrieval = gen.gen_retrieval(max(1, int(size * ratios["retrieval"])))
    org = gen.gen_organization(max(1, int(size * ratios["org"])))
    forget = gen.gen_forgetting(max(1, int(size * ratios["forget"])))
    reason = gen.gen_reasoning(max(1, int(size * ratios["reason"])))
    deep = gen.gen_deep(max(1, int(size * ratios["deep"])))
    all_mems = storage + retrieval + org + forget + reason + deep
    
    # 后处理：为同一人物的记忆按时间排序建立时序链
    gen._build_temporal_chains(all_mems)
    
    random.shuffle(all_mems)
    cats = {}
    for m in all_mems: cats[m["category"]] = cats.get(m["category"], 0) + 1

    if use_llm and llm:
        queries = generate_queries_llm(all_mems, max(30, size // 2), llm)
    else:
        queries = generate_queries_programmatic(all_mems, max(30, size // 2))

    return {
        "database_info": {
            "name": "MemTest Database", "version": "1.0.0",
            "total_count": len(all_mems), "categories": cats,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "memories": all_mems, "queries": queries
    }


if __name__ == "__main__":
    full = "--full" in sys.argv
    use_llm = "--llm" in sys.argv
    size = 100
    domain = "daily"
    time_distribution = "recent"
    for a in sys.argv:
        if a.startswith("--size="): size = int(a.split("=")[1])
        if a.startswith("--domain="): domain = a.split("=")[1]
        if a.startswith("--time="): time_distribution = a.split("=")[1]
    if full: size = 10000

    llm = None
    if use_llm:
        try:
            from llm_interface import create_llm
            llm = create_llm("deepseek")
            print(f"[LLM模式] 使用 DeepSeek API")
        except Exception as e:
            print(f"[警告] LLM初始化失败: {e}，回退到程序化模式")
            use_llm = False

    # 重新生成数据
    db = build_database(100, domain="daily", time_distribution="recent")
    with open("sample_db.json", "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"Generated sample_db.json: {len(db['memories'])} memories, {len(db['queries'])} queries")
