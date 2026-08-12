#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库每日更新机制（REQ-20260813-001 / T2）
1) 调用 intel_collector 采集当日情报
2) 输出当日知识更新汇总 data/daily-intel/YYYY-MM-DD.md
3) 发现重要新考点时，向对应知识卡【追加】带溯源链接的考点条目（不覆盖原卡、自动去重）

用法：
  python scripts/daily_kb_update.py               # 正常执行（会真实抓取）
  python scripts/daily_kb_update.py --dry-run     # 只汇总不写卡
  python scripts/daily_kb_update.py --date 2026-08-13
"""
import argparse
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intel_collector as ic

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
CARD_ROOT = BASE_DIR / "data" / "knowledge-cards"
OUT_DIR = BASE_DIR / "data" / "daily-intel"

# 重要新考点判定阈值
IMPORTANT_SCORE = 4

# 噪声模式：机构内部动态/宣传类，不进知识卡
NOISE_PATTERNS = ["党支部", "座谈会", "文明", "宣传", "守护成长", "中心组",
                  "主题党日", "召开会议", "工作会议召开", "志愿活动", "运动会"]
# 强考点关键词：命中即视为考点价值高（即使分值略低）
STRONG_KW = ["三支一扶", "政府工作报告", "中央一号文件", "二十届", "中央经济工作会议",
             "乡村振兴", "中国式现代化", "二十大", "习近平", "农业普查",
             "粮食", "耕地", "中原城市群", "黄河", "南水北调", "航空港", "公基"]
# 知识卡追加时允许的旧闻最大天数（RSS 缓存滞后，太旧的不追加）
MAX_AGE_DAYS = 7

# 考点 → 知识卡映射规则：(模块目录, 卡文件名, 匹配关键词)
CARD_RULES = [
    ("时政热点", "2024-2025年重要中央会议与习近平总书记重要讲话精神考点汇编.md",
     ["三支一扶", "政府工作报告", "中央一号文件", "二十届", "中央经济工作会议",
      "全国两会", "两会", "国务院", "中共中央"]),
    ("三农与乡村振兴", "粮食安全·耕地保护·乡村振兴核心政策考点.md",
     ["乡村振兴", "三农", "农业普查", "耕地", "粮食", "农村"]),
    ("中国特色社会主义理论", "习近平新时代中国特色社会主义思想核心考点.md",
     ["习近平", "二十大", "中国式现代化", "新时代"]),
    ("河南省情", "河南省地理·历史·文化·经济核心概况.md",
     ["河南", "中原", "郑州", "洛阳", "开封"]),
]


def match_card(title: str) -> tuple:
    """按关键词返回 (模块目录, 卡文件名)；无匹配返回 None"""
    for mod, fname, kws in CARD_RULES:
        if any(kw in title for kw in kws):
            return mod, fname
    return None


def is_worthy(item: dict) -> bool:
    """判定条目是否值得写入知识卡：高相关分 + 非噪声 + 强考点关键词兜底"""
    t = item["title"]
    if item["score"] >= 8:
        return True
    if any(n in t for n in NOISE_PATTERNS):
        return False
    if item["score"] >= IMPORTANT_SCORE and any(k in t for k in STRONG_KW):
        return True
    return False


def is_recent(item: dict) -> bool:
    """RSS 旧闻过滤：有 pub_date 且超过 MAX_AGE_DAYS 天的不写卡"""
    pd = item.get("pub_date") or ""
    if not pd:
        return True
    try:
        age = (datetime.now(CST) - datetime.strptime(pd, "%Y-%m-%d").replace(tzinfo=CST)).days
        return age <= MAX_AGE_DAYS
    except Exception:
        return True


def card_path(mod: str, fname: str) -> Path:
    return CARD_ROOT / mod / fname


def append_to_card(card: Path, item: dict, date_str: str) -> bool:
    """向知识卡追加新考点（带溯源链接），已存在同链接则跳过。返回是否追加"""
    if not card.exists():
        return False
    content = card.read_text(encoding="utf-8")
    if item["url"] in content:  # 溯源链接去重
        return False
    section = (
        f"\n---\n\n### 📌 每日更新 {date_str}：{item['title']}\n"
        f"- **来源**：{item['url']}\n"
        f"- **摘要**：{item.get('summary', item['title'])[:180]}\n"
        f"- **相关度**：{item['score']}（由 scripts/daily_kb_update.py 自动追加，保留溯源链接）\n"
    )
    with open(card, "a", encoding="utf-8") as f:
        f.write(section)
    return True


def main():
    ap = argparse.ArgumentParser(description="知识库每日更新")
    ap.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--dry-run", action="store_true", help="只生成汇总，不写知识卡")
    ap.add_argument("--min-score", type=int, default=IMPORTANT_SCORE,
                    help="重要考点最低分值（默认4）")
    args = ap.parse_args()

    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    print(f"[daily_kb_update] {date_str} 开始（重要考点阈值 {args.min_score}，dry-run={args.dry_run}）")

    # 1) 采集
    result = ic.collect(min_score=1)  # 采集全部 ≥1 分条目，重要与否由阈值判定
    ic.write_outputs(result, date_str)

    # 2) 重要条目 → 知识卡
    important = [it for it in result["items"] if it["score"] >= args.min_score]
    updates = []  # (模块, 卡名, 追加条数)
    skipped = []  # 高分但被过滤的条目
    for it in important:
        mc = match_card(it["title"])
        if not mc:
            continue
        if not is_worthy(it):
            skipped.append(it)
            continue
        if not is_recent(it):
            skipped.append(it)
            continue
        mod, fname = mc
        if args.dry_run:
            continue
        if append_to_card(card_path(mod, fname), it, date_str):
            updates.append((mod, fname))
            print(f"  📝 追加知识卡: {mod}/{fname} <- {it['title'][:40]}...")
    # 统计去重后的卡更新次数
    from collections import Counter
    upd_counter = Counter(f"{m}/{f}" for m, f in updates)

    # 3) 汇总文件 data/daily-intel/YYYY-MM-DD.md
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md = OUT_DIR / f"{date_str}.md"
    days_left = (ic.EXAM_DATE - datetime.now(CST)).days
    lines = [
        f"# 知识库每日更新汇总 {date_str}",
        "",
        f"- 生成时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 距河南三支一扶重考（2026-08-22）：**{days_left} 天**",
        f"- 数据源健康：{sum(1 for s in result['sources'] if s['ok'])}/{len(result['sources'])}",
        f"- 命中条目：{result['hits']} 条；重要条目（≥{args.min_score}分）：{len(important)} 条",
        "",
        "## 一、今日重要情报（≥{}分）".format(args.min_score),
        "",
    ]
    for it in important:
        lines.append(f"- ⭐{it['score']} [{it['source']}] {it['title']}")
        lines.append(f"  {it['url']}")
    lines += ["", "## 二、知识卡更新记录", ""]
    if upd_counter:
        for k, n in upd_counter.items():
            lines.append(f"- 📝 {k}：追加 {n} 条新考点（保留溯源链接）")
    else:
        lines.append("- 今日无新增重要考点（或全部与既有溯源链接重复，未追加）")
    if skipped:
        lines += ["", "### 高分但未写卡条目（噪声/旧闻/无强考点）", ""]
        for it in skipped:
            lines.append(f"- 跳过：⭐{it['score']} [{it['source']}] {it['title']}（{it.get('pub_date') or '无日期'}）")
    lines += ["", "## 三、数据源状态", ""]
    for s in result["sources"]:
        st = "✅" if s["ok"] else "❌"
        err = f"（{s['error']}）" if s["error"] else ""
        lines.append(f"- {st} {s['name']}：{s['count']} 条{err}")
    lines.append("")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[daily_kb_update] 汇总文件: {md}")
    print(f"[daily_kb_update] 知识卡更新: {dict(upd_counter) if upd_counter else '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
