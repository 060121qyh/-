# TA-001 修复报告 — Sprint V2

> 工号 TA-001 / 任务 SPRINTV2 / 日期 2026-08-13 / 依据 PM-001 任务单 coordination/inbox/pm-to-ta-SPRINTV2.json

## 一、执行摘要（6项任务完成状态表）

| # | 任务 | 优先级 | 状态 | 关键产出 |
|---|------|--------|------|----------|
| 1 | 玫红背景修复 | 🔴 | ✅ | static/platform.html：删除 p.background(245,10,93)，改 p.clear()；雷达图悬停交互；p5 加载轮询；CDP 像素采样透明率97.8%，截图 outputs/verify-1-overview-fixed.png |
| 2 | 全页面巡检 | 🔴 | ✅ | 修复4个前置bug（知识宝库 cards.map 白屏→改拉 /api/knowledge 数组；练题工坊 Array.isArray 恒false→适配 {questions:[]}；quiz.total 不存在→quiz_bank.total_questions；雷达图透明 BUG-1 见第三节）；5视图全部有内容 |
| 3 | 五字段迁移 | 🟡 | ✅ | scripts/migrate_quiz_five_fields.py：15题全部拆出 correct_answer/term_breakdown/option_analysis/exam_hint/mnemonic（explanation 保留兼容）；空字段 term_breakdown×1、option_analysis×2（题10/15 源数据缺段） |
| 4 | py-fsrs 接入 | 🟡 | ✅ | requirements.txt +fsrs>=6.3；mastery.json 12模块加 fsrs 对象（state/due/stability/difficulty/last_review/reps/step）；mastery.py FSRS 读写+复习推进（/api/mastery/update 实测 Review→Learning） |
| 5 | 脏数据清洗 | 🟡 | ✅ | scripts/clean_mastery_modules.py：shizheng+%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9 合并进"时政热点"（mastery 48/total 25），test模块删除；12模块对齐 goal.yaml；weak_modules=['时政热点'] |
| 6 | 每日计划 | 🟢 | ✅ | server/api/plan.py 新建：GET /api/plan/today（距考9天/可用3小时/到期复习时政热点+11新模块建议）；data/daily-plan/2026-08-13.json 生成；app.py 注册蓝图；overview.py 加 daily_plans |

## 二、逐任务详述

### 任务1：玫红背景修复（🔴）

- **修改文件**：`D:\乔一禾\项目工作区\多Agent学习导师\static\platform.html`
- **实现方案**：删除 `p.background(245,10,93)` 玫红整屏填充，改为 `p.clear()` 保留画布透明；同步补上雷达图悬停交互（mouseMoved 命中检测）与 p5 加载轮询（确保 p5.js 就绪后再初始化）。
- **验证证据**：CDP 像素采样透明率 97.8%（背景不再玫红、不再遮挡下方 DOM），截图 `outputs/verify-1-overview-fixed.png`。

### 任务2：全页面巡检（🔴）

- **修改文件**：`static/platform.html`、`server/api/quiz.py`、`server/api/overview.py` 等
- **实现方案**：对总览/知识宝库/每日计划/练题工坊/学习报告 5 视图逐页巡检，修复 4 个前置 bug：
  1. 知识宝库 `cards.map` 白屏 → 改为拉取 `/api/knowledge` 返回数组后渲染；
  2. 练题工坊 `Array.isArray` 恒 false → 适配服务端 `{questions:[]}` 结构；
  3. `quiz.total` 不存在 → 改用 `quiz_bank.total_questions`；
  4. 雷达图全透明（BUG-1，详见第三节）。
- **验证证据**：5 视图全部渲染有内容，浏览器 console error 0。

### 任务3：五字段迁移（🟡）

- **产出脚本**：`D:\乔一禾\项目工作区\多Agent学习导师\scripts\migrate_quiz_five_fields.py`
- **实现方案**：对题库 `data/quiz-bank/2026-08-12-001.json` 15 道题全部拆出五字段 `correct_answer / term_breakdown / option_analysis / exam_hint / mnemonic`，`explanation` 保留兼容旧前端。
- **验证证据**：15/15 题迁移完成；空字段：term_breakdown×1、option_analysis×2（第 10/15 题源数据缺段，属源数据问题，非迁移缺陷）。

### 任务4：py-fsrs 接入（🟡）

- **修改文件**：`requirements.txt`（+`fsrs>=6.3`）、`data/mastery/mastery.json`、`server/api/mastery.py`
- **实现方案**：mastery.json 12 个模块各加 `fsrs` 对象（state/due/stability/difficulty/last_review/reps/step）；mastery.py 增加 FSRS 读写与复习推进逻辑。
- **验证证据**：`/api/mastery/update` 实测状态 Review→Learning，复习调度正常推进。

### 任务5：脏数据清洗（🟡）

- **产出脚本**：`D:\乔一禾\项目工作区\多Agent学习导师\scripts\clean_mastery_modules.py`
- **实现方案**：将 `shizheng`、`%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9`（URL 编码的"时政热点"）合并进规范名"时政热点"（mastery 48 / total 25）；删除 `test` 测试模块。
- **验证证据**：清洗后 mastery 恰为 12 模块，与 `goal.yaml` 完全对齐；`weak_modules=['时政热点']`。

### 任务6：每日计划（🟢）

- **产出文件**：`D:\乔一禾\项目工作区\多Agent学习导师\server\api\plan.py`（新建）、`data/daily-plan/2026-08-13.json`（生成）
- **实现方案**：新增 `GET /api/plan/today` 端点——距考试 9 天 / 今日可用 3 小时 / 到期复习时政热点 + 11 个新模块建议；`app.py` 注册蓝图；`overview.py` 汇总接口增加 `daily_plans` 字段。
- **验证证据**：浏览器每日计划页正常展示今日计划与【今天】高亮。

## 三、QA 打回 Bug 修复（BUG-1~5，来自 outputs/qa-验收报告-SprintV2.md）

| Bug | 级别 | 根因 | 修复方案 | 验证证据 |
|-----|------|------|----------|----------|
| BUG-1 雷达图全透明 | 🔴高 | HSB colorMode alpha max=100 但传 0.x 值 → alpha≈12/255 可见像素0% | p.colorMode(p.HSB,360,100,100,100)→alpha上限1（与传入0.x同量纲） | CDP getImageData：修复后 maxAlpha=255、visiblePct=0.977%、coloredPct=2.63%，截图 outputs/verify-5-radar-visible.png |
| BUG-2 练题前端未接服务端 | 🟠中 | GET questions 剥离 _id + 前端纯本地判分 | 后端 list_questions 保留 question_id；前端 submitAnswerToServer() 异步 POST /api/quiz/submit（失败降级本地判分）；结果页显示同步条数 | 浏览器完整练15题 syncOk=15；答错Q1后2秒内服务端落库（wrong 3→4）；截图 outputs/verify-6-quiz-synced.png |
| BUG-3 错题计数双口径 | 🟡低 | _save_wrong_question_file 单次record覆盖后自增与列表统计不同源 | 弃用自增，改由调用方传累计值 wrong_count= | 连续答错两次：文件=列表=3；6个文件逐一一致 |
| BUG-4 计划页UTC日期 | 🟡低 | 前端用 Date 的 UTC 日期高亮"今天" | 前端 Date.now()+8h；后端 plan.py _today_shanghai()（UTC+8，Windows免tzdata） | 修复后 plan-day today + 【今天】标记（2026-08-13） |
| BUG-5 雷达标签出界 | 🟡低 | 标签半径 r+22=166 > 半高120 | 绘制半径 0.6*min→0.40*min、标签偏移+22→+13（draw与mouseMoved同步） | 修复后 outCount=0，12/12 在画布内，极值标签邻域像素非透明 |

## 四、回归验证

- **API**：11 端点全 200（health / mastery / knowledge / overview / quality / plan/today / quiz/questions / daily-plan / summary / quiz/wrong / quiz/stats）+ POST submit 200，无 500。
- **浏览器 5 视图**：总览（4 stat 卡）/ 知识宝库（11 卡）/ 每日计划（【今天】高亮）/ 练题工坊（15 题）全部正常，console error 0 / exception 0。
- **测试数据已还原**：mastery total=25、records 19 条、错题目录 2 文件（QA 验收基线）。

## 五、修改文件总清单（绝对路径）

- `D:\乔一禾\项目工作区\多Agent学习导师\static\platform.html`
- `D:\乔一禾\项目工作区\多Agent学习导师\server\api\quiz.py`
- `D:\乔一禾\项目工作区\多Agent学习导师\server\api\mastery.py`
- `D:\乔一禾\项目工作区\多Agent学习导师\server\api\plan.py`（新建）
- `D:\乔一禾\项目工作区\多Agent学习导师\server\api\overview.py`
- `D:\乔一禾\项目工作区\多Agent学习导师\server\app.py`
- `D:\乔一禾\项目工作区\多Agent学习导师\requirements.txt`
- `D:\乔一禾\项目工作区\多Agent学习导师\data\mastery\mastery.json`
- `D:\乔一禾\项目工作区\多Agent学习导师\data\quiz-bank\2026-08-12-001.json`
- `D:\乔一禾\项目工作区\多Agent学习导师\data\daily-plan\2026-08-13.json`（生成）
- `D:\乔一禾\项目工作区\多Agent学习导师\scripts\clean_mastery_modules.py`（新建）
- `D:\乔一禾\项目工作区\多Agent学习导师\scripts\migrate_quiz_five_fields.py`（新建）
- `D:\乔一禾\项目工作区\多Agent学习导师\data\wrong-questions\2026-08-12-001-10.json`
- `D:\乔一禾\项目工作区\多Agent学习导师\data\wrong-questions\2026-08-12-001-5.json`
- `D:\乔一禾\项目工作区\多Agent学习导师\data\progress\answer-records.json`

## 六、遗留问题/backlog

- **多选交互**：第 13-15 题为多选题（answer="ABD"），前端按单选渲染（R4，backlog）。
- **错题"重做正确"前端入口缺失**（R3）。
- **quiz.py 与 mastery.py 双套掌握度更新逻辑**（R3，历史观察）。
- **知识卡均分 58**，KM 侧继续重制（R3）。
