# QA-001 工作日志 — SprintV2 BUG-1~5 修复复验

- **任务 ID**：SPRINTV2-BUGFIX
- **工号**：QA-001（赛博质检官）
- **开始时间**：2026-08-13 05:44
- **完成时间**：2026-08-13 06:05
- **复验对象**：TA-001 对 BUG-1~5 的修复（`outputs/ta-修复报告-SprintV2.md`）
- **状态**：✅ 完成（结论：通过）

---

## 一、执行步骤（增量追加）

### 1. 环境核查与基线确认（05:44-05:46）
- 加载 `study-mentor-dashboard` skill + `cdp-verification-recipe` 参考。
- 确认 Flask localhost:8899 健康（PID 11524 期间中断，后重启为 PID 12568）。
- headless Chrome CDP 9222 就绪（期间掉线一次，用 `chrome.exe --headless=new --remote-debugging-port=9222 --user-data-dir=.kb-tmp/chrome-prof` 重启）。
- 基线确认：mastery 12 模块 / sum total=25；answer-records=19 条；wrong 列表=3 条；wrong-questions/ 目录仅 001-10、001-5 两文件。
- 代码改动核实（grep）：platform.html colorMode alpha=1、半径 0.40、偏移 +13（draw+mouseMoved 双处）、submitAnswerToServer、Date.now()+8h；quiz.py question_id 保留、submit 端点、wrong_count 调用方传值；plan.py _today_shanghai。
- 测试数据备份至 `.kb-tmp/qa-rv-backup/`（mastery/answer-records/wrong-questions/json + wrong-questions 目录）。

### 2. 只读复验（05:47-05:55，脚本 `.kb-tmp/qa_rv_bugfix_readonly.py`）
- **BUG-1**：CDP getImageData 采样雷达画布：maxAlpha=255、visiblePct=0.977%、coloredPct=0.014%；CDP 真实鼠标事件悬停 → tooltip「三农与乡村振兴：0%」opacity=1；全 DOM 玫红扫描 roseHits=0。截图 `outputs/qa-rv1-radar-visible.png`。
- **BUG-4**：`.plan-day.today` 存在、data-date=2026-08-13、【今天】标记；前端 Date.now()+8h=2026-08-13；后端 /api/plan/today plan.date=2026-08-13。截图 `outputs/qa-rv4-plan-today.png`。
- **BUG-5**：12 标签坐标全部 inside、outCount=0；顶/右/底/左极值标签邻域像素非透明 82~118、maxAlpha 153~170。截图 `outputs/qa-rv5-radar-labels.png`。
- **回归巡检**：4 nav-tab + 考点汇总按钮逐页点击——无玫红、无空白死区、可见元素正常；浏览器 fetch 12 个 API 全 200；console error 0 / exception 0。截图 `outputs/qa-rv-regression-summary.png`。
- 过程问题：CDP.evaluate 不支持第二参数（改用内嵌 JSON 字符串）；"summary" tab 不存在（考点汇总是知识宝库内按钮，已修正巡检方式）。

### 3. 写库复验 BUG-2/3（05:55-06:00，脚本 `.kb-tmp/qa_rv_bugfix_quiz.py`）
- **BUG-2**：浏览器完整练题流程：12 道单选全作答（Q1 故意答错）→ 完成练题 → 结果页「学习记录已同步服务端 12 条」（syncOk=12/fail=0）→ 2 秒后服务端核对：wrong 列表 3→4、Q1 落库 wrong_count=1、data/wrong-questions/2026-08-12-001-0.json 生成、answer-records 19→31。截图 `outputs/qa-rv2-quiz-sync.png`。
- **BUG-3**：第二轮 Q1 再答错一次 → 列表 wrong_count=2 == 文件 wrong_count=2（双口径一致）。
- 过程问题：结果页正则 `[^\n]*` 被 Python 转义成换行导致 JS SyntaxError，改为 `[^\\n]*` 修复；首次运行污染数据后先还原再重跑。

### 4. 报告审查（06:00-06:02）
- 抽查 TA 修改清单 9 项：app.py 注册 plan_bp ✅、overview.py daily_plans ✅、requirements fsrs ✅、两脚本存在 ✅、quiz-bank 五字段 ✅、mastery fsrs 12/12 ✅、platform.html/quiz.py/plan.py 关键改动 ✅ —— 全部属实。

### 5. 数据还原与基线复验（06:03）
- 删除测试新增 `data/wrong-questions/2026-08-12-001-0.json`；还原 mastery.json / answer-records.json / wrong-questions.json 三份备份。
- 还原后实测：mastery 12 模块 total=25、records=19、wrong 列表=3、目录 2 文件（001-10/001-5）✅ 与验收基线完全一致。

### 6. 产出（06:04-06:05）
- `outputs/qa-复验报告-SprintV2-BUGFIX.md`（复验结论 + 逐 Bug 复验表 + 回归 + 观察项 + 截图索引）。
- 本日志 `work-logs/active/QA-001-SPRINTV2-BUGFIX.md`。

---

## 二、复验结论速览

| Bug | 结果 | 关键证据 |
|-----|------|----------|
| BUG-1 雷达图全透明 | ✅ 通过 | maxAlpha=255、visiblePct=0.977%、tooltip 生效、0 玫红 |
| BUG-2 练题未接服务端 | ✅ 通过 | 结果页同步 12 条、wrong 3→4、records+12、文件落库 |
| BUG-3 错题计数双口径 | ✅ 通过 | 连错 2 次：列表=文件=2 |
| BUG-4 计划【今天】UTC | ✅ 通过 | 前后端均 2026-08-13（东八区） |
| BUG-5 雷达标签出界 | ✅ 通过 | outCount=0、极值标签像素非透明 |
| 回归 | ✅ 通过 | 5 视图无玫红/空白/死区、12 API 200、console 0 错误 |
| 数据基线 | ✅ 还原 | total=25、records 19、wrong 列表 3、目录 2 文件 |

## 三、产出文件清单

| 文件 | 说明 |
|------|------|
| `outputs/qa-复验报告-SprintV2-BUGFIX.md` | 正式复验报告（含截图索引） |
| `outputs/qa-rv1-radar-visible.png` | BUG-1 证据 |
| `outputs/qa-rv2-quiz-sync.png` | BUG-2/3 证据 |
| `outputs/qa-rv4-plan-today.png` | BUG-4 证据 |
| `outputs/qa-rv5-radar-labels.png` | BUG-5 证据 |
| `outputs/qa-rv-regression-summary.png` | 回归巡检 |
| `.kb-tmp/qa_rv_bugfix_readonly.py` / `qa_rv_bugfix_quiz.py` | 复验脚本（可复用） |
| `.kb-tmp/qa-rv-readonly.json` / `qa-rv-quiz.json` | 原始证据 JSON |
| `.kb-tmp/qa-rv-backup/` | 测试数据备份（还原后保留，供追溯） |

## 四、遇到的问题与处理

1. **CDP 9222 掉线**（Flask 亦随之中断）：重启 headless Chrome（--user-data-dir 复用 chrome-prof）+ 重启 Flask（PID 12568）后恢复。
2. **CDP.evaluate 双参数报错**：运行时不能传 arguments，改用 f-string 内嵌 JSON。
3. **"summary" tab 不存在**：平台 5 视图的"考点汇总"是知识宝库页内按钮（renderKnowledgeSummary），巡检方式修正。
4. **JS 正则转义**：Python 三引号内 `\n` 被转义破坏正则，用 `\\n` 修复。
5. **测试数据污染**：首轮 BUG-2/3 运行后数据 +13 条，按配方"先测后还"流程还原重跑，最终基线无损。

## 五、遗留事项（转交/建议）

- O2 观察项：wrong 列表 001-1 无对应文件（历史数据差异），建议后续归一化（非本次范围）。
- 多选交互（第 13-15 题）仍在 backlog R4，复验确认前端按单选渲染（预期行为）。
