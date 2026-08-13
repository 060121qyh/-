#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
河南三支一扶备考情报采集器（REQ-20260813-002 重构版 / TA-001）
=============================================================
针对用户反馈「推送都是小新闻（志愿者服务这类），考试不会考」重构：

1. 数据源扩充至 14 个真实可用源（2026-08-13 逐源实测），覆盖：
   中央（新华社/人民网/央视网/求是网）、法律（最高法/中国人大网/中国网信办）、
   三农（农业农村部）、经济（国家统计局/发改委）、科技（工信部/中国科学院）、
   河南（中原报业/河南省人事考试网 hnrsks.com 招考核心源）。
2. 模块分类：每条新闻自动打唯一主模块标签（时政/河南省情/法律/马哲/中特/
   三农/经济民生/科技产业）。
3. 重要度分级：🔴要闻 / 🟠重要 / 🟢参考（规则判断，输出 JSON 每条带 importance）。
4. 关键词体系重构：考试相关词 + 高价值新闻识别词，用于「评分排序 + 精华提炼」，
   不再是唯一过滤条件——先按重要度分级，再按关键词加权排序，低价值新闻直接过滤。
5. NOISE_PATTERNS 显式排除模式化小新闻（志愿者/主题党日/慰问/学校活动等）。
6. 每条输出：module / importance / essence（规则模板精华提炼）/ history（内置
   确认真实的历史映射表，命中才输出，禁止编造）。
7. 健壮性：单源失败优雅降级（sources 记录 ok/error）、请求重试、超时控制、
   旧闻过滤（pub_date 距今 >7 天剔除；无日期标旧闻风险）、编码处理、去重、
   爬虫礼仪（合理 UA / 超时 / 请求间隔）。

输出：
  - data/daily-intel/intel-YYYY-MM-DD.json   结构化情报（含新字段）
  - data/daily-intel/intel-YYYY-MM-DD.md     可读摘要（按重要度分组）

用法：
  python scripts/intel_collector.py                  # 抓取当天
  python scripts/intel_collector.py --date 2026-08-13
  python scripts/intel_collector.py --min-score 2    # 相关性门槛（🟢参考级生效）
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "daily-intel"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TIMEOUT = 12
MAX_AGE_DAYS = 7          # 旧闻阈值：pub_date 距今超过 7 天剔除
REQUEST_INTERVAL = 0.4    # 源间请求间隔（爬虫礼仪）

# 考试日期（河南三支一扶重考）
EXAM_DATE = datetime(2026, 8, 22, tzinfo=CST)

# =====================================================================
# 一、关键词体系（评分排序 + 精华提炼；不是唯一过滤条件）
# =====================================================================
# 招考相关词（用户强相关，权重最高）
KEYWORDS = {
    # —— 招考核心 ——
    "三支一扶": 6, "支农": 5, "支教": 5, "支医": 5, "帮扶乡村振兴": 5,
    "重考": 5, "补考": 5, "准考证": 5, "资格复审": 4, "笔试": 4, "面试": 4,
    "招募": 4, "公基": 4, "公共基础知识": 4, "报名": 3, "录用": 3,
    "河南": 3, "公告": 2,
    # —— 公基考纲词（高价值） ——
    "乡村振兴": 4, "中国式现代化": 4, "新质生产力": 4, "粮食安全": 4,
    "共同富裕": 4, "依法治国": 4, "全过程人民民主": 4, "基层治理": 4,
    "三农": 4, "中央一号文件": 4, "二十届三中全会": 4, "二十届四中全会": 4,
    "政府工作报告": 4, "中央经济工作会议": 4, "高质量发展": 3,
    "中国式现代化": 4, "强国建设": 3, "民族复兴": 3,
    # —— 高价值新闻识别词 ——
    "习近平": 4, "总书记": 4, "全会": 3, "中央政治局": 3, "两会": 3,
    "立法": 3, "法律": 2, "条例": 2, "草案": 2, "修订": 2, "施行": 2, "通过": 1,
    "印发": 3, "出台": 3, "部署": 2, "规划": 2, "意见": 2, "通知": 2, "方案": 2,
    "重要讲话": 3, "重要指示": 3, "经济数据": 3, "统计": 2, "同比": 2,
    "人工智能": 3, "科技": 2, "创新": 2, "航天": 2, "数字经济": 2,
    "农业农村": 3, "粮食": 2, "耕地": 2, "高标准农田": 3,
}

# =====================================================================
# 二、噪声过滤（模式化小新闻，直接剔除，不进入输出）
# =====================================================================
# 总书记相关活动不过噪声过滤（防止误杀「习近平就XX致慰问电」等真实新闻）
NOISE_PATTERNS = (
    "主题党日", "学雷锋", "志愿服务", "志愿者", "新时代文明实践",
    "文明创建", "文明单位", "文明城市", "精神文明",
    "清廉", "廉洁", "廉政", "党支部", "党建",
    "文艺演出", "文体活动", "文艺汇演", "书画展", "运动会",
    "慰问演出", "走访慰问", "看望慰问", "慰问活动",
    "幼儿园", "小学", "中学", "校园", "少先队", "开学季",
    "揭牌仪式", "授牌仪式", "签约仪式", "启动仪式",
    "纪念活动", "庆祝活动", "迎新春", "三八", "五四青年节", "教师节",
    # 中原网等地方站低价值内容（2026-08-13 实测补充）
    "缩线停运", "招标公告", "废纸出售", "废版出售", "印刷厂",
    "拟推荐对象的公示", "申报工作的通知",  # 组织评选类（英才计划等）由年份规则兜底
)
NOISE_BLACKLIST_URL = ("mail.", "english.", "/en/", "login", "信访",
                       "rss", "sitemap", "gov.cn/guoqing")
# 无意义导航链接（政务站首页常见）
NAV_TITLES = ("English", "邮箱", "登录", "门户网站", "设为首页", "加入收藏",
              "网站地图", "联系我们", "政务服务", "互动交流", "信息公开",
              "网上信访", "部长信箱", "中国政府网", "国务院部门网站", "地方频道",
              # 农业农村部等首页友情链接（实测补充）
              "中国农业农村信息网", "国家粮食和物资储备局", "世界粮食计划署",
              "中国农业信息网", "人事考试中心（", "信息中心",
              # 国家统计局/中科院首页友情链接与翻页导航（2026-08-13 实测补充）
              "中国统计学会", "中国统计教育学会", "联合国统计司",
              "可持续发展科技研究局", "更多通知公告",
              # 网站页脚信息（2026-08-13 实测：求是网页脚链接混入）
              "京公网安备", "互联网新闻信息服务许可证", "网站标识码",
              "备案号", "版权所有")

# 一般职业资格考试考务通知（非三支一扶/公务员/事业单位等核心招考）：剔除
GENERIC_EXAM_KEEP = ("三支一扶", "公务员", "事业单位", "遴选", "选调", "教师", "特岗")
GENERIC_EXAM_PATTERNS = ("执业药师", "消防工程师", "新闻记者", "造价工程师",
                         "建造师", "注册会计师", "经济师", "翻译专业",
                         "社会工作师", "监理工程师", "安全工程师", "审计师")

# =====================================================================
# 三、模块分类规则（按优先级匹配，保证每条新闻有且只有一个主模块）
# =====================================================================
MODULE_ORDER = ["河南省情", "法律", "三农", "经济民生", "科技产业", "马哲", "中特", "时政"]
MODULE_RULES = {
    "河南省情": ("河南", "豫"),
    "法律": ("立法", "法律", "法规", "条例", "草案", "施行", "修订", "法条",
             "最高法", "人民法院", "人民检察院", "检察", "宪法", "民法典",
             "法治", "依法", "司法", "庭审", "审议通过", "表决通过"),
    "三农": ("乡村振兴", "农业农村", "农业", "农村", "农民", "粮食", "耕地",
             "种业", "丰收", "农资", "高标准农田", "一号文件", "乡村", "宅基地"),
    "经济民生": ("GDP", "经济", "就业", "民生", "物价", "CPI", "消费", "投资",
                 "财政", "税收", "养老金", "社保", "医保", "工资", "外贸",
                 "进出口", "物价", "通胀", "降息", "国债"),
    "科技产业": ("科技", "创新", "人工智能", "AI", "新质生产力", "芯片", "量子",
                 "航天", "卫星", "算力", "数字经济", "新能源", "机器人",
                 "集成电路", "大模型", "6G", "低空经济"),
    "马哲": ("马克思", "哲学", "唯物", "辩证", "矛盾", "实践观"),
    "中特": ("中国特色社会主义", "中国式现代化", "社会主义", "人类命运共同体"),
    "时政": (),  # 兜底：未命中上述模块的政务/新闻站内容默认归时政
}

# =====================================================================
# 四、重要度分级（🔴要闻 / 🟠重要 / 🟢参考）
# =====================================================================
RED_MAJOR = ("二十届", "中央经济工作会议", "中央一号文件", "政府工作报告",
             "全国两会", "两会", "中央政治局", "二十大", "全会", "重要指示",
             "重要讲话", "中共中央", "国务院常务会议", "中央农村工作会议")
RED_LAW = ("立法法", "宪法修正", "民法典", "刑法修正", "国家安全法",
           "教育法", "立法", "法草案", "法修正案")
ORANGE_POLICY = ("印发", "出台", "发布", "部署", "规划", "意见", "通知",
                 "方案", "实施", "条例", "修订", "草案", "征求意见")
ORANGE_ECON = ("同比", "环比", "数据发布", "统计", "增速", "增长", "指数", "经济运行")
ORANGE_HENAN = ("省委", "省政府", "全省", "河南省委", "河南政府")

# 部委名（命中即判定为部委政策/动态 → 🟠重要）
MINISTRY_NAMES = ("国务院", "国家发改委", "发改委", "统计局", "农业农村部",
                  "工信部", "工业和信息化部", "科技部", "商务部", "财政部",
                  "人社部", "人力资源社会保障部", "网信办", "文旅部", "教育部",
                  "卫健委", "市场监管总局", "自然资源部", "交通运输部",
                  "生态环境部", "应急管理部", "水利部", "住建部", "民政部",
                  "人民银行", "金融监管总局")

# =====================================================================
# 五、历史关联映射表（只放确定真实的事件；未命中不输出，绝不编造）
# =====================================================================
HISTORY_LINKS = {
    "中央一号文件": "延续中央一号文件部署（2025年中央一号文件于2025年2月发布，聚焦乡村全面振兴，是公基三农模块高频考点）",
    "二十届三中全会": "2024年7月二十届三中全会通过《中共中央关于进一步全面深化改革、推进中国式现代化的决定》，是当前公基时政最高频考点",
    "二十届四中全会": "2025年10月二十届四中全会审议通过《中共中央关于制定国民经济和社会发展第十五个五年规划的建议》，'十五五'规划是近期时政重点",
    "新质生产力": "2023年9月习近平在黑龙江考察时首次提出，2024年写入政府工作报告，是科技产业模块核心概念",
    "粮食安全": "延续'藏粮于地、藏粮于技'战略部署，国家粮食安全是三农模块常考点",
    "乡村振兴": "2017年党的十九大报告首次提出实施乡村振兴战略，2025年中央一号文件聚焦乡村全面振兴",
    "中国式现代化": "2022年10月党的二十大系统阐述中国式现代化的中国特色与本质要求，是公基中特模块核心考点",
    "共同富裕": "2021年8月中央财经委员会第十次会议研究扎实促进共同富裕问题",
    "全过程人民民主": "2019年11月习近平在上海考察时首次提出；党的二十大报告原文指出'全过程人民民主是社会主义民主政治的本质属性'，是公基中特/时政高频考点",
    "依法治国": "2014年10月党的十八届四中全会专题研究全面推进依法治国，通过《中共中央关于全面推进依法治国若干重大问题的决定》",
    "民法典": "2020年5月十三届全国人大三次会议表决通过《中华人民共和国民法典》，2021年1月1日起施行",
    "政府工作报告": "每年3月全国两会期间国务院总理作政府工作报告，总结上年、部署当年经济社会发展重点",
    "中央经济工作会议": "每年12月召开，部署来年经济工作，是经济民生模块年度最高频考点",
    "全国两会": "每年3月召开，审议政府工作报告、国民经济和社会发展计划等，是公基时政必考事件",
    "中央农村工作会议": "每年12月召开，部署来年'三农'工作，与中央一号文件共同构成三农模块年度考点主线",
    "二十届五中全会": "2025年10月二十届四中全会（上一届全会）审议通过《中共中央关于制定国民经济和社会发展第十五个五年规划的建议》；二十届五中全会是接续四中全会的新一次中央全会，'十五五'规划是近期时政主线",
}

# =====================================================================
# 六、数据源配置（2026-08-13 全部实测 200 且能解析出真实链接）
# =====================================================================
SOURCES = [
    {
        "name": "河南省人事考试网-首页",
        "kind": "html",
        "url": "http://www.hnrsks.com/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,100})</a>',
        "cat": "河南",
        "note": "河南三支一扶招考核心源（zngg 招募公告栏目在首页）",
    },
    {
        "name": "新华网-时政RSS",
        "kind": "rss",
        "url": "http://www.news.cn/politics/news_politics.xml",
        "cat": "中央",
        "note": "新华社时政频道 RSS（内容可能滞后，靠日期过滤）",
    },
    {
        "name": "人民网-时政RSS",
        "kind": "rss",
        "url": "http://www.people.com.cn/rss/politics.xml",
        "cat": "中央",
        "note": "人民日报时政频道 RSS（正版地址 www.people.com.cn/rss/）",
    },
    {
        "name": "求是网",
        "kind": "html",
        "url": "https://www.qstheory.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "中央",
        "note": "求是杂志社官网，中央理论/时政深度文章",
    },
    {
        "name": "央视网-首页",
        "kind": "html",
        "url": "https://news.cctv.com/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "中央",
        "note": "央视新闻要闻（URL 带日期段可做旧闻过滤）",
    },
    {
        "name": "最高法",
        "kind": "html",
        "url": "https://www.court.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "法律",
        "note": "最高人民法院官网，司法解释/典型案例/法治动态",
    },
    {
        "name": "中国人大网-权威发布",
        "kind": "html",
        "url": "http://www.npc.gov.cn/npc/c2/kgfb/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "法律",
        "note": "全国人大官网权威发布栏目（法律通过/人事任免等）",
    },
    {
        "name": "中国网信办",
        "kind": "html",
        "url": "https://www.cac.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "法律",
        "note": "国家网信办，互联网法律/政策征求意见",
    },
    {
        "name": "农业农村部",
        "kind": "html",
        "url": "http://www.moa.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "三农",
        "note": "农业农村部官网，三农政策/粮食安全",
    },
    {
        "name": "国家统计局",
        "kind": "html",
        "url": "https://www.stats.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "经济",
        "note": "国家统计局官网，经济数据发布",
    },
    {
        "name": "发改委",
        "kind": "html",
        "url": "https://www.ndrc.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "经济",
        "note": "国家发改委，宏观经济政策/规划",
    },
    {
        "name": "工信部",
        "kind": "html",
        "url": "https://www.miit.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "科技",
        "note": "工信部官网，科技产业/工业经济",
    },
    {
        "name": "中国科学院",
        "kind": "html",
        "url": "https://www.cas.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,100})</a>',
        "cat": "科技",
        "note": "中科院官网，前沿科研进展（科技产业模块素材）",
    },
    {
        "name": "中原网-河南",
        "kind": "html",
        "url": "https://news.zynews.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,100})</a>',
        "cat": "河南",
        "note": "中原网（郑州报业集团），河南本地时政/民生动态",
    },
]


def _get(url: str, tries: int = 3, timeout: int = TIMEOUT):
    """带重试的 GET（非 200 或异常时退避重试，共 tries 次；
    2026-08-13 实测中原网偶发 SSLEOFError，重试 3 次可显著降低偶发失败率）"""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def clean_text(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<") \
         .replace("&gt;", ">").replace("&ldquo;", "“").replace("&rdquo;", "”") \
         .replace("&lsquo;", "‘").replace("&rsquo;", "’").replace("&#39;", "'")
    return re.sub(r"\s+", " ", t).strip()


def is_noise(title: str, url: str) -> bool:
    """噪声判定：模式化小新闻 / 无意义导航链接 / 一般考务通知"""
    t = title.strip()
    if len(t) < 6:
        return True
    if "'+" in t or "data.title" in t or "kapian" in t or "'+title" in t:
        return True  # JS 模板片段（求是网首页 '+data.title+' 等，2026-08-13 实测）
    if t.startswith("更多"):
        return True  # 栏目「更多…」翻页链接（2026-08-13 实测 cas.cn 首页出现）
    if any(k in t for k in NAV_TITLES):
        return True
    if re.match(r"^[\u4e00-\u9fa5]{2,7}人事考试网$", t):
        return True  # 各省人事考试网导航链接（hnrsks 首页友情链接）
    if url.count("http") > 1:
        return True  # 拼接错误的外部链接（如 cas.cn/http://... 导航残链）
    if any(k in url for k in NOISE_BLACKLIST_URL):
        return True
    # 一般职业资格考试考务通知（非核心招考）：剔除
    if "考务" in t and any(k in t for k in GENERIC_EXAM_PATTERNS) \
            and not any(k in t for k in GENERIC_EXAM_KEEP):
        return True
    # 机构传达学习/专题学习会（模式化宣传，非考试要闻；须在总书记豁免前判断）
    if any(k in t for k in ("专题学习", "传达学习习近平总书记",
                            "学习贯彻习近平总书记", "深入学习习近平总书记",
                            "贯彻落实习近平总书记")) and any(
            k in t for k in ("党委", "党组", "学校", "召开")):
        return True
    # 党建宣传噪声（REQ-20260813-002 修复轮 3 R3，KM-001 复审）：
    # 党建思想/专题党课/党课报告会/党建工作座谈会/党组(所院)传达学习非重要讲话语境
    # —— 中科院「党组传达学习全国党建工作座谈会精神」「学习贯彻习近平党建思想
    #    专题党课报告会」等党建宣传旧闻。判断逻辑：含 党课/党建思想/传达学习 且
    #    不含「总书记发表重要讲话/在XX会议上强调」→ 噪声；总书记真实要闻豁免
    if (any(k in t for k in ("党建思想", "专题党课", "党课报告会", "党课",
                             "党建工作座谈会", "党建工作"))
            or (any(k in t for k in ("传达学习", "学习贯彻", "深入学习",
                                     "贯彻落实", "专题学习"))
                and any(k in t for k in ("党组", "党委", "所党委", "院党委")))):
        # 总书记真实要闻语境豁免（保留🔴）：总书记发表重要讲话/重要指示/
        # 重要论述/主持，或「习近平/总书记(在…)?强调」——注意排除
        # 「XX调研 强调深入学习贯彻习近平党建思想」这类主语非总书记的
        # 党建宣传（R3 实测：工信部李乐成调研条）
        if not (any(k in t for k in ("总书记发表重要讲话", "发表重要讲话",
                                     "重要指示", "重要论述", "主持"))
                or re.search(r"(习近平|总书记)(?:在[^，。；]{0,24}?)?强调", t)):
            return True
    # 总书记相关活动不过噪声过滤（避免误杀真实要闻）
    if "习近平" in t or "总书记" in t:
        return False
    return any(k in t for k in NOISE_PATTERNS)


def title_year_stale(title: str, today: datetime) -> bool:
    """标题内年份早于当前年 → 旧闻（如『2024年度中原英才计划』）"""
    m = re.search(r"(20\d{2})\s*年", title)
    if m and int(m.group(1)) < today.year:
        return True
    return False


def extract_date_from_url(url: str) -> str:
    """从 URL 提取日期（YYYY-MM-DD 或 YYYY-MM），提取不到返回空串。
    支持 /YYYYMMDD/、/YYYY-MM-DD/、/YYYY/MM/DD/、/YYYYMM/（6位月份）、
    tYYYYMMDD 文件名日期（中科院/人大网/农业部源风格）等格式。
    提取优先级：8位日期 > 斜杠日期 > tYYYYMMDD > 6位月份 > 分隔月份。
    8 位/文件名日期要求校验为合法合理日期（2000-01-01 ~ 今天+1 天），
    6 位月份校验 01-12，避免误抓纯数字 ID。
    （REQ-20260813-002 修复轮 P1：补 8 位日期提取 + 合理范围校验；
     修复轮 3 R1：补 /YYYYMM/ 6位月份 + tYYYYMMDD 文件名日期）"""
    today = datetime.now(CST)
    min_d = datetime(2000, 1, 1, tzinfo=CST)
    max_d = today + timedelta(days=1)

    def _valid(y, m, d):
        try:
            dt = datetime(int(y), int(m), int(d), tzinfo=CST)
        except ValueError:
            return False
        return min_d <= dt <= max_d

    # 1) 8 位日期 /YYYYMMDD/（求是网/中科院等，2026-08-13 实测大量使用）
    m = re.search(r"/(20\d{2})(\d{2})(\d{2})/", url)
    if m and _valid(*m.groups()):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 2) /YYYY-MM-DD/ 或 /YYYY/MM/DD/
    m = re.search(r"/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", url)
    if m and _valid(*m.groups()):
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 3) 文件名 tYYYYMMDD（中科院/人大网/农业部 URL 风格，如 .../t20260612_xxx.html）
    #    要求 t 前缀 + 8 位数字 + 文件名边界（_ . / 或结束），校验合理日期
    m = re.search(r"t(20\d{2})(\d{2})(\d{2})(?:_|\.|/|$)", url)
    if m and _valid(*m.groups()):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 4) 6 位月份 /YYYYMM/（如 /202606/，校验月份 01-12）
    m = re.search(r"/(20\d{2})(\d{2})/", url)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 2000 <= y <= today.year + 1 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    # 5) /YYYY-MM/ 或 /YYYY/MM/（年份/月份范围校验）
    m = re.search(r"/(20\d{2})[-/](\d{1,2})", url)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 2000 <= y <= today.year + 1 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}"
    return ""


def get_pub_date(item: dict) -> str:
    """取条目日期：RSS pubDate 优先，其次 URL 日期段"""
    pub = item.get("pub_date") or ""
    if pub:
        return pub
    return extract_date_from_url(item.get("url", ""))


def is_stale(item: dict, today: datetime) -> tuple:
    """旧闻判定。返回 (是否剔除, 旧闻风险标记)
    - pub_date 有值且距今 > MAX_AGE_DAYS → 剔除
    - URL 年份段早于当前年（如 /2025/）→ 剔除
    - 无日期信息（或仅年份）→ 不武断剔除，但标旧闻风险（stale_risk）"""
    # URL 路径年份段早于当前年 → 直接剔除（如 /2025/）
    ym = re.search(r"/(20\d{2})/", item.get("url", ""))
    if ym and int(ym.group(1)) < today.year:
        return True, True
    pub = get_pub_date(item)
    if not pub:
        return False, True  # 无日期：不剔除，标风险
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", pub):
            pd = datetime.strptime(pub, "%Y-%m-%d").replace(tzinfo=CST)
            if (today - pd).days > MAX_AGE_DAYS:
                return True, False
            return False, False
        # 仅 YYYY-MM 或 YYYY：年份早于当前年即剔除
        if re.match(r"^\d{4}$", pub):
            if int(pub) < today.year:
                return True, True
            return False, True
        if re.match(r"^\d{4}-\d{2}$", pub):
            ym = datetime.strptime(pub, "%Y-%m").replace(tzinfo=CST)
            if (today - ym).days > MAX_AGE_DAYS:
                return True, True
            return False, True
    except ValueError:
        pass
    return False, True


# =====================================================================
# 六、专题/栏目/导航页识别（F2 中，修复轮4——KM-001 终审）
# =====================================================================
# 常驻栏目/专题/导航聚合页非实时新闻（KM-001 终审：10+ 条混入推送，含
# 「学习贯彻党的二十届四中全会精神」41 天旧专题、「聚焦党的二十届四中全会」
# 「深入学习贯彻习近平法治思想专题」「数据发布与解读」「开庭与庭审直播公告」
# 「中国网河南频道」及中科院奖项专题页等）。
# 规则：URL 命中栏目模式 → 直接剔除；标题以结构词开头（聚焦/学习贯彻等）
# 且无日期信号 → 进详情页时间核验：提取到时间且 ≤7 天 → 保留（新发评论文章，
# 如「聚焦二十届三中全会」类评论），>7 天或提取不到 → 剔除（按栏目页处理）。
COLUMN_URL_PATTERNS = (
    re.compile(r"chinacourt\.org/article/subjectdetail/"),   # 中国法院网专题聚合页
    re.compile(r"miit\.gov\.cn/ztzl/"),                      # 工信部专题专栏
    re.compile(r"cas\.cn/+/zt/"),                            # 中科院专题
    re.compile(r"cas\.cn/+/kxyj/kj/casjc/"),                 # 中科院杰出科技成就奖专题页
    re.compile(r"cas\.cn/+/kxyj/kj/cashz/"),                 # 中科院国际科技合作奖专题页
    re.compile(r"court\.gov\.cn/fabu/gengduo/"),             # 最高法「开庭与庭审直播公告」等列表页
    re.compile(r"stats\.gov\.cn/sj/?$"),                     # 统计局「数据发布与解读」栏目
    re.compile(r"^https?://[^/]+/?$"),                       # 频道根域名（中国网河南频道等）
)
COLUMN_TITLE_LEAD = re.compile(r"^(聚焦|学习贯彻|深入学习贯彻|直播公告|数据发布与解读|专题[:：])")


def is_column_url(url: str) -> bool:
    """URL 命中常驻栏目/专题/导航聚合页模式 → 非实时新闻，直接剔除"""
    return any(p.search(url) for p in COLUMN_URL_PATTERNS)


def is_column_title(title: str) -> bool:
    """标题以栏目/专题结构词开头（无详情页时间时按栏目页处理）"""
    return bool(COLUMN_TITLE_LEAD.match(title.strip()))


# =====================================================================
# 七、详情页发布时间提取层（F1 高，修复轮4——KM-001 终审打回主因）
# =====================================================================
# 背景：最高法 xiangqing 页/工信部 art 页/hnrsks 文章页等 URL 无日期段且无
# pub_date（约 114 条/日）完全绕过 7 天旧闻过滤——KM-001 终审抽样 46 条详情页
# 核验 32 条为 >7 天真实旧闻（最老 713 天；指导性案例 273-279 全批 166 天；
# 纪委五次全会 200 天；TOP2/TOP3 均为旧闻）。
# 修复：对 URL/pub_date 均无日期信号的条目，真实请求详情页提取发布时间
# （顺序尝试，与 KM 评审基准 km001_final_verify_003.py 同口径）：
#   ① <meta> date/publishdate/published_time 等标签
#   ② 正文头部「发布时间：YYYY-MM-DD HH:MM」
#   ③ 页面头部 6000 字符内可见日期（正文摘录型标题的背景日期靠①②先命中规避）
# 提取到 → 距今 >7 天剔除（指导性案例批量旧闻 273-279 被自然覆盖）；≤7 天 →
# 保留，pub_date 记为页面核验时间，stale_risk 清零。
# 提取不到 → 按「无法确认时效」策略处理（_unverifiable_policy 内注释说明理由）。
# 只对无日期条目发起详情页请求（有日期信号的不多发）；请求间隔
# DETAIL_REQ_INTERVAL、超时 DETAIL_TIMEOUT、_get 3 次重试；单页失败不影响整体。
DETAIL_REQ_INTERVAL = 0.3
DETAIL_TIMEOUT = 10
PAGE_DATE_META_PATTERNS = (
    re.compile(r'<meta[^>]+name="?(?:pubdate|publishdate|publish_date|'
               r'article:published_time|dc.date|date)"?[^>]+content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+name="?(?:pubdate|publishdate|'
               r'publish_date|article:published_time|dc.date|date)"?', re.I),
    re.compile(r'<meta[^>]+itemprop="datePublished"[^>]+content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"', re.I),
)
PAGE_DATE_BODY = re.compile(r"发布时间[:：]\s*(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?", re.I)
PAGE_DATE_HEAD = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?")


def _fmt_ymd(y: str, m: str, d: str) -> str:
    """格式化并校验 Y/M/D（非法日期返回空串）"""
    try:
        return datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def extract_page_publish_time(html: str, head_chars: int = 6000) -> tuple:
    """从详情页 HTML 提取发布时间（KM 评审基准同口径）。
    返回 (日期串 YYYY-MM-DD, 提取方式) 或 (None, 未找到)。"""
    for pat in PAGE_DATE_META_PATTERNS:
        m = pat.search(html)
        if m:
            m2 = re.match(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", m.group(1).strip())
            if m2:
                d = _fmt_ymd(*m2.groups())
                if d:
                    return d, "meta"
    m = PAGE_DATE_BODY.search(html[:head_chars])
    if m:
        d = _fmt_ymd(*m.groups())
        if d:
            return d, "发布时间头"
    m = PAGE_DATE_HEAD.search(html[:head_chars])
    if m:
        d = _fmt_ymd(*m.groups())
        if d:
            return d, "正文头部"
    return None, "未找到"


def fetch_detail_publish_time(url: str) -> tuple:
    """真实请求详情页提取发布时间；单页失败返回 (None, 失败原因)，不影响整体"""
    try:
        r = _get(url, tries=3, timeout=DETAIL_TIMEOUT)
        r.encoding = r.apparent_encoding or "utf-8"
        t, how = extract_page_publish_time(r.text)
        return (t, how) if t else (None, "页面无日期信号")
    except Exception as e:
        return None, f"请求失败:{type(e).__name__}"


# 无日期且详情页无法提取时间的条目 → 处理策略（F1，理由注释）：
# - 旧文重灾区源（最高法/工信部/hnrsks——KM 终审抽样 46 条中 32 条为 >7 天
#   真实旧闻）：无法确认时效即剔除——宁可少报不可错报，杜绝旧闻回流；
# - hnrsks 招考核心词豁免：三支一扶等招募公告性质决定其当前有效（报名期）；
# - 发改委 yyglxxbsgw.ndrc.gov.cn：JS 壳页面（1292 字节无 meta/正文日期），
#   属进行中征求意见公告，页面无日期可证其旧 → 降级🟢保留（不进 TOP3，
#   stale_risk=True 提示）；其余非重灾区源同理降级🟢。
# - 标题以栏目/专题结构词开头且无详情页时间 → 按栏目页处理（剔除）。
EXAM_CORE_KWS = ("三支一扶", "支农", "支教", "支医", "帮扶乡村振兴", "准考证", "资格复审")
UNVERIFIABLE_DROP_HOSTS = ("miit.gov.cn", "court.gov.cn", "chinacourt.org",
                           "hnrsks.com", "mp.weixin.qq.com")


def _unverifiable_policy(title: str, url: str) -> str:
    """无法确认时效条目的处理策略。返回 'drop'（剔除）或 'green'（降级🟢保留）"""
    if is_column_title(title):
        return "drop"  # 栏目/专题结构词开头且无详情页时间 → 按栏目页处理
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    if host in UNVERIFIABLE_DROP_HOSTS:
        if "hnrsks.com" in host and any(k in title for k in EXAM_CORE_KWS):
            return "green"  # 招考核心情报豁免：招募公告当前有效
        return "drop"      # 旧文重灾区：无法确认时效即剔除
    return "green"         # 其余源（发改委 JS 壳等）：降级🟢保留


# 模块分类前置优先级规则（REQ-20260813-002 修复轮 P3，KM-001 打回 5 例误分类）：
# 中央会议 > 法律案例 > 经济指标数据 > 计量/标准/技术规范 > 十五五中央层级
PRE_CENTRAL_MEETING = ("中央政治局", "中央经济工作会议", "中央农村工作会议",
                       "全国两会", "中共中央召开", "全会")
PRE_LEGAL_CASE = ("指导性案例", "典型案例", "司法解释", "裁定", "判决")
PRE_ECON_DATA = ("指数", "同比", "环比", "增速", "经济运行", "数据发布",
                 "统计公报", "业务量")
PRE_TECH_STANDARD = ("计量", "校准规范", "技术规范", "行业标准",
                     "强制性国家标准", "报批")


def classify_module(title: str, source_name: str) -> str:
    """模块分类：按优先级匹配关键词，返回唯一主模块
    修复（P3）：①政治局会议→时政（先于经济民生）；②指导性案例→法律（先于三农）；
    ③电商物流指数→经济民生（先于三农）；④行业计量规范→科技产业（先于法律）；
    ⑤"十五五"开局/综述含中央层级→时政。"""
    t = title
    # ① 中央重大会议 → 时政（政治局会议标题常含"经济形势"等词）
    if any(k in t for k in PRE_CENTRAL_MEETING):
        return "时政"
    # ② 法律案例类 → 法律（案例标题常含"种业/农业"等三农词）
    if any(k in t for k in PRE_LEGAL_CASE):
        return "法律"
    # ③ 经济指标/数据类 → 经济民生（"农村业务量"等易误判三农）
    if any(k in t for k in PRE_ECON_DATA):
        return "经济民生"
    # ④ 计量/标准/技术规范类 → 科技产业（"修订"等词易误判法律）
    if any(k in t for k in PRE_TECH_STANDARD):
        return "科技产业"
    # ⑤ "十五五"开局/综述含中央层级 → 时政
    if "十五五" in t and any(k in t for k in ("习近平", "党中央", "中央",
                                               "全国两会", "开局", "综述")):
        return "时政"
    for mod in MODULE_ORDER:
        if mod == "时政":
            continue  # 兜底最后处理
        if any(k in t for k in MODULE_RULES[mod]):
            return mod
    # 兜底：河南来源的未分类新闻——转载中央新闻归时政，本地新闻归河南省情
    # （修复轮 3 R5：中原网转载总书记/中央会议新闻不应一律归河南省情）
    if "中原网" in source_name:
        if any(k in t for k in ("习近平", "总书记", "党中央", "国务院",
                                "中央政治局", "全国两会", "中央经济工作会议",
                                "中央农村工作会议", "中共中央", "国家主席",
                                "全国人大", "中办", "国办", "外交部")):
            return "时政"
        return "河南省情"
    return "时政"


def classify_importance(title: str, module: str, source_name: str) -> str:
    """重要度分级：🔴要闻 / 🟠重要 / 🟢参考"""
    t = title
    # —— 🔴 要闻 ——
    # 三支一扶招考动态（对考生最高价值，必看；hnrsks 首页标题可能被 CSS 截断，
    # 用来源+URL 栏目（zngg=招募公告）兜底判定）
    if ("三支一扶" in t or "支农" in t or "支教" in t or "支医" in t) and (
            any(k in t for k in ("公告", "招募", "计划", "报名", "准考证",
                                 "笔试", "面试", "重考", "补考", "资格复审",
                                 "体检", "成绩", "公示"))
            or "人事考试" in source_name
            or "zngg" in t or "zngg" in source_name):
        return "🔴"
    # 总书记活动（REQ-20260813-002 修复轮 P5）：
    # 重要讲话/重要指示/重要文章/重要会议仍🔴；外交礼节性报道
    # （致电祝贺/通电话/欢迎仪式/记功通令等）降🟠；
    # 学习宣传语境（深入学习贯彻习近平X思想/专题栏目）降🟠（修复轮 3 R5）
    if "习近平" in t or "总书记" in t:
        if any(k in t for k in ("重要讲话", "重要指示", "重要文章", "重要论述",
                                "强调", "主持", "集体学习", "全会", "政治局会议",
                                "经济工作会议", "座谈会")):
            return "🔴"
        if any(k in t for k in ("致电", "祝贺", "通电话", "会谈", "会见",
                                "欢迎仪式", "贺电", "贺信", "唁电", "慰问",
                                "复信", "通令")):
            return "🟠"
        # 学习宣传语境（「深入学习贯彻习近平法治思想」专题/栏目页等）→ 🟠
        # 此类是学习宣传报道而非总书记本人活动，不应享受🔴兜底
        if any(k in t for k in ("深入学习贯彻", "学习贯彻", "专题学习",
                                "学习宣传", "专题", "栏目")):
            return "🟠"
        return "🔴"
    # 中央重大会议/重大政策文件
    if any(k in t for k in RED_MAJOR):
        return "🔴"
    # 重要法律表决通过/施行
    if any(k in t for k in ("表决通过", "审议通过", "施行")) and \
       any(k in t for k in ("法", "条例", "法规", "草案", "修正")):
        return "🔴"
    # —— 🟠 重要 ——
    # 河南省委省政府重大部署
    if any(k in t for k in ORANGE_HENAN) and any(k in t for k in ORANGE_POLICY):
        return "🟠"
    # 部委政策文件 / 部委动态（来源为部委网站或标题含部委名）
    if any(k in t for k in MINISTRY_NAMES) or any(k in s for s in
            ("发改委", "统计局", "农业农村部", "工信部", "最高法", "网信办",
             "中国科学院", "中国人大网") for k in [source_name]):
        if any(k in t for k in ORANGE_POLICY):
            return "🟠"
    # 经济数据发布
    if module == "经济民生" and any(k in t for k in ORANGE_ECON):
        return "🟠"
    # 法律类动态（修订/草案/征求意见/司法解释）
    if module == "法律" and any(k in t for k in ("修订", "草案", "征求意见",
                                                 "司法解释", "案例", "发布")):
        return "🟠"
    # 外交/会谈类（习近平会谈会见，上文已处理；部委对外活动；外交礼节降🟠 P5）
    if any(k in t for k in ("会谈", "会见", "访问", "出席", "峰会", "论坛",
                            "致电", "祝贺", "通电话", "欢迎仪式", "贺电", "通令")):
        return "🟠"
    return "🟢"


def history_link(title: str) -> str:
    """历史关联：命中内置映射表返回背景；未命中返回空串（不输出）"""
    for key in sorted(HISTORY_LINKS, key=len, reverse=True):
        if key in title:
            return HISTORY_LINKS[key]
    return ""


# 考点词库（essence 关键词只从这里取；通知/同比/公示等非考点词一律不用，P4 修复）
EXAM_KEYWORDS = (
    # 招考
    "三支一扶", "支农", "支教", "支医", "帮扶乡村振兴", "重考", "补考",
    "准考证", "资格复审", "笔试", "面试", "招募", "公基", "公共基础知识",
    "报名", "录用",
    # 公基核心概念
    "乡村振兴", "中国式现代化", "新质生产力", "粮食安全", "共同富裕",
    "依法治国", "全过程人民民主", "基层治理", "三农", "中央一号文件",
    "二十届三中全会", "二十届四中全会", "二十届五中全会", "政府工作报告",
    "中央经济工作会议", "中央农村工作会议", "全国两会", "高质量发展",
    "强国建设", "民族复兴", "二十大", "中国特色社会主义", "人类命运共同体",
    "一带一路", "深化改革", "高水平开放",
    # 法律
    "民法典", "宪法", "立法法", "立法", "司法", "法治", "知识产权",
    "司法解释", "条例",
    # 三农
    "农业", "农村", "农民", "粮食", "耕地", "种业", "高标准农田", "宅基地",
    # 经济民生
    "就业", "物价", "消费", "财政", "税收", "社保", "医保", "养老金",
    "外贸", "进出口", "GDP", "经济数据",
    # 科技产业
    "人工智能", "数字经济", "低空经济", "航天", "卫星", "芯片", "量子",
    "机器人", "集成电路", "大模型", "新能源", "创新驱动",
    # 河南
    "河南", "豫", "中原", "黄河", "郑州",
    # 生态
    "生态", "绿色", "碳达峰", "碳中和", "污染防治",
)

# 各模块主考点词（同一新闻多关键词命中时按模块取主词，避免交叉错乱，P4 修复）
MODULE_PRIMARY_KW = {
    "时政": ("中央经济工作会议", "二十届四中全会", "二十届五中全会", "全国两会",
             "政府工作报告", "二十大", "中国式现代化", "全过程人民民主",
             "依法治国", "高质量发展", "强国建设", "民族复兴", "深化改革",
             "中央农村工作会议", "中央一号文件"),
    "法律": ("民法典", "宪法", "立法法", "依法治国", "法治", "司法", "立法",
             "司法解释", "知识产权", "条例"),
    "三农": ("乡村振兴", "中央一号文件", "粮食安全", "耕地", "高标准农田",
             "种业", "三农", "粮食", "农业", "农村", "农民"),
    "经济民生": ("经济数据", "高质量发展", "共同富裕", "就业", "消费", "物价",
                 "财政", "税收", "社保", "医保", "GDP", "进出口"),
    "科技产业": ("新质生产力", "人工智能", "数字经济", "低空经济", "航天",
                 "创新驱动", "芯片", "量子", "机器人", "集成电路", "新能源"),
    "河南省情": ("河南", "豫", "中原", "黄河", "郑州"),
    "马哲": ("马克思主义", "辩证法", "唯物", "矛盾"),
    "中特": ("中国特色社会主义", "中国式现代化", "人类命运共同体", "社会主义"),
}

MODULE_KW_FALLBACK = {
    "时政": "时政热点", "法律": "法治建设", "三农": "乡村振兴",
    "经济民生": "高质量发展", "科技产业": "新质生产力", "河南省情": "河南省情",
    "马哲": "马克思主义", "中特": "中国特色社会主义",
}


def _cap60(s: str) -> str:
    """essence 长度硬上限 60 字（P4：>80 字问题修复）"""
    return s if len(s) <= 60 else s[:57] + "…"


def _pick_exam_kws(title: str, module: str) -> list:
    """按模块取考点词：模块主词优先，再补通用考点词，最多 2 个
    （P4：不再从 KEYWORDS 全表取词，排除通知/同比/公示等非考点词）"""
    prim = [k for k in MODULE_PRIMARY_KW.get(module, ()) if k in title]
    rest = [k for k in EXAM_KEYWORDS if k in title and k not in prim]
    return (prim + rest)[:2]


def _core_event(title: str, max_len: int = 22) -> str:
    """提取标题核心事件：去【】前缀/时间状语/公文式开头/机构名开头/冗余动词/文种后缀
    （P4：essence 不再整段复制标题）"""
    t = re.sub(r"^【[^】]+】", "", title).strip()
    t = re.sub(r"^(20\d{2})年\d{1,2}月\d{1,2}日", "", t).strip()
    t = re.sub(r"^(工业和信息化部|最高人民法院|最高法|最高人民检察院|农业农村部|"
               r"国家统计局|国家发展改革委|国家发改委|中国科学院|国务院|"
               r"中共中央|中央军委|河南省委|河南省政府|两部门|七部门|十部门)", "", t).strip()
    t = re.sub(r"^等?[一二三四五六七八九十\d]{1,2}部门(?:办公厅?（(?:办公室|综合司)）|联合)?"
               r"(?:印发|关于|开展)?", "", t).strip()
    t = re.sub(r"^(关于|关于开展|关于公开征求|关于向社会公开征求|关于印发)", "", t).strip()
    t = re.sub(r"^(召开|举行|发布|印发|出台|举办)", "", t).strip()
    t = re.sub(r"(的通知|的公示|的公告|的征求意见稿|的函)$", "", t).strip()
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"


def _essence_leader(title: str, kw_part: str) -> str:
    """总书记新闻 essence：按事件类型细分模板（P4：标题不整段复制）"""
    if any(k in title for k in ("讲话", "强调", "指示", "重要论述", "发表重要")):
        return f"【考点】总书记重要论述，重点掌握核心论断与表述（{kw_part}）"
    m = re.search(r"《([^》]{2,24})》", title)
    if any(k in title for k in ("重要文章", "署名文章", "《求是》")):
        # 取最后一个书名号内容为文章名（过滤《求是》杂志名本身，避免「发表《求是》」）
        arts = [a for a in re.findall(r"《([^》]{2,24})》", title) if a != "求是"]
        art = f"《{arts[-1]}》" if arts else "重要文章"
        return f"【考点】总书记在《求是》发表{art}，重点掌握文章主题与核心论断"
    if any(k in title for k in ("政治局会议", "全会", "经济工作会议", "召开会议",
                                "主持召开", "集体学习", "座谈会")):
        return f"【考点】中央重要会议，重点掌握会议主题与部署重点（{kw_part}）"
    if any(k in title for k in ("考察", "调研", "走访")):
        return f"【考点】总书记考察调研，关注相关领域政策表述（{kw_part}）"
    if any(k in title for k in ("会谈", "会见", "访问", "致电", "通电话",
                                "欢迎仪式", "贺电", "通令")):
        return "【考点】外交活动报道，关注我国外交主张与大国关系"
    if any(k in title for k in ("出席", "开幕式", "大会")):
        return f"【考点】总书记出席重要活动，关注会议主题与我国立场（{kw_part}）"
    return f"【考点】总书记相关动态，结合{kw_part}理解时政背景"


def build_essence(title: str, module: str, importance: str, summary: str) -> str:
    """精华提炼：1-2 句考点提炼（≤60 字），禁止臆造（REQ-20260813-002 修复轮 P4）
    - 考点词只取 EXAM_KEYWORDS（排除通知/同比/公示等非考点词）
    - 多关键词命中时按模块主词优先（MODULE_PRIMARY_KW），避免交叉错乱
    - 核心事件从标题提取（去时间状语/机构名/冗余动词），不整段复制标题"""
    kws = _pick_exam_kws(title, module)
    kw_part = "、".join(kws) if kws else MODULE_KW_FALLBACK.get(module, "核心表述")
    core = _core_event(title)

    # 招考动态（三支一扶等）：考生最直接情报
    if any(k in title for k in ("三支一扶", "支农", "支教", "支医", "帮扶乡村振兴",
                                "招募", "准考证", "资格复审")):
        return _cap60("【考点】河南三支一扶招考动态，重点核对报名、笔试与准考证安排，"
                      "以省人事考试网公告为准")
    # 总书记相关：按事件类型细分模板
    if "习近平" in title or "总书记" in title:
        return _cap60(_essence_leader(title, kw_part))
    # 法律
    if module == "法律":
        if any(k in title for k in ("草案", "修订", "审议", "表决通过")):
            return _cap60(f"【考点】{core}，重点掌握立法进程与施行时间")
        if any(k in title for k in ("施行", "实施")):
            return _cap60(f"【考点】{core}，重点掌握施行时间与适用要点")
        if any(k in title for k in ("指导性案例", "典型案例", "案例")):
            return _cap60(f"【考点】{core}，关注裁判要旨与法律适用")
        return _cap60(f"【考点】{core}，法律模块关注新法动态与核心制度")
    # 三农
    if module == "三农":
        return _cap60(f"【考点】{core}，聚焦粮食安全与乡村振兴主线")
    # 经济民生
    if module == "经济民生":
        if any(k in title for k in ("同比", "环比", "指数", "增速", "经济运行")):
            return _cap60(f"【考点】{core}，关注宏观指标走势与政策背景")
        return _cap60(f"【考点】{core}，关注就业、物价、消费等民生指标")
    # 科技产业
    if module == "科技产业":
        if any(k in title for k in ("计量", "标准", "规范")):
            return _cap60(f"【考点】{core}，关注行业标准与技术规范动态")
        return _cap60(f"【考点】{core}，关注新质生产力与创新动态")
    # 河南省情
    if module == "河南省情":
        return _cap60(f"【考点】{core}，河南省情为河南三支一扶特色考点")
    # 马哲
    if module == "马哲":
        return _cap60(f"【考点】{core}，注意哲学原理与最新论述结合考查")
    # 中特
    if module == "中特":
        return _cap60(f"【考点】{core}，中特核心概念需掌握理论内涵与实践要求")
    # 时政兜底
    if any(k in title for k in ("会议", "全会", "座谈", "论坛")):
        return _cap60(f"【考点】{core}，关注会议主题、重要论断与决策部署")
    if any(k in title for k in ("印发", "出台", "发布", "部署", "规划", "意见", "方案")):
        return _cap60(f"【考点】{core}，政策文件是公基时政常考点")
    return _cap60(f"【考点】{core}，建议结合{kw_part}理解时政背景")


def score_title(title: str, summary: str = "") -> int:
    """按关键词对标题+摘要打分"""
    s = 0
    text = title + " " + summary
    for kw, w in KEYWORDS.items():
        if kw in text:
            s += w
    return s


def fetch_html_links(source: dict) -> list:
    """抓 HTML 列表页，正则提取 (url, title) 条目"""
    resp = _get(source["url"])
    resp.encoding = resp.apparent_encoding or "utf-8"
    items = []
    for m in re.finditer(source.get("link_re", ""), resp.text):
        href, title = m.group(1), clean_text(m.group(2))
        if not href.startswith("http"):
            href = urljoin(source["url"], href)
        if not title:
            continue
        items.append({"url": href, "title": title})
    return items


def fetch_rss(source: dict) -> list:
    """抓 RSS/Atom 源，返回带 pub_date 的条目"""
    if not HAS_FEEDPARSER:
        raise RuntimeError("feedparser 未安装：pip install feedparser")
    resp = _get(source["url"])
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries[:50]:
        title = clean_text(getattr(e, "title", ""))
        link = getattr(e, "link", "")
        summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", ""))
        pub = ""
        for attr in ("published_parsed", "updated_parsed"):
            pp = getattr(e, attr, None)
            if pp:
                try:
                    pub = datetime(*pp[:6]).astimezone(CST).strftime("%Y-%m-%d")
                    break
                except Exception:
                    pass
        if title:
            items.append({"url": link, "title": title, "summary": summary[:200],
                          "pub_date": pub})
    return items


def collect(min_score: int = 2) -> dict:
    """抓取全部数据源 → 噪声过滤 → 旧闻过滤 → 分级分类 → 评分排序"""
    today = datetime.now(CST)
    result = {"generated_at": today.strftime("%Y-%m-%d %H:%M:%S %Z"),
              "exam_date": "2026-08-22",
              "days_left": (EXAM_DATE - today).days,
              "sources": [], "items": []}
    # F1 详情页核验统计（修复轮4：无日期条目处理明细，供评审追溯）
    result["detail_verify"] = {"no_date_total": 0, "page_time_ok": 0,
                               "page_old_dropped": 0, "unverifiable_dropped": 0,
                               "unverifiable_green": 0}
    dv = result["detail_verify"]
    for src in SOURCES:
        entry = {"name": src["name"], "url": src["url"], "ok": False,
                 "error": None, "count": 0}
        try:
            if src["kind"] == "rss":
                raw = fetch_rss(src)
            else:
                raw = fetch_html_links(src)
            scored = []
            for it in raw:
                title = it["title"].strip()
                if is_noise(title, it["url"]):
                    continue  # 模式化小新闻直接剔除
                if title_year_stale(title, today):
                    continue  # 标题内年份早于当前年 → 旧闻
                stale, risk = is_stale(it, today)
                if stale:
                    continue  # 旧闻剔除
                # ---- F2：常驻栏目/专题/导航聚合页直接剔除（非实时新闻）----
                if is_column_url(it["url"]):
                    continue
                module = classify_module(title, src["name"])
                importance = classify_importance(title, module, src["name"])
                # 🟢低分条目提前过滤（修复轮4 优化：避免为最终会被 min-score
                # 过滤的 🟢 零分导航/栏目垃圾条目浪费详情页请求——实测可省百次请求）
                s = score_title(title, it.get("summary", ""))
                if importance == "🟢" and s < min_score:
                    continue
                # ---- F1：详情页发布时间提取层 ----
                # 仅 URL/pub_date 均无日期信号（risk 且 get_pub_date 为空）的条目
                # 才发起详情页请求；有日期信号的不多发。单页失败不影响整体。
                page_time, page_how = None, ""
                if risk and not get_pub_date(it):
                    dv["no_date_total"] += 1
                    page_time, page_how = fetch_detail_publish_time(it["url"])
                    time.sleep(DETAIL_REQ_INTERVAL)  # 详情页请求间隔（爬虫礼仪）
                    if page_time:
                        pd = datetime.strptime(page_time, "%Y-%m-%d").replace(tzinfo=CST)
                        age = (today - pd).days
                        if age > MAX_AGE_DAYS:
                            dv["page_old_dropped"] += 1
                            print(f"    🗑️ 详情页时间>7天({age}天): {title[:42]}")
                            continue
                        dv["page_time_ok"] += 1
                        risk = False  # 页面时间确认时效，stale_risk 清零
                    else:
                        # 无法确认时效 → 策略处理（_unverifiable_policy 注释说明理由）
                        if _unverifiable_policy(title, it["url"]) == "drop":
                            dv["unverifiable_dropped"] += 1
                            print(f"    🗑️ 无日期且无法核验剔除: {title[:42]}")
                            continue
                        dv["unverifiable_green"] += 1
                        if importance != "🔴":
                            importance = "🟢"  # 无法确认时效 → 降级🟢（不进 TOP3）
                        print(f"    ⚠️ 无日期无法核验降🟢: {title[:42]}")
                # 🟢参考级才受 --min-score 限制（F1 降级后的 🟢 在此兜底过滤）
                if importance == "🟢" and s < min_score:
                    continue
                essence = build_essence(title, module, importance,
                                        it.get("summary", ""))
                item = {
                    "title": title,
                    "url": it["url"],
                    "source": src["name"],
                    "score": s,
                    "pub_date": page_time or get_pub_date(it),
                    "module": module,
                    "importance": importance,
                    "essence": essence,
                    "stale_risk": risk,
                }
                if page_time:
                    item["page_time_source"] = page_how  # 页面核验提取方式（meta/发布时间头/正文头部）
                hist = history_link(title)
                if hist:
                    item["history"] = hist
                scored.append(item)
            # 按重要度 + 评分排序
            imp_order = {"🔴": 0, "🟠": 1, "🟢": 2}
            scored.sort(key=lambda x: (imp_order.get(x["importance"], 3),
                                       -x["score"]))
            entry["ok"] = True
            entry["count"] = len(scored)
            result["items"].extend(scored)
            print(f"  ✅ {src['name']}: 抓取 {len(raw)} 条，命中 {len(scored)} 条")
        except Exception as e:  # 单源失败不影响整体
            entry["error"] = f"{type(e).__name__}: {e}"
            print(f"  ⚠️  {src['name']}: 失败 - {entry['error']}")
        result["sources"].append(entry)
        time.sleep(REQUEST_INTERVAL)  # 爬虫礼仪：请求间隔
    # 排序（重要度优先，同级按分数）后再去重，保证保留最高重要度/最高分的条目
    imp_order = {"🔴": 0, "🟠": 1, "🟢": 2}
    result["items"].sort(key=lambda x: (imp_order.get(x["importance"], 3),
                                        -x["score"]))
    result["items"] = _dedup(result["items"])
    result["hits"] = len(result["items"])
    result["top_keywords"] = _top_keywords(result["items"])
    print(f"[intel_collector] 详情页核验(F1): 无日期 {dv['no_date_total']} 条 → "
          f"页面时间确认 {dv['page_time_ok']} / 详情页旧闻剔除 {dv['page_old_dropped']} / "
          f"无法核验剔除 {dv['unverifiable_dropped']} / 降级🟢 {dv['unverifiable_green']}")
    return result


def _norm_title(title: str) -> str:
    """标题归一化：去掉【新闻联播】等包装前缀，用于跨源同内容去重"""
    t = re.sub(r"^【[^】]+】", "", title).strip()
    return t


def _dedup(items: list) -> list:
    """去重：URL 去重 + 同源同标题前40字去重 + 跨源归一化标题前30字去重"""
    seen_url, seen_title = set(), set()
    seen_norm = set()
    uniq = []
    for it in items:
        tk = (it["source"], it["title"][:40])
        norm = _norm_title(it["title"])[:30]
        if it["url"] in seen_url or tk in seen_title or norm in seen_norm:
            continue
        seen_url.add(it["url"])
        seen_title.add(tk)
        seen_norm.add(norm)
        uniq.append(it)
    return uniq


def _top_keywords(items: list, n: int = 8) -> list:
    c = Counter()
    for it in items:
        text = it["title"] + " " + it.get("essence", "")
        for kw, w in KEYWORDS.items():
            if kw in text:
                c[kw] += w
    return [k for k, _ in c.most_common(n)]


def write_outputs(result: dict, date_str: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = OUT_DIR / f"intel-{date_str}.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    mp = OUT_DIR / f"intel-{date_str}.md"
    src_ok = sum(1 for s in result["sources"] if s["ok"])
    lines = [
        f"# 每日情报汇总 {date_str}",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 距河南三支一扶重考（2026-08-22）：**{result['days_left']} 天**",
        f"- 数据源健康：{src_ok}/{len(result['sources'])} 可用",
        f"- 命中条目：{result['hits']} 条",
        f"- 高频关键词：{'、'.join(result['top_keywords'])}",
        "",
        "## 数据源状态",
        "",
    ]
    for s in result["sources"]:
        status = "✅" if s["ok"] else "❌"
        err = f"（{s['error']}）" if s["error"] else ""
        lines.append(f"- {status} {s['name']}：{s['count']} 条{err}")
    # 按重要度分组展示
    imp_order = ["🔴", "🟠", "🟢"]
    imp_names = {"🔴": "🔴 要闻（必看）", "🟠": "🟠 重要", "🟢": "🟢 参考"}
    lines += ["", "## 命中条目（按重要度）", ""]
    for imp in imp_order:
        group = [it for it in result["items"] if it["importance"] == imp]
        if not group:
            continue
        lines.append(f"### {imp_names[imp]}（{len(group)} 条）")
        lines.append("")
        for it in group:
            lines.append(f"- {it['importance']} [{it['module']}] [{it['source']}] {it['title']}")
            lines.append(f"  {it['url']}")
            lines.append(f"  💡 {it['essence']}")
            if it.get("history"):
                lines.append(f"  📜 {it['history']}")
            lines.append("")
    with open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"json": str(jp), "md": str(mp)}


def main():
    ap = argparse.ArgumentParser(description="河南三支一扶备考情报采集（REQ-20260813-002）")
    ap.add_argument("--date", default=None, help="输出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--min-score", type=int, default=2,
                    help="🟢参考级新闻相关性最低分值（默认2；🔴/🟠重要新闻豁免）")
    args = ap.parse_args()
    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    print(f"[intel_collector] 开始抓取 {date_str}（min-score={args.min_score}）...")
    result = collect(min_score=args.min_score)
    paths = write_outputs(result, date_str)
    ok = sum(1 for s in result["sources"] if s["ok"])
    print(f"[intel_collector] 完成：源健康 {ok}/{len(result['sources'])}，命中 {result['hits']} 条")
    print(f"  JSON: {paths['json']}")
    print(f"  MD:   {paths['md']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
