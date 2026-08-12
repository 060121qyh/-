#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端飞书情报推送脚本（REQ-20260813-001 / T4）
供 GitHub Actions 定时任务使用：把当日情报摘要推送到飞书群。

与本地 server/api/push.py 的区别：
  - 本脚本自包含：只从环境变量读取 FEISHU_APP_ID / FEISHU_APP_SECRET /
    FEISHU_CHAT_ID（为空时回退 FEISHU_HOME_CHANNEL），不依赖 .env 文件、
    Flask、本地路径；
  - 推送内容 = 当日情报摘要的「距考天数 + 关键动态 + 与我相关 + 建议动作」
    友好格式，不整篇堆原文；
  - 云端仓库没有知识卡/题库数据（.gitignore 已排除相关目录），本脚本只读取
    data/daily-intel/ 下由 intel_collector.py 生成的当日情报文件。

用法：
  python scripts/push_intel.py                # 推送当天情报
  python scripts/push_intel.py --date 2026-08-13
  python scripts/push_intel.py --dry-run      # 只打印将发送的内容，不调用飞书 API

退出码：
  0  推送成功；或当日无情报文件（打印「无当日情报，跳过推送」）
  1  飞书密钥缺失（FEISHU_APP_ID / FEISHU_APP_SECRET / 聊天 ID 未配置）
  2  网络/API 调用失败（自动重试 1 次后仍失败；
     workflow 中该步骤已设 continue-on-error: true）
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent.parent
INTEL_DIR = BASE_DIR / "data" / "daily-intel"

# 河南三支一扶重考日期
EXAM_DATE = datetime(2026, 8, 22, tzinfo=CST)

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
TIMEOUT = 15


def get_credentials():
    """只从环境变量读取飞书凭证（绝不读 .env 文件）"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    chat_id = (os.environ.get("FEISHU_CHAT_ID", "").strip()
               or os.environ.get("FEISHU_HOME_CHANNEL", "").strip())
    return app_id, app_secret, chat_id


def load_intel(date_str):
    """读取当日情报：md 必读（消息正文素材），json 可选（结构化数据优先）"""
    md_path = INTEL_DIR / f"intel-{date_str}.md"
    json_path = INTEL_DIR / f"intel-{date_str}.json"
    if not md_path.exists():
        return None, None, None
    md_text = md_path.read_text(encoding="utf-8")
    data = None
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ 情报 JSON 解析失败（回退 md 解析）：{e}")
            data = None
    return md_text, data, md_path


def parse_items_from_md(md_text):
    """从 md 摘要中解析命中条目：`- ⭐N [来源] 标题` + 下一行 URL"""
    items = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^-\s*⭐(\d+)\s*\[([^\]]+)\]\s*(.+)$", lines[i].strip())
        if m:
            item = {"score": int(m.group(1)), "source": m.group(2).strip(),
                    "title": m.group(3).strip(), "url": ""}
            if i + 1 < len(lines) and re.match(r"^\s*https?://", lines[i + 1].strip()):
                item["url"] = lines[i + 1].strip()
            items.append(item)
            i += 2
        else:
            i += 1
    return items


def classify(item):
    """把情报条目归入用户关心的类别，用于「与我相关」部分"""
    t = item.get("title", "")
    if any(k in t for k in ("三支一扶", "支农", "支教", "支医", "招募", "报名",
                            "准考证", "重考", "补考", "笔试")):
        return "招考"
    if "河南" in t:
        return "河南"
    if any(k in t for k in ("乡村振兴", "农业", "农村", "一号文件", "粮食",
                            "耕地", "三农")):
        return "三农"
    if any(k in t for k in ("习近平", "二十届", "全会", "政府工作报告", "时政")):
        return "时政"
    return "其他"


def build_message(date_str, md_text, data):
    """把情报整理成「距考天数 + 关键动态 + 与我相关 + 建议动作」友好消息"""
    # ---- 结构化数据优先，md 兜底 ----
    days_left = None
    items = []
    src_ok = src_total = None
    if data:
        days_left = data.get("days_left")
        items = data.get("items", [])
        srcs = data.get("sources", [])
        if srcs:
            src_ok = sum(1 for s in srcs if s.get("ok"))
            src_total = len(srcs)
    if not items:
        items = parse_items_from_md(md_text)
    if days_left is None:
        m = re.search(r"距河南三支一扶重考（2026-08-22）：\*\*(\d+)\s*天\*\*", md_text)
        days_left = int(m.group(1)) if m else (EXAM_DATE - datetime.now(CST)).days
    if src_ok is None:
        m = re.search(r"数据源健康：(\d+)/(\d+)", md_text)
        if m:
            src_ok, src_total = int(m.group(1)), int(m.group(2))

    # ---- 消息标题 ----
    title = f"📰 备考情报速递 · {date_str[5:].replace('-', '/')} · 距考 {days_left} 天"

    # ---- 1) 距考天数 ----
    text = f"**⏰ 距河南三支一扶重考（2026-08-22）：{days_left} 天**\n\n---\n\n"

    # ---- 2) 今日关键动态（按相关分取前 6 条，不堆原文） ----
    text += "### 📋 今日关键动态\n\n"
    top = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:6]
    if top:
        for it in top:
            line = f"- ⭐{it['score']} [{it.get('source', '')[:6]}] "
            if it.get("url"):
                line += f"[{it['title'][:38]}]({it['url']})"
            else:
                line += it["title"][:38]
            text += line + "\n"
    else:
        text += "- 今日暂无高相关条目，建议关注河南省人事考试网最新公告。\n"
    text += "\n---\n\n"

    # ---- 3) 与我相关（按类别挑最高分条目，各取 1 条） ----
    text += "### 🎯 与我相关\n\n"
    by_cat = {}
    for it in items:
        c = classify(it)
        if c not in by_cat or it.get("score", 0) > by_cat[c].get("score", 0):
            by_cat[c] = it
    cat_names = {"招考": "招考动态", "河南": "河南本地", "三农": "三农政策",
                 "时政": "时政要点"}
    shown = 0
    for c in ("招考", "河南", "三农", "时政"):
        it = by_cat.get(c)
        if not it:
            continue
        name = cat_names.get(c, c)
        if it.get("url"):
            text += f"• **{name}**：[{it['title'][:34]}]({it['url']})\n"
        else:
            text += f"• **{name}**：{it['title'][:34]}\n"
        shown += 1
    if shown == 0:
        text += "• 今日暂无与你强相关的条目，保持常规复习节奏即可。\n"
    text += "\n---\n\n"

    # ---- 4) 建议动作（按距考天数分档） ----
    text += "### ✅ 建议动作\n\n"
    if days_left is None:
        text += "1. 浏览河南省人事考试网最新公告，确认重考安排。\n"
        text += "2. 完成当日时政选择题与错题复盘。\n"
    elif days_left >= 10:
        text += "1. 按模块系统复习：时政热点 + 法律 + 马哲。\n"
        text += "2. 每日完成 10-15 道选择题，错题进错题本。\n"
    elif days_left >= 5:
        text += "1. **专项突破**：时政热点（二十大/二十届三中全会/一号文件）+ 河南考情。\n"
        text += "2. 复盘错题本，重点攻克反复出错的模块。\n"
        text += "3. 关注河南省人事考试网，留意重考公告与准考证打印安排。\n"
    elif days_left >= 2:
        text += "1. 全真模拟：按考试时间做整套公基卷，训练时间分配。\n"
        text += "2. 核对准考证打印时间（8/19 起）与考点路线。\n"
    else:
        text += "1. 调整作息，保证睡眠，不再做新题难题。\n"
        text += "2. 备齐准考证、身份证与考试文具，踩点考点。\n"

    # ---- 尾部：数据源健康与生成时间 ----
    if src_ok is not None:
        text += f"\n---\n\n📡 数据源 {src_ok}/{src_total} 可用 · 生成于 {date_str}"
    return title, text


def _get_tenant_access_token(app_id, app_secret):
    """获取飞书 tenant_access_token（参照 server/api/push.py 模式）"""
    resp = requests.post(TOKEN_URL,
                         json={"app_id": app_id, "app_secret": app_secret},
                         timeout=TIMEOUT)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书Token获取失败: {data.get('msg', 'unknown')}")
    return data["tenant_access_token"]


def _send_feishu_message(chat_id, title, content_md, app_id, app_secret):
    """发送飞书 interactive 卡片消息（blue header + markdown）"""
    token = _get_tenant_access_token(app_id, app_secret)
    msg_body = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps({
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [{"tag": "markdown", "content": content_md}],
        }, ensure_ascii=False),
    }
    resp = requests.post(MSG_URL,
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"},
                         json=msg_body,
                         timeout=TIMEOUT)
    result = resp.json()
    if result.get("code") == 0:
        return {"success": True,
                "message_id": result.get("data", {}).get("message_id", "")}
    return {"success": False,
            "error": f"code={result.get('code')} msg={result.get('msg')}"}


def main():
    ap = argparse.ArgumentParser(description="云端飞书情报推送（T4）")
    ap.add_argument("--date", default=None, help="情报日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将发送的内容，不调用飞书 API（本地验证用）")
    args = ap.parse_args()

    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    md_text, data, md_path = load_intel(date_str)
    if md_text is None:
        print(f"无当日情报（{date_str}），跳过推送")
        return 0

    title, content = build_message(date_str, md_text, data)
    print(f"【将推送内容】日期: {date_str} | 情报文件: {md_path}")
    print(f"标题: {title}")
    print("=" * 60)
    print(content)
    print("=" * 60)

    if args.dry_run:
        print("[dry-run] 未调用飞书 API，验证通过")
        return 0

    app_id, app_secret, chat_id = get_credentials()
    if not app_id or not app_secret:
        print("错误：缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET（脚本只读环境变量）")
        return 1
    if not chat_id:
        print("错误：缺少 FEISHU_CHAT_ID / FEISHU_HOME_CHANNEL")
        return 1

    # 网络失败自动重试 1 次（共 2 次尝试），仍失败 exit 2
    last_err = None
    for attempt in (1, 2):
        try:
            result = _send_feishu_message(chat_id, title, content,
                                          app_id, app_secret)
            if result.get("success"):
                print(f"✅ 推送成功 message_id={result.get('message_id')}")
                return 0
            last_err = result.get("error")
            print(f"⚠️ 第 {attempt} 次尝试失败: {last_err}")
        except Exception as e:
            last_err = str(e)
            print(f"⚠️ 第 {attempt} 次尝试异常: {e}")
        time.sleep(3)
    print(f"错误：推送失败（已重试 1 次）：{last_err}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
