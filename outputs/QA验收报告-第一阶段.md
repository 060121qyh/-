# QA验收报告 — 第一阶段（T-001 ~ T-003）

| 字段 | 内容 |
|------|------|
| **审查编号** | QA-20260812-001 |
| **审查人** | QA-001（赛博质检官） |
| **被审查人** | TA-001（技术执行） |
| **审查时间** | 2026-08-12 22:07 |
| **审查范围** | T-001（项目骨架）、T-002（Flask应用）、T-003（数据文件） |
| **服务器** | http://localhost:8899（运行中 ✅） |
| **审查结论** | ⚠️ **有条件通过 — 1个Critical缺陷需修复后重新验收** |

---

## 一、验收清单总览

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 功能完整性（API端点） | ⚠️ 部分通过 | 6/7 端点正常，1个Critical缺陷 |
| 2 | 代码规范 | ✅ 通过 | 无硬编码密钥，错误处理完整 |
| 3 | 边界条件 | ✅ 通过 | 空数据/缺失参数/路径遍历/404均正确处理 |
| 4 | PM规格对照 | ✅ 通过 | 0.0.0.0:8899、CORS头、health端点均符合 |
| 5 | 数据迁移验证 | ⚠️ 部分通过 | 知识卡完整（11张），题库合法；模块覆盖不足 |

---

## 二、API端点测试详情

### 2.1 GET端点（全部正常）

| 端点 | 方法 | 状态码 | 返回 | 验证 |
|------|------|--------|------|------|
| `/api/health` | GET | 200 | `{"status":"ok","goal_id":"henan-szyf-20260822"}` | ✅ |
| `/api/knowledge` | GET | 200 | `{"total":11,"cards":[...]}` — 11张知识卡 | ✅ |
| `/api/quiz` | GET | 200 | `{"total":15,"quizzes":[...]}` — 1个题库文件 | ✅ |
| `/api/quiz/questions` | GET | 200 | `{"total":15,"questions":[...]}` — 15道题 | ✅ |
| `/api/mastery` | GET | 200 | `{"modules":{...12模块...},"updated":"2026-08-12"}` | ✅ |
| `/api/overview` | GET | 200 | 距考10天, KB=11, 题库=15, 12模块 | ✅ |
| `/api/push` | GET | 200 | `{"configured":false,"status":"not_configured"}` | ✅ |

### 2.2 POST端点

| 端点 | 方法 | 状态码 | 验证 |
|------|------|--------|------|
| `/api/mastery/update` | POST | 200 | 正确更新掌握度（逻辑验证通过，见下方） | ✅ |
| `/api/push/test` | POST | 501 | 桩实现，预期行为 | ✅ |

**掌握度更新逻辑验证**（4步序列测试）：
```
正确+正确+错误 → mastery=75%, rate=0.75, total=4
新模块     → mastery=0%, rate=0.0, total=1（自动初始化）
趋势判断   → up/down/flat 均正确
```

### 2.3 🔴 CRITICAL: 知识卡详情端点完全不可用

**端点**: `GET /api/knowledge/card?path=...`

**严重程度**: 🔴 Critical — 功能阻断

**现象**: 所有5个模块的知识卡详情请求均返回 HTTP 500，无一成功。

```
测试结果: 0/5 OK, 5/5 FAIL
  三农与乡村振兴 → 500
  中共党史       → 500
  中国特色社会主义理论 → 500
  公文写作       → 500
  时政热点       → 500
```

**根因**: `server/api/knowledge.py` 第94-96行的路径安全检查存在 Windows 兼容性缺陷：

```python
full_path = full_path.resolve()
kb_dir_resolved = kb_dir.resolve()
if not str(full_path).startswith(str(kb_dir_resolved)):
    return jsonify({"error": "非法的路径"}), 403
```

`Path("data/knowledge-cards").resolve()` 在此 Windows 环境下返回的是相对路径 `data\knowledge-cards`，而 `(Path("data/knowledge-cards") / card_path).resolve()` 返回的是绝对路径 `D:\...\data\knowledge-cards\...`，导致 `str.startswith()` 比较始终失败（随后被外层 `except` 捕获为500而非403，因为 `return` 后面抛了异常）。

**建议修复**: 使用 `PROJECT_ROOT` 构建绝对路径，避免依赖 CWD 的 `resolve()`：
```python
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
kb_dir = PROJECT_ROOT / "data" / "knowledge-cards"
```

---

## 三、边界条件测试

| 测试场景 | 预期 | 实际 | 结果 |
|----------|------|------|------|
| 缺 path 参数 (`/api/knowledge/card`) | 400 | `{"error":"缺少 path 参数"}` 400 | ✅ |
| 路径遍历 (`?path=../../../etc/passwd`) | 403 | `{"error":"非法的路径"}` 403 | ✅ |
| 不存在的知识卡 (`?path=nonexistent.md`) | 404 | `{"error":"知识卡不存在"}` 404 | ✅ |
| 空模块筛选 (`?module=nonexistent`) | 200 空列表 | `{"total":0,"cards":[]}` 200 | ✅ |
| POST 空请求体 | 400 | `{"error":"请求体为空"}` 400 | ✅ |
| POST 缺 correct 字段 | 400 | `{"error":"缺少 correct 参数"}` 400 | ✅ |
| POST 缺 module 字段 | 400 | `{"error":"缺少 module 参数"}` 400 | ✅ |
| 无效难度值 (`?difficulty=abc`) | 200 不过滤 | 返回全部题目 | ✅ |
| 不存在模块筛选 (`?module=noexist`) | 200 空列表 | `{"total":0,"questions":[]}` | ✅ |
| 不存在的API端点 | 404 | `{"error":"Not found"}` 404 | ✅ |

**结论**: 边界条件处理优秀，错误信息清晰且为中文。

---

## 四、代码规范审查

### 4.1 安全隐患检查 ✅

| 检查项 | 结果 |
|--------|------|
| 硬编码密钥/密码 | ✅ 无 — `FEISHU_APP_SECRET` 仅从环境变量读取 |
| 路径遍历防护 | ✅ knowledge.py 有 `resolve()+startswith()` 防护（虽然当前有Bug） |
| SQL注入风险 | N/A — 无数据库 |
| CORS配置 | ✅ `Access-Control-Allow-Origin: *`，`Allow-Methods` 完整 |

### 4.2 代码结构 ✅

- **模块化设计优秀**: Blueprint 分离 (`knowledge/quiz/mastery/push/overview`)，各API文件职责单一
- **配置管理**: `config.yaml` + 环境变量覆盖，设计合理
- **错误处理**: 每个端点有 try/except，返回统一JSON格式
- **代码量**: 总计 ~540 行（不含数据），精简无冗余

### 4.3 发现的小问题

| 位置 | 问题 | 严重度 |
|------|------|--------|
| `mastery.py:126` | `data["updated"] = "2026-08-12"` 硬编码日期 | 🟢 Minor |
| `knowledge.py:70-78` | `except Exception` 吞掉所有异常，不利于调试 | 🟢 Minor |
| `quiz.py:36-37` | `except Exception: continue` 静默跳过损坏的JSON | 🟢 Minor |
| `app.py:73` | `.replace("data/knowledge-cards", "data")` 字符串替换不够健壮 | 🟡 Moderate |

---

## 五、PM规格对照

| PM规格要求 | 实现 | 状态 |
|------------|------|------|
| 服务器绑定 `0.0.0.0:8899` | config.yaml `host: "0.0.0.0"`, `port: 8899` | ✅ |
| CORS 头 | `Access-Control-Allow-Origin: *` | ✅ |
| `/api/health` 端点 | 返回 `{"status":"ok","goal_id":"..."}` | ✅ |
| 知识卡API | `/api/knowledge` + `/api/knowledge/card` | ⚠️ card端点不可用 |
| 题库API | `/api/quiz` + `/api/quiz/questions` | ✅ |
| 掌握度API | `/api/mastery` + `/api/mastery/update` | ✅ |
| 总览API | `/api/overview`（含倒计时、统计） | ✅ |

---

## 六、数据迁移验证

### 6.1 知识卡

| 模块 | 卡片数 | 总大小 | 状态 |
|------|--------|--------|------|
| 时政热点 | 3 | 20,708 bytes | ✅ |
| 中国特色社会主义理论 | 1 | 4,919 bytes | ✅ |
| 马克思主义哲学 | 1 | 4,739 bytes | ✅ |
| 法律 | 1 | 5,584 bytes | ✅ |
| 中共党史 | 1 | 3,383 bytes | ✅ |
| 三农与乡村振兴 | 1 | 2,864 bytes | ✅ |
| 经济常识 | 1 | 2,916 bytes | ✅ |
| 公文写作 | 1 | 3,067 bytes | ✅ |
| 河南省情 | 1 | 2,449 bytes | ✅ |
| **历史人文** | **0** | — | 🔴 缺失 |
| **地理科技** | **0** | — | 🔴 缺失 |
| **毛泽东思想** | **0** | — | 🔴 缺失 |
| **合计** | **11** | **50,629 bytes** | 9/12 模块已覆盖 |

### 6.2 题库

- **文件**: `data/quiz-bank/2026-08-12-001.json`（31KB）
- **题目数**: 15 题
- **结构合法性**: ✅ 所有题目包含 `stem/options/answer/type/module/difficulty/explanation` 七字段
- **模块分布**: 时政热点 100%，其他11模块 0%
- **题型分布**: 单选题 12, 多选题 2, 不定项选择题 1

**⚠️ 数据格式注意**: Q12-Q14（多选题/不定项）的 `answer` 字段为字符串拼接（"ABD","AB","ABC"），非数组格式 `["A","B","D"]`。前端需做字符串拆分处理。

### 6.3 掌握度数据

- **文件**: `data/mastery/mastery.json`（存在且合法JSON）
- **模块数**: 12（全覆盖 config.yaml 中所有模块）
- **初始状态**: 全0（正确）

---

## 七、审查结论与建议

### 结论: ⚠️ 有条件通过

**必须修复（打回重验）**:
> 🔴 **C-001**: `/api/knowledge/card` 端点路径解析Bug导致全部请求500错误。修复后QA-001重新验收。

**建议修复（不阻塞通过）**:
> 🟡 **M-001**: 补充 历史人文、地理科技、毛泽东思想 三个模块的知识卡（交由KM-001）
> 🟡 **M-002**: 补充其他11个模块的题库（交由KM-001）
> 🟡 **M-003**: `app.py:73` 的 `DATA_DIR` 解析改用 `pathlib` 而非字符串replace
> 🟢 **m-001**: `mastery.py:126` 日期改用 `datetime.date.today().isoformat()`
> 🟢 **m-002**: `quiz.py:36-37` 的静默异常增加日志记录
> 🟢 **m-003**: 多选题 `answer` 字段建议统一为数组格式

### 优秀实践（值得保留）
- Blueprint模块化架构，扩展性好
- 统一的错误处理与中文错误消息
- 环境变量覆盖配置文件的设计
- 路径遍历防护意识
- 掌握度更新逻辑的 `trend`/`weak` 自动判定

---

*报告生成: QA-001 | 2026-08-12 22:07 | 审查耗时: 约25分钟*
