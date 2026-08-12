"""
server/api/overview.py — 总览API
提供考试倒计时、模块统计等总览信息。
"""
import json
from pathlib import Path
from datetime import datetime, date
from flask import Blueprint, jsonify, current_app

overview_bp = Blueprint("overview", __name__)


def _get_data_dir():
    return Path(current_app.config.get("DATA_DIR", "data"))


@overview_bp.route("/api/overview", methods=["GET"])
def get_overview():
    """GET /api/overview — 总览信息"""
    try:
        exam_date_str = current_app.config.get("EXAM_DATE", "2026-08-22")
        try:
            exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
        except ValueError:
            exam_date = date(2026, 8, 22)

        today = date.today()
        days_remaining = (exam_date - today).days

        # 统计知识卡
        kb_dir = _get_data_dir() / "knowledge-cards"
        kb_count = 0
        kb_modules = {}
        if kb_dir.exists():
            for md_file in kb_dir.rglob("*.md"):
                kb_count += 1
                rel = md_file.relative_to(kb_dir)
                module = str(rel.parent) if str(rel.parent) != "." else "未分类"
                kb_modules[module] = kb_modules.get(module, 0) + 1

        # 统计题库
        quiz_dir = _get_data_dir() / "quiz-bank"
        quiz_count = 0
        if quiz_dir.exists():
            for json_file in quiz_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        questions = json.load(f)
                    quiz_count += len(questions)
                except Exception:
                    pass

        # 掌握度概览
        mastery_path = _get_data_dir() / "mastery" / "mastery.json"
        mastery_data = {}
        mastery_modules = {}
        weak_modules = []
        recommended_focus = ""
        if mastery_path.exists():
            try:
                with open(mastery_path, "r", encoding="utf-8") as f:
                    mastery_data = json.load(f)
                mastery_modules = mastery_data.get("modules", {})
                weak_modules = mastery_data.get("weak_modules", [])
                recommended_focus = mastery_data.get("recommended_focus", "")
            except Exception:
                pass

        # 每日计划列表（前端每日计划视图时间轴数据源）
        plan_dir = _get_data_dir() / "daily-plan"
        daily_plans = []
        if plan_dir.exists():
            for pf in sorted(plan_dir.glob("*.json")):
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        p = json.load(f)
                    daily_plans.append({
                        "date": p.get("date", pf.stem),
                        "title": p.get("title", ""),
                    })
                except Exception:
                    continue

        return jsonify({
            "status": "ok",
            "goal_id": current_app.config.get("GOAL_ID", "henan-szyf-20260822"),
            "exam_date": exam_date_str,
            "days_remaining": max(0, days_remaining),
            "knowledge_cards": {
                "total": kb_count,
                "modules": kb_modules,
            },
            "quiz_bank": {
                "total_questions": quiz_count,
            },
            "mastery": {
                "modules": mastery_modules,
                "weak_modules": weak_modules,
                "recommended_focus": recommended_focus,
            },
            "mastery_summary": {
                "total_modules": len(mastery_modules),
                "weak_modules": len(weak_modules),
                "recommended_focus": recommended_focus,
            },
            "daily_plans": daily_plans,
            "modules": current_app.config.get("MODULES", []),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
