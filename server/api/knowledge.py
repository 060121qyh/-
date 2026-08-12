"""
server/api/knowledge.py — 知识卡API
提供知识卡列表、单卡详情、跨卡汇总和质量评分功能。
"""
import os
import json
import re
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app

knowledge_bp = Blueprint("knowledge", __name__)


def _get_data_dir():
    return Path(current_app.config.get("DATA_DIR", "data"))


def _get_knowledge_cards_dir():
    return _get_data_dir() / "knowledge-cards"


def _list_cards():
    """扫描知识卡目录，返回所有知识卡信息列表"""
    kb_dir = _get_knowledge_cards_dir()
    if not kb_dir.exists():
        return []

    cards = []
    for md_file in sorted(kb_dir.rglob("*.md")):
        rel_path = md_file.relative_to(kb_dir)
        module = str(rel_path.parent) if str(rel_path.parent) != "." else "未分类"
        title = rel_path.stem

        preview = ""
        size = md_file.stat().st_size
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            preview_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("# ") or not stripped:
                    continue
                preview_lines.append(stripped)
                if len("".join(preview_lines)) > 200:
                    break
            preview = " ".join(preview_lines)[:200]
        except Exception:
            preview = ""

        cards.append({
            "title": title,
            "module": module,
            "path": str(rel_path).replace("\\", "/"),
            "size": size,
            "preview": preview,
        })

    return cards


def _score_knowledge_card(content):
    """知识卡质量评分（10维度，满分100）—— 评分引擎"""
    score = 0
    details = []
    dims = {}

    # 1. 字数检查（≥800字 = 10分）
    clean_len = len(content.replace('\n', '').replace(' ', ''))
    if clean_len >= 1500:
        score += 10
        details.append("字数充足(+10)")
        dims["字数"] = 10
    elif clean_len >= 800:
        score += 6
        details.append("字数达标(+6)")
        dims["字数"] = 6
    else:
        details.append("字数不足(<800)")
        dims["字数"] = 0

    # 2. 知识点章节数（≥4 = 15分）
    h2_count = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2_count >= 6:
        score += 15
        details.append(f"知识点丰富({h2_count}节,+15)")
        dims["知识点章节"] = 15
    elif h2_count >= 4:
        score += 10
        details.append(f"知识点达标({h2_count}节,+10)")
        dims["知识点章节"] = 10
    elif h2_count >= 2:
        score += 5
        details.append(f"知识点偏少({h2_count}节,+5)")
        dims["知识点章节"] = 5
    else:
        details.append("无明显分节结构")
        dims["知识点章节"] = 0

    # 3. 表格（有 = 15分）
    has_table = "|---" in content or "| --" in content
    if has_table:
        score += 15
        details.append("含对比表格(+15)")
        dims["表格"] = 15
    else:
        details.append("缺少表格")
        dims["表格"] = 0

    # 4. 记忆口诀（有 = 15分）
    has_mnemonic = any(w in content for w in ['口诀', '记忆', '速记', '巧记', '顺口溜', '背诵', '记法'])
    if has_mnemonic:
        score += 15
        details.append("含记忆口诀(+15)")
        dims["口诀"] = 15
    else:
        details.append("缺少记忆口诀")
        dims["口诀"] = 0

    # 5. 考情分析（有 = 10分）
    has_exam_hint = any(w in content for w in ['考情', '高频', '常考', '必考', '考查方式', '出题角度', '命题'])
    if has_exam_hint:
        score += 10
        details.append("含考情分析(+10)")
        dims["考情分析"] = 10
    else:
        details.append("缺少考情分析")
        dims["考情分析"] = 0

    # 6. 来源标注（有 = 5分）
    has_source = any(w in content for w in ['来源：', '出处：', '来源:', '出处:', '可信度'])
    if has_source:
        score += 5
        details.append("标注来源(+5)")
        dims["来源标注"] = 5
    else:
        dims["来源标注"] = 0

    # 7. 结构完整性（序号/列表 = 5分）
    has_numbered = bool(re.search(r'^\d+[\.\、)]', content, re.MULTILINE))
    has_bullets = bool(re.search(r'^[\-\*] ', content, re.MULTILINE))
    if has_numbered or has_bullets:
        score += 5
        details.append("结构化列表(+5)")
        dims["结构化"] = 5
    else:
        dims["结构化"] = 0

    # 8. 重点标记（加粗 = 5分）
    has_emphasis = bool(re.search(r'\*\*.*?\*\*', content))
    if has_emphasis:
        score += 5
        details.append("重点标记(+5)")
        dims["重点标记"] = 5
    else:
        dims["重点标记"] = 0

    # 9. 考试分值关联（10分）
    has_score_mention = bool(re.search(r'(\d+)\s*分|占\s*(\d+)%|(\d+)%\s*左右', content))
    if has_score_mention:
        score += 10
        details.append("分值关联(+10)")
        dims["分值关联"] = 10
    else:
        dims["分值关联"] = 0

    # 10. 例题/真题引用（10分）
    has_example = any(w in content for w in ['例题', '真题', '例如', '举例', '示例'])
    if has_example:
        score += 10
        details.append("含例题参考(+10)")
        dims["例题"] = 10
    else:
        dims["例题"] = 0

    level = "优秀" if score >= 80 else "良好" if score >= 55 else "一般" if score >= 30 else "待完善"
    return {
        "score": score,
        "level": level,
        "dimensions": dims,
        "details": details,
        "max_score": 100,
        "word_count": clean_len
    }


# ============ API Routes ============

@knowledge_bp.route("/api/knowledge", methods=["GET"])
def list_knowledge():
    """GET /api/knowledge — 列出所有知识卡"""
    try:
        module_filter = request.args.get("module", "").strip()
        cards = _list_cards()

        if module_filter:
            cards = [c for c in cards if c["module"] == module_filter]

        return jsonify({
            "total": len(cards),
            "cards": cards,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/api/knowledge/card", methods=["GET"])
def get_card_detail():
    """GET /api/knowledge/card?path=xxx — 获取单张知识卡详情"""
    try:
        card_path = request.args.get("path", "").strip()
        if not card_path:
            return jsonify({"error": "缺少 path 参数"}), 400

        kb_dir = _get_knowledge_cards_dir()
        full_path = kb_dir / card_path

        full_path = full_path.resolve()
        kb_dir_resolved = kb_dir.resolve()
        if not str(full_path).startswith(str(kb_dir_resolved)):
            return jsonify({"error": "非法的路径"}), 403

        if not full_path.exists() or not full_path.is_file():
            return jsonify({"error": "知识卡不存在"}), 404

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        rel_path = full_path.relative_to(kb_dir_resolved)
        module = str(rel_path.parent) if str(rel_path.parent) != "." else "未分类"

        # 附带质量评分
        quality = _score_knowledge_card(content)

        return jsonify({
            "title": rel_path.stem,
            "module": module,
            "path": str(rel_path).replace("\\", "/"),
            "content": content,
            "size": full_path.stat().st_size,
            "quality": quality,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/api/quality", methods=["GET"])
def quality_report():
    """GET /api/quality — 知识卡质量评分报告
    可选 ?path=xxx 或 ?card=xxx 查询单卡评分
    """
    try:
        card_filter = request.args.get("path", "").strip() or request.args.get("card", "").strip()

        if card_filter:
            # 单卡查询
            kb_dir = _get_knowledge_cards_dir()
            full_path = kb_dir / card_filter
            if not full_path.exists():
                return jsonify({"error": "知识卡不存在"}), 404
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            quality = _score_knowledge_card(content)
            return jsonify({
                "card": card_filter,
                **quality
            })

        # 全量报告
        cards = _list_cards()
        scored = []
        total_score = 0
        for card in cards:
            kb_dir = _get_knowledge_cards_dir()
            full_path = kb_dir / card["path"]
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                quality = _score_knowledge_card(content)
                scored.append({
                    "title": card["title"],
                    "module": card["module"],
                    "path": card["path"],
                    "score": quality["score"],
                    "level": quality["level"],
                    "dimensions": quality["dimensions"],
                    "details": quality["details"],
                    "word_count": quality["word_count"],
                })
                total_score += quality["score"]
            except Exception:
                scored.append({
                    "title": card["title"],
                    "module": card["module"],
                    "path": card["path"],
                    "score": 0,
                    "level": "待完善",
                    "dimensions": {},
                    "details": ["读取失败"],
                    "word_count": 0,
                })

        avg = round(total_score / max(len(scored), 1), 1)
        return jsonify({
            "total_cards": len(scored),
            "average_score": avg,
            "quality_level": "优秀" if avg >= 80 else "良好" if avg >= 55 else "需改进",
            "cards": sorted(scored, key=lambda x: x["score"], reverse=True),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/api/summary", methods=["GET"])
def knowledge_summary():
    """GET /api/summary — 跨卡知识汇总"""
    try:
        cards = _list_cards()
        summary = []
        kb_dir = _get_knowledge_cards_dir()
        for card in cards:
            full_path = kb_dir / card["path"]
            if not full_path.exists():
                continue
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            h2s = re.findall(r'^## (.+)$', content, re.MULTILINE)
            bolds = re.findall(r'\*\*(.+?)\*\*', content)
            key_bolds = [b for b in bolds if 3 < len(b) < 80][:6]
            tables = re.findall(r'^\|(.+)\|$', content, re.MULTILINE)

            summary.append({
                "title": card["title"],
                "module": card["module"],
                "key_points": h2s[:8],
                "key_terms": key_bolds[:6],
                "table_count": len([t for t in tables if '---' not in t and t.strip()]) // 3,
            })

        all_modules = list(set(c["module"] for c in summary))
        return jsonify({
            "total_cards": len(summary),
            "modules_covered": all_modules,
            "total_key_points": sum(len(c["key_points"]) for c in summary),
            "cards": summary,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
