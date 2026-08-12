# QA-001 工作日志 — Sprint V2 严格验收

- **任务 ID**：QA-001-SPRINTV2
- **工号**：QA-001（赛博质检官）
- **开始时间**：2026-08-13 05:14
- **状态**：✅ 已完成（验收结论：有条件通过）

---

## 任务目标

对 Sprint V2 实施做严格验收：真实浏览器逐区域检查（禁止只 curl）——五标签页渲染、雷达图（无玫红/有内容/可交互）、练题全流程、API 一致性、回归冒烟，产出验收报告。

## 执行步骤（增量）

1. **05:14 环境确认**：服务器 health 200；headless Chrome 151（CDP 9222）已连 localhost:8899；复用 TA-001 脚本基建（.kb-tmp/cdp_verify.py 的 get_page_ws/CDP 类，未修改其文件）。
2. **05:15 API 基线抓取**：health/knowledge/quality/quiz/questions/mastery/overview/plan/today/daily-plan 全 200，存 .kb-tmp/qa-baseline/。确认：mastery 12 模块全带 fsrs、题库 15 题五字段齐、plan_today 距考 9 天。
3. **05:16 数据备份**：mastery.json、answer-records.json、wrong-questions.json → .kb-tmp/qa-backup/（练题测试会产生污染，必须先备份）。
4. **05:16 源码研读**：确认前端练题为纯本地判分（fetch 仅 5 个 GET、无 POST）→ 预判错题记录需 API 链路验证；`_load_all_questions` 合成 `_id`（文件名-索引）；GET 接口剥离 `_id`。
5. **05:16 API 错题链路实测**：curl+python POST /api/quiz/submit（001-1 答错）→ 200，is_correct=false，五段式 structured 返回；data/wrong-questions/001-1.json 生成、wrong 列表/answer-records/stats 全更新 → **服务端链路可用**。随即恢复备份（时政热点 total 25 复原）。
6. **05:18 编写验收脚本** .kb-tmp/qa_sprintv2_audit.py（自包含 CDP 类 + Log/Network 捕获 + Input.dispatchMouseEvent 悬停 + 像素采样 + 逐页截图）。
7. **05:19 浏览器全流程验收**（headless Chrome 真实渲染）：
   - 总览：4 stat 卡、12 模块条、header 距考 9 天 ✅
   - 玫红扫描：全页 0 命中、canvas rosePct=0 ✅
   - **雷达交互：悬停 tooltip「公文写作：0%」「法律：0%」opacity=1，移开=0 ✅**
   - **雷达内容：画布 maxAlpha=12/255、可见像素 0% → 内容不可见 ❌（BUG-1，高）**
   - 知识宝库 11 卡、考点汇总 9 模块 56 考点、每日计划详情渲染、练题工坊 15 题 ✅
   - 练题全流程：Q1 答错→判分→五段式解析 5 段全渲染→Q2 答对→结果页 93%（14/15）→错题回顾 1 题 ✅
   - console 错误 0、异常 0、网络失败 0 ✅
   - 页面内 fetch POST submit → 200 落库（证据留档后清理）
8. **05:20 数据清理**：删 001-0 错题文件、还原 3 个数据文件 → 校验与验收前完全一致（modules 12/时政热点 total 25/stats total 19/wrong 3）✅
9. **05:21 一致性核对**：9 项页面↔API 数值全对齐（见报告§五）。
10. **05:22 补充验证**：计划页 today 高亮缺失 → 定位为 `toISOString()` UTC 时区 bug（utcToday=08-12 vs localToday=08-13，BUG-4）；/api/summary 数值与页面一致。
11. **05:23 代码审查（F）**：plan.py 生成逻辑正确（FSRS due/弱项优先/时间分配/落盘）；mastery.py update 有校验、旧数据兼容、FSRS 推进与降级。无阻断问题。
12. **05:24–05:35 产出**：outputs/qa-验收报告-SprintV2.md（含结论/记录表/Bug 清单/实测记录/一致性表/截图索引）+ 本日志。

## 产出文件

- `outputs/qa-验收报告-SprintV2.md`（主交付物）
- `outputs/qa-sprintv2-*.png` × 10（截图证据）
- `.kb-tmp/qa-sprintv2-report.json`（原始证据数据）
- `.kb-tmp/qa-baseline/`、`.kb-tmp/qa-backup/`（基线与备份，验收后保留以备追溯）

## 验收结论

**有条件通过**：11/12 项通过；雷达图「有内容渲染」未通过（BUG-1 高）；另有 BUG-2（中，练题前端未接服务端）、BUG-3/4/5（低）。详见验收报告 Bug 清单。

## 遇到的问题与处理

- **curl 中文 JSON POST 失败**（"请求体为空"）：git-bash 引号/编码问题 → 改用文件 --data-binary 与 python urllib 双路复测，均 200。
- **雷达像素采样时机**：p5 异步渲染 → 采样带 3 次重试 + 等待 7s；并用 maxAlpha/visiblePct 硬指标而非肉眼。
- **模型看不了图片**：所有判断基于 CDP 读 DOM 文本/computed style/像素 alpha 数值，截图仅作证据文件。
- **测试数据污染**：submit 会改 mastery/records/wrong 三处 → 全程备份-还原，验收结束已校验还原一致。

## 交接建议（给 PM/TA）

1. TA-001 优先修 BUG-1（雷达 alpha 值域），修复后 QA 复验雷达区域截图；顺带处理 BUG-5（标签溢出）。
2. BUG-2 决定产品口径：练题是否要服务端记录（错题本/掌握度）——若要，接 POST /api/quiz/submit 并让 GET questions 返回 question_id。
3. BUG-3/BUG-4 为低优先小修。
