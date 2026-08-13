#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端飞书情报推送脚本（REQ-20260813-002 重构版 / TA-001）
=========================================================
针对用户反馈「推送都是小新闻，考试不会考，要最热最新最重要的实时新闻 +
像新闻一样给信息、再精华、与我相关、还有历史因果链」重构推送格式：

1. 顶部：距考天数 + 「今日最值得关注 TOP3」（按 importance 排序，🔴优先）
2. 正文：按模块分组（时政/河南省情/法律/马哲/中特/三农/经济民生/科技产业，
   有内容的模块才显示），每条 = 重要度标记 + 标题 + 1-2句精华提炼 + 历史关联
3. 底部：「与我相关」备考建议（结合模块构成与距考天数生成）

与 intel_collector.py 新 JSON 字段对接：module / importance / essence / history。
兼容旧版 JSON（无新字段时回退旧逻辑，不报错）。

用法：
  python scripts/push_intel.py                # 推送当天情报
  python scripts/push_intel.py --date 2026-08-13
  python scripts/push_intel.py --dry-run      # 只打印将发送的内容，不调用飞书 API

退出码：
  0  推送成功；或当日无情报文件（打印「无当日情报，跳过推送」）
  1  飞书密钥缺失（FEISHU_APP_ID / FEISHU_APP_SECRET / 聊天 ID 未配置）
  2  网络/API 调用失败（自动重试 1 次后仍失败；
     workflow 中该步骤已设 continue-on-error: true）

凭证只从环境变量读取：FEISHU_APP_ID / FEISHU_APP_SECRET /
FEISHU_CHAT_ID（为空时回退 FEISHU_HOME_CHANNEL）。
"""
import argparse
import json
import os
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

# 模块展示顺序与中文名（有内容的模块才显示）
MODULE_ORDER = ["时政", "河南省情", "法律", "马哲", "中特", "三农",
                "经济民生", "科技产业"]
MODULE_ICONS = {"时政": "🏛️", "河南省情": "🏮", "法律": "⚖️", "马哲": "📖",
                "中特": "🇨🇳", "三农": "🌾", "经济民生": "📊", "科技产业": "🔬"}

# 重要度排序权重（🔴 > 🟠 > 🟢）
IMPORTANCE_ORDER = {"🔴": 0, "🟠": 1, "🟢": 2}

# 来源短名映射
SOURCE_SHORT_NAMES = {
    "河南省人事考试网-首页": "河南人事考试网",
    "新华网-时政RSS": "新华网",
    "人民网-时政RSS": "人民网",
    "求是网": "求是网",
    "央视网-首页": "央视网",
    "最高法": "最高法",
    "中国人大网-权威发布": "中国人大网",
    "中国网信办": "中国网信办",
    "农业农村部": "农业农村部",
    "国家统计局": "国家统计局",
    "发改委": "发改委",
    "工信部": "工信部",
    "中国科学院": "中科院",
    "中原网-河南": "中原网",
}


def get_credentials():
    """只从环境变量读取飞书凭证（绝不读 .env 文件）"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    chat_id = (os.environ.get("FEISHU_CHAT_ID", "").strip()
               or os.environ.get("FEISHU_HOME_CHANNEL", "").strip())
    return app_id, app_secret, chat_id


def load_intel(date_str):
    """读取当日情报 JSON（新格式），失败返回 None"""
    json_path = INTEL_DIR / f"intel-{date_str}.json"
    if not json_path.exists():
        return None, None, None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ 情报 JSON 解析失败：{e}")
        return None, None, None
    return data, data, json_path


def short_source(name):
    """来源短名"""
    return SOURCE_SHORT_NAMES.get(name, name if len(name) <= 8 else name[:7] + "…")


def clip_title(t, n=36):
    """标题截断"""
    if "..." in t or "…" in t:
        return t
    return t if len(t) <= n else t[: n - 1] + "…"


def sort_items(items):
    """按重要度（🔴>🟠>🟢）→ 分数 排序"""
    return sorted(items, key=lambda x: (IMPORTANCE_ORDER.get(x.get("importance", "🟢"), 3),
                                        -x.get("score", 0)))


def top3(items):
    """今日最值得关注 TOP3：按重要度排序取前 3；🔴不足时补 🟠"""
    ordered = sort_items(items)
    red = [it for it in ordered if it.get("importance") == "🔴"]
    orange = [it for it in ordered if it.get("importance") == "🟠"]
    green = [it for it in ordered if it.get("importance") == "🟢"]
    picks = (red + orange + green)[:3]
    return picks


def item_line(it, with_url=True):
    """单条新闻行：重要度 + 标题 + 精华 + 历史关联"""
    imp = it.get("importance", "🟢")
    title = it.get("title", "")
    lines = [f"{imp} {title}"]
    essence = it.get("essence", "")
    if essence:
        lines.append(f"　💡 {essence}")
    history = it.get("history", "")
    if history:
        lines.append(f"　📜 {history}")
    if with_url and it.get("url"):
        lines.append(f"　🔗 {it['url']}")
    return "\n".join(lines)


def build_message(date_str, data):
    """构建「距考天数 + TOP3 + 模块分组 + 与我相关」推送内容"""
    items = data.get("items", []) if data else []
    days_left = (data or {}).get("days_left") or (EXAM_DATE - datetime.now(CST)).days
    srcs = (data or {}).get("sources", [])
    src_ok = sum(1 for s in srcs if s.get("ok"))
    src_total = len(srcs)

    # ---- 标题 ----
    title = f"📰 备考情报速递 · {date_str[5:].replace('-', '/')} · 距考 {days_left} 天"

    # ---- 1) 距考天数 ----
    text = f"**⏰ 距河南三支一扶重考（2026-08-22）：{days_left} 天**\n\n---\n\n"

    # ---- 2) 今日最值得关注 TOP3 ----
    text += "### 🔥 今日最值得关注 TOP3\n\n"
    picks = top3(items)
    if picks:
        for idx, it in enumerate(picks, 1):
            imp = it.get("importance", "🟢")
            src = short_source(it.get("source", ""))
            text += f"**{idx}. {imp} [{src}]** {clip_title(it.get('title', ''), 40)}\n"
            essence = it.get("essence", "")
            if essence:
                text += f"　💡 {essence}\n"
            history = it.get("history", "")
            if history:
                text += f"　📜 {history}\n"
            if it.get("url"):
                text += f"　🔗 {it['url']}\n"
            text += "\n"
    else:
        text += "- 今日暂无高价值条目，建议关注河南省人事考试网最新公告。\n"
    text += "\n---\n\n"

    # ---- 3) 按模块分组 ----
    text += "### 📋 今日要点（按模块）\n\n"
    by_module = {}
    for it in items:
        by_module.setdefault(it.get("module", "时政"), []).append(it)
    shown_any = False
    for mod in MODULE_ORDER:
        group = by_module.get(mod, [])
        if not group:
            continue
        shown_any = True
        icon = MODULE_ICONS.get(mod, "📌")
        text += f"**{icon} {mod}**\n"
        for it in sort_items(group)[:4]:  # 每模块最多 4 条，避免刷屏
            imp = it.get("importance", "🟢")
            src = short_source(it.get("source", ""))
            u = it.get("url", "")
            # P5：模块分组内条目补飞书 markdown 链接 [标题](url)
            if u:
                text += f"- {imp} [{src}] [{clip_title(it.get('title', ''), 38)}]({u})\n"
            else:
                text += f"- {imp} [{src}] {clip_title(it.get('title', ''), 38)}\n"
            essence = it.get("essence", "")
            if essence:
                text += f"　💡 {essence}\n"
            history = it.get("history", "")
            if history:
                text += f"　📜 {history}\n"
        text += "\n"
    if not shown_any:
        text += "- 今日暂无条目。\n"
    text += "\n---\n\n"

    # ---- 4) 与我相关（备考建议） ----
    text += "### 🎯 与我相关\n\n"
    suggestions = build_suggestions(items, days_left)
    if suggestions:
        for s in suggestions:
            text += f"• {s}\n"
    else:
        text += "• 今日暂无强相关条目，保持常规复习节奏即可。\n"

    # ---- 尾部：数据源健康与生成时间 ----
    if src_total:
        text += f"\n---\n\n📡 数据源 {src_ok}/{src_total} 可用 · 生成于 {date_str}"
    return title, text


def build_suggestions(items, days_left):
    """「与我相关」建议：基于模块构成 + 距考天数生成"""
    s = []
    modules = {it.get("module", "") for it in items}
    imps = {it.get("importance", "") for it in items}
    titles = " ".join(it.get("title", "") for it in items)

    # 招考动态最优先
    if any(k in titles for k in ("三支一扶", "招募", "准考证", "重考", "补考")):
        s.append("📌 河南三支一扶招考动态已更新，务必核对报名/考试/准考证安排，"
                 "以河南省人事考试网公告为准。")
    # 本周重点（🔴要闻高频考点提示）
    red_hist = [it.get("history", "") for it in items
                if it.get("importance") == "🔴" and it.get("history")]
    if red_hist:
        s.append(f"📖 今日🔴要闻含历史考点线索：{red_hist[0][:60]}…，建议结合知识卡复习。")
    if "法律" in modules:
        s.append("⚖️ 法律模块有动态，公基法律考点侧重新法施行时间与核心条款，"
                 "建议结合民法典、新修订法律复习。")
    if "三农" in modules or "乡村振兴" in titles:
        s.append("🌾 三农/乡村振兴是公基高频考点，重点掌握中央一号文件主线与"
                 "'藏粮于地、藏粮于技'。")
    if "科技产业" in modules or "新质生产力" in titles:
        s.append("🔬 科技产业动态涉及新质生产力，注意与2024年写入政府工作报告的"
                 "背景衔接。")
    if "河南省情" in modules:
        s.append("🏮 河南省情动态是河南三支一扶特色考点，关注省委省政府重大部署。")
    if "经济民生" in modules:
        s.append("📊 经济数据发布注意同比/环比口径，公基经济模块常考宏观指标含义。")

    # 距考天数分档
    if days_left >= 10:
        s.append("✅ 距考尚早：按模块系统复习时政热点+法律+马哲，每日10-15道选择题。")
    elif days_left >= 5:
        s.append("✅ 冲刺期：专项突破时政热点（二十届四中全会/中央一号文件/新质生产力）"
                 "+ 河南考情，复盘错题本。")
    elif days_left >= 2:
        s.append("✅ 全真模拟：按考试时间做整套公基卷，核对准考证打印时间与考点路线。")
    else:
        s.append("✅ 调整作息保证睡眠，备齐准考证、身份证与文具，不再做新题难题。")
    return s


def _get_tenant_access_token(app_id, app_secret):
    """获取飞书 tenant_access_token"""
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
    ap = argparse.ArgumentParser(description="云端飞书情报推送（REQ-20260813-002）")
    ap.add_argument("--date", default=None, help="情报日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将发送的内容，不调用飞书 API（本地验证用）")
    args = ap.parse_args()

    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    data, _, json_path = load_intel(date_str)
    if data is None:
        print(f"无当日情报（{date_str}），跳过推送")
        return 0

    title, content = build_message(date_str, data)
    print(f"【将推送内容】日期: {date_str} | 情报文件: {json_path}")
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
