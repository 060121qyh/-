# -*- coding: utf-8 -*-
"""
scripts/migrate_quiz_five_fields.py — 题库五字段强类型化迁移（Sprint V2 任务3）
把 data/quiz-bank/*.json 中每题 explanation 单字段内嵌的五段式文本，
拆分为五个独立字段写入每题顶层：
  correct_answer / term_breakdown / option_analysis / exam_hint / mnemonic
同时保留原 explanation 字段（内容不动）作兼容。
解析逻辑与 server/api/quiz.py 的 _parse_five_segment_explanation 保持一致。

用法: python scripts/migrate_quiz_five_fields.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUIZ_DIR = ROOT / "data" / "quiz-bank"

FIELDS = ["correct_answer", "term_breakdown", "option_analysis", "exam_hint", "mnemonic"]
MARKERS = {
    "正确答案": "correct_answer",
    "术语拆解": "term_breakdown",
    "选项辨析": "option_analysis",
    "考情提示": "exam_hint",
    "记忆口诀": "mnemonic",
}


def parse_five_segments(explanation_text):
    """与 server/api/quiz.py 运行时解析器相同的拆分逻辑"""
    segments = {f: "" for f in FIELDS}
    if not explanation_text:
        return segments

    lines = explanation_text.strip().split("\n")
    current_segment = None
    segment_content = []

    for line in lines:
        matched = False
        for marker, key in MARKERS.items():
            # 前缀匹配：兼容【术语拆解——逐字解释…】这类变体标题
            if f"【{marker}" in line:
                if current_segment and segment_content:
                    segments[current_segment] = "\n".join(segment_content).strip()
                current_segment = key
                segment_content = [line]
                matched = True
                break
        if not matched and current_segment:
            segment_content.append(line)

    if current_segment and segment_content:
        segments[current_segment] = "\n".join(segment_content).strip()

    # 完全无法解析时，整体放 correct_answer 并在报告中标记
    if not any(v for v in segments.values()):
        segments["correct_answer"] = explanation_text
    return segments


def main():
    total_questions = 0
    problems = []  # (file, idx, 说明)
    migrated_files = []

    for json_file in sorted(QUIZ_DIR.glob("*.json")):
        if json_file.suffix != ".json":
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            questions = json.load(f)

        file_problems = []
        for i, q in enumerate(questions):
            total_questions += 1
            explanation = q.get("explanation", "")
            segs = parse_five_segments(explanation)

            # 迁移写入（不删除原 explanation）
            for field in FIELDS:
                q[field] = segs[field]

            # 记录无法解析出的字段
            if explanation:
                for field in FIELDS:
                    if not segs[field]:
                        file_problems.append((i, q.get("stem", "")[:30], field))
            else:
                file_problems.append((i, q.get("stem", "")[:30], "explanation为空"))

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        migrated_files.append(json_file.name)
        problems.extend((json_file.name, i, stem, field) for i, stem, field in file_problems)

    # ===== 校验 =====
    valid = True
    checked = 0
    for json_file in sorted(QUIZ_DIR.glob("*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            questions = json.load(f)
        for i, q in enumerate(questions):
            checked += 1
            missing = [f for f in FIELDS if f not in q]
            if missing:
                valid = False
                print(f"[FAIL] {json_file.name}#{i} 缺字段: {missing}")

    print(f"[OK] 迁移完成: {len(migrated_files)} 个文件, {total_questions} 题")
    print(f"[CHECK] 校验通过: {checked} 题全部包含五字段键" if valid else "[CHECK] 校验失败")
    print(f"[DETAIL] explanation 字段已保留，内容未改动")
    if problems:
        print(f"[WARN] 无法解析出的字段（已置空）:")
        for file, i, stem, field in problems:
            print(f"  - {file} 第{i}题 [{field}] {stem}...")
    else:
        print("[INFO] 所有题目五字段均解析成功，无空字段")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
