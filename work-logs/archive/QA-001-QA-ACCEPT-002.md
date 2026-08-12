# QA-001 工作日志 — QA-ACCEPT-002

| 字段 | 内容 |
|------|------|
| **任务ID** | QA-ACCEPT-002 |
| **工号** | QA-001（赛博质检官） |
| **任务来源** | 父任务 QA-001 验收 TA-001 修复产出（BLK修复+T005-T012-2） |
| **开始时间** | 2026-08-12 22:55 |
| **关联任务单** | coordination/inbox/pm-to-ta-BLK修复+T005-T012.json |
| **被审查对象** | TA-001 产出：outputs/ta-修复报告2.md + server/api/ 代码 |

## 执行步骤

1. **读取输入**：ta-修复报告2.md、任务单（7条验收标准）、QA验收报告-第一阶段.md（格式参照）、协作协议、agent-registry.csv。
2. **探测服务器**：`curl /api/health` → 200 + status=ok（TA 启动的 flask 进程在 127.0.0.1:5000，PID 1924/5200，`flask --app app.py run --host 0.0.0.0 --port 5000`，Python 3.13），无需自己启动。
3. **首次 curl 实测**（git-bash 直接传中文参数 / `--data-urlencode`）：knowledge/card 与 quality 均返回 404「知识卡不存在」——复现了 TA 报告备注4 所述的 git-bash 中文编码问题（非代码缺陷）。改用**手动 URL 编码**（Python urllib + 手工 %XX 编码）后全部通过。
4. **独立实测（真实 curl，手动URL编码）**：
   - `GET /api/health` → **200** status=ok
   - `GET /api/knowledge/card?path=<URL编码>.md` → **200** title/module/quality.score=100
   - `GET /api/quality?path=<同上>` → **200** score=100 level=优秀 10维度 max_score=100
   - `GET /api/quality?card=<同上>` → **200**（兼容参数）score=100
   - `POST /api/quiz/submit {"question_id":"2026-08-12-001-5","answer":"C"}` → **200** is_correct=False correct_answer=B 五段式(5段完整)
   - `POST ... answer=B` → **200** is_correct=True
   - `POST ... user_answer=C` → **200** is_correct=False（字段兼容）
   - `GET /api/mastery` → **200** 模块掌握度
5. **边界条件**：path=不存在的卡 → 404（card/quality 均404，非500）✅；缺path → 400；路径遍历 → 403；POST空body → 400。
6. **代码规范性核验**：
   - knowledge.py:220 `kb_dir_resolved = kb_dir.resolve()` ✅；:230 `full_path.relative_to(kb_dir_resolved)` ✅；:221 路径穿越防护（403）
   - knowledge.py:254 `card_filter = request.args.get("path","").strip() or request.args.get("card","").strip()`（?path= 优先）✅
   - quiz.py:288 `@quiz_bp.route("/api/quiz/submit", methods=["POST"])` ✅；:304 `(body.get("user_answer","") or body.get("answer","")).strip().upper()` ✅
   - 评分引擎 knowledge.py:63-185 十维度齐全 ✅；五段式解析 quiz.py:120-167 ✅；错题目录/写文件 quiz.py:30-52 ✅；mastery更新 quiz.py:366-393 ✅
7. **数据落盘验证**：错题文件 data/wrong-questions/2026-08-12-001-5.json 存在且 last_wrong 实时更新；mastery.json 时政热点 total 16→22 实时递增。
8. **🔴 发现 Bug（真实可复现）**：连续 5 次提交错误答案后，data/wrong-questions/2026-08-12-001-5.json 的 wrong_count **始终卡在 2**（应为 7），而主文件 data/progress/wrong-questions.json 正确累计到 9。根因：quiz.py:47 `existing.update(record)` 用新构造的 record（wrong_count=1）覆盖已有计数。TA 自测仅覆盖 1→2 递增场景，未覆盖多次连续答错。
9. **.bak 核验**：knowledge.py.bak / quiz.py.bak / mastery.py.bak / push.py.bak 全部存在 ✅
10. **文档完整性**：ta-修复报告2.md 含 11 处 HTTP_CODE/HTTP 实测证据、每端点有 curl 输出 ✅

## 产出文件

- outputs/qa-验收报告2.md（主报告，结论：**有条件通过**）
- coordination/outbox/qa-report-QA-ACCEPT-002.md（协作协议要求的 outbox 副本）

## 遇到的问题

1. git-bash curl 传中文参数编码问题导致首测 404（与 TA 备注4 一致，非代码问题）→ 改用手动 URL 编码解决。
2. 发现 wrong_count 卡 2 的累计逻辑 Bug（TA 自测盲区），已报告，不自行修改代码。

## 测试副作用（如实记录）

- 时政热点 mastery: total 16→22, mastery 56→48, weak false→true（测试提交 6 次答题所致）
- 错题文件 last_wrong 更新多次；主错题文件 wrong_count 递增
- 如需纯净基线数据请 PM-001 决策（未擅自清理）

## 完成时间

2026-08-12 23:052026-08-12 23:05
