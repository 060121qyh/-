#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-20260813-001（TA-001）: 修复老库第10/15题五段式字段缺陷
对应 KM-ISSUE-2026-02 / KM-ISSUE-2026-03（KM-001 审核报告 1.2 节）

修复内容：
  第10题「2025年经济工作九项任务之首」：补写【选项辨析】段 + 同步更新 explanation
  第15题「乡村振兴措施逐项判断」（不定项）：correct_answer 精简为【正确答案】ABC；
        term_breakdown 补术语拆解；option_analysis 移入原逐项排查内容；同步重拼 explanation

用法：python scripts/fix_quiz_20260813.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "data/quiz-bank/2026-08-12-001.json"

# 复用 expand_quiz_bank.py 的五段式校验函数
sys.path.insert(0, str(ROOT / "scripts"))
from expand_quiz_bank import validate_file  # noqa: E402

# ============ 第10题：补写【选项辨析】段 ============
Q10_OPTION_ANALYSIS = """【选项辨析】
• A（❌）："以科技创新引领新质生产力发展"位列2025年经济工作九项重点任务第②项。发展新质生产力虽属重要任务，但并非"之首"。
• B（❌）："有效防范化解重点领域风险"排在九项任务第⑤位——2024年12月中央经济工作会议将风险防范置于第⑤项，体现2025年更侧重"发展"而非"防风险"，不居首位。
• C（✅）："大力提振消费、提高投资效益，全方位扩大国内需求"正是2024年12月中央经济工作会议确定的2025年经济工作九项重点任务之首。内需=消费+投资，2025年头号任务即"大力提振消费"。
• D（❌）："统筹推进新型城镇化和乡村全面振兴"是九项任务第⑥项，不居首位。"""

# 第10题 explanation 插入点：九项任务排序段结束（"⑨ 加大保障和改善民生力度"）之后、【考情提示】之前
Q10_EXP_ANCHOR = "⑨ 加大保障和改善民生力度"


# ============ 第15题：拆分重构 ============
Q15_TERM_BREAKDOWN = """【术语拆解】
• 「"公司+合作社+农户"利益联结机制」：2025年中央一号文件强调的"联农带农机制"典型形式——龙头企业负责加工、销售，合作社居中组织，农户负责种养，三方按约定分享产业链增值收益，是"着力壮大县域富民产业"的重要抓手。
• 「农村人居环境整治提升行动」：一号文件"着力推进乡村建设"部署的重要内容，核心包括厕所革命、生活污水和垃圾治理、村容村貌提升等，本题措施②（厕所革命+污水处理）即属此类。
• 「防止返贫动态监测机制」：对脱贫不稳定户、边缘易致贫户等做到"早发现、早干预、早帮扶"，守住"不发生规模性返贫致贫"底线（"两条底线"之一）。
• 「耕地"非农化"与"非粮化"」：耕地保护红线要求——坚决遏制耕地"非农化"（改变耕地用途搞非农建设，如违规建高尔夫球场）、防止"非粮化"（种树挖塘等改变种粮用途），18亿亩耕地红线不可触碰。
【题型说明】不定项选择题=可能只有1个正确，也可能有多个正确。三支一扶2025年新增题型，多选/少选/错选均不得分，难度最大！"""

Q15_OPTION_ANALYSIS = """【选项辨析】（逐项排查）
• A（✅正确）："公司+合作社+农户"模式是2025年一号文件强调的"联农带农机制"的典型形式。龙头企业负责加工和销售，合作社居中协调，农户负责种植养殖→三方分享产业链增值收益。
• B（✅正确）：厕所革命、污水处理是"农村人居环境整治提升行动"的核心内容。注意"厕所革命"是习近平总书记亲自推动的民生工程。
• C（✅正确）："早发现、早干预、早帮扶"的"三早"机制是一号文件中防止返贫动态监测的具体要求。
• D（❌错误→关键陷阱）：①一号文件反复强调"坚决遏制耕地'非农化'、防止'非粮化'"，建设高尔夫球场是典型的"非农化"，属于严重违法违规行为。②耕地保护的红线是18亿亩，任何占用耕地的非农建设都要严格审批。③"盘活"是指提高土地利用效率，不是改变耕地用途。
• E（❌错误）："两条底线"仅指粮食安全+不发生规模性返贫致贫。措施①属于产业发展范畴，虽然有助于农民增收，但不是"两条底线"的直接体现。措施③对应的是第二条底线。但E选项说的是"措施①③均体现了"——由于措施①不能体现，所以E是错的。这里考察的是对"两条底线"具体范围的精确理解。"""


def fix_q10(q):
    """第10题：补写 option_analysis，并在 explanation 中【完整九项任务排序】后插入【选项辨析】段"""
    assert "九项重点任务之首" in q["stem"], "定位第10题失败"
    assert not q["option_analysis"].strip(), "第10题 option_analysis 应为空（修复前状态校验）"
    assert "【选项辨析】" not in q["explanation"], "第10题 explanation 不应已有【选项辨析】段"

    q["option_analysis"] = Q10_OPTION_ANALYSIS

    # 在 explanation 的九项任务排序段末尾（⑨...）之后插入【选项辨析】
    assert Q10_EXP_ANCHOR in q["explanation"], "第10题 explanation 缺少插入锚点"
    q["explanation"] = q["explanation"].replace(
        Q10_EXP_ANCHOR, Q10_EXP_ANCHOR + "\n\n" + Q10_OPTION_ANALYSIS, 1
    )


def fix_q15(q):
    """第15题：correct_answer 精简为【正确答案】ABC；term_breakdown/option_analysis 补全；重拼 explanation"""
    assert "乡村振兴" in q["stem"] and "高尔夫球场" in q["stem"], "定位第15题失败"
    assert "【逐项排查】" in q["correct_answer"], "第15题 correct_answer 应含错位的【逐项排查】内容"

    q["correct_answer"] = "【正确答案】ABC"
    q["term_breakdown"] = Q15_TERM_BREAKDOWN
    q["option_analysis"] = Q15_OPTION_ANALYSIS

    # explanation 重拼：五段式顺序 = 正确答案 + 术语拆解 + 选项辨析 + 考情提示 + 记忆口诀
    exp = (
        q["correct_answer"]
        + "\n\n" + q["term_breakdown"]
        + "\n\n" + q["option_analysis"]
        + "\n\n" + q["exam_hint"]
        + "\n\n" + q["mnemonic"]
    )
    q["explanation"] = exp


def main():
    # 1) 备份
    bak = BANK.with_suffix(".json.fixbak")
    shutil.copy2(BANK, bak)
    print(f"✅ 备份已生成: {bak}")

    # 2) 加载并修复
    with open(BANK, encoding="utf-8") as f:
        qs = json.load(f)
    assert isinstance(qs, list) and len(qs) == 15, f"老库应为15题，实际 {len(qs)}"

    fix_q10(qs[9])
    fix_q15(qs[14])

    # 3) 写回
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(qs, f, ensure_ascii=False, indent=2)
    print(f"✅ 修复完成并写回: {BANK}")

    # 4) 用 expand_quiz_bank 五段式校验函数验证老库
    ok, errors, n, dist = validate_file(BANK, verbose=False)
    if not ok:
        print("❌ 修复后老库校验未通过：")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"✅ 修复后老库五段式校验通过（{n} 题）")

    # 5) 打印两题修复后关键字段摘要
    for idx in (9, 14):
        q = qs[idx]
        fields = {
            "correct_answer": q["correct_answer"],
            "term_breakdown": q["term_breakdown"],
            "option_analysis": q["option_analysis"],
            "exam_hint": q["exam_hint"],
            "mnemonic": q["mnemonic"],
        }
        print(f"\n--- 第{idx + 1}题（{q['stem'][:20]}...）修复后摘要 ---")
        for k, v in fields.items():
            print(f"  {k}: 非空={'是' if v.strip() else '否'}，长度={len(v.strip())}，前30字={v.strip()[:30]!r}")


if __name__ == "__main__":
    main()
