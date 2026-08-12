# -*- coding: utf-8 -*-
"""
server/api/plan.py — 每日计划API（Sprint V2 任务6）
基于 mastery.json 的 FSRS due 字段 + data/goals/goal.yaml 生成当日学习计划：
  - 到期复习模块（FSRS due <= 今天，按掌握度升序=弱优先）
  - 新内容建议（state=New 模块，按 goal priority 排序）
  - 时间分配（daily_available_hours，早/中/晚）
  - 考试倒计时

路由:
  GET /api/plan/today           — 生成/返回今日计划
  GET /api/daily-plan?date=xx   — 前端每日计划视图使用的接口（返回数组）
"""
import json
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, jsonify, request, current_app

try:
    import yaml
except ImportError:
    yaml = None

plan_bp = Blueprint("plan", __name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

SHANGHAI_OFFSET = timedelta(hours=8)  # Asia/Shanghai 固定 UTC+8 偏移（Windows 无需 tzdata）


def _today_shanghai():
    """东八区（Asia/Shanghai, UTC+8）当天日期。
    BUG-4 加固：避免 UTC 日期在本地清晨 0-8 点时仍为前一日，导致计划日期/高亮错位。
    """
    return (datetime.now(timezone.utc) + SHANGHAI_OFFSET).date()


def _get_data_dir():
    try:
        return Path(current_app.config.get("DATA_DIR", "data"))
    except Exception:
        return PROJECT_ROOT / "data"


def _get_goal_path():
    return _get_data_dir() / "goals" / "goal.yaml"


def _get_plan_dir():
    return _get_data_dir() / "daily-plan"


def _get_mastery_path():
    return _get_data_dir() / "mastery" / "mastery.json"


def _load_goal():
    path = _get_goal_path()
    if not path.exists() or yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _load_mastery():
    path = _get_mastery_path()
    if not path.exists():
        return {"modules": {}, "weak_modules": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"modules": {}, "weak_modules": []}


def _parse_due_date(due_str):
    """解析 FSRS due 字段为 date；失败返回 None"""
    if not due_str:
        return None
    try:
        return datetime.fromisoformat(due_str).date()
    except (ValueError, TypeError):
        return None


def build_plan(plan_date_str=None):
    """生成某日学习计划 dict；plan_date_str 缺省用服务器当天日期"""
    plan_date = date.fromisoformat(plan_date_str) if plan_date_str else date.today()
    goal = _load_goal()
    mastery = _load_mastery()
    modules = mastery.get("modules", {})
    weak_modules = mastery.get("weak_modules", [])

    exam_date_str = goal.get("exam_date", "2026-08-22")
    try:
        exam_date = date.fromisoformat(exam_date_str)
    except (ValueError, TypeError):
        exam_date = date(2026, 8, 22)
    days_left = max(0, (exam_date - plan_date).days)

    priority = goal.get("priority", [])
    hours = goal.get("daily_available_hours", 3)

    # 1) 到期复习：FSRS due <= 今天 或 弱项模块
    due_reviews = []
    # 2) 新内容建议：state=New 未开始模块
    new_modules = []
    for name, m in modules.items():
        fsrs = m.get("fsrs") or {}
        state = fsrs.get("state", "New")
        due = _parse_due_date(fsrs.get("due"))
        if state == "New":
            new_modules.append(name)
        elif due is not None and due <= plan_date:
            due_reviews.append({
                "module": name,
                "mastery": m.get("mastery", 0),
                "correct_rate": m.get("correct_rate", 0),
                "total": m.get("total", 0),
                "weak": m.get("weak", False),
                "due": fsrs.get("due"),
                "reps": fsrs.get("reps", 0),
            })

    # 复习排序：掌握度升序（弱优先），weak 标记再优先
    due_reviews.sort(key=lambda r: (0 if r["weak"] else 1, r["mastery"]))
    # 新内容按 goal priority 顺序
    prio_index = {p: i for i, p in enumerate(priority)}
    new_modules.sort(key=lambda n: prio_index.get(n, 999))

    # 时间分配（小时）
    review_hours = 0
    new_hours = 0
    if hours > 0:
        if due_reviews:
            review_hours = round(min(1.5, hours * 0.5), 1)
        remaining = max(0, hours - review_hours)
        new_hours = round(remaining, 1)
        if not due_reviews:
            new_hours = hours

    # 标题与正文（Markdown）
    title = f"{plan_date.isoformat()} 学习计划（距考试 {days_left} 天）"
    lines = [f"# {plan_date.isoformat()} 学习计划", ""]
    lines.append(f"> 距 2026-08-22 三支一扶重考还有 **{days_left} 天** · 今日可用 **{hours} 小时**")
    lines.append("")

    lines.append("## 一、到期复习（FSRS 排程）")
    if due_reviews:
        for r in due_reviews:
            weak_tag = "（弱项）" if r["weak"] else ""
            lines.append(
                f"- **{r['module']}**{weak_tag}：掌握度 {r['mastery']}%，"
                f"累计练习 {r['total']} 题，正确率 {round(r['correct_rate']*100)}%，"
                f"FSRS 复习 {r['reps']} 次"
            )
        lines.append(f"- 建议时长：约 {review_hours} 小时（先易后难，薄弱模块优先）")
    else:
        lines.append("- 今日无到期复习模块 ✅")
    lines.append("")

    lines.append("## 二、新内容建议")
    if new_modules:
        for i, n in enumerate(new_modules[:5], 1):
            lines.append(f"- {i}. **{n}**")
        if len(new_modules) > 5:
            lines.append(f"- …（其余 {len(new_modules)-5} 个模块可自行安排）")
        lines.append(f"- 建议时长：约 {new_hours} 小时（优先 priority 列表中的模块）")
    else:
        lines.append("- 全部模块均已进入复习阶段 🎉")
    lines.append("")

    lines.append("## 三、今日时间分配")
    slots = [("早", "07:00-08:00"), ("中", "12:30-13:30"), ("晚", "20:00-21:30")]
    for label, time_range in slots:
        lines.append(f"- {label}（{time_range}）：约 1 小时")
    lines.append("")

    lines.append("## 四、今日目标")
    lines.append("- [ ] 完成到期复习模块的错题回顾（每题看五段式解析）")
    lines.append("- [ ] 学习 1 个新模块知识卡，并完成 5 道对应练习")
    lines.append("- [ ] 睡前用记忆口诀快速过一遍今日考点")
    lines.append("")

    content = "\n".join(lines)

    return {
        "date": plan_date.isoformat(),
        "title": title,
        "content": content,
        "summary": {
            "days_left": days_left,
            "available_hours": hours,
            "due_review_count": len(due_reviews),
            "due_review_modules": [r["module"] for r in due_reviews],
            "new_module_count": len(new_modules),
            "new_modules": new_modules[:5],
            "weak_modules": weak_modules,
        },
    }


def _load_plan_file(plan_date_str):
    """读取 data/daily-plan/<date>.json，不存在返回 None"""
    path = _get_plan_dir() / f"{plan_date_str}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_plan_file(plan):
    """写入 data/daily-plan/<date>.json"""
    plan_dir = _get_plan_dir()
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = plan_dir / f"{plan['date']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return path


@plan_bp.route("/api/plan/today", methods=["GET"])
def plan_today():
    """GET /api/plan/today — 生成并返回今日计划（同时落盘 data/daily-plan/）"""
    try:
        today_str = _today_shanghai().isoformat()  # BUG-4：东八区当天日期
        plan = _load_plan_file(today_str)
        if plan is None:
            plan = build_plan(today_str)
            _save_plan_file(plan)
        return jsonify({"status": "ok", "plan": plan})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@plan_bp.route("/api/daily-plan", methods=["GET"])
def daily_plan_list():
    """GET /api/daily-plan?date=YYYY-MM-DD — 前端每日计划视图接口。
    有 date 参数：返回 [ {date,title,content} ]（不存在则即时生成并落盘）；
    无 date 参数：返回所有已生成计划的 [ {date,title} ] 列表。
    """
    try:
        date_str = request.args.get("date", "").strip()
        plan_dir = _get_plan_dir()
        if date_str:
            plan = _load_plan_file(date_str)
            if plan is None:
                plan = build_plan(date_str)
                _save_plan_file(plan)
            return jsonify([plan])
        # 列表模式
        plans = []
        if plan_dir.exists():
            for pf in sorted(plan_dir.glob("*.json")):
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        p = json.load(f)
                    plans.append({"date": p.get("date", pf.stem), "title": p.get("title", "")})
                except Exception:
                    continue
        return jsonify(plans)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
