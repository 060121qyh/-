# -*- coding: utf-8 -*-
"""
scripts/clean_mastery_modules.py — mastery.json 脏数据清洗（Sprint V2 任务5）
1. 合并 shizheng 与 %E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9（URL编码"时政热点"）→ 时政热点（mastery 按正确题数加权）
2. 删除 test模块
3. 对齐 config.yaml / goal.yaml 的 12 个 knowledge_modules（法律键名取简称，与 config 一致）
4. weak_modules 同步清理
用法: python scripts/clean_mastery_modules.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTERY_PATH = ROOT / "data" / "mastery" / "mastery.json"

# 与 config.yaml modules / goal.yaml knowledge_modules 对齐（法律取简称）
CANONICAL_MODULES = [
    "时政热点", "中国特色社会主义理论", "马克思主义哲学", "毛泽东思想",
    "中共党史", "三农与乡村振兴", "法律", "经济常识", "地理科技",
    "历史人文", "公文写作", "河南省情",
]

URL_DECODED_ALIASES = {
    "shizheng": "时政热点",
    "%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9": "时政热点",  # URL编码的"时政热点"
    "test模块": None,  # 删除
}


def merge_module(base, extra):
    """合并两个模块统计：按正确题数加权"""
    base_total = base.get("total", 0)
    extra_total = extra.get("total", 0)
    base_correct = base.get("correct_rate", 0) * base_total
    extra_correct = extra.get("correct_rate", 0) * extra_total
    new_total = base_total + extra_total
    new_correct = base_correct + extra_correct
    new_rate = round(new_correct / new_total, 4) if new_total else 0
    return {
        "mastery": min(100, round(new_rate * 100)),
        "trend": base.get("trend", "flat"),
        "total": new_total,
        "correct_rate": new_rate,
        "weak": (new_rate * 100) < 40 or new_rate < 0.5,
    }


def main():
    if not MASTERY_PATH.exists():
        print(f"[ERROR] {MASTERY_PATH} 不存在")
        return 1

    with open(MASTERY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    modules = data.get("modules", {})
    removed = []
    merged = {}

    # 先合并别名模块
    for key in list(modules.keys()):
        target = URL_DECODED_ALIASES.get(key)
        if target is None and key in URL_DECODED_ALIASES:
            removed.append(key)
            continue
        if target and target != key:
            if target not in merged:
                merged[target] = dict(modules[target]) if target in modules else {
                    "mastery": 0, "trend": "flat", "total": 0, "correct_rate": 0, "weak": False,
                }
            merged[target] = merge_module(merged[target], modules[key])
            removed.append(key)

    # 写入合并结果
    for k, v in merged.items():
        modules[k] = v

    # 删除多余模块
    for key in list(modules.keys()):
        if key not in CANONICAL_MODULES:
            if key not in removed:
                removed.append(key)
            del modules[key]

    # 补齐缺失的 12 模块（保持全 0）
    for m in CANONICAL_MODULES:
        if m not in modules:
            modules[m] = {
                "mastery": 0, "trend": "flat", "total": 0, "correct_rate": 0, "weak": False,
            }

    # 保证 12 模块顺序与配置一致
    ordered = {m: modules[m] for m in CANONICAL_MODULES}
    data["modules"] = ordered

    # weak_modules 同步
    data["weak_modules"] = [m for m, v in ordered.items() if v.get("weak")]

    with open(MASTERY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] 清洗完成")
    print(f"  移除模块: {removed}")
    print(f"  模块总数: {len(ordered)} (应为12)")
    print(f"  weak_modules: {data['weak_modules']}")
    print(f"  时政热点合并后: {ordered['时政热点']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
