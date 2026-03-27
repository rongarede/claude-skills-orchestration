#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reflex-audit: 收集反射链统计数据和 workflow run 历史"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

STATS_PATH = Path(os.path.expanduser("~/mem/mem/workflows/trigger-stats.json"))
RUNS_DIR = Path(os.path.expanduser("~/mem/mem/workflows/runs"))
TRIGGER_MAP = Path(os.path.expanduser("~/mem/mem/workflows/trigger-map.md"))

REFLECTIONS = [
    "research", "explore", "implement", "document", "audit",
    "verify", "commit", "journal", "memory", "devour", "define"
]


def load_stats():
    """加载 trigger-stats.json"""
    if not STATS_PATH.exists():
        print(f"ERROR: {STATS_PATH} not found", file=sys.stderr)
        return None
    with open(STATS_PATH) as f:
        return json.load(f)


def scan_runs():
    """扫描 workflow runs 目录，提取 Phase 状态"""
    if not RUNS_DIR.exists():
        return []

    runs = []
    for path in sorted(RUNS_DIR.glob("*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")

        # 提取 frontmatter
        fm = {}
        fm_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()

        # 提取 Phase 表格行
        phases = []
        for line in content.splitlines():
            if line.startswith("|") and not line.startswith("| Phase") and not line.startswith("|---"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 4:
                    phase = {
                        "phase": cols[0],
                        "name": cols[1],
                        "agent": cols[2],
                        "status": cols[3],
                    }
                    if len(cols) >= 6:
                        phase["retry"] = cols[4]
                        phase["strategy"] = cols[5]
                    if len(cols) >= 7:
                        phase["summary"] = cols[6]
                    phases.append(phase)

        runs.append({
            "file": path.name,
            "frontmatter": fm,
            "phases": phases,
            "phase_count": len(phases),
        })

    return runs


def check_trigger_map():
    """检查 trigger-map.md 中定义的反射数量"""
    if not TRIGGER_MAP.exists():
        return {"exists": False}

    content = TRIGGER_MAP.read_text(encoding="utf-8")
    lines = content.splitlines()

    sections = []
    for line in lines:
        if line.startswith("## "):
            sections.append(line[3:].strip())

    return {
        "exists": True,
        "lines": len(lines),
        "sections": sections,
    }


def main():
    result = {
        "collected_at": datetime.now().isoformat(),
        "stats": None,
        "runs_summary": None,
        "trigger_map": None,
    }

    # 1. 统计数据
    stats = load_stats()
    if stats:
        reflection_stats = {}
        for r in REFLECTIONS:
            if r in stats.get("rules", {}):
                entry = stats["rules"][r]
                total = entry["success"] + entry["failure"] + entry["skip"]
                success_rate = (
                    round(entry["success"] / total * 100, 1) if total > 0 else None
                )
                reflection_stats[r] = {
                    "success": entry["success"],
                    "failure": entry["failure"],
                    "skip": entry["skip"],
                    "total": total,
                    "success_rate": success_rate,
                    "cb_state": entry.get("cb_state", "UNKNOWN"),
                    "cb_consecutive_failures": entry.get("cb_consecutive_failures", 0),
                }
            else:
                reflection_stats[r] = {"missing": True}

        result["stats"] = {
            "updated_at": stats.get("updated_at"),
            "reflections": reflection_stats,
        }

    # 2. Workflow runs
    runs = scan_runs()
    result["runs_summary"] = {
        "total_runs": len(runs),
        "runs": runs[:10],  # 最近 10 个
    }

    # 3. Trigger map
    result["trigger_map"] = check_trigger_map()

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
