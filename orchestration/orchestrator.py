#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多Agent学习导师 — 主编排器 v2.0
================================
负责：
1. Agent 身份管理（工号注册、上下文生成）
2. Inbox 文件监听与自动调度（PM-001 写任务单 → 编排器检测 → 生成 dispatch 指令）
3. 任务队列与工作日志生命周期管理
4. 全局状态看板

用法：python orchestrator.py <命令> [参数]

命令:
  show-agents       列出所有Agent
  agent-context     输出指定Agent的完整上下文提示词
  scan-inbox        扫描 coordination/inbox/ 中的新任务单
  dispatch          为 inbox 中的任务生成 delegate_task 调用描述
  process-inbox     完整流程：扫描→验证→生成 dispatch→标记已处理
  next-task         从任务队列取下一个待分配任务
  log-start         记录任务开始
  log-complete      记录任务完成并归档
  status            查看当前系统状态（含 inbox 概况）
"""

import json
import os
import sys
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEFINITIONS_DIR = PROJECT_DIR / "agent-definitions"
LOGS_ACTIVE = PROJECT_DIR / "work-logs" / "active"
LOGS_ARCHIVE = PROJECT_DIR / "work-logs" / "archive"
TASK_QUEUE = BASE_DIR / "task-queue.json"
COORD_INBOX = PROJECT_DIR / "coordination" / "inbox"
COORD_OUTBOX = PROJECT_DIR / "coordination" / "outbox"
COORD_DECISIONS = PROJECT_DIR / "coordination" / "decisions"
INBOX_PROCESSED = COORD_INBOX / "processed"


def load_agent(agent_id):
    """加载Agent定义文件"""
    for f in DEFINITIONS_DIR.iterdir():
        if f.name.startswith(agent_id) and f.suffix == ".json":
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def load_all_agents():
    """加载所有Agent定义"""
    agents = {}
    for f in sorted(DEFINITIONS_DIR.iterdir()):
        if f.suffix == ".json":
            agent = json.loads(f.read_text(encoding="utf-8"))
            agents[agent["工号"]] = agent
    return agents


def load_task_queue():
    """加载任务队列"""
    if not TASK_QUEUE.exists():
        return {"tasks": [], "completed": [], "version": "1.0"}
    return json.loads(TASK_QUEUE.read_text(encoding="utf-8"))


def save_task_queue(queue):
    """保存任务队列"""
    TASK_QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def build_agent_context(agent_id):
    """构建Agent的完整工作上下文提示词"""
    agent = load_agent(agent_id)
    if not agent:
        return f"错误：未找到Agent {agent_id}"

    all_agents = load_all_agents()

    context = f"""【Agent身份卡】
工号: {agent['工号']}
名称: {agent['名称']}
角色: {agent['角色']}

【你的核心职责】
{chr(10).join(f"- {d}" for d in agent['核心职责'])}

【严格禁止事项】—— 这些你绝对不能做：
{chr(10).join(f"- {d}" for d in agent['禁止事项'])}

【你的输出格式】
{json.dumps(agent['输出格式'], ensure_ascii=False, indent=2)}

【协作Agent一览】
"""
    for aid, a in all_agents.items():
        if aid != agent_id:
            context += f"- {aid} ({a['名称']}): {a['角色']} — {', '.join(a['核心职责'][:2])}\n"

    context += f"""
【工作日志要求】
每次任务开始时，你必须在 work-logs/active/{agent_id}-{{任务ID}}.md 中记录：
- 开始时间、任务ID、接收的任务描述
- 每完成一个步骤追加记录
- 完成后写入完成时间和产出摘要

【重要提醒】
你是一个独立Agent，只做你角色范围内的事。遇到不属于你职责的问题，
明确说"这不是我的职责范围，请转交XX Agent处理"。
"""

    if "协作协议" in agent:
        context += "\n【协作协议】\n"
        for k, v in agent["协作协议"].items():
            context += f"- {k}: {v}\n"

    return context


def scan_inbox():
    """扫描 inbox 目录，返回待处理任务列表"""
    if not COORD_INBOX.exists():
        return []

    tasks = []
    for f in sorted(COORD_INBOX.iterdir()):
        if not f.suffix == ".json":
            continue
        if f.name.startswith("_"):  # 跳过已标记的
            continue
        try:
            task = json.loads(f.read_text(encoding="utf-8"))
            # 验证必要字段
            required = ["任务ID", "发件Agent", "收件Agent", "优先级", "任务标题"]
            missing = [k for k in required if k not in task]
            task["_file"] = str(f)
            task["_valid"] = len(missing) == 0
            task["_missing"] = missing
            task["_size"] = f.stat().st_size
            tasks.append(task)
        except json.JSONDecodeError as e:
            tasks.append({
                "_file": str(f),
                "_valid": False,
                "_error": f"JSON解析错误: {e}",
                "任务ID": "INVALID",
                "发件Agent": "?",
                "收件Agent": "?"
            })
    return tasks


def generate_dispatch(task):
    """为单个 inbox 任务生成 delegate_task 调用描述"""
    agent_id = task.get("收件Agent", "")
    agent = load_agent(agent_id)

    if not agent:
        return f"# ❌ 未知Agent: {agent_id}"

    # Agent 身份
    identity = build_agent_context(agent_id)

    # 任务描述
    task_desc = f"""
# PM-001 发来的任务单

**任务ID**: {task.get('任务ID', '?')}
**优先级**: {task.get('优先级', '?')}
**截止时间**: {task.get('截止时间', '无')}

## 任务标题
{task.get('任务标题', '')}

## 任务描述
{task.get('任务描述', '')}

## 验收标准
{chr(10).join(f"- {ac}" for ac in task.get('验收标准', []))}

## 产出要求
{json.dumps(task.get('产出要求', {}), ensure_ascii=False, indent=2)}

## 禁止事项
{chr(10).join(f"- {b}" for b in task.get('禁止事项', ['不自行增加PM未提及的功能']))}
"""

    # 输入参考
    inputs = task.get('输入', {})
    refs = inputs.get('参考文件', [])
    if refs:
        task_desc += f"\n## 参考文件\n{chr(10).join(f'- {r}' for r in refs)}\n"

    dispatch = f"""
{'='*60}
📋 delegate_task 调用描述 — {agent_id}
{'='*60}

### context 参数（Agent身份+项目背景）:
```
{identity[:200]}...
(完整上下文通过 orchestrator.py agent-context {agent_id} 获取)
```

### goal 参数（任务指令）:
```
{task_desc}
```

### 工作日志路径:
work-logs/active/{agent_id}-{task.get('任务ID','TASK')}.md

### 产出文件:
{task.get('产出要求', {}).get('文件路径', '待定')}

{'='*60}
"""
    return dispatch


def mark_processed(task_file):
    """将已处理的 inbox 文件移到 processed 子目录"""
    src = Path(task_file)
    if not src.exists():
        return False
    INBOX_PROCESSED.mkdir(parents=True, exist_ok=True)
    dst = INBOX_PROCESSED / src.name
    shutil.move(str(src), str(dst))
    return True


def update_state_board(scan_results):
    """更新协调状态看板"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [f"## Inbox 扫描 — {now}", ""]

    valid = [t for t in scan_results if t.get("_valid")]
    invalid = [t for t in scan_results if not t.get("_valid")]

    lines.append(f"| 状态 | 数量 |")
    lines.append(f"|------|:----:|")
    lines.append(f"| 有效任务单 | {len(valid)} |")
    lines.append(f"| 无效/错误 | {len(invalid)} |")
    lines.append("")

    if valid:
        lines.append("### 待处理任务")
        lines.append("| 任务ID | 发件→收件 | 优先级 | 标题 |")
        lines.append("|--------|-----------|:------:|------|")
        for t in valid:
            lines.append(
                f"| {t['任务ID']} | {t['发件Agent']}→{t['收件Agent']} "
                f"| {t['优先级']} | {t['任务标题'][:50]} |"
            )
        lines.append("")

    if invalid:
        lines.append("### ⚠️ 问题文件")
        for t in invalid:
            fname = Path(t["_file"]).name
            err = t.get("_error", f"缺字段: {t.get('_missing',[])}")
            lines.append(f"- ❌ `{fname}`: {err}")

    lines.append(f"\n> 扫描时间: {now} | 编排器 v2.0")

    report_path = COORD_DECISIONS / "inbox-scan-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ============================================================
# 命令处理
# ============================================================

def cmd_show_agents():
    agents = load_all_agents()
    print(f"{'工号':<10} {'名称':<16} {'角色':<10} {'状态'}")
    print("-" * 50)
    for aid, a in agents.items():
        print(f"{aid:<10} {a['名称']:<16} {a['角色']:<10} 就绪")


def cmd_agent_context(agent_id):
    print(build_agent_context(agent_id))


def cmd_scan_inbox():
    """扫描 inbox，列出所有待处理任务"""
    tasks = scan_inbox()
    if not tasks:
        print("📭 inbox 为空，无待处理任务。")
        return

    valid = [t for t in tasks if t.get("_valid")]
    invalid = [t for t in tasks if not t.get("_valid")]

    print(f"📬 inbox 扫描结果: {len(valid)} 有效 + {len(invalid)} 无效\n")

    for t in valid:
        print(f"  ✅ {t['任务ID']}: {t['发件Agent']}→{t['收件Agent']}")
        print(f"     标题: {t['任务标题'][:60]}")
        print(f"     优先级: {t['优先级']} | 大小: {t['_size']}B")
        ac_count = len(t.get('验收标准', []))
        print(f"     验收标准: {ac_count}条")
        print()

    for t in invalid:
        err = t.get("_error", f"缺字段: {t.get('_missing',[])}")
        print(f"  ❌ {Path(t['_file']).name}: {err}\n")

    # 更新扫描报告
    report = update_state_board(tasks)
    print(f"📄 扫描报告已生成: {report}")


def cmd_dispatch(agent_id=None):
    """为 inbox 中的任务生成 dispatch 描述"""
    tasks = scan_inbox()
    valid = [t for t in tasks if t.get("_valid")]

    if agent_id:
        valid = [t for t in valid if t["收件Agent"] == agent_id]

    if not valid:
        print(f"📭 没有{'给 ' + agent_id + ' 的' if agent_id else ''}待处理任务。")
        return

    for t in valid:
        print(generate_dispatch(t))


def cmd_process_inbox():
    """完整流程：扫描→验证→生成 dispatch→标记已处理"""
    tasks = scan_inbox()
    valid = [t for t in tasks if t.get("_valid")]
    invalid = [t for t in tasks if not t.get("_valid")]

    print(f"🔍 扫描完成: {len(valid)} 有效, {len(invalid)} 无效\n")

    if invalid:
        print("⚠️ 跳过无效文件:")
        for t in invalid:
            err = t.get("_error", f"缺字段: {t.get('_missing',[])}")
            print(f"  ❌ {Path(t['_file']).name}: {err}")
        print()

    if not valid:
        print("✅ 无待处理任务，inbox 已清。")
        return

    print(f"📋 准备调度 {len(valid)} 个任务:\n")

    for i, t in enumerate(valid, 1):
        aid = t["收件Agent"]
        print(f"{'─'*60}")
        print(f"[{i}/{len(valid)}] {t['任务ID']} → {aid} ({t['优先级']})")
        print(f"{'─'*60}")
        print(generate_dispatch(t))

    # 标记已处理
    print(f"\n{'='*60}")
    print("✅ 全部任务已生成 dispatch 描述。")
    print(f"   原文件已移至: {INBOX_PROCESSED}/")
    print(f"   下一步: 在 Hermes 中使用 delegate_task 按上述描述拉起 Agent")
    print(f"{'='*60}")

    for t in valid:
        mark_processed(t["_file"])

    update_state_board(tasks)


def cmd_next_task(agent_id=None):
    queue = load_task_queue()
    pending = [t for t in queue["tasks"] if t["status"] == "待分配"]
    if not pending:
        print("当前无待分配任务。")
        return
    task = pending[0]
    if agent_id:
        task["assigned_to"] = agent_id
        task["status"] = "进行中"
        task["assigned_at"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
        save_task_queue(queue)
    print(json.dumps(task, ensure_ascii=False, indent=2))


def cmd_log_start(task_id, agent_id, description=""):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    log_file = LOGS_ACTIVE / f"{agent_id}-{task_id}.md"
    content = f"""# 工作日志

- **任务ID**: {task_id}
- **工号**: {agent_id}
- **开始时间**: {now}
- **任务描述**: {description}

---

## 执行记录

| 时间 | 步骤 | 产出 |
|------|------|------|
| {now} | 任务开始 | — |

"""
    LOGS_ACTIVE.mkdir(parents=True, exist_ok=True)
    log_file.write_text(content, encoding="utf-8")
    print(f"工作日志已创建: {log_file}")


def cmd_log_complete(task_id, agent_id, summary=""):
    log_file = LOGS_ACTIVE / f"{agent_id}-{task_id}.md"
    if not log_file.exists():
        print(f"错误：未找到日志文件 {log_file}")
        return

    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n| {now} | 任务完成 | {summary} |\n")
        f.write(f"\n---\n**完成时间**: {now}\n**产出摘要**: {summary}\n")

    LOGS_ARCHIVE.mkdir(parents=True, exist_ok=True)
    archive_file = LOGS_ARCHIVE / f"{agent_id}-{task_id}.md"
    shutil.move(str(log_file), str(archive_file))
    print(f"日志已归档: {archive_file}")


def cmd_status():
    agents = load_all_agents()
    queue = load_task_queue()

    pending = [t for t in queue["tasks"] if t["status"] == "待分配"]
    in_progress = [t for t in queue["tasks"] if t["status"] == "进行中"]
    completed = queue.get("completed", [])

    active_logs = list(LOGS_ACTIVE.iterdir()) if LOGS_ACTIVE.exists() else []
    archive_logs = list(LOGS_ARCHIVE.iterdir()) if LOGS_ARCHIVE.exists() else []

    # Inbox 状态
    inbox_tasks = scan_inbox()
    inbox_valid = [t for t in inbox_tasks if t.get("_valid")]

    print(f"=== 多Agent学习导师 系统状态 ===")
    print(f"时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}")
    print(f"\nAgent ({len(agents)}个):")
    for aid in agents:
        busy = any(t.get("assigned_to") == aid for t in in_progress)
        status = "⏳ 工作中" if busy else "✅ 空闲"
        print(f"  {aid}: {status}")

    print(f"\n📬 Inbox 协调系统:")
    print(f"  待处理任务单: {len(inbox_valid)}")
    for t in inbox_valid:
        print(f"    → {t['发件Agent']}→{t['收件Agent']}: {t['任务标题'][:40]}")

    print(f"\n任务队列:")
    print(f"  待分配: {len(pending)}")
    print(f"  进行中: {len(in_progress)}")
    print(f"  已完成: {len(completed)}")

    print(f"\n工作日志:")
    print(f"  活跃日志: {len(active_logs)}")
    print(f"  归档日志: {len(archive_logs)}")


# ============================================================
# 入口
# ============================================================

COMMANDS = {
    "show-agents": (cmd_show_agents, 0, "列出所有Agent"),
    "agent-context": (cmd_agent_context, 1, "输出Agent上下文 <工号>"),
    "scan-inbox": (cmd_scan_inbox, 0, "扫描 inbox 中的新任务单"),
    "dispatch": (cmd_dispatch, 0, "生成 dispatch 描述 [工号]"),
    "process-inbox": (cmd_process_inbox, 0, "扫描→生成调度→标记已处理"),
    "next-task": (cmd_next_task, 0, "取下一个待分配任务 [工号]"),
    "log-start": (cmd_log_start, 2, "记录任务开始 <任务ID> <工号>"),
    "log-complete": (cmd_log_complete, 2, "归档任务日志 <任务ID> <工号>"),
    "status": (cmd_status, 0, "查看系统状态"),
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python orchestrator.py <命令> [参数]\n")
        for name, (fn, min_args, desc) in COMMANDS.items():
            print(f"  {name:<18} {desc}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"未知命令: {cmd}")
        print(f"可用: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    fn, min_args, _ = COMMANDS[cmd]
    args = sys.argv[2:]

    if len(args) < min_args:
        print(f"用法: orchestrator.py {cmd} (需要{min_args}个参数)")
        sys.exit(1)

    if cmd == "agent-context":
        fn(args[0])
    elif cmd == "dispatch":
        fn(args[0] if args else None)
    elif cmd in ("next-task",):
        fn(args[0] if args else None)
    elif cmd in ("log-start", "log-complete"):
        fn(args[0], args[1] if len(args) > 1 else args[0])
    else:
        fn()
