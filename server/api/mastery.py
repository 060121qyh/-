"""
server/api/mastery.py — 掌握度API
读写掌握度数据，支持更新。兼容 FSRS 排程字段（Sprint V2 任务4）。
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app

mastery_bp = Blueprint("mastery", __name__)


def _get_data_dir():
    return Path(current_app.config.get("DATA_DIR", "data"))


def _get_mastery_path():
    return _get_data_dir() / "mastery" / "mastery.json"


def _fsrs_defaults(state="New"):
    """FSRS 排程字段默认值（与 fsrs 库 Card 结构对齐）"""
    return {
        "state": state,
        "due": None,
        "stability": None,
        "difficulty": None,
        "last_review": None,
        "reps": 0,
        "step": 0,
    }


def _review_fsrs(module_fsrs, correct, now=None):
    """用 fsrs 库对模块级卡片做一次复习调度，返回更新后的 fsrs 字段。
    复习正确 Rating.Good，错误 Rating.Again；首次复习用新卡初始化。
    """
    try:
        from fsrs import Card, Scheduler, Rating, State
    except ImportError:
        return _fallback_fsrs(module_fsrs, correct, now)

    now = now or datetime.now(timezone.utc)
    d = module_fsrs or {}
    try:
        if d.get("reps", 0) > 0 and d.get("due"):
            st = getattr(State, d.get("state", "Review"), State.Review)
            card = Card(
                state=st,
                step=d.get("step", 0),
                stability=d.get("stability"),
                difficulty=d.get("difficulty"),
                due=datetime.fromisoformat(d["due"]),
                last_review=(
                    datetime.fromisoformat(d["last_review"])
                    if d.get("last_review") else None
                ),
            )
        else:
            card = Card()  # 新卡，首次复习
        rating = Rating.Good if correct else Rating.Again
        new_card, _ = Scheduler().review_card(card, rating, now)
        return {
            "state": new_card.state.name,
            "due": new_card.due.isoformat(),
            "stability": new_card.stability,
            "difficulty": new_card.difficulty,
            "last_review": (
                new_card.last_review.isoformat() if new_card.last_review else None
            ),
            "reps": d.get("reps", 0) + 1,
            "step": new_card.step,
        }
    except Exception:
        return _fallback_fsrs(d, correct, now)


def _fallback_fsrs(module_fsrs, correct, now=None):
    """fsrs 库异常时降级为简单间隔排程（幂等，不抛错）"""
    now = now or datetime.now(timezone.utc)
    d = module_fsrs or {}
    reps = d.get("reps", 0) + 1
    interval_days = 1 if reps <= 1 else min(30, 2 ** (reps - 1))
    return {
        "state": "Review",
        "due": (now + timedelta(days=interval_days)).isoformat(),
        "stability": d.get("stability") or 1.0,
        "difficulty": d.get("difficulty") or 5.0,
        "last_review": now.isoformat(),
        "reps": reps,
        "step": 0,
    }


def _load_mastery():
    """加载掌握度数据"""
    path = _get_mastery_path()
    if not path.exists():
        return _default_mastery()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_mastery()


def _default_mastery():
    """返回默认的12模块掌握度（全0）"""
    modules = current_app.config.get("MODULES", [])
    data = {
        "updated": "2026-08-12",
        "modules": {},
        "weak_modules": [],
        "recommended_focus": "时政热点（核心模块，占分最高）",
    }
    for m in modules:
        data["modules"][m] = {
            "mastery": 0,
            "trend": "flat",
            "total": 0,
            "correct_rate": 0,
            "weak": False,
            "fsrs": _fsrs_defaults("New"),
        }
    return data


def _save_mastery(data):
    """保存掌握度数据"""
    path = _get_mastery_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@mastery_bp.route("/api/mastery", methods=["GET"])
def get_mastery():
    """GET /api/mastery — 获取全量掌握度"""
    try:
        data = _load_mastery()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@mastery_bp.route("/api/mastery/update", methods=["POST"])
def update_mastery():
    """POST /api/mastery/update — 提交答题结果，更新掌握度"""
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "请求体为空"}), 400

        module = body.get("module", "").strip()
        correct = body.get("correct", None)

        if not module:
            return jsonify({"error": "缺少 module 参数"}), 400
        if correct is None:
            return jsonify({"error": "缺少 correct 参数"}), 400

        data = _load_mastery()
        modules = data.get("modules", {})

        if module not in modules:
            modules[module] = {
                "mastery": 0,
                "trend": "flat",
                "total": 0,
                "correct_rate": 0,
                "weak": False,
                "fsrs": _fsrs_defaults("New"),
            }
        elif "fsrs" not in modules[module]:
            # 兼容旧数据：补充 FSRS 字段
            modules[module]["fsrs"] = _fsrs_defaults(
                "Review" if modules[module].get("total", 0) > 0 else "New"
            )

        prev_mastery = modules[module]["mastery"]

        # 更新统计
        modules[module]["total"] = modules[module]["total"] + 1
        prev_correct = modules[module]["correct_rate"] * (modules[module]["total"] - 1)
        new_correct_total = prev_correct + (1 if correct else 0)
        modules[module]["correct_rate"] = round(
            new_correct_total / modules[module]["total"], 4
        )
        modules[module]["mastery"] = min(
            100, round(modules[module]["correct_rate"] * 100)
        )
        modules[module]["weak"] = (
            modules[module]["mastery"] < 40 or modules[module]["correct_rate"] < 0.5
        )

        # 趋势判断
        if modules[module]["mastery"] > prev_mastery:
            modules[module]["trend"] = "up"
        elif modules[module]["mastery"] < prev_mastery:
            modules[module]["trend"] = "down"
        else:
            modules[module]["trend"] = "flat"

        # 更新弱模块列表
        data["weak_modules"] = [
            m for m, v in modules.items() if v["weak"]
        ]
        data["updated"] = datetime.now().strftime("%Y-%m-%d")

        # FSRS 排程：根据本次答题结果推进模块级卡片
        modules[module]["fsrs"] = _review_fsrs(modules[module].get("fsrs"), bool(correct))

        _save_mastery(data)

        return jsonify({
            "status": "updated",
            "module": module,
            "mastery": modules[module],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
