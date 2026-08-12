"""
server/api/push.py — 飞书推送API
Token管理（缓存2h自动刷新）、消息构建与发送。
"""
import json
import time
import os
import requests
from datetime import datetime, date, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app

push_bp = Blueprint("push", __name__)

# 全局 Token 缓存
_token_cache = {
    "token": None,
    "expires_at": 0,
}


def _get_feishu_credentials():
    """从环境变量获取飞书凭证"""
    return {
        "app_id": os.environ.get("FEISHU_APP_ID", ""),
        "app_secret": os.environ.get("FEISHU_APP_SECRET", ""),
        "chat_id": os.environ.get("FEISHU_CHAT_ID", "") or os.environ.get("FEISHU_HOME_CHANNEL", ""),
    }


def _get_tenant_access_token():
    """获取飞书 tenant_access_token，缓存2h"""
    global _token_cache

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    creds = _get_feishu_credentials()
    if not creds["app_id"] or not creds["app_secret"]:
        raise ValueError("飞书凭证未配置：缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": creds["app_id"], "app_secret": creds["app_secret"]},
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"飞书Token请求失败: {e}")

    if data.get("code") != 0:
        raise RuntimeError(f"飞书Token获取失败: {data.get('msg', 'unknown')}")

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data.get("expire", 7200)  # 默认2h
    return _token_cache["token"]


def _send_feishu_message(chat_id, title, content_md):
    """发送飞书 interactive 消息（blue header + markdown）"""
    token = _get_tenant_access_token()

    msg_body = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps({
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": content_md}
            ],
        }, ensure_ascii=False),
    }

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=msg_body,
            timeout=15,
        )
        result = resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if result.get("code") == 0:
        return {"success": True, "message_id": result.get("data", {}).get("message_id", "")}
    else:
        return {"success": False, "error": f"code={result.get('code')} msg={result.get('msg')}"}


def _build_push_content(period="manual"):
    """构建推送消息内容"""
    # 距考天数
    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst)
    exam_date = datetime(2026, 8, 22, tzinfo=cst)
    days_left = (exam_date - now).days

    if period == "morning":
        title = f"☀️ 早间考情 · {now.strftime('%m/%d')}"
        text = f"**⏰ 距河南三支一扶重考：{days_left} 天**\n\n"
        text += "---\n\n"
        text += "### 📋 今日重点\n\n"
        text += "1. **时政热点**：浏览新华网今日头条、关注最新政策动态\n"
        text += "2. **法律模块**：复习宪法·刑法·民法·行政法核心概念\n"
        text += "3. **三农政策**：重点记忆2025年中央一号文件要点\n"
        text += "4. **河南考情**：关注河南省人事考试网公告\n\n"
        text += f"📅 报名截止：8/13 17:00 | 准考证：8/19起打印\n\n"
        text += f"🖥️ [打开学习看板](http://localhost:8899)"

    elif period == "noon":
        title = f"🌤️ 午间速递 · {now.strftime('%m/%d')}"
        text = f"**⏰ 距考试：{days_left} 天**\n\n"
        text += "---\n\n"
        text += "### 🔥 午间练题建议\n\n"
        text += "1. **时政选择题**：完成5道单选题+2道多选题\n"
        text += "2. **马哲辨析**：对立统一·实践认识论·唯物史观\n"
        text += "3. **经济常识**：宏观经济指标速记\n\n"
        text += "---\n\n"
        text += "### 📊 今日时政方向\n\n"
        text += "重点关注：新质生产力·二十届三中全会·政府工作报告·一号文件\n\n"
        text += f"🖥️ [打开练题页](http://localhost:8899)"

    elif period == "evening":
        title = f"🌙 晚间汇总 · {now.strftime('%m/%d')}"
        text = f"**⏰ 距考试：{days_left} 天**\n\n"
        text += "---\n\n"
        text += "### 📝 今日汇总\n\n"
        text += "复习进度自查：\n"
        text += "- 时政知识卡：3张 ✅\n"
        text += "- 练题：建议15题/天\n"
        text += "- 错题复盘：检查错题本\n\n"
        text += "---\n\n"
        text += "### 🔮 明日预告\n\n"
        text += "模块：中特理论 + 法律 + 三农\n"
        text += "练题：单选15题 + 多选5题\n\n"
        text += f"🖥️ [打开错题本](http://localhost:8899)"

    else:
        title = f"📚 学习导师 · {now.strftime('%m/%d')}"
        text = f"**⏰ 距河南三支一扶重考：{days_left} 天**\n\n"
        text += "---\n\n"
        text += "### 📖 今日学习建议\n\n"
        text += "1. 时政：浏览今日新华网头条\n"
        text += "2. 法律：复习宪法刑法民法核心概念\n"
        text += "3. 马哲：掌握对立统一实践认识论\n"
        text += "4. 练题：平台15道时政选择题\n\n"
        text += "---\n\n"
        text += f"🖥️ PC: http://localhost:8899"

    return title, text


# ============ API Routes ============

@push_bp.route("/api/push", methods=["GET"])
def push_status():
    """GET /api/push — 飞书推送状态"""
    creds = _get_feishu_credentials()
    feishu_configured = bool(creds["app_id"] and creds["app_secret"] and creds["chat_id"])
    return jsonify({
        "configured": feishu_configured,
        "app_id": creds["app_id"][:8] + "***" if creds["app_id"] else "",
        "schedule": current_app.config.get("PUSH_SCHEDULE", []),
        "status": "ready" if feishu_configured else "not_configured",
    })


@push_bp.route("/api/push/test", methods=["POST"])
def push_test():
    """POST /api/push/test — 手动测试推送
    
    可选请求体: {"period": "morning|noon|evening|manual"}
    """
    try:
        creds = _get_feishu_credentials()
        if not creds["app_id"] or not creds["app_secret"]:
            return jsonify({
                "success": False,
                "error": "飞书凭证未配置。请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET",
            }), 400

        if not creds["chat_id"]:
            return jsonify({
                "success": False,
                "error": "飞书群聊未配置。请设置环境变量 FEISHU_CHAT_ID 或 FEISHU_HOME_CHANNEL",
            }), 400

        # 获取推送时段
        body = request.get_json(silent=True) or {}
        period = body.get("period", "manual").strip()

        # 构建消息
        title, text = _build_push_content(period)

        # 发送
        result = _send_feishu_message(creds["chat_id"], title, text)

        return jsonify({
            "period": period,
            **result,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
