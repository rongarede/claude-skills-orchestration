#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reflex-fuzz: 生成 fuzz 测试进度报告"""

import json
import os
from pathlib import Path
from datetime import datetime

STATS_FILE = Path(os.path.expanduser("~/mem/mem/workflows/trigger-stats.json"))
RUNS_DIR = Path(os.path.expanduser("~/mem/mem/workflows/runs"))

def main():
    # 统计
    with open(STATS_FILE) as f:
        data = json.load(f)

    rules = data.get("rules", data.get("reflexes", {}))
    total_success = sum(e.get("success", 0) for e in rules.values())
    total_failure = sum(e.get("failure", 0) for e in rules.values())
    total = total_success + total_failure

    # Fuzz runs
    fuzz_runs = sorted([
        f.name for f in RUNS_DIR.glob("*fuzz*")
    ])

    # 全部 runs
    all_runs = sorted([f.name for f in RUNS_DIR.glob("*.md")])

    print("## Fuzz 测试进度报告")
    print(f"\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"\n### 概览")
    print(f"- 反射总触发：{total}（成功 {total_success} / 失败 {total_failure}）")
    print(f"- 成功率：{total_success/total*100:.1f}%" if total > 0 else "- 成功率：N/A")
    print(f"- Workflow Runs 总数：{len(all_runs)}")
    print(f"- Fuzz Runs 数：{len(fuzz_runs)}")

    # CB 状态
    cb_issues = [name for name, e in rules.items() if e.get("cb_state") != "CLOSED"]
    if cb_issues:
        print(f"\nCB 非 CLOSED：{', '.join(cb_issues)}")
    else:
        print(f"\n全部 CB CLOSED")

    # Fuzz 轮次列表
    if fuzz_runs:
        print(f"\n### Fuzz 轮次")
        for run in fuzz_runs:
            print(f"- {run}")

if __name__ == "__main__":
    main()
