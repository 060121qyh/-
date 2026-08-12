#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题库扩充脚本 — 支持按模块增量新增题目 + 五段式字段完整性校验 + 去重
用途：河南三支一扶公基备考题库管理（REQ-20260813-001 / T1）

用法：
  # 1) 仅校验新增题库文件（五段式完整性 + 格式）
  python scripts/expand_quiz_bank.py --validate data/quiz-bank/2026-08-13-001.json

  # 2) 增量合并：把新题并入现有题库（按题干去重），输出合并后文件
  python scripts/expand_quiz_bank.py --merge \
      --bank data/quiz-bank/2026-08-12-001.json \
      --new  data/quiz-bank/2026-08-13-001.json \
      --out  data/quiz-bank/2026-08-13-merged.json

  # 3) 只打印统计
  python scripts/expand_quiz_bank.py --stats data/quiz-bank/2026-08-12-001.json
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 12 个必填字段（与现有题库完全一致）
REQUIRED_FIELDS = [
    "type", "module", "difficulty", "stem", "options", "answer",
    "explanation", "correct_answer", "term_breakdown",
    "option_analysis", "exam_hint", "mnemonic",
]
# 五段式解析字段（质量门槛：全部非空）
FIVE_SECTION_FIELDS = [
    "correct_answer", "term_breakdown", "option_analysis", "exam_hint", "mnemonic",
]
# 合法题型
VALID_TYPES = {"单选题", "多选题", "不定项选择题"}
# 合法模块（以平台 12 模块为准，含知识卡目录名）
VALID_MODULES = {
    "时政热点", "中国特色社会主义理论", "马克思主义哲学", "毛泽东思想",
    "中共党史", "三农与乡村振兴", "法律", "经济常识", "地理科技",
    "历史人文", "公文写作", "河南省情",
}


def normalize_stem(stem: str) -> str:
    """题干归一化：去空白/标点，用于去重比对"""
    return re.sub(r"[\s，。、（）()“”\"\'：:？?！!·—…]", "", stem)


def validate_question(q, idx: int, errors: list) -> None:
    """校验单题：字段完整性 + 五段式非空 + 格式合法"""
    loc = f"第{idx + 1}题"
    if not isinstance(q, dict):
        errors.append(f"{loc}: 不是 JSON 对象")
        return
    for f in REQUIRED_FIELDS:
        if f not in q:
            errors.append(f"{loc}: 缺少字段 [{f}]")
            continue
        v = q[f]
        if v is None or (isinstance(v, str) and not v.strip()):
            errors.append(f"{loc}: 字段 [{f}] 为空")
    # 五段式字段必须为有效文本（非空 + 含对应标记；correct_answer 短格式为正常）
    # 口径对齐 KM-001 审核报告 1.1 节：correct_answer 短（7-14字符，如【正确答案】C）为正常格式；
    # 其余四字段（术语拆解/选项辨析/考情提示/记忆口诀）内容较长，要求长度≥8 防占位符。
    opts = q.get("options") if isinstance(q.get("options"), dict) else {}
    for f in FIVE_SECTION_FIELDS:
        v = q.get(f, "")
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{loc}: 五段式字段 [{f}] 为空")
            continue
        if f == "correct_answer":
            # 须含「正确答案」标记与至少一个答案字母（如【正确答案】C / 【正确答案】ABD）
            if "【正确答案】" not in v or not any(c in v for c in opts):
                errors.append(f"{loc}: 五段式字段 [correct_answer] 须含「正确答案」标记与答案字母")
        elif len(v.strip()) < 8:
            errors.append(f"{loc}: 五段式字段 [{f}] 内容过短/无效")
    # type
    if q.get("type") not in VALID_TYPES:
        errors.append(f"{loc}: type [{q.get('type')}] 非法，应为 {sorted(VALID_TYPES)}")
    # module
    if q.get("module") not in VALID_MODULES:
        errors.append(f"{loc}: module [{q.get('module')}] 不在平台模块清单内")
    # difficulty
    d = q.get("difficulty")
    if not isinstance(d, int) or not (1 <= d <= 5):
        errors.append(f"{loc}: difficulty [{d}] 非法，应为 1–5 整数")
    # options：字典且 ≥2 项，answer 必须是其中一个键
    opts = q.get("options")
    if not isinstance(opts, dict) or len(opts) < 2:
        errors.append(f"{loc}: options 必须为 ≥2 项的字典")
    else:
        for k, v in opts.items():
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{loc}: 选项 {k} 内容为空")
        ans = q.get("answer")
        if q.get("type") in ("多选题", "不定项选择题"):
            # 多选答案：由 2 个及以上选项键组成的字符串（如 "ABC"）
            if not (isinstance(ans, str) and len(ans) >= 2
                    and all(c in opts for c in ans) and len(set(ans)) == len(ans)):
                errors.append(f"{loc}: 多选答案 [{ans}] 需为 2 个及以上不重复选项键（如 \"ABC\"）")
        elif ans not in opts:
            errors.append(f"{loc}: answer [{ans}] 不在选项键 {list(opts.keys())} 中")
        if isinstance(ans, str) and ans:
            for c in ans:
                if c in opts and (not isinstance(opts[c], str) or not opts[c].strip()):
                    errors.append(f"{loc}: 正确答案 {c} 内容为空")
    # explanation 应包含五段式各段标题（前缀匹配：兼容「【术语拆解——逐字解释…】」类带修饰语标题）
    exp = q.get("explanation", "")
    exp_lines = [ln.strip() for ln in exp.splitlines()] if exp else []
    for tag in ["【正确答案】", "【术语拆解】", "【选项辨析】", "【考情提示】", "【记忆口诀】"]:
        tag_core = tag[:-1]  # 去掉右括号】，如「【术语拆解」
        if not any(ln.startswith(tag_core) for ln in exp_lines):
            errors.append(f"{loc}: explanation 缺少段标题 [{tag}]")


def load_questions(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):  # 兼容 {questions:[...]} 包装
        data = data.get("questions", [])
    if not isinstance(data, list):
        raise ValueError(f"{path}: 顶层必须是数组（或 {questions:[]} 包装）")
    return data


def validate_file(path: Path, verbose: bool = True) -> tuple:
    """校验整个题库文件，返回 (通过?, 错误列表, 题数, 模块分布)"""
    qs = load_questions(path)
    errors = []
    for i, q in enumerate(qs):
        validate_question(q, i, errors)
    dist = Counter(q.get("module", "(无模块)") for q in qs)
    if verbose:
        print(f"文件: {path}")
        print(f"总题数: {len(qs)}")
        print(f"模块分布: {dict(dist)}")
        if errors:
            print(f"❌ 校验失败，共 {len(errors)} 处问题：")
            for e in errors:
                print("  -", e)
        else:
            print("✅ 五段式字段完整性校验通过")
    return (not errors, errors, len(qs), dist)


def merge_banks(bank_qs: list, new_qs: list) -> tuple:
    """合并题库（按归一化题干去重，新题优先保留），返回 (合并结果, 新增数, 重复数)"""
    seen = {normalize_stem(q["stem"]) for q in bank_qs}
    merged = list(bank_qs)
    added = 0
    dup = 0
    for q in new_qs:
        key = normalize_stem(q["stem"])
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        merged.append(q)
        added += 1
    return merged, added, dup


def main():
    ap = argparse.ArgumentParser(description="题库扩充与校验")
    ap.add_argument("--validate", type=Path, help="仅校验指定题库 JSON")
    ap.add_argument("--stats", type=Path, help="打印题库统计")
    ap.add_argument("--merge", action="store_true", help="增量合并模式")
    ap.add_argument("--bank", type=Path, help="现有题库文件（合并基底）")
    ap.add_argument("--new", type=Path, help="新增题目文件")
    ap.add_argument("--out", type=Path, help="合并输出文件")
    args = ap.parse_args()

    if args.validate:
        ok, errors, n, dist = validate_file(args.validate)
        sys.exit(0 if ok else 1)

    if args.stats:
        validate_file(args.stats)
        sys.exit(0)

    if args.merge:
        if not (args.bank and args.new and args.out):
            ap.error("--merge 需要 --bank --new --out")
        # 先校验新题文件
        ok, errors, n, dist = validate_file(args.new, verbose=True)
        if not ok:
            print("❌ 新题文件未通过校验，拒绝合并")
            sys.exit(1)
        bank_qs = load_questions(args.bank)
        new_qs = load_questions(args.new)
        merged, added, dup = merge_banks(bank_qs, new_qs)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"✅ 合并完成: 基底 {len(bank_qs)} 题 + 新增 {added} 题（去重跳过 {dup}）")
        print(f"   输出: {args.out}（共 {len(merged)} 题）")
        ok2, errs2, n2, dist2 = validate_file(args.out, verbose=True)
        sys.exit(0 if ok2 else 1)

    ap.print_help()


if __name__ == "__main__":
    main()
