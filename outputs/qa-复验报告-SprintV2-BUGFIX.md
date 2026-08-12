# QA-001 复验报告 — SprintV2 BUG-1~5 修复（TA-001）

> 工号 QA-001 / 任务 SPRINTV2-BUGFIX / 日期 2026-08-13 / 复验对象 `outputs/ta-修复报告-SprintV2.md`
> 复验方式：**真实 headless Chrome + CDP（端口 9222）像素采样与流程驱动**，禁止仅 curl；服务端落库以 API + 本地文件双核对。

---

## 一、复验结论

# ✅ 通过

TA-001 对 BUG-1~5 的五项修复**全部验证通过**；回归（5 视图 + 12 API + 数据基线）无异常；**未发现新增阻塞问题**（仅有 4 项非阻塞观察项，见第五节）。测试产生的数据已全部清理还原，基线完好。

| 项目 | 结果 |
|------|------|
| BUG-1 雷达图可见 | ✅ 通过（maxAlpha=255，visiblePct=0.977%） |
| BUG-2 练题全流程服务端落库 | ✅ 通过（syncOk=12，wrong 3→4，records+12） |
| BUG-3 错题计数双口径一致 | ✅ 通过（连错2次：列表=文件=2） |
| BUG-4 每日计划【今天】东八区 | ✅ 通过（前后端均为 2026-08-13） |
| BUG-5 雷达 12 标签在画布内 | ✅ 通过（outCount=0，极值标签像素非透明） |
| 回归：5 视图 + API + 基线 | ✅ 通过（无玫红/空白/死区，12 API 全 200） |
| 报告审查（六节结构+文件清单） | ✅ 通过（抽查 9 项改动全部属实） |

---

## 二、逐 Bug 复验记录

### BUG-1（🔴 高）雷达图全透明 —— ✅ 通过

| 项 | 内容 |
|----|------|
| 复验方法 | headless Chrome 打开 `/` 总览视图 → CDP `getImageData` 采样 `#mastery-canvas-wrap canvas`（950×240）→ CDP `Input.dispatchMouseEvent` 悬停 → 全 DOM computed-style 玫红扫描 |
| 证据 | ① 像素采样：`maxAlpha=255`、`visiblePct=0.977%`、`coloredPct=0.014%`（均 >0，雷达图真实可见）；② 悬停顶部标签后 tooltip 显示 `三农与乡村振兴：0%`、`opacity=1`（交互生效）；③ 玫红元素扫描 `roseHits=0`（页面无 RGB(245,10,93)） |
| 代码核实 | `static/platform.html:1032` `p.colorMode(p.HSB, 360, 100, 100, 1)` —— alpha 上限与传入 0.x 同量纲，与 TA 声称一致 |
| 截图 | `outputs/qa-rv1-radar-visible.png` |

> 备注：TA 声称 coloredPct=2.63%，QA 实测 0.014%——因 QA 判定更严格（排除玫红与灰色像素）。两者均证明"存在非透明彩色像素"，验收标准（可见像素>0）通过，不构成问题。

### BUG-2（🟠 中）练题前端未接服务端 —— ✅ 通过

| 项 | 内容 |
|----|------|
| 复验方法 | 浏览器走完整练题流程：练题工坊 → 开始练题 → 逐题作答（Q1 故意答错、其余答对）→ 完成练题 → 结果页 → 核对服务端落库（/api/quiz/wrong、answer-records、data/wrong-questions/） |
| 证据 | ① 结果页提示 **「学习记录已同步服务端 12 条」**（`syncOk=12, fail=0`，console 无错误）；② 答错 Q1（`2026-08-12-001-0`）后：wrong 列表 **3→4**、Q1 `wrong_count=1`；③ `data/wrong-questions/2026-08-12-001-0.json` 2 秒内生成（含 module/type/stem/last_wrong）；④ answer-records **19→31（+12）** |
| 代码核实 | `quiz.py:284` `q_copy["question_id"] = q.get("_id","")`（保留 ID）；`quiz.py:295` POST `/api/quiz/submit`；`platform.html:1468` `submitAnswerToServer()` 异步 fire-and-forget、失败降级本地判分；结果页 `renderQuizResult` 显示同步条数 —— 与 TA 声称一致 |
| 截图 | `outputs/qa-rv2-quiz-sync.png` |

### BUG-3（🟡 低）错题计数双口径不一致 —— ✅ 通过

| 项 | 内容 |
|----|------|
| 复验方法 | 浏览器对同一题（Q1）连续答错 2 次（两轮练题各错 1 次），对比 `/api/quiz/wrong` 列表值与 `data/wrong-questions/2026-08-12-001-0.json` 文件值 |
| 证据 | 连错 2 次后：列表 `wrong_count=2` **==** 文件 `wrong_count=2`（`consistent=true`，且符合"连错两次=2"预期） |
| 代码核实 | `quiz.py:35` `_save_wrong_question_file(question_id, record, wrong_count=None)`：先剔除 record 内 wrong_count（`:52`），再以调用方累计值写入（`:54`）；列表侧 `existing[0]["wrong_count"]+1` 为唯一累计口径（`:365-370`）—— 与 TA 声称一致 |
| 截图 | 复用 `outputs/qa-rv2-quiz-sync.png`（第二轮结果页，错题回顾 15 题） |

### BUG-4（🟡 低）每日计划【今天】UTC 日期 —— ✅ 通过

| 项 | 内容 |
|----|------|
| 复验方法 | 浏览器切每日计划 tab 检查高亮元素与日期；curl 后端 `/api/plan/today` 比对 date 字段（东八区 2026-08-13） |
| 证据 | ① 浏览器：`.plan-day.today` 存在、`data-date="2026-08-13"`、文本含 **【今天】**；② 前端口径 `Date.now()+8h → 2026-08-13`；③ 后端 `/api/plan/today` 返回 `plan.date="2026-08-13"` |
| 代码核实 | `platform.html:1269` `new Date(Date.now()+8*3600*1000).toISOString().slice(0,10)`；`plan.py:31-35` `_today_shanghai()` = `(datetime.now(timezone.utc)+SHANGHAI_OFFSET).date()`，`plan_today()` 以其为当天 —— 与 TA 声称一致 |
| 截图 | `outputs/qa-rv4-plan-today.png` |

### BUG-5（🟡 低）雷达 12 标签出界 —— ✅ 通过

| 项 | 内容 |
|----|------|
| 复验方法 | CDP 按前端相同几何（`r=min(w,h)*0.40`、偏移 `r+13`、`-HALF_PI + i/n*2π`）计算 12 标签坐标并断言在画布内；对顶/右/底/左 4 个极值标签做 24×24 邻域像素采样证明文字画出 |
| 证据 | ① 12/12 标签 `inside=true`、**outCount=0**（y 范围 11~229，画布高 240）；② 极值标签邻域非透明像素 82~118 个、maxAlpha 153~170（文字真实渲染）；③ 悬停命中（BUG-1 部分）同样命中标签，证明 mouseMoved 与 draw 坐标一致 |
| 代码核实 | `platform.html:1022` `r = Math.min(p.width,p.height)*0.40`；`:1071-1072`（draw）与 `:1122-1123`（mouseMoved）两处均 `r+13` —— draw/悬停同步修改，与 TA 声称一致 |
| 截图 | `outputs/qa-rv5-radar-labels.png` |

---

## 三、回归验证

### 3.1 五个视图（真实浏览器逐页点击巡检）

| 视图 | active | 内容量 | 玫红 | 空白/死区 | console |
|------|--------|--------|------|-----------|---------|
| 学案总览 | ✅ | 可见元素 105、主区文本 153 | 0 | 无 | 0 错误 |
| 知识宝库 | ✅ | 可见元素 123、文本 2873 | 0 | 无 | 0 错误 |
| 每日计划 | ✅ | 可见元素 19、plan-day 1 个（含【今天】） | 0 | 无 | 0 错误 |
| 练题工坊 | ✅ | 可见元素 23、开始界面正常 | 0 | 无 | 0 错误 |
| 考点汇总（宝库内按钮） | ✅ | 文本 1956、含标题、无加载失败 | 0 | 无 | 0 错误 |

- 全页 computed-style 玫红扫描：**roseHits=0**（5 视图均无 RGB(245,10,93)）
- 全程 console error **0**、Runtime.exception **0**
- 截图：`outputs/qa-rv-regression-summary.png`

### 3.2 关键 API（浏览器环境 fetch，非 curl）

| 端点 | 状态 | | 端点 | 状态 |
|------|------|-|------|------|
| /api/health | 200 | | /api/quiz/wrong | 200 |
| /api/knowledge | 200 | | /api/quiz/stats | 200 |
| /api/mastery | 200 | | /api/plan/today | 200 |
| /api/overview | 200 | | /api/daily-plan | 200 |
| /api/quiz/questions | 200 | | /api/quality | 200 |
| /api/daily-plan?date=2026-08-13 | 200 | | /api/summary | 200 |

**12/12 全 200，无 500。**

### 3.3 数据基线还原确认

测试前备份于 `.kb-tmp/qa-rv-backup/`（mastery / answer-records / wrong-questions / wrong-questions 目录），测试后删除新增错题文件并还原三个 JSON：

| 基线项 | 验收值 | 测试后实测 | 还原后实测 |
|--------|--------|-----------|-----------|
| mastery 模块数 | 12 | 12 | **12** ✅ |
| mastery total（累计练题） | 25 | 38（+13） | **25** ✅ |
| answer-records 条数 | 19 | 32（+13） | **19** ✅ |
| wrong-questions 列表 | 3 | 4（+Q1） | **3** ✅ |
| wrong-questions/ 目录文件 | 仅 2 个历史文件（001-10、001-5） | 3（+001-0） | **2** ✅ |

> 说明：复验产生的 001-0 错题文件、13 条答题记录、mastery 增量已全部清理还原；服务器进程（Flask PID 12568）与 headless Chrome（CDP 9222）保持运行。

---

## 四、报告审查（TA-001 修复报告）

- **六节结构**：执行摘要 / 逐任务详述 / QA 打回 Bug 修复表 / 回归验证 / 修改文件清单 / 遗留问题 —— 完整 ✅
- **修改文件清单抽查（9 项全部属实）**：
  1. `platform.html` colorMode alpha 上限 1、半径 0.40、标签偏移 +13（draw 与 mouseMoved 两处）✅
  2. `quiz.py` question_id 保留、/api/quiz/submit 端点、wrong_count 调用方传值 ✅
  3. `plan.py` _today_shanghai()、/api/plan/today ✅
  4. `app.py` 注册 plan_bp ✅
  5. `overview.py` daily_plans 字段 ✅
  6. `requirements.txt` fsrs>=6.3 ✅
  7. `scripts/clean_mastery_modules.py`、`scripts/migrate_quiz_five_fields.py` 存在 ✅
  8. quiz-bank 15 题五字段（抽查 Q1：correct_answer/term_breakdown/option_analysis/exam_hint/mnemonic 齐全）✅
  9. mastery.json 12 模块均含 fsrs 对象 ✅

---

## 五、新增问题与观察项（均非阻塞）

| # | 级别 | 说明 |
|---|------|------|
| O1 | ℹ️ 观察 | 题库第 13-15 题（answer=ABD/AB/ABC 多选）前端仍按单选渲染——TA 已列入 backlog（R4），本次复验跳过不答，未污染数据；与修复无关 |
| O2 | ℹ️ 观察 | wrong 列表含 `001-1`（cnt=1）但 `data/wrong-questions/` 无对应文件——BUG-3 修复前的历史数据差异（修复后写入路径均成对）；建议后续做一次历史数据归一（TA 报告中"6文件逐一一致"指修复后的新写入，复验已确认新写入一致） |
| O3 | ℹ️ 观察 | coloredPct 数值口径：TA 声称 2.63% vs QA 实测 0.014%（判定条件差异），均 >0，不构成问题 |
| O4 | ℹ️ 观察 | 每日计划时间线仅 1 张卡片（data/daily-plan/ 仅 2026-08-13.json）——数据现状，非缺陷 |

---

## 六、截图索引

| 截图 | 对应检查项 |
|------|-----------|
| `outputs/qa-rv1-radar-visible.png` | BUG-1 雷达图可见 + 悬停 tooltip |
| `outputs/qa-rv2-quiz-sync.png` | BUG-2 练题结果页「学习记录已同步服务端 12 条」+ 错题回顾 |
| `outputs/qa-rv4-plan-today.png` | BUG-4 每日计划【今天】高亮（2026-08-13） |
| `outputs/qa-rv5-radar-labels.png` | BUG-5 雷达 12 标签在画布内 |
| `outputs/qa-rv-regression-summary.png` | 回归：5 视图巡检 |

---

*QA-001 赛博质检官 · 2026-08-13 · 复验证据 JSON：`.kb-tmp/qa-rv-readonly.json`、`.kb-tmp/qa-rv-quiz.json`*
