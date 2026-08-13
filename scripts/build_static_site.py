# -*- coding: utf-8 -*-
"""
scripts/build_static_site.py — GitHub Pages 静态站点构建脚本（REQ-20260813-004 任务2）

功能：
1. 按 server/api/knowledge.py 的同款解析逻辑，把 data/knowledge-cards/**/*.md 编译为 JSON
   （卡片列表 / 单卡详情 / 质量评分 / 考点汇总，与 /api/knowledge、/api/quality、
    /api/knowledge/card、/api/summary 返回结构同构）
2. 把 data/quiz-bank/ 的合并题库编译为 JSON（与 /api/quiz/questions 返回结构同构，
   含 question_id 字段，供前端练题与判分使用）
3. 编译 /api/overview 同构数据（倒计时 / 知识卡统计 / 题库统计 / 每日计划列表）
4. 把 static/platform.html 复制为 static-site/index.html，并注入
   <script>window.STATIC_DATA = {...}</script>（API 不可达时前端自动降级读静态数据）
5. 复制静态资源（marked/p5/manifest/service-worker/icons）到 static-site/，写 .nojekyll

零第三方依赖（仅 Python 标准库），本地与 GitHub Actions 均可直接运行。
"""
import json
import re
import shutil
import sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KB_DIR = DATA_DIR / "knowledge-cards"
QUIZ_DIR = DATA_DIR / "quiz-bank"
STATIC_DIR = ROOT / "static"
OUT_DIR = ROOT / "static-site"
OUT_DATA_DIR = OUT_DIR / "data"

GOAL_ID = "henan-szyf-20260822"
EXAM_DATE = "2026-08-22"


# ============================================================
# 知识卡解析（与 server/api/knowledge.py 逻辑保持一致）
# ============================================================
def _list_cards():
    """扫描知识卡目录，返回卡片信息列表（与 knowledge.py _list_cards 同构）"""
    if not KB_DIR.exists():
        return []
    cards = []
    # REQ-20260813-003：按文件 mtime 倒序，最新在前
    for md_file in sorted(KB_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        rel_path = md_file.relative_to(KB_DIR)
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
            "update_time": datetime.fromtimestamp(md_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "preview": preview,
        })
    return cards


def _score_knowledge_card(content):
    """知识卡质量评分（10维度，满分100）——与 knowledge.py _score_knowledge_card 同构"""
    score = 0
    details = []
    dims = {}
    clean_len = len(content.replace('\n', '').replace(' ', ''))
    if clean_len >= 1500:
        score += 10; details.append("字数充足(+10)"); dims["字数"] = 10
    elif clean_len >= 800:
        score += 6; details.append("字数达标(+6)"); dims["字数"] = 6
    else:
        details.append("字数不足(<800)"); dims["字数"] = 0

    h2_count = len(re.findall(r'^## ', content, re.MULTILINE))
    if h2_count >= 6:
        score += 15; details.append(f"知识点丰富({h2_count}节,+15)"); dims["知识点章节"] = 15
    elif h2_count >= 4:
        score += 10; details.append(f"知识点达标({h2_count}节,+10)"); dims["知识点章节"] = 10
    elif h2_count >= 2:
        score += 5; details.append(f"知识点偏少({h2_count}节,+5)"); dims["知识点章节"] = 5
    else:
        details.append("无明显分节结构"); dims["知识点章节"] = 0

    has_table = "|---" in content or "| --" in content
    if has_table:
        score += 15; details.append("含对比表格(+15)"); dims["表格"] = 15
    else:
        details.append("缺少表格"); dims["表格"] = 0

    has_mnemonic = any(w in content for w in ['口诀', '记忆', '速记', '巧记', '顺口溜', '背诵', '记法'])
    if has_mnemonic:
        score += 15; details.append("含记忆口诀(+15)"); dims["口诀"] = 15
    else:
        details.append("缺少记忆口诀"); dims["口诀"] = 0

    has_exam_hint = any(w in content for w in ['考情', '高频', '常考', '必考', '考查方式', '出题角度', '命题'])
    if has_exam_hint:
        score += 10; details.append("含考情分析(+10)"); dims["考情分析"] = 10
    else:
        details.append("缺少考情分析"); dims["考情分析"] = 0

    has_source = any(w in content for w in ['来源：', '出处：', '来源:', '出处:', '可信度'])
    if has_source:
        score += 5; details.append("标注来源(+5)"); dims["来源标注"] = 5
    else:
        dims["来源标注"] = 0

    has_numbered = bool(re.search(r'^\d+[\.\、)]', content, re.MULTILINE))
    has_bullets = bool(re.search(r'^[\-\*] ', content, re.MULTILINE))
    if has_numbered or has_bullets:
        score += 5; details.append("结构化列表(+5)"); dims["结构化"] = 5
    else:
        dims["结构化"] = 0

    has_emphasis = bool(re.search(r'\*\*.*?\*\*', content))
    if has_emphasis:
        score += 5; details.append("重点标记(+5)"); dims["重点标记"] = 5
    else:
        dims["重点标记"] = 0

    has_score_mention = bool(re.search(r'(\d+)\s*分|占\s*(\d+)%|(\d+)%\s*左右', content))
    if has_score_mention:
        score += 10; details.append("分值关联(+10)"); dims["分值关联"] = 10
    else:
        dims["分值关联"] = 0

    has_example = any(w in content for w in ['例题', '真题', '例如', '举例', '示例'])
    if has_example:
        score += 10; details.append("含例题参考(+10)"); dims["例题"] = 10
    else:
        dims["例题"] = 0

    level = "优秀" if score >= 80 else "良好" if score >= 55 else "一般" if score >= 30 else "待完善"
    return {
        "score": score, "level": level, "dimensions": dims, "details": details,
        "max_score": 100, "word_count": clean_len,
    }


# ============================================================
# 题库编译（与 server/api/quiz.py 结构同构）
# ============================================================
def _build_quiz():
    """使用最新合并题库 2026-08-13-merged.json 编译题目列表。
    与 /api/quiz/questions 同构：每道题带 question_id（<文件名stem>-<序号>）。"""
    # 优先取日期最新的 *-merged.json；不存在则回退读取全部 *.json 合并去重
    merged_files = sorted(QUIZ_DIR.glob("*-merged.json"))
    questions = []
    source_file = None
    if merged_files:
        source_file = merged_files[-1]
        with open(source_file, "r", encoding="utf-8") as f:
            questions = json.load(f)
    else:
        source_file = None
        seen = set()
        for jf in sorted(QUIZ_DIR.glob("*.json")):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    qs = json.load(f)
            except Exception:
                continue
            for q in qs:
                key = json.dumps(q, ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    questions.append(q)
        source_file = "ALL"
    for i, q in enumerate(questions):
        q["_id"] = f"{Path(source_file).stem if source_file != 'ALL' else 'merged'}-{i}"
        q["question_id"] = q["_id"]
    return {"total": len(questions), "questions": questions}


# ============================================================
# 总览编译（与 /api/overview 同构）
# ============================================================
def _build_overview(kb_cards, quiz_total):
    try:
        exam_date = datetime.strptime(EXAM_DATE, "%Y-%m-%d").date()
    except ValueError:
        exam_date = date(2026, 8, 22)
    today = (datetime.now(timezone.utc) + timedelta(hours=8)).date()  # 东八区口径
    days_remaining = max(0, (exam_date - today).days)

    kb_modules = {}
    for c in kb_cards:
        kb_modules[c["module"]] = kb_modules.get(c["module"], 0) + 1

    # 掌握度（本机 data/mastery 存在则编译；云端 CI 无此数据 → 空结构优雅降级）
    mastery_data = {}
    mastery_modules = {}
    weak_modules = []
    recommended_focus = ""
    mastery_path = DATA_DIR / "mastery" / "mastery.json"
    if mastery_path.exists():
        try:
            with open(mastery_path, "r", encoding="utf-8") as f:
                mastery_data = json.load(f)
            mastery_modules = mastery_data.get("modules", {})
            weak_modules = mastery_data.get("weak_modules", [])
            recommended_focus = mastery_data.get("recommended_focus", "")
        except Exception:
            pass

    # 每日计划列表
    plan_dir = DATA_DIR / "daily-plan"
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

    return {
        "status": "ok",
        "goal_id": GOAL_ID,
        "exam_date": EXAM_DATE,
        "days_remaining": days_remaining,
        "knowledge_cards": {"total": len(kb_cards), "modules": kb_modules},
        "quiz_bank": {"total_questions": quiz_total},
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
        "modules": sorted(kb_modules.keys()),
    }


# ============================================================
# 主构建流程
# ============================================================
def main():
    print("[1/6] 扫描知识卡 ...")
    cards = _list_cards()
    print(f"      知识卡 {len(cards)} 张，模块 {len(set(c['module'] for c in cards))} 个")

    print("[2/6] 编译单卡详情 + 质量评分 ...")
    cards_detail = {}
    quality_cards = []
    total_score = 0
    for c in cards:
        try:
            with open(KB_DIR / c["path"], "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        quality = _score_knowledge_card(content)
        cards_detail[c["path"]] = {
            "title": c["title"], "module": c["module"], "path": c["path"],
            "content": content, "size": c["size"], "quality": quality,
        }
        quality_cards.append({
            "title": c["title"], "module": c["module"], "path": c["path"],
            "score": quality["score"], "level": quality["level"],
            "dimensions": quality["dimensions"], "details": quality["details"],
            "word_count": quality["word_count"],
        })
        total_score += quality["score"]
    avg = round(total_score / max(len(quality_cards), 1), 1)
    quality = {
        "total_cards": len(quality_cards),
        "average_score": avg,
        "quality_level": "优秀" if avg >= 80 else "良好" if avg >= 55 else "需改进",
        "cards": sorted(quality_cards, key=lambda x: x["score"], reverse=True),
    }

    print("[3/6] 编译考点汇总 (/api/summary 同构) ...")
    summary_cards = []
    for c in cards:
        content = cards_detail.get(c["path"], {}).get("content", "")
        if not content:
            continue
        h2s = re.findall(r'^## (.+)$', content, re.MULTILINE)
        bolds = re.findall(r'\*\*(.+?)\*\*', content)
        key_bolds = [b for b in bolds if 3 < len(b) < 80][:6]
        tables = re.findall(r'^\|(.+)\|$', content, re.MULTILINE)
        summary_cards.append({
            "title": c["title"], "module": c["module"],
            "key_points": h2s[:8], "key_terms": key_bolds[:6],
            "table_count": len([t for t in tables if '---' not in t and t.strip()]) // 3,
        })
    all_modules = list(set(c["module"] for c in summary_cards))
    summary = {
        "total_cards": len(summary_cards),
        "modules_covered": all_modules,
        "total_key_points": sum(len(c["key_points"]) for c in summary_cards),
        "cards": summary_cards,
    }

    print("[4/6] 编译题库 ...")
    quiz = _build_quiz()
    print(f"      题库 {quiz['total']} 题")

    print("[5/6] 编译总览 ...")
    overview = _build_overview(cards, quiz["total"])
    print(f"      距考试 {overview['days_remaining']} 天 · 每日计划 {len(overview['daily_plans'])} 条")

    # ---- 组装 STATIC_DATA（各字段与 API 响应同构）----
    static_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "static",
        "overview": overview,
        "knowledge": {"total": len(cards), "cards": cards},
        "quality": quality,
        "cards": cards_detail,
        "quiz": quiz,
        "summary": summary,
    }

    print("[6/6] 生成 static-site/ ...")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # data/*.json（供 service worker 预缓存；页面本身以内联注入为准，file:// 下也可用）
    with open(OUT_DATA_DIR / "knowledge.json", "w", encoding="utf-8") as f:
        json.dump({"total": len(cards), "cards": cards, "quality": quality,
                   "cards_detail": cards_detail, "summary": summary}, f,
                  ensure_ascii=False, indent=1)
    with open(OUT_DATA_DIR / "quiz.json", "w", encoding="utf-8") as f:
        json.dump(quiz, f, ensure_ascii=False, indent=1)

    # index.html = platform.html 副本 + 注入 STATIC_DATA
    html_src = STATIC_DIR / "platform.html"
    html = html_src.read_text(encoding="utf-8")
    injected = f'<script>window.STATIC_DATA = {json.dumps(static_data, ensure_ascii=False)};</script>'
    marker = "<script>\n// ========================================\n// 赛博导师 · 学案 — 前端逻辑"
    if marker not in html:
        print("ERROR: 未找到注入锚点（platform.html 前端逻辑脚本块），中止")
        sys.exit(2)
    html = html.replace(marker, injected + "\n" + marker, 1)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"      已注入 STATIC_DATA（{len(injected)} 字符）→ static-site/index.html")

    # 复制静态资源
    for name in ["marked.min.js", "p5.min.js", "manifest.json", "service-worker.js"]:
        src = STATIC_DIR / name
        if src.exists():
            shutil.copy2(src, OUT_DIR / name)
            print(f"      复制 {name}")
        else:
            print(f"      [警告] {name} 不存在，跳过")
    icons_src = STATIC_DIR / "icons"
    if icons_src.exists():
        shutil.copytree(icons_src, OUT_DIR / "icons", dirs_exist_ok=True)
        print("      复制 icons/")

    # .nojekyll：GitHub Pages 不做 Jekyll 处理（下划线目录/文件照常发布）
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # 校验
    check = (OUT_DIR / "index.html").read_text(encoding="utf-8")
    ok = "window.STATIC_DATA" in check and check.count("window.STATIC_DATA") >= 1
    print(f"\n构建完成：static-site/ 共 {len(list(OUT_DIR.rglob('*')))} 个文件")
    print(f"STATIC_DATA 注入校验：{'通过' if ok else '失败'}")
    print(f"知识卡 {len(cards)} 张 / 题库 {quiz['total']} 题 / 质量均分 {avg}")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
