# QA-001 Sprint V2 验收报告

- **验收对象**：Sprint V2 实施（TA-001 改动：platform.html 雷达图/知识宝库/练题工坊修复、quiz-bank 五字段拆分、mastery.json FSRS 化、plan.py 新建、mastery.py FSRS 读写、requirements 补 fsrs）
- **验收人**：QA-001 赛博质检官
- **验收时间**：2026-08-13 05:15–05:35
- **验收环境**：Windows 10 · headless Chrome 151（CDP 9222）真实浏览器逐区域检查 + Python CDP 脚本（.kb-tmp/qa_sprintv2_audit.py）
- **服务器**：Flask localhost:8899（health 200）

---

## 一、验收结论

> ### 🔶 **有条件通过（Conditional PASS）**
>
> 核心功能（五标签页渲染、无玫红、雷达交互、练题全流程、五段式解析、API 一致性、回归冒烟）全部通过；
> **但雷达图「有实际内容渲染」未通过**（画布内容不可见，严重度 高），另有 1 个中级闭环缺陷与 3 个低级缺陷，
> 需 TA-001 修复后复验雷达图区域。

- ✅ 通过项：**11/12**（含 5 个标签页逐页渲染、雷达交互、练题全流程、五段式解析、错题记录 API 链路、API 一致性、回归冒烟）
- ❌ 未通过项：**1/12**（A-2 雷达图画布内容渲染——不可见）
- 🐞 Bug 总数：**5**（高 1 / 中 1 / 低 3）

---

## 二、逐项验收记录表

| 检查项 | 验收方法（真实浏览器） | 证据 | 结果 |
|---|---|---|---|
| A-1 雷达图无玫红背景 | 打开总览页，CDP 对 `#mastery-canvas-wrap canvas` 像素采样 + 全页 computed style 玫红扫描 | canvas rosePct=**0**；全页玫红元素命中 **0** 个；body 背景 rgb(245,240,232)（纸色非玫红） | ✅ 通过 |
| A-2 雷达图有实际内容渲染 | 画布像素 alpha 统计（getImageData 全量） | **maxAlpha=12/255≈4.7%，alpha>50 的可见像素占比 0%，alpha>10 仅 0.002%** —— 多边形/轴线/文字全部绘制在近乎透明 alpha 上，画布实际不可见 | ❌ **未通过（BUG-1）** |
| A-3 雷达图可交互（悬停 tooltip） | CDP `Input.dispatchMouseEvent` 派发 mouseMoved 到模块标签坐标，读取 tooltip DOM | 悬停「公文写作」→ tooltip 文本「公文写作：0%」opacity=**1**；悬停「法律」→「法律：0%」opacity=1；移开(3,3) → opacity=**0** | ✅ 通过 |
| B-1 总览页 | 点击导航、读 DOM | active tab=overview；4 个 stat-card（距考 9 天/已练模块 1/12/知识卡 11/题库 15）；12 个模块进度条；header「备考中 · 距考 9 天」；无 error-msg；无空白 | ✅ 通过 |
| B-2 知识宝库 | 点击「知识宝库」tab | 11 张知识卡（.card-item）+ 徽章 11 + 均分 58；非空白；无 error | ✅ 通过 |
| B-3 每日计划 | 点击「每日计划」tab → 点击计划日 | 1 个 .plan-day（2026-08-13 计划）；**无"暂无学习计划"空态**；点击后 #plan-detail visible=true，markdown 渲染 394 字符（含距考 9 天/时政热点 48% 复习建议） | ✅ 通过（注：today 高亮缺失见 BUG-4） |
| B-4 练题工坊 | 点击「练题工坊」tab | 「共 15 题待练」+ 开始练题按钮 + 2 个筛选（全部/时政热点）；非空白 | ✅ 通过 |
| B-5 考点汇总 | 知识宝库页点「📋 考点汇总」按钮 | 渲染「覆盖 9 个模块 · 共 56 个考点」+ 考点卡片列表；非空白、无 loading 残留、无 error | ✅ 通过 |
| B-6 无死区/切换正常 | 依次点击 5 个视图，每次断言 active tab 与内容变化 | 每个视图 active tab 正确、内容随之渲染（见 B-1~B-5）；无空白页 | ✅ 通过 |
| B-7 无 console 错误 | CDP 全程捕获 console/exception/log/network | console error **0** 条；异常 **0**；网络失败 **0**；仅 1 条 getImageData 性能 warning（来自本验收采样代码，非应用） | ✅ 通过 |
| C 练题全流程 | 浏览器实际操作：开始练题 → 答错 Q1 → 判分 → 五段式解析 → 答对 Q2 → 快速答完 → 结果页 → 页面内 fetch POST 提交 | 详见「四、练题全流程实测记录」 | ✅ 通过（前端闭环缺失见 BUG-2） |
| D API 与页面一致性 | 页面 DOM 数值 ↔ curl API 数值逐项比对 | 详见「五、API 一致性核对表」，全部一致 | ✅ 通过 |
| E 回归冒烟 | curl 全部关键 API 状态码 | 9 个端点全 **200**，无 500（见「六、回归冒烟」） | ✅ 通过 |
| F 代码审查（快速） | 阅读 server/api/plan.py、mastery.py 改动 | plan.py 生成逻辑正确（FSRS due 解析/弱项优先/时间分配/落盘）；mastery.py update 有参数校验、旧数据兼容、FSRS 推进、异常降级。无阻塞性问题（观察项见「八、遗留风险」） | ✅ 通过（无阻断） |

---

## 三、Bug 清单

| ID | 严重级别 | 标题 | 复现步骤 | 截图/证据描述 | 指定修复人 |
|---|---|---|---|---|---|
| BUG-1 | 🔴 高 | 雷达图画布内容不可见（HSB alpha 值域错用） | 打开 http://localhost:8899/ 总览页，观察「📊 模块掌握度」下方雷达图区域 | 画布 950×240 全透明：maxAlpha=12/255≈4.7%，可见像素(alpha>50) 占比 **0%**。`initMasteryCanvas` 中 `p.colorMode(p.HSB,360,100,100,100)` 已把 alpha 上限设为 100，但所有 `stroke/fill` 仍传 0.2/0.3/0.4/0.6/0.7/0.22 这类 0~1 区间 alpha → 全部 ≈0 透明度。截图 `outputs/qa-sprintv2-radar-scrolled.png`（区域为空白浅色面板）；对比：交互 tooltip（DOM）正常 | TA-001 |
| BUG-2 | 🟠 中 | 练题前端闭环未接服务端（错题记录仅 API 直连可用） | ①浏览器练题答错一题 → 提交后查 `data/wrong-questions/` 与 `/api/quiz/wrong`：**无新增**（前端纯本地判分，`selectAnswer/finishQuiz` 不调用任何 POST）；②且 GET `/api/quiz/questions` 剥离 `_id` 字段（`list_questions` 第 278 行过滤 `_` 前缀），API 客户端拿不到合法 `question_id`，无法调 `/api/quiz/submit`（需猜「文件名-索引」格式） | 页面内 fetch POST `/api/quiz/submit`（question_id=2026-08-12-001-0）→ 200 且正确落库（wrong 文件+列表+answer-records+stats 全更新），证明服务端链路本身可用，缺的只是前端接线。截图 `outputs/qa-sprintv2-quiz-result.png`（页面错题回顾仅有会话内展示） | TA-001 |
| BUG-3 | 🟡 低 | 错题 wrong_count 双口径不一致 | 对同一题连续答错后对比 `data/wrong-questions/<id>.json` 与 `data/progress/wrong-questions.json` | 实测 001-1 题：独立文件 wrong_count=**2**，列表 wrong_count=**3**（`_save_wrong_question_file` 基于 `record.wrong_count=1` 再 +1，列表基于累计值，两处口径不同） | TA-001 |
| BUG-4 | 🟡 低 | 每日计划「今天」高亮时区错误（UTC vs 本地） | 东八区清晨（本地 05:xx，UTC 仍为前一日）打开每日计划页 | `platform.html` 第 1262 行用 `new Date().toISOString().slice(0,10)` 取"今天"，实测 utcToday=**2026-08-12**、localToday=**2026-08-13**，导致当日计划 `.plan-day` 无 `today` 类（实测 cls='plan-day'）。每天 UTC 零点前（本地 08:00 前）打开都会缺失高亮 | TA-001 |
| BUG-5 | 🟡 低 | 雷达图 6/12 个模块标签绘制在画布外 | 打开总览页查看雷达图标签布局 | 标签半径 r+22=166px > 画布半高 120px：顶部 3 个（三农/中共党史/马哲）y<0、底部 3 个（地理/时政/毛概）y>240，超出画布被裁剪，即使修复 BUG-1 也看不到、也无法悬停命中（CDP 坐标推算验证）。截图 `outputs/qa-sprintv2-tab-overview.png` | TA-001 |

---

## 四、练题全流程实测记录（真实浏览器逐步操作）

| 步骤 | 浏览器操作 | 页面反馈（DOM 实测） | 截图 |
|---|---|---|---|
| 1 选题 | 练题工坊 → 点「开始练题」 | 进入第 1/15 题 · 单选题（时政热点）：「2025年GDP增长预期目标为（ ）左右」，4 个选项 | qa-sprintv2-tab-quiz-home.png |
| 2 作答（故意答错） | 点选项 A（正确答案 B） | 选项 B 高亮 `.correct`、选项 A 高亮 `.wrong`（红），`#quiz-explanation` visible | qa-sprintv2-quiz-q1-wrong.png |
| 3 五段式解析 | 读取解析面板文本 | **五段全部渲染**：【正确答案】B（5%）、【术语拆解】3 条、【选项辨析】4 条、【考情提示】、【记忆口诀】——五字段 `markerInText` 全 true | qa-sprintv2-quiz-q1-wrong.png |
| 4 作答（答对） | 下一题 → 点正确答案 C | 选项 C `.correct`，无 `.wrong`，解析面板显示【正确答案】C（4%） | qa-sprintv2-quiz-q2-correct.png |
| 5 完成 | 剩余 13 题全部答对 → 「完成练题」 | 结果页：score-circle **93%**、14/15 正确、错题回顾 1 题（你的答案 A → 正确答案 B） | qa-sprintv2-quiz-result.png |
| 6 错题记录 | 页面内 fetch POST /api/quiz/submit（模拟服务端闭环） | HTTP 200，is_correct=false，返回五段式 structured 5 键；服务端落库：`data/wrong-questions/2026-08-12-001-0.json` 生成、wrong 列表 +1、answer-records +1、stats 更新 | 报告正文 §三 BUG-2 |

> ⚠️ 说明：第 6 步是因前端未接服务端（BUG-2）而采取的 API 链路验证；浏览器纯点击流程本身不产生服务端记录。
> **测试数据已清理**：删除本轮生成的 001-0 错题文件，还原 mastery.json / answer-records.json / wrong-questions.json 至验收前状态（时政热点 total=25、stats total=19、wrong=3），已验证一致。

---

## 五、API 与页面数据一致性核对表

| 数据项 | API 侧（curl） | 页面侧（真实浏览器 DOM） | 一致 |
|---|---|---|---|
| 距考天数 | /api/overview days_remaining=**9**；/api/plan/today days_left=**9** | header「距考 9 天」；计划标题「距考试 9 天」 | ✅ |
| 知识卡数量 | /api/overview knowledge_cards.total=**11**；/api/knowledge 返回 **11** 条 | 知识宝库 11 张卡片、徽章 **11** | ✅ |
| 掌握度模块数 | /api/mastery modules=**12** 个（全带 fsrs 字段） | 总览 12 个模块进度条；雷达图 12 轴（交互验证） | ✅ |
| 时政热点掌握度 | /api/mastery 时政热点 mastery=**48%**、total=25 | 总览模块条「时政热点 48%」 | ✅ |
| 题库数量 | /api/quiz/questions total=**15**（五字段齐：correct_answer/term_breakdown/option_analysis/exam_hint/mnemonic） | 练题工坊「共 **15** 题待练」；筛选 2 个（全部/时政热点，与 15 题全为时政热点一致） | ✅ |
| 五段式字段 | /api/quiz/questions 每题含 5 字段（空字段统计：term_breakdown×1、option_analysis×2，与任务描述一致） | Q1 解析面板五段标记全渲染（非空字段全出现） | ✅ |
| 每日计划 | /api/plan/today：2026-08-13、距考 9 天、可用 3 小时、到期复习[时政热点]、新模块 11 个 | 计划页标题/详情 markdown 内容逐字一致（时政热点 48%·25 题·FSRS 25 次） | ✅ |
| 考点汇总 | /api/summary：modules_covered=**9** 模块、total_key_points=**56** | 考点汇总页「覆盖 9 个模块 · 共 56 个考点」 | ✅ |
| 弱项模块 | /api/mastery weak_modules=['时政热点'] | /api/plan/today 到期复习含时政热点（弱项） | ✅ |

---

## 六、回归冒烟（E）

| 端点 | 状态码 | 端点 | 状态码 |
|---|---|---|---|
| /api/health | 200 | /api/mastery | 200 |
| /api/knowledge | 200 | /api/overview | 200 |
| /api/quality | 200 | /api/plan/today | 200 |
| /api/quiz/questions | 200 | /api/daily-plan | 200 |
| /api/summary | 200 | /api/quiz/submit(POST) | 200 |
| /api/quiz/wrong(GET) | 200 | /api/quiz/stats | 200 |

无 500。✅

---

## 七、截图证据索引（outputs/）

| 文件 | 内容 |
|---|---|
| qa-sprintv2-tab-overview.png | 总览页（stat 卡/模块条/雷达区域整体） |
| qa-sprintv2-radar-scrolled.png | 雷达图区域滚动后特写（可见空白画布——BUG-1 证据） |
| qa-sprintv2-tab-knowledge.png | 知识宝库（11 卡片） |
| qa-sprintv2-tab-summary.png | 考点汇总（9 模块 56 考点） |
| qa-sprintv2-tab-plan.png | 每日计划（1 个计划日） |
| qa-sprintv2-tab-plan-detail.png | 计划详情展开（markdown 渲染） |
| qa-sprintv2-tab-quiz-home.png | 练题工坊首页（15 题） |
| qa-sprintv2-quiz-q1-wrong.png | Q1 答错：correct/wrong 高亮 + 五段式解析 |
| qa-sprintv2-quiz-q2-correct.png | Q2 答对：正确高亮 + 解析 |
| qa-sprintv2-quiz-result.png | 结果页 93%（14/15）+ 错题回顾 1 题 |

---

## 八、遗留风险 / 观察项

1. **雷达图区域整体效果**：受 BUG-1 + BUG-5 叠加，当前用户看到的雷达图区域是空白的浅色面板（wrap 背景 rgba(255,255,255,0.3)），模块数据只能靠下方 DOM 进度条查看。修复 BUG-1 后需复验 BUG-5（标签溢出）与画布高度适配（h=240 固定，min-height 320px 容器）。
2. **答题数据链路分裂**：`quiz.py submit_answer` 与 `mastery.py update_mastery` 各有一套掌握度更新逻辑（重复实现），且前端均未调用——后续若接入前端，建议统一收敛到一个端点，避免双份逻辑漂移（当前实测两处行为一致）。
3. **错题「重做正确」闭环**：`/api/quiz/wrong` POST 支持 retry_correct 标记，但前端无对应入口（依赖 BUG-2 修复一并接入）。
4. **知识卡均分 58 分**：知识宝库显示均分 58（KM 侧内容质量指标，非本次范围，仅记录）。

---

*报告生成：QA-001 · 2026-08-13 · 证据文件 .kb-tmp/qa-sprintv2-report.json（原始数据）*
