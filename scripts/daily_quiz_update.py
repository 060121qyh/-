#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日新题自动生成脚本（REQ-20260813-001 / T1b）
读取当日情报（data/daily-intel/intel-YYYY-MM-DD.md / .json）+
参考知识卡（data/knowledge-cards/ 目录），模板化生成 3-5 道新题：

  - 当日时政/河南动态相关 1-3 题（由情报命中关键词驱动）
  - 可复用知识卡主题 1-2 题（由知识卡文件存在性驱动）

生成后**复用 expand_quiz_bank.py 的校验与合并逻辑**：
  1. 每题过 validate_question（12 必填字段 + 五段式 ≥8 字符 + 题型/模块/
     difficulty/options 校验）；
  2. 全部通过 → 写入 data/quiz-bank/YYYY-MM-DD-intel-new.json；
  3. 按题干归一化去重 merge 进 data/quiz-bank/YYYY-MM-DD-merged.json
     （原题全部保留，重复运行幂等）。

用法：
  python scripts/daily_quiz_update.py                # 用当天情报生成
  python scripts/daily_quiz_update.py --date 2026-08-13
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 复用同目录 expand_quiz_bank.py 的校验/合并函数（其含 __main__ 守卫，import 不触发 main）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from expand_quiz_bank import (validate_question, load_questions,  # noqa: E402
                              merge_banks)

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
INTEL_DIR = BASE_DIR / "data" / "daily-intel"
QUIZ_DIR = BASE_DIR / "data" / "quiz-bank"
KC_DIR = BASE_DIR / "data" / "knowledge-cards"

MIN_QUESTIONS = 3   # 至少生成 3 道
MAX_QUESTIONS = 5   # 至多生成 5 道


# =====================================================================
# 模板 1：河南三支一扶招募公告发布渠道（时政热点，情报驱动）
# =====================================================================
def make_q1(items):
    hits = [it for it in items
            if any(k in it.get("title", "") for k in ("三支一扶", "支农", "支教", "支医"))]
    if not hits:
        return None
    src = hits[0]
    correct = "【正确答案】A（河南省人事考试网）"
    term = ("【术语拆解】\n"
            "• 「三支一扶」：支教、支农、支医和帮扶乡村振兴计划的简称，是国家引导高校"
            "毕业生到基层就业的重要项目，河南省2026年高校毕业生三支一扶计划招募公告即"
            "发布于河南省人事考试网。\n"
            "• 「河南省人事考试网（www.hnrsks.com）」：河南省人事考试中心官方网站，"
            "河南省公务员录用、事业单位公开招聘、三支一扶招募等各类人事考试信息的"
            "第一权威发布渠道。")
    opt = ("【选项辨析】\n"
           "• A（✅）：河南省2026年高校毕业生三支一扶计划招募公告发布在河南省人事考试网"
           "「站内公告」栏目，报名、准考证打印、成绩查询等环节均以该网站通知为准。\n"
           "• B：河南省教育厅官网主要发布教育行政、招生考试类信息，不承担三支一扶招募"
           "公告发布职能。\n"
           "• C：河南省农业农村厅官网侧重涉农政策宣传，并非人事考试公告渠道。\n"
           "• D：中国人事考试网面向全国统一组织的职业资格考试，地方三支一扶招募公告"
           "不在该网发布。")
    hint = ("【考情提示】招考信息渠道类题目是时政/河南考情的高频考点，答题要点是"
            "「以官方渠道发布为准」：三支一扶、公务员、事业单位招考信息均以河南省人事"
            "考试网发布为准。")
    mnem = ("【记忆口诀】河南招考认人事考试网，三支一扶看 hnrsks（河南省人事考试网域名）")
    explanation = (correct + "\n\n" + term + "\n\n" + opt + "\n\n" + hint + "\n"
                   + mnem + f"\n\n【来源】{src.get('title', '')} {src.get('url', '')}")
    return {
        "type": "单选题", "module": "时政热点", "difficulty": 2,
        "stem": "河南省2026年高校毕业生“三支一扶”计划招募，考生获取公告、报名、"
                "准考证打印等官方信息应以（ ）发布为准。",
        "options": {"A": "河南省人事考试网（www.hnrsks.com）",
                    "B": "河南省教育厅官网",
                    "C": "河南省农业农村厅官网",
                    "D": "中国人事考试网"},
        "answer": "A", "explanation": explanation,
        "correct_answer": correct, "term_breakdown": term,
        "option_analysis": opt, "exam_hint": hint, "mnemonic": mnem,
    }


# =====================================================================
# 模板 2：第四次全国农业普查年份（三农与乡村振兴，情报驱动 + 知识卡关联）
# =====================================================================
def make_q2(items, kc_available):
    hits = [it for it in items if "农业普查" in it.get("title", "")]
    if not hits and not kc_available:
        return None
    src = hits[0] if hits else None
    correct = "【正确答案】B（2026年）"
    term = ("【术语拆解】\n"
            "• 「全国农业普查」：由国家统一组织的重大国情国力调查，依据《中华人民共和国"
            "统计法》和《全国农业普查条例》开展，每10年进行一次（1996年、2006年、"
            "2016年、2026年分别为第一至第四次）。\n"
            "• 「第四次全国农业普查」：国务院印发通知决定2026年开展，是在以中国式现代化"
            "全面推进中华民族伟大复兴的新征程上开展的一项重大国情国力调查。")
    opt = ("【选项辨析】\n"
           "• A 2025年：2025年是印发开展普查通知的年份，但普查正式开展年份为2026年，"
           "注意区分「印发通知年份」与「普查开展年份」。\n"
           "• B（✅）：2026年为第四次全国农业普查年，符合农业普查十年一次、逢6年份"
           "开展的周期规律。\n"
           "• C 2027年：若在2027年开展则打破十年周期，与历次普查间隔不符。\n"
           "• D 2028年：间隔过长，不符合农业普查十年一次的周期安排。")
    hint = ("【考情提示】农业普查年份与周期是三农时政常考点，记住「十年一次、逢6开展」"
            "的规律（1996/2006/2016/2026），并注意区分通知印发年份与普查开展年份。")
    mnem = "【记忆口诀】农业普查十年一轮、逢6开查：九六、零六、一六、二六"
    explanation = (correct + "\n\n" + term + "\n\n" + opt + "\n\n" + hint + "\n"
                   + mnem + (f"\n\n【来源】{src.get('title', '')} {src.get('url', '')}"
                             if src else ""))
    return {
        "type": "单选题", "module": "三农与乡村振兴", "difficulty": 2,
        "stem": "根据《中华人民共和国统计法》和《全国农业普查条例》的规定，国务院"
                "决定于（ ）年开展第四次全国农业普查。",
        "options": {"A": "2025年", "B": "2026年", "C": "2027年", "D": "2028年"},
        "answer": "B", "explanation": explanation,
        "correct_answer": correct, "term_breakdown": term,
        "option_analysis": opt, "exam_hint": hint, "mnemonic": mnem,
    }


# =====================================================================
# 模板 3：卢氏县基层治理创新（河南省情，情报驱动）
# =====================================================================
def make_q3(items):
    hits = [it for it in items
            if any(k in it.get("title", "") for k in ("卢氏", "凉亭"))]
    if not hits:
        return None
    src = hits[0]
    correct = "【正确答案】A（“凉亭夜话”）"
    term = ("【术语拆解】\n"
            "• 「凉亭夜话」：河南省三门峡市卢氏县基层治理创新实践，源于卢氏县木桐乡群众"
            "的自发行动，村民在树下院落、乡间凉亭围坐议事，后发展为党委引领下的制度化"
            "实践，被媒体称为以「小议事」撬动「大治理」。\n"
            "• 「基层治理创新」：以群众议事平台为载体推动治理重心下移，让群众从治理对象"
            "变为治理参与者。")
    opt = ("【选项辨析】\n"
           "• A（✅）：「凉亭夜话」是卢氏县木桐乡群众自发形成、后由党委引领制度化的"
           "议事模式，是当地基层治理的典型创新品牌。\n"
           "• B「板凳会」：安徽等地推广的基层议事形式，与卢氏县凉亭夜话不同源。\n"
           "• C「院坝会」：云贵川等地常见的群众会形式，并非河南卢氏首创。\n"
           "• D「流动议事会」：泛指巡回式议事形式，不是卢氏县的具体创新品牌。")
    hint = ("【考情提示】河南本地社会治理典型经验是河南省情模块的命题素材，注意"
            "「地点—做法」的对应关系，选项常混入外省经验作干扰。")
    mnem = "【记忆口诀】卢氏木桐凉亭下，夜话议事大治理"
    explanation = (correct + "\n\n" + term + "\n\n" + opt + "\n\n" + hint + "\n"
                   + mnem + f"\n\n【来源】{src.get('title', '')} {src.get('url', '')}")
    return {
        "type": "单选题", "module": "河南省情", "difficulty": 3,
        "stem": "河南省三门峡市卢氏县探索形成的、以“小议事”撬动“大治理”的基层"
                "治理创新模式是（ ）。",
        "options": {"A": "“凉亭夜话”", "B": "“板凳会”",
                    "C": "“院坝会”", "D": "“流动议事会”"},
        "answer": "A", "explanation": explanation,
        "correct_answer": correct, "term_breakdown": term,
        "option_analysis": opt, "exam_hint": hint, "mnemonic": mnem,
    }


# =====================================================================
# 模板 4：18亿亩耕地红线（三农与乡村振兴，知识卡复用题）
# =====================================================================
def make_q4(kc_available):
    if not kc_available:
        return None
    correct = "【正确答案】C（18亿亩）"
    term = ("【术语拆解】\n"
            "• 「18亿亩耕地红线」：我国耕地保有量的底线，是保障国家粮食安全的根基，"
            "由《粮食安全保障法》以法律形式明确。\n"
            "• 「非农化/非粮化」：耕地被用于非农业建设称「非农化」，被改种非粮食作物称"
            "「非粮化」，两者均须坚决遏制。\n"
            "• 「粮食安全保障法」：2023年12月通过、2024年6月1日起施行的我国粮食领域"
            "基础性法律。")
    opt = ("【选项辨析】\n"
           "• A 15亿亩：偏低，历史上曾作为阶段性保护目标，但现行法定红线为18亿亩。\n"
           "• B 16亿亩：同样低于法定红线，为干扰数字。\n"
           "• C（✅）：18亿亩是《粮食安全保障法》明确的耕地红线，与「谷物基本自给、"
           "口粮绝对安全」的国家粮食安全战略相配套。\n"
           "• D 20亿亩：高于法定红线，我国现实耕地保有量未达到该数值。")
    hint = ("【考情提示】耕地红线数值是三支一扶三农模块高频考点，重点记忆18亿亩，"
            "并掌握「非农化」「非粮化」两个概念的对应关系。")
    mnem = "【记忆口诀】耕地红线十八亿，非农非粮双遏制"
    explanation = (correct + "\n\n" + term + "\n\n" + opt + "\n\n" + hint + "\n"
                   + mnem + "\n\n【来源】知识卡《粮食安全·耕地保护·乡村振兴核心政策考点》")
    return {
        "type": "单选题", "module": "三农与乡村振兴", "difficulty": 2,
        "stem": "根据2024年施行的《中华人民共和国粮食安全保障法》，国家实行最严格的"
                "耕地保护制度，严守（ ）耕地红线，坚决遏制耕地“非农化”、防止“非粮化”。",
        "options": {"A": "15亿亩", "B": "16亿亩", "C": "18亿亩", "D": "20亿亩"},
        "answer": "C", "explanation": explanation,
        "correct_answer": correct, "term_breakdown": term,
        "option_analysis": opt, "exam_hint": hint, "mnemonic": mnem,
    }


# =====================================================================
# 模板 5：《乡村振兴责任制实施办法》印发主体（时政热点，情报驱动）
# =====================================================================
def make_q5(items):
    hits = [it for it in items
            if any(k in it.get("title", "") for k in ("乡村振兴责任制", "乡村振兴责任"))]
    if not hits:
        return None
    src = hits[0]
    correct = "【正确答案】A（中共中央办公厅、国务院办公厅）"
    term = ("【术语拆解】\n"
            "• 「乡村振兴责任制」：以制度形式明确中央和国家机关有关部门、地方各级党委"
            "和政府推进乡村振兴的责任，实行中央统筹、省负总责、市县乡抓落实的工作机制。\n"
            "• 「实施办法」：对乡村振兴责任落实作出的具体制度安排，印发后要求各地区"
            "各部门认真遵照执行。")
    opt = ("【选项辨析】\n"
           "• A（✅）：《乡村振兴责任制实施办法》由中共中央办公厅、国务院办公厅印发，"
           "属于中央层面联合发文，权威层级最高。\n"
           "• B 农业农村部：作为主管部门负责组织实施与督导，但不是印发主体。\n"
           "• C 国家发展改革委：承担部分涉农规划职能，不承担该文件印发职责。\n"
           "• D 全国人大常委会：行使立法权，不印发此类党内规范性文件。")
    hint = ("【考情提示】「印发主体」类时政题重在记忆发文机关层级：重要涉农文件多为"
            "中办、国办联合印发，部委文件则为部门单独印发，两者层级不同。")
    mnem = "【记忆口诀】乡村振兴责任制，中办国办联合印"
    explanation = (correct + "\n\n" + term + "\n\n" + opt + "\n\n" + hint + "\n"
                   + mnem + f"\n\n【来源】{src.get('title', '')} {src.get('url', '')}")
    return {
        "type": "单选题", "module": "时政热点", "difficulty": 3,
        "stem": "近日印发的《乡村振兴责任制实施办法》是由（ ）印发的。",
        "options": {"A": "中共中央办公厅、国务院办公厅",
                    "B": "农业农村部",
                    "C": "国家发展和改革委员会",
                    "D": "全国人大常委会"},
        "answer": "A", "explanation": explanation,
        "correct_answer": correct, "term_breakdown": term,
        "option_analysis": opt, "exam_hint": hint, "mnemonic": mnem,
    }


def load_intel(date_str):
    """读取当日情报，返回 (items 列表, days_left)；json 优先，md 兜底"""
    jp = INTEL_DIR / f"intel-{date_str}.json"
    mp = INTEL_DIR / f"intel-{date_str}.md"
    items, days_left = [], None
    if jp.exists():
        data = json.loads(jp.read_text(encoding="utf-8"))
        items = data.get("items", [])
        days_left = data.get("days_left")
    if not items and mp.exists():
        # md 兜底：解析 `- ⭐N [来源] 标题` 行
        for line in mp.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^-\s*⭐\d+\s*\[[^\]]+\]\s*(.+)$", line.strip())
            if m:
                items.append({"title": m.group(1).strip(), "url": "", "score": 0})
    return items, days_left


def build_questions(items, kc_available):
    """按模板生成题目，控制 3-5 道：情报题优先，知识卡题兜底"""
    intel_questions = [q for q in (make_q1(items), make_q2(items, kc_available),
                                   make_q3(items), make_q5(items)) if q]
    kc_questions = [q for q in (make_q4(kc_available),) if q]
    if len(intel_questions) > MAX_QUESTIONS - len(kc_questions):
        intel_questions = intel_questions[:MAX_QUESTIONS - len(kc_questions)]
    questions = intel_questions + kc_questions
    return questions[:MAX_QUESTIONS]


def main():
    ap = argparse.ArgumentParser(description="每日新题自动生成（T1b）")
    ap.add_argument("--date", default=None, help="情报日期 YYYY-MM-DD（默认今天）")
    args = ap.parse_args()
    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")

    print(f"[daily_quiz_update] 基于 {date_str} 情报生成新题...")
    items, days_left = load_intel(date_str)
    if not items:
        print(f"❌ 未找到 {date_str} 情报（{INTEL_DIR}/intel-{date_str}.json/.md）")
        return 1
    print(f"  情报条目 {len(items)} 条，距考 {days_left} 天")

    kc_dir = KC_DIR / "三农与乡村振兴"
    kc_available = kc_dir.exists() and any(kc_dir.glob("*.md"))
    print(f"  知识卡参考：{'可用（' + str(kc_dir) + '）' if kc_available else '不可用'}")

    questions = build_questions(items, kc_available)
    if len(questions) < MIN_QUESTIONS:
        print(f"❌ 仅生成 {len(questions)} 道（<{MIN_QUESTIONS}），放弃写入")
        return 1
    print(f"  模板命中生成 {len(questions)} 道新题")

    # ---- 复用 expand_quiz_bank.validate_question 逐题校验 ----
    errors = []
    for i, q in enumerate(questions):
        validate_question(q, i, errors)
    if errors:
        print("❌ 新题校验失败：")
        for e in errors:
            print("  -", e)
        return 1
    print(f"  ✅ {len(questions)} 道新题全部通过五段式校验")

    # ---- 写入当日新题文件 ----
    new_path = QUIZ_DIR / f"{date_str}-intel-new.json"
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"  ✅ 新题文件: {new_path}（{new_path.stat().st_size} 字节）")

    # ---- 复用 expand_quiz_bank.merge_banks 按题干去重合并 ----
    merged_path = QUIZ_DIR / f"{date_str}-merged.json"
    if merged_path.exists():
        bank_qs = load_questions(merged_path)
    else:
        bank_qs = []
    merged, added, dup = merge_banks(bank_qs, questions)
    merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"  ✅ 合并完成: 基底 {len(bank_qs)} 题 + 新增 {added} 题"
          f"（去重跳过 {dup}）→ {merged_path}（共 {len(merged)} 题）")

    # ---- 合并结果整体复验（区分「新题错误」与「基底既有历史遗留」） ----
    ok, errs, n, dist = validate_file_quiet(merged_path)
    base_n = len(bank_qs)  # 基底题数，>= base_n 的题号属于本次新题
    new_errs, base_errs = [], []
    for e in errs:
        m = re.match(r"^第(\d+)题", e)
        idx = int(m.group(1)) - 1 if m else -1
        (new_errs if idx >= base_n else base_errs).append(e)
    if not new_errs:
        print(f"  ✅ 合并后题库复验: {n} 题, 新题错误 0 处, 模块分布 {dict(dist)}")
        if base_errs:
            print(f"  ⚠️ 基底既有 {len(base_errs)} 处历史遗留问题"
                  f"（{base_n} 题中旧格式题，非本次新增，"
                  f"见 2026-08-12-001 迁移记录）")
        return 0
    print(f"  ❌ 新题存在 {len(new_errs)} 处校验错误：")
    for e in new_errs:
        print("  -", e)
    return 1


def validate_file_quiet(path):
    """调用 expand_quiz_bank.validate_file 做整体复验（静默模式）"""
    from expand_quiz_bank import validate_file
    return validate_file(path, verbose=False)


if __name__ == "__main__":
    sys.exit(main())
