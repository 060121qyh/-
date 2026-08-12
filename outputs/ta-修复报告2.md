# TA-001 修复报告2

**任务ID**: BLK修复+T005-T012
**发件Agent**: PM-001
**执行Agent**: TA-001（赛博工程师）
**日期**: 2026-08-12
**状态**: ✅ 全部端点核验通过（待 QA-001 验收）
**说明**: 本报告为第二轮复核报告。上一轮（ta-修复报告.md）的修改经逐行核验**全部仍生效、无回归**，本轮未改动任何代码文件，仅做核验 + 服务器实测。

---

## 修复概览

| Bug/任务 | 标题 | 状态 | 验证方式 |
|---------|------|------|---------|
| BLK-001 | /api/knowledge/card 路径解析500 | ✅ 修复仍在，实测200 | curl 200 + title |
| BLK-002 | /api/quality 404/参数问题 | ✅ 修复仍在，实测200 | curl 200 + 10维度评分 |
| BLK-003 | /api/quiz/submit POST 405 | ✅ 修复仍在，实测200 | curl POST 200 + 五段式解析 |
| T-005 | 知识卡质量评分引擎(10维度满分100) | ✅ 实测通过 | /api/quality?path= → score=100 |
| T-006 | 练题五段式解析 | ✅ 实测通过 | POST /api/quiz/submit → 5段结构化 |
| T-012 | 错题追踪(data/wrong-questions/) | ✅ 实测落盘 | 错题文件 wrong_count 1→2 |
| T-010 | 掌握度实时更新(mastery.json) | ✅ 实测落盘 | total 13→15, mastery 62→60 |

---

## 详细核验与实测

### BLK-001: /api/knowledge/card 路径解析500错误

**文件**: `server/api/knowledge.py` 第220、230行

**核验结论**: 上轮修复仍在，无回归。
- 第220行: `kb_dir_resolved = kb_dir.resolve()` ✅
- 第230行: `rel_path = full_path.relative_to(kb_dir_resolved)` ✅（上轮由 `relative_to(kb_dir)` 修复而来）
- 另有第221行路径穿越防护（`startswith(kb_dir_resolved)` 检查，非法路径返回403）。

**curl 实测证据**（真实执行，中文路径经 URL 编码）:
```bash
$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" \
  "http://127.0.0.1:5000/api/knowledge/card?path=%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9/2025%E5%B9%B4%E5%9B%BD%E5%8A%A1%E9%99%A2%E6%94%BF%E5%BA%9C%E5%B7%A5%E4%BD%9C%E6%8A%A5%E5%91%8A%EF%BC%88%E6%9D%8E%E5%BC%BA%E6%80%BB%E7%90%86%C2%B7%E5%8D%81%E5%9B%9B%E5%B1%8A%E5%85%A8%E5%9B%BD%E4%BA%BA%E5%A4%A7%E4%B8%89%E6%AC%A1%E4%BC%9A%E8%AE%AE%EF%BC%89%E6%A0%B8%E5%BF%83%E8%80%83%E7%82%B9.md"
```
真实返回（解析后）:
```
HTTP: 200
title: 2025年国务院政府工作报告（李强总理·十四届全国人大三次会议）核心考点
module: 时政热点
path: 时政热点/2025年国务院政府工作报告（李强总理·十四届全国人大三次会议）核心考点.md
size: 4779
quality.score: 100
content_len: 2077
```

**结论**: ✅ HTTP 200 + title 字段，验收标准1通过。

---

### BLK-002: /api/quality 404/参数问题

**文件**: `server/api/knowledge.py` 第254行

**核验结论**: 上轮修复仍在，无回归。`?path=` 优先于 `?card=`：
```python
card_filter = request.args.get("path", "").strip() or request.args.get("card", "").strip()
```

**curl 实测证据**（真实执行）:
```bash
$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" \
  "http://127.0.0.1:5000/api/quality?path=<同上URL编码路径>"
```
真实返回:
```
HTTP_CODE:200
card: 时政热点/2025年国务院政府工作报告（李强总理·十四届全国人大三次会议）核心考点.md
score: 100
level: 优秀
max_score: 100
word_count: 1802
dimensions: 10个维度 = {例题:10, 分值关联:10, 口诀:15, 字数:10, 来源标注:5,
           知识点章节:15, 结构化:5, 考情分析:10, 表格:15, 重点标记:5}  (合计100)
details: ["字数充足(+10)","知识点丰富(7节,+15)","含对比表格(+15)","含记忆口诀(+15)",
         "含考情分析(+10)","标注来源(+5)","结构化列表(+5)","重点标记(+5)",
         "分值关联(+10)","含例题参考(+10)"]
```
兼容性验证 `?card=` 同样返回 HTTP 200（同结构响应）。

**结论**: ✅ HTTP 200 + 10维度评分(满分100)，验收标准2通过。

---

### BLK-003: /api/quiz/submit POST 405

**文件**: `server/api/quiz.py` 第288、304行

**核验结论**: 上轮修复仍在，无回归。
- 第288行: `@quiz_bp.route("/api/quiz/submit", methods=["POST"])` ✅
- 第304行: `user_answer = (body.get("user_answer", "") or body.get("answer", "")).strip().upper()` ✅（兼容 answer 字段）

**curl 实测证据**（真实执行，错误答案分支）:
```bash
$ curl -s -X POST -H "Content-Type: application/json" \
  -d '{"question_id":"2026-08-12-001-5","answer":"C"}' \
  -w "\n---HTTP_CODE:%{http_code}---\n" http://127.0.0.1:5000/api/quiz/submit
```
真实返回（解析后）:
```
HTTP: 200
is_correct: False          (题目5正确答案为B，提交C判错，逻辑正确)
user_answer: C
correct_answer: B
mastery_updated: True
五段式 segments(5个): correct_answer / term_breakdown / option_analysis / exam_hint / mnemonic
  correct_answer: 【正确答案】B（高质量发展）
  term_breakdown: 【术语拆解】• 「首要任务」：排在第一位、最重要的任务...
  exam_hint:      【考情提示】这是"帽子题"——考概念的准确定位...
  mnemonic:       【记忆口诀】"质量首要改动力，共同富裕是本质"
```
正确答案分支（answer=B）真实返回: `HTTP: 200, is_correct: True` ✅

**结论**: ✅ POST 200 + is_correct + 五段式解析，验收标准3通过。

---

### T-005: 知识卡质量评分引擎（10维度满分100）

**核验结论**: `server/api/knowledge.py` 第63-185行 `_score_knowledge_card()` 完整存在，10个维度（字数10/知识点章节15/表格15/口诀15/考情分析10/来源标注5/结构化5/重点标记5/分值关联10/例题10 = 满分100）。实测见 BLK-002：score=100, level=优秀, word_count=1802。

---

### T-006: 练题交互五段式解析

**核验结论**: `server/api/quiz.py` 第120-167行 `_parse_five_segment_explanation()` 完整存在，将 `【正确答案】【术语拆解】【选项辨析】【考情提示】【记忆口诀】` 解析为结构化JSON。实测见 BLK-003：返回5个段落字段。

---

### T-012: 错题追踪 (data/wrong-questions/)

**核验结论**: `server/api/quiz.py` 第30-52行 `_get_wrong_dir()` / `_save_wrong_question_file()` 完整存在，submit 错题分支（第360行）调用写入。

**curl 实测证据**（上述 answer=C 判错请求后，真实落盘）:
```bash
$ ls data/wrong-questions/
2026-08-12-001-10.json
2026-08-12-001-5.json

$ cat data/wrong-questions/2026-08-12-001-5.json
{
  "question_id": "2026-08-12-001-5",
  "module": "时政热点",
  "type": "单选题",
  "stem": "习近平总书记强调，（ ）是全面建设社会主义现代化国家的首要任务。",
  "wrong_count": 2,            ← 实测前为1，本次答错后自动+1
  "last_wrong": "2026-08-12T22:52:57.710048",
  "retry_correct": false
}
```

**结论**: ✅ 错题自动写入 data/wrong-questions/，验收标准5（前半）通过。

---

### T-010: 掌握度实时更新 (data/mastery/mastery.json)

**核验结论**: `server/api/quiz.py` 第366-393行 mastery 更新逻辑完整存在（correct_rate/mastery/trend/weak_modules 自动维护）。

**curl 实测证据**（真实对比）:
```bash
# 测试前基线: 时政热点 total=13, correct_rate=0.6154, mastery=62
# 第1次答错(answer=C)后: total=14, correct_rate=0.5714, mastery=57, trend=down
# 第2次答对(answer=B)后: total=15, correct_rate=0.6, mastery=60, trend=up

$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" http://127.0.0.1:5000/api/mastery
HTTP: 200
updated: 2026-08-12
weak_modules: ['test模块']
recommended_focus: 时政热点（核心模块，占分最高）
模块数: 15
时政热点: {"correct_rate": 0.6, "mastery": 60, "total": 15, "trend": "up", "weak": false}
```

**结论**: ✅ 掌握度随答题实时更新（total 13→15、mastery 62→60、trend down→up），验收标准5（后半）通过。

---

### 附加验证: GET /api/health

```bash
$ curl -s -w "\n---HTTP_CODE:%{http_code}---\n" http://127.0.0.1:5000/api/health
{"goal_id":"henan-szyf-20260822","status":"ok"}
HTTP_CODE:200
```
**结论**: ✅ HTTP 200 + status=ok，验收标准4通过。

### 附加验证: scripts/verify_fixes.py 交叉验证

将 verify_fixes.py 复制至 .kb-tmp/ 并将 BASE 端口改为 5000 后真实运行（运行后已清理临时文件）:
```
PASS AC1: knowledge/card path resolution
PASS AC2: quality 10-dimension scoring
PASS AC3: quiz submit with answer field
PASS AC4: mastery correct_rate updated
PASS AC5: wrong-questions/ directory (2 files)
RESULTS: 5 passed, 0 failed out of 5
ALL PASSED
```

---

## 改动文件汇总

**本轮修改文件: 无**（上轮修复经核验全部仍生效，无回归，未改动任何 server/api/ 下代码）

| 文件 | 上轮改动 | 本轮动作 | 说明 |
|------|---------|---------|------|
| `server/api/knowledge.py` | BLK-001(1行) + BLK-002(2行) | 核验无回归 | relative_to(kb_dir_resolved) + ?path=优先 |
| `server/api/quiz.py` | T-012错题目录 + answer兼容(~30行) | 核验无回归 | _save_wrong_question_file + answer字段 |

## 备份文件核验

| 备份文件 | 状态 |
|---------|------|
| `server/api/knowledge.py.bak` | ✅ 存在（上轮已有，未删除未重建） |
| `server/api/quiz.py.bak` | ✅ 存在（上轮已有，未删除未重建） |
| `server/api/mastery.py.bak` | ✅ 存在（上轮已有，未删除未重建） |
| `server/api/push.py.bak` | ✅ 存在（上轮已有，未删除未重建） |

## 验收标准对照表

| # | 验收标准 | 结果 | HTTP |
|---|---------|------|------|
| 1 | `curl /api/knowledge/card?path=时政热点/xxx.md` → 200 + title | ✅ | 200 |
| 2 | `curl /api/quality?path=时政热点/xxx.md` → 200 + 10维度评分(满分100) | ✅ | 200 |
| 3 | `curl -X POST /api/quiz/submit` question_id+answer → 200 + is_correct + 五段式解析 | ✅ | 200 |
| 4 | `curl /api/health` → 200 + status=ok | ✅ | 200 |
| 5 | 错题写入 data/wrong-questions/、掌握度更新 mastery.json 被验证 | ✅ | 实测落盘 |
| 6 | 所有修改文件有 .bak 备份 | ✅ | 4个.bak均在 |
| 7 | 产出 outputs/ta-修复报告2.md 含 curl 实测结果 | ✅ | 本文件 |

---

## 备注（供 PM/QA 参考，非本任务范围）

1. **服务器端口**: config.yaml 默认 8899；为匹配本任务单验收标准的 5000 端口，本轮以 `SERVER_PORT=5000` 环境变量覆盖启动（server/app.py 原生支持，未改代码）。服务器已后台运行于 127.0.0.1:5000。
2. **mastery.json 含历史测试脏数据**: 存在 `test模块`(weak=true)、`shizheng`、`%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9`（URL编码残留）等非标准模块名（共15个模块，配置标准为12个）。来源为历史测试写入，不影响端点功能；是否清理属数据管理范围，未擅自处理，建议由 PM-001 决策。
3. **测试产生的数据变更**: 本次实测共新增 2 条答题记录、错题 2026-08-12-001-5 wrong_count 由1增至2、时政热点 total 13→15。如需纯净基线数据请告知。
4. **上一轮 404 复现说明**: 初测时 git-bash 直接传中文参数给 curl 出现编码问题导致 404（非代码问题），改用 URL 编码后全部通过；报告中均为真实 curl 输出。
