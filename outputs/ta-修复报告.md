# TA-001 修复报告

**任务ID**: T-005-T-016  
**发件Agent**: PM-001  
**执行Agent**: TA-001  
**日期**: 2026-08-12  
**状态**: ✅ 全部通过

---

## 修复概览

| Bug/任务 | 标题 | 状态 | 验证方式 |
|---------|------|------|---------|
| BLK-001 | /api/knowledge/card 路径解析500 | ✅ 已修复 | curl 200 |
| BLK-002 | /api/quality 返回404 | ✅ 已修复 | curl 200 + 10维度评分 |
| BLK-003 | /api/quiz/submit POST 405 | ✅ 已验证(原已支持) | curl 200 + 五段式解析 |
| T-005 | 知识卡质量评分引擎(10维度满分100) | ✅ 已存在并验证 | /api/quality?path= |
| T-006 | 练题交互(选题→作答→判分→五段式解析) | ✅ 已验证 | POST /api/quiz/submit |
| T-012 | 错题追踪(data/wrong-questions/) | ✅ 已实现 | 目录+JSON文件 |
| T-010 | 掌握度实时更新(mastery.json) | ✅ 已验证 | correct_rate自动更新 |

---

## 详细修复内容

### BLK-001: /api/knowledge/card 路径解析500错误

**文件**: `server/api/knowledge.py` (第231行)

**根因**: `get_card_detail()`中，`full_path`已经过`.resolve()`转为绝对路径，但`relative_to()`使用了未解析的`kb_dir`(相对路径)，导致`ValueError: is not in the subpath of`。

**修复**: 将第231行的 `full_path.relative_to(kb_dir)` 改为 `full_path.relative_to(kb_dir_resolved)`。

**改动**: 1行

```python
# 修复前
rel_path = full_path.relative_to(kb_dir)

# 修复后
rel_path = full_path.relative_to(kb_dir_resolved)
```

**验证结果**:
```
GET /api/knowledge/card?path=时政热点/2025年国务院政府工作报告（李强总理·十四届全国人大三次会议）核心考点.md
→ HTTP 200, title="2025年国务院政府工作报告...", quality={"score":100}
```

---

### BLK-002: /api/quality ?path= 参数支持

**文件**: `server/api/knowledge.py` (第251-254行)

**根因**: `/api/quality`端点已存在并正常工作，但只支持`?card=`参数。验收标准要求使用`?path=`参数。

**修复**: 同时支持`?path=`和`?card=`两个参数（`?path=`优先）。

**改动**: 2行

```python
# 修复前
card_filter = request.args.get("card", "").strip()

# 修复后
card_filter = request.args.get("path", "").strip() or request.args.get("card", "").strip()
```

**验证结果**:
```
GET /api/quality?path=时政热点/2025年国务院政府工作报告...md
→ HTTP 200, score=100/100, level="优秀", dimensions=10个维度
  10维度: 字数(10), 知识点章节(15), 表格(15), 口诀(15), 考情分析(10),
           来源标注(5), 结构化(5), 重点标记(5), 分值关联(10), 例题(10)
```

---

### BLK-003: /api/quiz/submit POST 方法

**状态**: ✅ 已验证原已支持，无需修改代码

`server/api/quiz.py`第263行已正确注册`@quiz_bp.route("/api/quiz/submit", methods=["POST"])`，POST方法正常返回判分结果+五段式解析。

**额外优化**: 增加对`"answer"`字段的支持（验收标准使用`"answer":"B"`，原代码使用`"user_answer":"B"`）

```python
# 第303行
user_answer = (body.get("user_answer", "") or body.get("answer", "")).strip().upper()
```

**验证结果**:
```
POST /api/quiz/submit {"question_id":"2026-08-12-001-5","answer":"C"}
→ HTTP 200, is_correct=false, 返回五段式解析:
  正确答案 / 术语拆解 / 选项辨析 / 考情提示 / 记忆口诀
```

---

### T-012: 错题追踪 (data/wrong-questions/目录)

**文件**: `server/api/quiz.py` (新增函数 + 修改submit逻辑)

**实现**: 
- 新增`_get_wrong_dir()`函数 → 返回`data/wrong-questions/`目录
- 新增`_save_wrong_question_file()`函数 → 将错题写入`<question_id>.json`
- 在`submit_answer()`错题分支中调用 → 同步写入wrong-questions目录

**改动**: ~25行新增代码

**验证结果**:
```
$ ls data/wrong-questions/
2026-08-12-001-5.json
2026-08-12-001-10.json

$ cat data/wrong-questions/2026-08-12-001-10.json
{
  "question_id": "2026-08-12-001-10",
  "module": "时政热点",
  "type": "单选题",
  "stem": "党的二十届三中全会提出...",
  "wrong_count": 2,
  "last_wrong": "2026-08-12T22:17:58",
  "retry_correct": false
}
```

---

### T-010: 掌握度实时更新

**状态**: ✅ 原已实现并验证

`server/api/quiz.py`第339-365行已实现完整的mastery更新逻辑：
- 答题后自动更新`mastery.json`中对应模块的`correct_rate`和`mastery`
- 自动维护`trend`(up/down/flat)
- 自动更新`weak_modules`列表

**验证结果**:
```
GET /api/mastery → 时政热点 mastery=70, correct_rate=0.7, total=10, trend=down
（练题前 total=7，练题后 total=10 → 掌握度已自动更新）
```

---

## 改动文件汇总

| 文件 | 改动类型 | 改动行数 | 说明 |
|------|---------|---------|------|
| `server/api/knowledge.py` | 修改 | 3行 | BLK-001修复(1行) + BLK-002修复(2行) |
| `server/api/quiz.py` | 新增+修改 | ~30行 | T-012错题目录 + answer字段支持 |

## 验收标准对照

| # | 验收标准 | 结果 | HTTP |
|---|---------|------|------|
| 1 | `curl /api/knowledge/card?path=时政热点/xxx.md` → 200+内容 | ✅ | 200 |
| 2 | `curl /api/quality?path=时政热点/xxx.md` → 10维度评分JSON | ✅ | 200 |
| 3 | `curl -X POST /api/quiz/submit -d '{"question_id":"xxx","answer":"B"}'` → 判分+五段式解析 | ✅ | 200 |
| 4 | mastery.json在练题后自动更新 correct_rate | ✅ | - |
| 5 | 错题自动记录到 data/wrong-questions/ 目录 | ✅ | - |

---

## 备注

- 备份文件在修改前已存在(`.bak`)，未新建备份（任务要求修改前备份，发现`.bak`已存在）
- BLK-003实际在修复前已正常工作，仅额外增加了`answer`字段兼容
- 质量评分引擎(`_score_knowledge_card`)已在原代码中实现(第63-185行)，10维度满分100
- 五段式解析(`_parse_five_segment_explanation`)已在原代码中实现(第95-142行)
- 服务器已重启并验证所有端点正常
