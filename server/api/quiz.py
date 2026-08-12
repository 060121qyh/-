"""
server/api/quiz.py — 题库API
提供题库概要、题目列表、练题提交、自动判分、五段式解析、错题追踪。
"""
import json
import random
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

quiz_bp = Blueprint("quiz", __name__)


def _get_data_dir():
    return Path(current_app.config.get("DATA_DIR", "data"))


def _get_quiz_dir():
    return _get_data_dir() / "quiz-bank"


def _get_progress_dir():
    return _get_data_dir() / "progress"


def _get_wrong_path():
    return _get_progress_dir() / "wrong-questions.json"


def _get_wrong_dir():
    """错题目录：data/wrong-questions/"""
    return _get_data_dir() / "wrong-questions"


def _save_wrong_question_file(question_id, record, wrong_count=None):
    """将错题单独写入 data/wrong-questions/<question_id>.json

    BUG-3 修复：wrong_count 以调用方传入的累计口径为准（与 wrong-questions.json 列表
    的累计值一致），不再被单次 record（wrong_count 恒为 1）update 覆盖后自增，
    避免独立文件与列表接口两处计数双口径漂移（历史 bug：文件恒为 2、列表持续累加）。
    """
    wrong_dir = _get_wrong_dir()
    wrong_dir.mkdir(parents=True, exist_ok=True)
    file_path = wrong_dir / f"{question_id}.json"
    existing = {}
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    record = {k: v for k, v in record.items() if k != "wrong_count"}
    existing.update(record)
    existing["wrong_count"] = wrong_count if wrong_count is not None else existing.get("wrong_count", 0) + 1
    existing["last_wrong"] = datetime.now().isoformat()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _get_answer_records_path():
    return _get_progress_dir() / "answer-records.json"


def _load_all_questions():
    """加载题库中所有题目"""
    quiz_dir = _get_quiz_dir()
    if not quiz_dir.exists():
        return []

    all_questions = []
    for json_file in sorted(quiz_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                questions = json.load(f)
            for i, q in enumerate(questions):
                q["_source"] = json_file.name
                q["_id"] = f"{json_file.stem}-{i}"
            all_questions.extend(questions)
        except Exception:
            continue

    return all_questions


def _load_wrong_questions():
    """加载错题记录"""
    path = _get_wrong_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_wrong_questions(data):
    """保存错题记录"""
    path = _get_wrong_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_answer_records():
    """加载答题记录"""
    path = _get_answer_records_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_answer_records(data):
    """保存答题记录"""
    path = _get_answer_records_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_five_segment_explanation(explanation_text):
    """将五段式解析解析为结构化JSON"""
    if not explanation_text:
        return {"raw": explanation_text}

    segments = {
        "correct_answer": "",
        "term_breakdown": "",
        "option_analysis": "",
        "exam_hint": "",
        "mnemonic": "",
    }

    # 按段落标记拆分
    lines = explanation_text.strip().split('\n')

    current_segment = None
    segment_content = []

    segment_markers = {
        "正确答案": "correct_answer",
        "术语拆解": "term_breakdown",
        "选项辨析": "option_analysis",
        "考情提示": "exam_hint",
        "记忆口诀": "mnemonic",
    }

    for line in lines:
        matched = False
        for marker, key in segment_markers.items():
            # 前缀匹配：兼容【术语拆解——逐字解释…】这类变体标题
            if f"【{marker}" in line:
                if current_segment and segment_content:
                    segments[current_segment] = '\n'.join(segment_content).strip()
                current_segment = key
                segment_content = [line]
                matched = True
                break
        if not matched and current_segment:
            segment_content.append(line)

    if current_segment and segment_content:
        segments[current_segment] = '\n'.join(segment_content).strip()

    # 如果没有解析到结构化内容，返回原文
    if not any(v for v in segments.values()):
        segments["correct_answer"] = explanation_text

    return {"structured": segments}


# ============ API Routes ============

@quiz_bp.route("/api/quiz", methods=["GET"])
def quiz_summary():
    """GET /api/quiz — 题库概要"""
    try:
        quiz_dir = _get_quiz_dir()
        if not quiz_dir.exists():
            return jsonify({"total": 0, "quizzes": []})

        quizzes = []
        total_questions = 0
        for json_file in sorted(quiz_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    questions = json.load(f)
            except Exception:
                questions = []

            total_questions += len(questions)

            modules = {}
            types = {}
            for q in questions:
                m = q.get("module", "未知")
                t = q.get("type", "未知")
                modules[m] = modules.get(m, 0) + 1
                types[t] = types.get(t, 0) + 1

            quizzes.append({
                "file": json_file.name,
                "question_count": len(questions),
                "modules": modules,
                "types": types,
            })

        return jsonify({
            "total": total_questions,
            "quizzes": quizzes,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quiz_bp.route("/api/quiz/questions", methods=["GET"])
def list_questions():
    """GET /api/quiz/questions — 获取题目，支持筛选"""
    try:
        all_questions = _load_all_questions()

        module_filter = request.args.get("module", "").strip()
        type_filter = request.args.get("type", "").strip()
        difficulty_str = request.args.get("difficulty", "").strip()
        mode = request.args.get("mode", "all").strip()
        count_str = request.args.get("count", "").strip()

        filtered = all_questions

        if module_filter:
            filtered = [q for q in filtered if q.get("module", "") == module_filter]

        if type_filter:
            filtered = [q for q in filtered if q.get("type", "") == type_filter]

        if difficulty_str:
            try:
                diff = int(difficulty_str)
                filtered = [q for q in filtered if q.get("difficulty", 0) >= diff]
            except ValueError:
                pass

        # 模式处理
        if mode == "wrong":
            wrong_qs = _load_wrong_questions()
            wrong_ids = {w["question_id"] for w in wrong_qs if not w.get("retry_correct", False)}
            filtered = [q for q in filtered if q.get("_id", "") in wrong_ids]

        elif mode == "random":
            random.shuffle(filtered)

        elif mode == "weak":
            # 薄弱模块优先：通过mastery数据判断
            mastery_path = _get_data_dir() / "mastery" / "mastery.json"
            weak_modules = []
            if mastery_path.exists():
                try:
                    with open(mastery_path, "r", encoding="utf-8") as f:
                        mastery = json.load(f)
                    weak_modules = mastery.get("weak_modules", [])
                except Exception:
                    pass
            if weak_modules:
                weak_qs = [q for q in filtered if q.get("module", "") in weak_modules]
                other_qs = [q for q in filtered if q.get("module", "") not in weak_modules]
                filtered = weak_qs + other_qs

        # 数量限制
        if count_str:
            try:
                count = int(count_str)
                filtered = filtered[:count]
            except ValueError:
                pass

        # 移除内部字段（BUG-2 修复：保留 question_id 供前端提交闭环使用）
        result = []
        for q in filtered:
            q_copy = {k: v for k, v in q.items() if not k.startswith("_")}
            q_copy["question_id"] = q.get("_id", "")
            result.append(q_copy)

        return jsonify({
            "total": len(result),
            "questions": result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quiz_bp.route("/api/quiz/submit", methods=["POST"])
def submit_answer():
    """POST /api/quiz/submit — 提交答案，自动判分，返回五段式解析

    请求体: {
        "question_id": "xxx",
        "user_answer": "B",
        "module": "时政热点"  // 可选，用于掌握度更新
    }
    """
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "请求体为空"}), 400

        question_id = body.get("question_id", "").strip()
        user_answer = (body.get("user_answer", "") or body.get("answer", "")).strip().upper()
        module_name = body.get("module", "").strip()

        if not question_id or not user_answer:
            return jsonify({"error": "缺少 question_id 或 user_answer"}), 400

        # 查找题目
        all_questions = _load_all_questions()
        question = None
        for q in all_questions:
            if q.get("_id") == question_id:
                question = q
                break

        if not question:
            return jsonify({"error": "题目不存在"}), 404

        correct_answer = question.get("answer", "").strip().upper()
        is_correct = (user_answer == correct_answer)

        # 记录答题
        record = {
            "question_id": question_id,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "module": question.get("module", module_name),
            "type": question.get("type", ""),
            "timestamp": datetime.now().isoformat(),
        }

        records = _load_answer_records()
        records.append(record)
        _save_answer_records(records)

        # 错题记录
        if not is_correct:
            wrongs = _load_wrong_questions()
            # 检查是否已存在
            existing = [w for w in wrongs if w["question_id"] == question_id]
            wrong_record = {
                "question_id": question_id,
                "module": question.get("module", ""),
                "type": question.get("type", ""),
                "stem": question.get("stem", "")[:100],
                "wrong_count": 1,
                "last_wrong": datetime.now().isoformat(),
                "retry_correct": False,
            }
            if not existing:
                wrongs.append(wrong_record.copy())
                total_wrong_count = 1
            else:
                # BUG-3 修复：以列表累计值为唯一口径，两处落库使用同一数值
                existing[0]["wrong_count"] = existing[0].get("wrong_count", 0) + 1
                existing[0]["last_wrong"] = datetime.now().isoformat()
                total_wrong_count = existing[0]["wrong_count"]
            _save_wrong_questions(wrongs)
            # 同时写入 data/wrong-questions/<question_id>.json（累计口径与列表一致）
            _save_wrong_question_file(question_id, wrong_record, wrong_count=total_wrong_count)

        # 五段式解析
        explanation = question.get("explanation", "")
        structured_explanation = _parse_five_segment_explanation(explanation)

        # 尝试更新掌握度
        mastery_updated = False
        if module_name or question.get("module"):
            mod = module_name or question.get("module")
            try:
                mastery_path = _get_data_dir() / "mastery" / "mastery.json"
                if mastery_path.exists():
                    with open(mastery_path, "r", encoding="utf-8") as f:
                        mastery_data = json.load(f)
                    modules = mastery_data.get("modules", {})
                    if mod in modules:
                        prev_mastery = modules[mod]["mastery"]
                        modules[mod]["total"] = modules[mod]["total"] + 1
                        prev_correct = modules[mod]["correct_rate"] * (modules[mod]["total"] - 1)
                        new_correct_total = prev_correct + (1 if is_correct else 0)
                        modules[mod]["correct_rate"] = round(new_correct_total / modules[mod]["total"], 4)
                        modules[mod]["mastery"] = min(100, round(modules[mod]["correct_rate"] * 100))
                        modules[mod]["weak"] = modules[mod]["mastery"] < 40 or modules[mod]["correct_rate"] < 0.5
                        if modules[mod]["mastery"] > prev_mastery:
                            modules[mod]["trend"] = "up"
                        elif modules[mod]["mastery"] < prev_mastery:
                            modules[mod]["trend"] = "down"
                        mastery_data["weak_modules"] = [m for m, v in modules.items() if v["weak"]]
                        with open(mastery_path, "w", encoding="utf-8") as f:
                            json.dump(mastery_data, f, ensure_ascii=False, indent=2)
                        mastery_updated = True
            except Exception:
                pass

        return jsonify({
            "is_correct": is_correct,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "explanation": structured_explanation,
            "raw_explanation": explanation,
            "record": record,
            "mastery_updated": mastery_updated,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quiz_bp.route("/api/quiz/wrong", methods=["GET"])
def list_wrong_questions():
    """GET /api/quiz/wrong — 获取错题列表"""
    try:
        module_filter = request.args.get("module", "").strip()
        wrongs = _load_wrong_questions()

        if module_filter:
            wrongs = [w for w in wrongs if w.get("module", "") == module_filter]

        return jsonify({
            "total": len(wrongs),
            "wrong_questions": wrongs,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quiz_bp.route("/api/quiz/wrong", methods=["POST"])
def record_wrong_answer():
    """POST /api/quiz/wrong — 手动记录/更新错题"""
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "请求体为空"}), 400

        question_id = body.get("question_id", "").strip()
        retry_correct = body.get("retry_correct", None)

        wrongs = _load_wrong_questions()
        found = None
        for w in wrongs:
            if w["question_id"] == question_id:
                found = w
                break

        if retry_correct is not None and found:
            found["retry_correct"] = retry_correct
            if retry_correct:
                found["retry_date"] = datetime.now().isoformat()
            _save_wrong_questions(wrongs)
            return jsonify({"status": "updated", "question_id": question_id, "retry_correct": retry_correct})

        if not found:
            return jsonify({"status": "not_found", "question_id": question_id}), 404

        return jsonify({"status": "no_change", "question_id": question_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quiz_bp.route("/api/quiz/stats", methods=["GET"])
def answer_stats():
    """GET /api/quiz/stats — 答题统计"""
    try:
        records = _load_answer_records()
        total = len(records)
        correct = sum(1 for r in records if r.get("is_correct"))
        rate = round(correct / max(total, 1), 4)

        by_module = {}
        for r in records:
            mod = r.get("module", "未知")
            if mod not in by_module:
                by_module[mod] = {"total": 0, "correct": 0}
            by_module[mod]["total"] += 1
            if r.get("is_correct"):
                by_module[mod]["correct"] += 1

        for mod in by_module:
            by_module[mod]["rate"] = round(
                by_module[mod]["correct"] / max(by_module[mod]["total"], 1), 4
            )

        wrongs = _load_wrong_questions()
        active_wrongs = [w for w in wrongs if not w.get("retry_correct")]

        return jsonify({
            "total": total,
            "correct": correct,
            "rate": rate,
            "by_module": by_module,
            "wrong_count": len(wrongs),
            "active_wrong_count": len(active_wrongs),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
