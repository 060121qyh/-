#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个性化实时情报采集器（REQ-20260813-001 / T3）
抓取与用户（河南三支一扶 2026-08-22 重考备考者）强相关的信息：
  - 河南三支一扶招募动态、考试公告（河南省人事考试网 hnrsks.com）
  - 公基考纲相关时政（新华网/人民网时政 RSS）
  - 河南本地动态（河南省人民政府网 henan.gov.cn）

输出：
  - data/daily-intel/intel-YYYY-MM-DD.json   结构化情报
  - data/daily-intel/intel-YYYY-MM-DD.md     可读摘要

用法：
  python scripts/intel_collector.py            # 抓取当天
  python scripts/intel_collector.py --date 2026-08-13
  python scripts/intel_collector.py --min-score 2   # 提高相关性门槛
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "daily-intel"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TIMEOUT = 12

# 考试日期（河南三支一扶重考）
EXAM_DATE = datetime(2026, 8, 22, tzinfo=CST)

# ---------- 用户强相关关键词（命中即计分） ----------
KEYWORDS = {
    "三支一扶": 5, "支农": 4, "支教": 4, "支医": 4, "帮扶乡村振兴": 4,
    "重考": 4, "补考": 4, "笔试": 3, "面试": 3, "资格复审": 3, "体检": 3,
    "河南": 3, "河南省": 3, "公基": 3, "公共基础知识": 3,
    "公告": 2, "通知": 2, "报名": 2, "准考证": 3, "成绩": 2, "公示": 2,
    "时政": 2, "政府工作报告": 2, "中央一号文件": 3, "二十届": 2,
    "事业单位": 2, "公务员": 1, "招聘": 1, "录用": 2, "遴选": 1,
    "乡村振兴": 2, "基层": 1, "大学生": 1,
}

# ---------- 数据源配置 ----------
SOURCES = [
    {
        "name": "河南省人事考试网-首页",
        "kind": "html",
        "url": "http://www.hnrsks.com/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,100})</a>',
        "note": "河南省人事考试网首页（含\"三支一扶\"招募公告 zngg 栏目）",
    },
    {
        "name": "新华网-时政",
        "kind": "rss",
        "url": "http://www.news.cn/politics/news_politics.xml",
        "note": "新华网时政频道 RSS",
    },
    {
        "name": "人民网-时政",
        "kind": "rss",
        "url": "http://www.people.com.cn/rss/politics.xml",
        "note": "人民网时政频道 RSS（正版地址 www.people.com.cn/rss/）",
    },
    {
        "name": "中国政府网-要闻",
        "kind": "html",
        "url": "https://www.gov.cn/yaowen/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>',
        "note": "中国政府网要闻（JS 动态页，可能抓取失败，优雅降级）",
    },
    {
        "name": "河南省人民政府网-要闻",
        "kind": "html",
        "url": "https://www.henan.gov.cn/",
        "link_re": r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>',
        "note": "河南省政府网首页要闻（有反爬 403 可能，优雅降级）",
    },
]


def _get(url: str, tries: int = 2):
    """带重试的 GET"""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def score_title(title: str) -> int:
    """按关键词对标题/摘要打分，返回相关度分值"""
    s = 0
    for kw, w in KEYWORDS.items():
        if kw in title:
            s += w
    return s


def clean_text(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t).strip()


def fetch_html_links(source: dict) -> list:
    """抓 HTML 列表页，正则提取 (url, title)，返回得分条目"""
    resp = _get(source["url"])
    resp.encoding = resp.apparent_encoding or "utf-8"
    items = []
    for m in re.finditer(source.get("link_re", ""), resp.text):
        href, title = m.group(1), clean_text(m.group(2))
        if not href.startswith("http"):
            href = urljoin(source["url"], href)
        if not title:
            continue
        items.append({"url": href, "title": title})
    return items


def fetch_rss(source: dict) -> list:
    """抓 RSS/Atom 源，返回 (url, title, summary) 条目"""
    if not HAS_FEEDPARSER:
        raise RuntimeError("feedparser 未安装：pip install feedparser")
    resp = _get(source["url"])
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries[:40]:
        title = clean_text(getattr(e, "title", ""))
        link = getattr(e, "link", "")
        summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", ""))
        pub = ""
        for attr in ("published_parsed", "updated_parsed"):
            pp = getattr(e, attr, None)
            if pp:
                try:
                    pub = datetime(*pp[:6]).astimezone(CST).strftime("%Y-%m-%d")
                    break
                except Exception:
                    pass
        if title:
            items.append({"url": link, "title": title, "summary": summary[:200],
                          "pub_date": pub})
    return items


def collect(min_score: int = 2) -> dict:
    """抓取全部数据源，过滤并评分，返回结构化结果"""
    result = {"generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
              "exam_date": "2026-08-22",
              "days_left": (EXAM_DATE - datetime.now(CST)).days,
              "sources": [], "items": []}
    for src in SOURCES:
        entry = {"name": src["name"], "url": src["url"], "ok": False, "error": None, "count": 0}
        try:
            if src["kind"] == "rss":
                raw = fetch_rss(src)
            else:
                raw = fetch_html_links(src)
            scored = []
            for it in raw:
                s = score_title(it["title"] + " " + it.get("summary", ""))
                if s >= min_score:
                    scored.append({**it, "score": s, "source": src["name"]})
            scored.sort(key=lambda x: x["score"], reverse=True)
            entry["ok"] = True
            entry["count"] = len(scored)
            result["items"].extend(scored)
            print(f"  ✅ {src['name']}: 抓取 {len(raw)} 条，命中 {len(scored)} 条")
        except Exception as e:  # 单源失败不影响整体
            entry["error"] = f"{type(e).__name__}: {e}"
            print(f"  ⚠️  {src['name']}: 失败 - {entry['error']}")
        result["sources"].append(entry)
        time.sleep(0.5)
    # 去重（按 url；同源同标题只保留一条）
    seen_url, seen_title = set(), set()
    uniq = []
    for it in result["items"]:
        tk = (it["source"], it["title"][:40])
        if it["url"] in seen_url or tk in seen_title:
            continue
        seen_url.add(it["url"])
        seen_title.add(tk)
        uniq.append(it)
    result["items"] = uniq
    result["hits"] = len(uniq)
    result["top_keywords"] = _top_keywords(uniq)
    return result


def _top_keywords(items: list, n: int = 8) -> list:
    c = Counter()
    for it in items:
        text = it["title"] + " " + it.get("summary", "")
        for kw, w in KEYWORDS.items():
            if kw in text:
                c[kw] += w
    return [k for k, _ in c.most_common(n)]


def write_outputs(result: dict, date_str: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = OUT_DIR / f"intel-{date_str}.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    mp = OUT_DIR / f"intel-{date_str}.md"
    lines = [
        f"# 每日情报汇总 {date_str}",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 距河南三支一扶重考（2026-08-22）：**{result['days_left']} 天**",
        f"- 数据源健康：{sum(1 for s in result['sources'] if s['ok'])}/{len(result['sources'])} 可用",
        f"- 命中条目：{result['hits']} 条",
        f"- 高频关键词：{'、'.join(result['top_keywords'])}",
        "",
        "## 数据源状态",
        "",
    ]
    for s in result["sources"]:
        status = "✅" if s["ok"] else "❌"
        err = f"（{s['error']}）" if s["error"] else ""
        lines.append(f"- {status} {s['name']}：{s['count']} 条{err}")
    lines += ["", "## 命中条目", ""]
    for it in result["items"]:
        lines.append(f"- ⭐{it['score']} [{it['source']}] {it['title']}")
        lines.append(f"  {it['url']}")
        if it.get("summary"):
            lines.append(f"  {it['summary'][:150]}")
    lines.append("")
    with open(mp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"json": str(jp), "md": str(mp)}


def main():
    ap = argparse.ArgumentParser(description="个性化实时情报采集")
    ap.add_argument("--date", default=None, help="输出日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--min-score", type=int, default=2, help="相关性最低分值（默认2）")
    args = ap.parse_args()
    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    print(f"[intel_collector] 开始抓取 {date_str}（最低相关分 {args.min_score}）...")
    result = collect(min_score=args.min_score)
    paths = write_outputs(result, date_str)
    print(f"[intel_collector] 完成：命中 {result['hits']} 条")
    print(f"  JSON: {paths['json']}")
    print(f"  MD:   {paths['md']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
