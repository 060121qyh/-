# QA验收报告2 — BLK修复+T005-T012（QA-001 独立复验）

| 字段 | 内容 |
|------|------|
| **审查编号** | QA-20260812-002 |
| **审查人** | QA-001（赛博质检官） |
| **被审查人** | TA-001（技术执行） |
| **审查时间** | 2026-08-12 22:55 ~ 23:05 |
| **审查范围** | BLK-001/002/003 修复复核 + T-005/T-006/T-010/T-012 功能验证（任务单：coordination/inbox/pm-to-ta-BLK修复+T005-T012.json） |
| **服务器** | http://127.0.0.1:5000（运行中 ✅，flask --app app.py run --port 5000，PID 1924/5200） |
| **审查结论** | ⚠️ **有条件通过 — 7条验收标准全部通过，发现 1 个 Moderate Bug（BUG-001）需 TA-001 修复后复核** |

> 说明：本报告为 QA-001 独立复验，所有 curl 命令均真实执行，非采信 TA 自报。git-bash 直接传中文参数给 curl 存在编码问题（首测 404，复现 TA 报告备注4 现象），改用**手动 URL 编码**（%XX）后全部通过——该现象非代码缺陷，与 TA 报告一致。

---

## 一、验收标准对照表（含真实 curl 输出）

| # | 验收标准 | 判定 | 真实 HTTP | 实测证据 |
|---|---------|------|-----------|---------|
| 1 | `GET /api/knowledge/card?path=<相对路径>.md` → 200 + title | ✅ 通过 | **200** | title=2025年国务院政府工作报告…核心考点, module=时政热点, quality.score=100, size=4779 |
| 2 | `GET /api/quality?path=<相对路径>.md` → 200 + 10维度评分(满分100) | ✅ 通过 | **200** | score=100, level=优秀, max_score=100, dimensions=10 维 |
| 3 | `POST /api/quiz/submit` question_id+answer → 200 + is_correct + 五段式解析 | ✅ 通过 | **200** | is_correct=False, correct_answer=B, structured 5 段齐全 |
| 4 | `GET /api/health` → 200 + status=ok | ✅ 通过 | **200** | `{"goal_id":"henan-szyf-20260822","status":"ok"}` |
| 5 | 错题写入 data/wrong-questions/、掌握度更新 mastery.json 被验证 | ✅ 通过（附 BUG-001） | 实测落盘 | 错题文件存在且 last_wrong 实时更新；mastery total 16→22 实时递增 |
| 6 | 所有修改文件有 .bak 备份 | ✅ 通过 | 文件核验 | knowledge/quiz/mastery/push 4 个 .bak 全部存在 |
| 7 | 产出 outputs/ta-修复报告2.md 含 curl 实测结果 | ✅ 通过 | 文档核验 | 含 11 处 HTTP_CODE/HTTP 实测证据，每端点均有 curl 输出 |

**总体：7/7 通过。** 验收标准 5 的"写入"行为已验证，但发现 wrong_count 累计逻辑缺陷（BUG-001，见 Bug 清单），故整体判定**有条件通过**。

---

## 二、API 端点测试详情（QA-001 真实 curl 实测）

### 2.1 GET 端点

| 端点 | 方法 | 状态码 | 实测返回要点 | 结果 |
|------|------|--------|-------------|------|
| `/api/health` | GET | **200** | `{"goal_id":"henan-szyf-20260822","status":"ok"}` | ✅ |
| `/api/knowledge/card?path=<URL编码>` | GET | **200** | title/module/quality.score=100/size=4779 | ✅ |
| `/api/quality?path=<URL编码>` | GET | **200** | score=100, level=优秀, max_score=100, 10维度 | ✅ |
| `/api/quality?card=<URL编码>` | GET | **200** | score=100（`?card=` 兼容参数） | ✅ |
| `/api/mastery` | GET | **200** | 15+ 模块掌握度、weak_modules、recommended_focus | ✅ |
| `/api/knowledge`（附加） | GET | **200** | total=11 张知识卡 | ✅ |

**BLK-001 实测（验收标准1，真实 curl 命令）：**
```bash
$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" \
  "http://127.0.0.1:5000/api/knowledge/card?path=%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9/2025%E5%B9%B4%E5%9B%BD%E5%8A%A1%E9%99%A2%E6%94%BF%E5%BA%9C%E5%B7%A5%E4%BD%9C%E6%8A%A5%E5%91%8A%EF%BC%88%E6%9D%8E%E5%BC%BA%E6%80%BB%E7%90%86%C2%B7%E5%8D%81%E5%9B%9B%E5%B1%8A%E5%85%A8%E5%9B%BD%E4%BA%BA%E5%A4%A7%E4%B8%89%E6%AC%A1%E4%BC%9A%E8%AE%AE%EF%BC%89%E6%A0%B8%E5%BF%83%E8%80%83%E7%82%B9.md"
```
真实返回（解析后）：
```
HTTP: 200
title: 2025年国务院政府工作报告（李强总理·十四届全国人大三次会议）核心考点
module: 时政热点
quality.score: 100
size: 4779
```
**结论**: ✅ 验收标准1通过。BLK-001 修复有效（`relative_to(kb_dir_resolved)` 生效，无回归）。

**BLK-002 实测（验收标准2，真实 curl 命令）：**
```bash
$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" \
  "http://127.0.0.1:5000/api/quality?path=<同上URL编码>"
```
真实返回（解析后）：
```
HTTP_CODE: 200
score: 100
level: 优秀
max_score: 100
dimensions: 10 个维度（字数10/知识点章节15/表格15/口诀15/考情分析10/来源标注5/结构化5/重点标记5/分值关联10/例题10 = 合计100）
```
`?card=` 兼容参数实测同样返回 **200** + score=100。**结论**: ✅ 验收标准2通过。

### 2.2 POST 端点

**BLK-003 实测（验收标准3，真实 curl 命令）：**
```bash
$ curl -s -X POST -H "Content-Type: application/json" \
  -d '{"question_id":"2026-08-12-001-5","answer":"C"}' \
  -w "\n---HTTP_CODE:%{http_code}---\n" http://127.0.0.1:5000/api/quiz/submit
```
真实返回（解析后）：
```
HTTP: 200
is_correct: False          （题目5正确答案为B，提交C判错，逻辑正确）
user_answer: C
correct_answer: B
五段式 segments(5个): correct_answer / term_breakdown / option_analysis / exam_hint / mnemonic
  correct_answer: 【正确答案】B（高质量发展）
  term_breakdown: 【术语拆解】• 「首要任务」：排在第一位、最重要的任务...
  option_analysis: 【选项辨析——区分四个概念的定位】• A 全面深化改革：定位是"根本动力"...
  exam_hint:      【考情提示】这是"帽子题"——考概念的准确定位...
  mnemonic:       【记忆口诀】"质量首要改动力，共同富裕是本质"
```
**附加验证（真实执行）**：`answer=B` → HTTP 200 + is_correct=True ✅；`user_answer=C` → HTTP 200 + is_correct=False ✅（字段兼容确认）。

> 注：本环境 git-bash 下 `curl -d` 实测可正常发送 JSON body（未出现技能文档所述吞 body 现象），POST 结果与 TA 报告一致。

**结论**: ✅ 验收标准3通过。BLK-003 修复有效（POST 方法注册 + answer 字段兼容，无回归）。

### 2.3 T-005 / T-006 / T-010 / T-012 功能验证

| 任务 | 验证方式 | 结果 |
|------|---------|------|
| T-005 质量评分引擎(10维度100分) | `knowledge.py:63-185 _score_knowledge_card()` 代码核验 + `/api/quality` 实测 score=100 | ✅ |
| T-006 五段式解析 | `quiz.py:120-167 _parse_five_segment_explanation()` 代码核验 + submit 实测 5 段齐全 | ✅ |
| T-012 错题追踪 | 实测落盘 data/wrong-questions/2026-08-12-001-5.json（存在、last_wrong 实时更新）+ `_save_wrong_question_file` 代码核验 | ✅（写入行为；wrong_count 累计见 BUG-001） |
| T-010 掌握度实时更新 | mastery.json 实测 total 16→22 递增、mastery/trend/weak 随答题实时变化 + quiz.py:366-393 代码核验 | ✅ |

### 2.4 交叉验证（scripts/verify_fixes.py，QA 独立重跑）

将 `scripts/verify_fixes.py` 复制至 `.kb-tmp/` 并将 BASE 端口改为 5000（不改原文件，运行后已清理临时副本），真实运行结果：

```
PASS AC1: knowledge/card path resolution
PASS AC2: quality 10-dimension scoring
PASS AC3: quiz submit with answer field
PASS AC4: mastery correct_rate updated
PASS AC5: wrong-questions/ directory (2 files)

==================================================
RESULTS: 5 passed, 0 failed out of 5
ALL PASSED
==================================================
```

与 TA 报告自测结果完全一致，独立复验确认无回归。

### 2.5 正式验证记录（hermes verify --json）

项目检测配方 "Flask app"，`hermes verify --json` 真实运行通过，结果文件存于 `outputs/hermes-verify-result.json`：

```json
{"recipe": "Flask app", "ok": true, "phases": [{"phase": "bootstrap", "exitCode": 0, "ok": true, "timedOut": false, "duration": 4.907}]}
```

结合 §2.1-§2.4 的端点实测（全部 200）与 verify_fixes.py 5/5 PASSED，形成完整验证证据链。

---

## 三、边界条件测试（真实 curl 实测）

| 测试场景 | 预期 | 实际 | 结果 |
|----------|------|------|------|
| `?path=` 传不存在的卡（card 端点） | 404 而非 500 | `{"error":"知识卡不存在"}` **404** | ✅ |
| `?path=` 传不存在的卡（quality 端点） | 404 而非 500 | `{"error":"知识卡不存在"}` **404** | ✅ |
| 缺 path 参数（card 端点） | 400 | `{"error":"缺少 path 参数"}` **400** | ✅ |
| 路径遍历 `?path=../../../etc/passwd` | 403 | `{"error":"非法的路径"}` **403** | ✅ |
| POST 空 body `{}` | 400 | `{"error":"请求体为空"}` **400** | ✅ |

**结论**: 边界条件处理正确，不存在的卡返回合理的 404 而非 500，无回归。

---

## 四、代码规范性核验（逐行确认）

| 检查项 | 位置 | 代码/结论 | 结果 |
|--------|------|-----------|------|
| BLK-001 relative_to 修复 | `knowledge.py:220,230` | `kb_dir_resolved = kb_dir.resolve()` + `full_path.relative_to(kb_dir_resolved)` 真实存在于代码中 | ✅ |
| BLK-001 路径穿越防护 | `knowledge.py:221` | `str(full_path).startswith(str(kb_dir_resolved))` → 403 | ✅ |
| BLK-002 `?path=` 优先 | `knowledge.py:254` | `card_filter = request.args.get("path","").strip() or request.args.get("card","").strip()` 真实存在 | ✅ |
| BLK-003 POST 方法注册 | `quiz.py:288` | `@quiz_bp.route("/api/quiz/submit", methods=["POST"])` 真实存在 | ✅ |
| BLK-003 answer 字段兼容 | `quiz.py:304` | `(body.get("user_answer","") or body.get("answer","")).strip().upper()` 真实存在 | ✅ |
| T-005 评分引擎 10 维度 | `knowledge.py:63-185` | 字数10/章节15/表格15/口诀15/考情10/来源5/结构化5/重点5/分值10/例题10 | ✅ |
| T-012 错题文件写入 | `quiz.py:30-52, 360` | `_get_wrong_dir()` / `_save_wrong_question_file()` 存在并被 submit 调用 | ✅ |
| .bak 备份 | `server/api/*.bak` | knowledge/quiz/mastery/push 4 个 .bak 全部存在（8月12日 22:07） | ✅ |
| 文档完整性 | `outputs/ta-修复报告2.md` | 含 11 处 HTTP_CODE/HTTP 实测证据，每个端点均有 curl 输出 | ✅ |

---

## 五、Bug 清单

| ID | 严重级别 | 描述 | 状态 |
|----|---------|------|------|
| **BUG-001** | 🟡 **Moderate** | **data/wrong-questions/<id>.json 的 wrong_count 卡在 2，无法累计**。根因：`quiz.py:47` `existing.update(record)` 用新构造的 `record`（wrong_count=1）覆盖已有文件的 wrong_count，随后 `:49` 再 +1，导致无论答错多少次，单文件 wrong_count 恒为 2。实测：连续提交 5 次错误答案后，`data/wrong-questions/2026-08-12-001-5.json` wrong_count 仍为 2（正确应为 7），而主文件 `data/progress/wrong-questions.json` 正确累计至 9——双写数据不一致。TA 自测仅覆盖 1→2 的单次递增场景，未覆盖多次连续答错。**修复建议（供 TA 参考）**：`_save_wrong_question_file` 中先读取已有 wrong_count 再递增，勿用新 record 覆盖（如改为 `existing["wrong_count"] = existing.get("wrong_count", 0) + 1` 且不 update 计数键）。 | 🆕 待 TA-001 修复 |
| 无 | — | 其余验收项未发现其他 Bug | — |

---

## 六、遗留风险与建议

1. **git-bash curl 中文参数编码问题**（非代码缺陷，环境现象）：直接传中文给 curl 或 `--data-urlencode` 会因编码问题 404，须手动 URL 编码（%XX）。建议在项目文档/技能中固化该用法，避免后续 Agent 误判为代码 Bug。
2. **mastery.json 含历史测试脏数据**（TA 报告备注2 已提及）：存在 `test模块`(weak=true)、`shizheng`、`%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9`(URL编码残留) 等非标准模块名（共15+模块，配置标准12个）。不阻塞端点功能，是否清理由 PM-001 决策。
3. **测试产生的数据变更**（QA-001 实测副作用，如实上报）：时政热点 mastery total 16→23、mastery 56→43、weak false→true（QA 共提交 7 次答题，含交叉验证脚本 1 次）；错题文件 last_wrong 多次更新。如需纯净基线数据请 PM-001 决策，QA 未擅自清理。
4. **BUG-001 影响面**：错题目录文件与主文件 wrong_count 不一致，长期运行会导致"重复错误次数"统计失真，间接影响弱项识别与推荐（quiz.py `?mode=weak` 依赖主文件数据，主文件正确，故当前功能可用；但目录文件不可作为统计源）。

---

## 七、审查结论

### 结论：⚠️ 有条件通过

- **7/7 条验收标准全部通过**（真实 curl 实测 HTTP 200 + 数据落盘 + 代码核验 + 文档核验）。
- BLK-001/002/003 修复均确认无回归，代码规范性达标。
- **必须处理（不阻塞核心功能但需修复）**：
  > 🟡 **BUG-001**: `_save_wrong_question_file` 中 `existing.update(record)` 导致 data/wrong-questions/ 单文件 wrong_count 卡在 2，无法累计。TA-001 修复后 QA-001 快速复核（仅复核该点，无需全量重验）。
- 修复后由 QA-001 复核 BUG-001，确认无误后整体转「通过」。

### 优秀实践（值得保留）
- TA 报告证据详实（每端点含真实 curl 输出与解析后结果），交叉验证脚本 PASS 记录完整。
- 修复点集中、注释清晰，`?path=` 优先的兼容设计合理。
- 服务器以 SERVER_PORT=5000 覆盖启动符合验收标准，未改 config 默认值，做法规范。

---

*报告生成: QA-001 | 2026-08-12 23:05 | 审查方式: 独立 curl 实测 + 代码逐行核验 | 严禁伪造原则: 所有 HTTP 码均为本机真实执行结果*
