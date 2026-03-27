#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reflex-audit: 分析反射链健康状态并评分"""

import json
import os
import sys
from pathlib import Path

STATS_PATH = Path(os.path.expanduser("~/mem/mem/workflows/trigger-stats.json"))
TRIGGER_MAP_SSOT = Path(os.path.expanduser("~/mem/mem/workflows/trigger-map.md"))
TRIGGER_MAP_RULES = Path(
    os.path.expanduser("~/.claude/rules/trigger-map.md")
)

REFLECTIONS = [
    "research", "explore", "implement", "document", "audit",
    "verify", "commit", "journal", "memory", "devour", "define"
]

WEIGHTS = {
    "coverage": 0.20,
    "failure_recovery": 0.25,
    "efficiency": 0.15,
    "balance": 0.15,
    "cb_health": 0.15,
    "consistency": 0.10,
}


def load_stats():
    """Load trigger-stats.json and return parsed dict, or None if missing."""
    if not STATS_PATH.exists():
        return None
    with open(STATS_PATH, encoding="utf-8") as f:
        return json.load(f)


def score_coverage(stats):
    """覆盖度：11 个反射是否都有使用记录"""
    rules = stats.get("rules", {})
    used = 0
    details = []
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        total = (entry.get("success", 0)
                 + entry.get("failure", 0)
                 + entry.get("skip", 0))
        if total > 0:
            used += 1
        else:
            details.append(f"「{r}」从未使用")

    score = round(used / len(REFLECTIONS) * 10, 1)
    desc = f"{used}/{len(REFLECTIONS)} 个反射有使用记录"
    if details:
        desc += "；" + "、".join(details)
    return score, desc


def score_failure_recovery(stats):
    """失败恢复：失败后是否有恢复（简化判断：失败少则好）"""
    rules = stats.get("rules", {})
    total_failures = 0
    total_ops = 0
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        total_failures += entry.get("failure", 0)
        total_ops += entry.get("success", 0) + entry.get("failure", 0)

    if total_ops == 0:
        return 10.0, "无操作记录，无法评估"

    failure_rate = total_failures / total_ops
    # 失败率 0% → 10分，50%+ → 0分
    score = max(0, round((1 - failure_rate * 2) * 10, 1))
    pct = round(failure_rate * 100, 1)
    desc = f"总失败率 {pct}%（{total_failures}/{total_ops}）"
    return score, desc


def score_efficiency(stats):
    """效率：跳步比例是否合理（10-30% 视为健康）"""
    rules = stats.get("rules", {})
    total_skip = 0
    total_ops = 0
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        total_skip += entry.get("skip", 0)
        total_ops += (entry.get("success", 0)
                      + entry.get("failure", 0)
                      + entry.get("skip", 0))

    if total_ops == 0:
        return 10.0, "无操作记录"

    skip_rate = total_skip / total_ops
    # 10-30% 跳步率最佳
    if 0.10 <= skip_rate <= 0.30:
        score = 10.0
    elif skip_rate < 0.10:
        score = round(skip_rate / 0.10 * 8 + 2, 1)  # 0% → 2分, 10% → 10分
    else:
        score = max(0, round((1 - (skip_rate - 0.30) / 0.70) * 10, 1))

    return score, f"跳步率 {round(skip_rate * 100, 1)}%（{total_skip}/{total_ops}）"


def score_balance(stats):
    """均衡性：反射间使用比例是否健康"""
    rules = stats.get("rules", {})
    usages = []
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        total = entry.get("success", 0) + entry.get("failure", 0)
        usages.append(total)

    non_zero = [u for u in usages if u > 0]
    if len(non_zero) < 2:
        return 5.0, "使用数据不足，无法评估均衡性"

    max_usage = max(non_zero)
    min_usage = min(non_zero)
    ratio = max_usage / min_usage if min_usage > 0 else float("inf")

    # ratio 1:1 → 10分, 10:1+ → 2分
    if ratio <= 2:
        score = 10.0
    elif ratio <= 5:
        score = round(10 - (ratio - 2) * 1.5, 1)
    else:
        score = max(2, round(10 - (ratio - 2) * 1.0, 1))

    return score, f"最高/最低使用比 {round(ratio, 1)}:1"


def score_cb_health(stats):
    """CB 健康：有无 OPEN/HALF-OPEN 状态"""
    rules = stats.get("rules", {})
    issues = []
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        cb = entry.get("cb_state", "CLOSED")
        if cb == "OPEN":
            issues.append(f"「{r}」= OPEN")
        elif cb == "HALF-OPEN":
            issues.append(f"「{r}」= HALF-OPEN")

    if not issues:
        return 10.0, "全部 CLOSED"

    score = max(0, 10 - len(issues) * 3)
    return score, "；".join(issues)


def score_consistency():
    """一致性：trigger-map SSOT 和 rules 副本是否同步"""
    if not TRIGGER_MAP_SSOT.exists() or not TRIGGER_MAP_RULES.exists():
        return 5.0, "文件缺失，无法比对"

    ssot = TRIGGER_MAP_SSOT.read_text(encoding="utf-8")
    rules = TRIGGER_MAP_RULES.read_text(encoding="utf-8")

    if ssot == rules:
        return 10.0, "SSOT 与 rules 副本完全一致"

    # 计算差异行数
    ssot_lines = set(ssot.splitlines())
    rules_lines = set(rules.splitlines())
    diff = len(ssot_lines.symmetric_difference(rules_lines))
    score = max(0, 10 - diff)
    return score, f"SSOT 与 rules 副本有 {diff} 行差异"


def grade(total):
    """总分映射为字母等级"""
    thresholds = [
        (90, "A"), (85, "A-"), (80, "B+"), (75, "B"),
        (70, "C+"), (65, "C"), (60, "D"),
    ]
    for threshold, letter in thresholds:
        if total >= threshold:
            return letter
    return "F"


def main():
    """Run reflex-audit analysis and print JSON report."""
    stats = load_stats()
    if not stats:
        print("ERROR: Cannot load trigger-stats.json", file=sys.stderr)
        sys.exit(1)

    scores = {}
    scores["coverage"] = score_coverage(stats)
    scores["failure_recovery"] = score_failure_recovery(stats)
    scores["efficiency"] = score_efficiency(stats)
    scores["balance"] = score_balance(stats)
    scores["cb_health"] = score_cb_health(stats)
    scores["consistency"] = score_consistency()

    # 加权总分
    total = 0
    for dim, (score, _) in scores.items():
        # score 0-10, weight sums to 1.0, result 0-100
        total += score * WEIGHTS[dim] * 10

    total = round(total, 1)
    letter = grade(total)

    # 输出结果
    result = {
        "total_score": total,
        "grade": letter,
        "dimensions": {},
    }
    dim_names = {
        "coverage": "覆盖度",
        "failure_recovery": "失败恢复",
        "efficiency": "效率",
        "balance": "均衡性",
        "cb_health": "CB 健康",
        "consistency": "一致性",
    }

    for dim, (score, desc) in scores.items():
        result["dimensions"][dim] = {
            "name": dim_names[dim],
            "score": score,
            "weight": WEIGHTS[dim],
            "description": desc,
        }

    # 热力图数据
    heatmap = []
    rules = stats.get("rules", {})
    for r in REFLECTIONS:
        entry = rules.get(r, {})
        total_uses = entry.get("success", 0) + entry.get("failure", 0)
        if total_uses > 0:
            ok = entry.get("success", 0)
            success_rate = round(ok / total_uses * 100, 1)
        else:
            success_rate = None
        heatmap.append({
            "reflection": r,
            "total_uses": total_uses,
            "success_rate": success_rate,
            "cb_state": entry.get("cb_state", "UNKNOWN"),
        })

    result["heatmap"] = heatmap

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
