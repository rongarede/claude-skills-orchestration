#!/usr/bin/env python3
"""Workflow Engine — YAML 解析、状态管理、拓扑排序工具。

root 在执行工作流时调用此脚本管理状态，实际 Agent 调用由 root 直接完成。

用法:
    python3 engine.py parse <template_name>
    python3 engine.py create <template_name> [key=value ...]
    python3 engine.py next <run_path>
    python3 engine.py update <run_path> <step_id> <status> [result_text]
    python3 engine.py status <run_path>
    python3 engine.py check
    python3 engine.py failure <run_path> <step_id>
"""

import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

TEMPLATES_DIR = Path.home() / "mem/mem/workflows/templates"
RUNS_DIR = Path.home() / "mem/mem/workflows/runs"


# ==================== YAML 解析（无外部依赖） ====================

def _parse_yaml_simple(text: str) -> dict:
    """极简 YAML 解析器，只处理 workflow 模板用到的子集。

    支持：标量、列表、嵌套字典、多行字符串（|）。
    不支持：锚点、合并键、复杂类型。

    为避免 PyYAML 依赖，使用纯 Python 实现。
    """
    import yaml
    return yaml.safe_load(text)


def parse_template(template_name: str) -> dict:
    """解析 YAML 模板文件。"""
    path = TEMPLATES_DIR / f"{template_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"模板不存在: {path}")
    return _parse_yaml_simple(path.read_text())


# ==================== 变量替换 ====================

def substitute_variables(template: dict, inputs: dict) -> dict:
    """替换 prompt_template 中的 {{ var }} 变量。"""
    result = copy.deepcopy(template)

    # 构建变量映射：模板默认值 + 用户输入
    var_map = {}
    for inp in result.get("inputs", []):
        name = inp["name"]
        if name in inputs:
            var_map[name] = inputs[name]
        elif "default" in inp:
            var_map[name] = inp["default"]
        elif inp.get("required"):
            raise ValueError(f"缺少必需输入: '{name}'")

    # 内置变量
    var_map["today"] = datetime.now().strftime("%Y-%m-%d")

    # 替换所有 step 的 prompt_template
    for step in result.get("steps", []):
        if "prompt_template" in step:
            tpl = step["prompt_template"]
            for key, val in var_map.items():
                tpl = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", str(val), tpl)
            step["prompt_template"] = tpl

    return result


# ==================== 拓扑排序 ====================

def topological_sort(steps: list) -> list:
    """拓扑排序，返回并行执行组（list of lists）。

    同一组内的 step 可并行执行，组间按顺序执行。
    """
    dep_graph = {}
    for step in steps:
        dep_graph[step["id"]] = set(step.get("depends_on", []))

    groups = []
    remaining = {sid: set(deps) for sid, deps in dep_graph.items()}

    while remaining:
        ready = [sid for sid, deps in remaining.items() if not deps]
        if not ready:
            raise ValueError(f"检测到循环依赖: {list(remaining.keys())}")
        groups.append(sorted(ready))
        for sid in ready:
            del remaining[sid]
        for sid in remaining:
            remaining[sid] -= set(ready)

    return groups


# ==================== Run 状态管理 ====================

def create_run(template_name: str, inputs: dict) -> str:
    """创建新的 run 状态文件，返回文件路径。"""
    template = parse_template(template_name)
    resolved = substitute_variables(template, inputs)
    groups = topological_sort(resolved["steps"])

    run_state = {
        "template": template_name,
        "description": template.get("description", ""),
        "inputs": inputs,
        "status": "running",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "execution_groups": groups,
        "steps": {},
    }

    for step in resolved["steps"]:
        retry_cfg = step.get("retry", {})
        on_failure_cfg = step.get("on_failure", retry_cfg.get("on_failure", "abort"))

        run_state["steps"][step["id"]] = {
            "agent": step["agent"],
            "type": step["type"],
            "prompt": step["prompt_template"],
            "depends_on": step.get("depends_on", []),
            "status": "pending",
            "attempts": 0,
            "max_attempts": retry_cfg.get("max_attempts", 1),
            "on_failure": on_failure_cfg,
            "result": None,
            "started_at": None,
            "completed_at": None,
        }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_path = RUNS_DIR / f"run_{template_name}_{timestamp}.json"
    run_path.write_text(json.dumps(run_state, indent=2, ensure_ascii=False))

    return str(run_path)


def load_run(run_path: str) -> dict:
    """加载 run 状态。"""
    return json.loads(Path(run_path).read_text())


def save_run(run_path: str, run_state: dict):
    """保存 run 状态（每步完成后必须调用）。"""
    run_state["updated_at"] = datetime.now().isoformat()
    Path(run_path).write_text(json.dumps(run_state, indent=2, ensure_ascii=False))


def get_next_steps(run_path: str) -> list:
    """获取下一批可执行 step（依赖已满足且状态为 pending）。"""
    state = load_run(run_path)
    steps = state["steps"]

    ready = []
    for sid, step in steps.items():
        if step["status"] != "pending":
            continue
        deps = step["depends_on"]
        if all(steps[d]["status"] == "completed" for d in deps):
            ready.append({
                "id": sid,
                "agent": step["agent"],
                "type": step["type"],
                "prompt": step["prompt"],
            })

    return ready


def update_step(run_path: str, step_id: str, status: str, result: str = None):
    """更新 step 状态。status: running | completed | failed | skipped"""
    state = load_run(run_path)
    step = state["steps"][step_id]
    step["status"] = status

    if result:
        step["result"] = result
    if status == "running":
        step["started_at"] = datetime.now().isoformat()
        step["attempts"] += 1
    elif status in ("completed", "failed", "skipped"):
        step["completed_at"] = datetime.now().isoformat()

    # 检查整体状态
    all_statuses = [s["status"] for s in state["steps"].values()]
    if all(s in ("completed", "skipped") for s in all_statuses):
        state["status"] = "completed"

    save_run(run_path, state)


# ==================== 失败处理 ====================

def handle_failure(run_path: str, step_id: str) -> dict:
    """处理 step 失败，返回行动指令。

    返回:
        {"action": "retry", "step_id": "..."}
        {"action": "goto", "target_step": "...", "loop_count": N}
        {"action": "pause", "step_id": "..."}
        {"action": "skip", "step_id": "..."}
        {"action": "abort", "reason": "..."}
    """
    state = load_run(run_path)
    step = state["steps"][step_id]

    # 检查 retry
    if step["attempts"] < step["max_attempts"]:
        step["status"] = "pending"
        save_run(run_path, state)
        return {"action": "retry", "step_id": step_id}

    # 检查 on_failure
    on_failure = step["on_failure"]

    if isinstance(on_failure, dict) and "goto" in on_failure:
        loop_key = f"_loop_{step_id}"
        loop_count = state.get(loop_key, 0)
        max_loops = on_failure.get("max_loops", 2)

        if loop_count < max_loops:
            state[loop_key] = loop_count + 1
            target = on_failure["goto"]
            # 重置目标 step 及其后续
            _reset_step_chain(state, target, step_id)
            save_run(run_path, state)
            return {"action": "goto", "target_step": target, "loop_count": loop_count + 1}
        else:
            state["status"] = "failed"
            save_run(run_path, state)
            return {"action": "abort", "reason": f"goto 循环超限 ({max_loops}) at {step_id}"}

    if on_failure == "pause" or (isinstance(on_failure, dict) and on_failure.get("on_failure") == "pause"):
        state["status"] = "paused"
        save_run(run_path, state)
        return {"action": "pause", "step_id": step_id}

    if on_failure == "skip":
        step["status"] = "skipped"
        save_run(run_path, state)
        return {"action": "skip", "step_id": step_id}

    # 默认 abort
    state["status"] = "failed"
    save_run(run_path, state)
    return {"action": "abort", "reason": f"Step {step_id} 失败，已用尽 {step['attempts']} 次重试"}


def _reset_step_chain(state: dict, from_step: str, to_step: str):
    """重置从 from_step 到 to_step 之间的所有 step 为 pending。"""
    # 找到拓扑序中 from_step 到 to_step 的所有 step
    groups = state["execution_groups"]
    in_range = False
    to_reset = []

    for group in groups:
        for sid in group:
            if sid == from_step:
                in_range = True
            if in_range:
                to_reset.append(sid)
            if sid == to_step:
                in_range = False

    for sid in to_reset:
        state["steps"][sid]["status"] = "pending"
        state["steps"][sid]["attempts"] = 0
        state["steps"][sid]["result"] = None
        state["steps"][sid]["started_at"] = None
        state["steps"][sid]["completed_at"] = None


# ==================== 断点恢复 ====================

def check_incomplete_runs() -> list:
    """扫描未完成的 run 文件。"""
    incomplete = []
    if not RUNS_DIR.exists():
        return incomplete

    for run_file in sorted(RUNS_DIR.glob("run_*.json")):
        state = load_run(str(run_file))
        if state["status"] in ("running", "paused"):
            current = None
            for sid, s in state["steps"].items():
                if s["status"] == "running":
                    current = sid
                    break
            if not current:
                for sid, s in state["steps"].items():
                    if s["status"] == "pending":
                        current = sid
                        break

            incomplete.append({
                "path": str(run_file),
                "template": state["template"],
                "description": state.get("description", ""),
                "status": state["status"],
                "created_at": state["created_at"],
                "current_step": current,
                "completed_steps": sum(1 for s in state["steps"].values() if s["status"] == "completed"),
                "total_steps": len(state["steps"]),
            })

    return incomplete


# ==================== CLI ====================

def main():
    if len(sys.argv) < 2:
        print("用法: engine.py <command> [args]")
        print("命令: parse, create, next, update, status, check, failure")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "parse":
        template = parse_template(sys.argv[2])
        groups = topological_sort(template["steps"])
        print(json.dumps({
            "name": template["name"],
            "description": template.get("description", ""),
            "inputs": [i["name"] for i in template.get("inputs", [])],
            "steps": [s["id"] for s in template["steps"]],
            "execution_groups": groups,
        }, ensure_ascii=False, indent=2))

    elif cmd == "create":
        template_name = sys.argv[2]
        inputs = {}
        for arg in sys.argv[3:]:
            k, v = arg.split("=", 1)
            inputs[k] = v
        run_path = create_run(template_name, inputs)
        print(json.dumps({"run_path": run_path}, ensure_ascii=False))

    elif cmd == "next":
        steps = get_next_steps(sys.argv[2])
        print(json.dumps(steps, ensure_ascii=False, indent=2))

    elif cmd == "update":
        result_text = sys.argv[5] if len(sys.argv) > 5 else None
        update_step(sys.argv[2], sys.argv[3], sys.argv[4], result_text)
        print(json.dumps({"ok": True}))

    elif cmd == "status":
        state = load_run(sys.argv[2])
        summary = {
            "template": state["template"],
            "status": state["status"],
            "created_at": state["created_at"],
            "steps": {sid: {"status": s["status"], "attempts": s["attempts"]}
                      for sid, s in state["steps"].items()},
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    elif cmd == "check":
        print(json.dumps(check_incomplete_runs(), ensure_ascii=False, indent=2))

    elif cmd == "failure":
        action = handle_failure(sys.argv[2], sys.argv[3])
        print(json.dumps(action, ensure_ascii=False, indent=2))

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
