#!/usr/bin/env python3
"""
AI三支一扶学习导师 v2.0 — 模块化API服务器
基于 Flask 的本地 HTTP 服务，提供 RESTful API 和静态文件服务。

启动: python server/app.py
访问: http://localhost:8899
"""

import os
import sys
import yaml
from pathlib import Path
from flask import Flask, jsonify

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server.api.knowledge import knowledge_bp
from server.api.quiz import quiz_bp
from server.api.mastery import mastery_bp
from server.api.push import push_bp
from server.api.overview import overview_bp
from server.api.plan import plan_bp


def load_config():
    """加载 config.yaml 配置文件"""
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        print(f"[WARN] config.yaml not found at {config_path}, using defaults")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # 环境变量覆盖
    if os.environ.get("SERVER_PORT"):
        config.setdefault("server", {})["port"] = int(os.environ["SERVER_PORT"])
    if os.environ.get("SERVER_HOST"):
        config.setdefault("server", {})["host"] = os.environ["SERVER_HOST"]
    if os.environ.get("DATA_DIR"):
        config.setdefault("paths", {})["knowledge_cards"] = os.environ["DATA_DIR"]
        # 使用环境变量统一设置数据目录

    return config


def create_app():
    """创建 Flask 应用实例"""
    app = Flask(
        __name__,
        static_folder=str(PROJECT_ROOT / "static"),
        static_url_path="/static",
    )

    # 加载配置
    config = load_config()

    # 提取关键配置项
    server_cfg = config.get("server", {})
    paths_cfg = config.get("paths", {})
    exam_cfg = config.get("exam", {})
    modules = config.get("modules", [])
    design = config.get("design", {})
    push_cfg = config.get("push", {})

    # 存入 Flask config
    app.config["SERVER_HOST"] = server_cfg.get("host", "0.0.0.0")
    app.config["SERVER_PORT"] = int(server_cfg.get("port", 8899))
    app.config["GOAL_ID"] = config.get("project", {}).get("goal_id", "henan-szyf-20260822")
    app.config["EXAM_DATE"] = exam_cfg.get("exam_date", config.get("project", {}).get("exam_date", "2026-08-22"))
    app.config["DATA_DIR"] = paths_cfg.get("knowledge_cards", "data").replace("data/knowledge-cards", "data")
    app.config["MODULES"] = modules
    app.config["PUSH_SCHEDULE"] = push_cfg.get("schedule", [])

    # 飞书配置（优先读 .env）
    app.config["FEISHU_APP_ID"] = os.environ.get("FEISHU_APP_ID", "")
    app.config["FEISHU_APP_SECRET"] = os.environ.get("FEISHU_APP_SECRET", "")
    app.config["FEISHU_CHAT_ID"] = os.environ.get("FEISHU_CHAT_ID", "")

    # 注册 Blueprint
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(mastery_bp)
    app.register_blueprint(push_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(plan_bp)

    # ========== CORS (after each request) ==========
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    # ========== Health Check ==========
    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "goal_id": app.config.get("GOAL_ID", "henan-szyf-20260822"),
        })

    # ========== Static File Serving ==========
    @app.route("/")
    def index():
        return app.send_static_file("platform.html")

    @app.route("/<path:path>")
    def serve_static(path):
        # 对于非 API 路径，尝试从 static 目录提供
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        return app.send_static_file(path)

    # ========== Error Handlers ==========
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    host = app.config["SERVER_HOST"]
    port = app.config["SERVER_PORT"]

    print(f"""
╔══════════════════════════════════════════════════════╗
║     AI 三支一扶学习导师 v2.0 — 模块化 API 服务器        ║
╠══════════════════════════════════════════════════════╣
║  本地访问: http://localhost:{port}                     ║
║  API 根路径: /api/health                              ║
║  知识卡: /api/knowledge                               ║
║  题库:   /api/quiz                                    ║
║  掌握度: /api/mastery                                 ║
║  总览:   /api/overview                                ║
╚══════════════════════════════════════════════════════╝
""")
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
