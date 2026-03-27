#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
task-dispatcher: 任务拆分、依赖分析、时间预估
"""

import json
import re
import sys
from typing import List, Dict, Any, Tuple

# ==================== 时间预估配置 ====================

# 单位：秒
TIME_LIMITS = {
    "max_subtask": 120,      # 单个子任务最大时间（2分钟）
    "warning_threshold": 90,  # 警告阈值（1.5分钟）
    "min_subtask": 10,        # 最小合理时间（10秒）
}

# 任务类型预估时间（秒）
TASK_TIME_ESTIMATES = {
    # 简单任务 (10-30秒)
    "配置": 15,
    "修复": 20,
    "格式化": 15,
    "重命名": 20,
    "注释": 15,

    # 中等任务 (30-60秒)
    "函数": 45,
    "方法": 45,
    "测试": 60,
    "接口": 50,
    "类型": 40,

    # 复杂任务 (60-120秒) - 边界
    "功能": 90,
    "组件": 90,
    "服务": 100,

    # 过大任务 (>120秒) - 必须拆分
    "模块": 180,
    "系统": 300,
    "重构": 150,
    "架构": 240,
}

# ==================== 任务拆分 ====================

def should_split(task: str) -> bool:
    """
    判断任务是否需要拆分
    """
    # 必须拆分的情况
    if "并" in task or "和" in task or "+" in task:
        return True
    if count_target_files(task) > 1:
        return True
    if has_multiple_verbs(task):
        return True
    if estimated_lines_changed(task) > 100:
        return True
    return False


def count_target_files(task: str) -> int:
    """
    估算任务涉及的文件数量
    """
    # 简单启发式：文件路径模式
    file_patterns = re.findall(r'\b[\w/]+\.(ts|js|rs|py|go|java)\b', task)
    return len(set(file_patterns))


def has_multiple_verbs(task: str) -> bool:
    """
    检查任务是否包含多个动词（多个操作）
    """
    verbs = ["实现", "测试", "重构", "修复", "添加", "删除", "更新", "创建", "优化", "编写"]
    count = sum(1 for v in verbs if v in task)
    return count > 1


def estimated_lines_changed(task: str) -> int:
    """
    估算代码变更行数
    """
    # 简单启发式：根据任务复杂度关键词
    complexity_markers = {
        "模块": 200,
        "系统": 300,
        "功能": 100,
        "函数": 50,
        "方法": 30,
        "修复": 20,
        "配置": 10,
    }
    for marker, lines in complexity_markers.items():
        if marker in task:
            return lines
    return 50  # 默认


# ==================== 依赖分析 ====================

def analyze_dependencies(subtasks: List[Dict[str, Any]]) -> List[List[int]]:
    """
    分析子任务依赖关系，返回执行批次

    输入: [{"id": 1, "deps": []}, {"id": 2, "deps": [1]}, ...]
    输出: [[1], [2, 3], [4]]  # 每个内层列表是一个可并发批次
    """
    # 构建依赖图
    graph = {t["id"]: set(t.get("deps", [])) for t in subtasks}
    all_ids = set(graph.keys())

    batches = []
    completed = set()

    while len(completed) < len(all_ids):
        # 找出所有依赖已满足的任务
        ready = [
            tid for tid in all_ids
            if tid not in completed and graph[tid].issubset(completed)
        ]

        if not ready:
            # 检测循环依赖
            remaining = all_ids - completed
            raise ValueError(f"检测到循环依赖: {remaining}")

        batches.append(ready)
        completed.update(ready)

    return batches


# ==================== 验证结果 ====================

def is_verification_failed(exit_code: int, stdout: str, expected_pattern: str = None) -> bool:
    """
    判断验证是否失败
    """
    # 明确失败
    if exit_code != 0:
        return True

    # 输出包含错误标记
    error_markers = ["FAIL", "Error", "error:", "FAILED", "panic", "Exception"]
    if any(err in stdout for err in error_markers):
        return True

    # 预期内容缺失
    if expected_pattern and expected_pattern not in stdout:
        return True

    return False


# ==================== 时间预估 ====================

def estimate_task_time(task: str) -> Tuple[int, str, bool]:
    """
    预估任务执行时间

    返回: (预估秒数, 风险等级, 是否需要拆分)
    风险等级: "ok" | "warning" | "reject"
    """
    estimated_seconds = 30  # 默认 30 秒

    # 根据关键词匹配
    for keyword, seconds in TASK_TIME_ESTIMATES.items():
        if keyword in task:
            estimated_seconds = max(estimated_seconds, seconds)

    # 额外因素调整
    # 1. 多文件 +50%
    file_count = count_target_files(task)
    if file_count > 1:
        estimated_seconds = int(estimated_seconds * (1 + 0.3 * (file_count - 1)))

    # 2. 多动词 +30%
    if has_multiple_verbs(task):
        estimated_seconds = int(estimated_seconds * 1.3)

    # 3. 代码行数因素
    lines = estimated_lines_changed(task)
    if lines > 100:
        estimated_seconds = int(estimated_seconds * 1.5)

    # 判断风险等级
    max_time = TIME_LIMITS["max_subtask"]
    warning_time = TIME_LIMITS["warning_threshold"]

    if estimated_seconds > max_time:
        return (estimated_seconds, "reject", True)
    elif estimated_seconds > warning_time:
        return (estimated_seconds, "warning", False)
    else:
        return (estimated_seconds, "ok", False)


def check_timeout(actual_seconds: int, estimated_seconds: int) -> Tuple[str, str]:
    """
    检查实际执行时间与预估时间的偏差

    返回: (状态, 诊断信息)
    状态: "normal" | "slow" | "timeout" | "abnormal"
    """
    max_time = TIME_LIMITS["max_subtask"]

    # 硬超时
    if actual_seconds > max_time:
        return ("timeout", f"执行超时 ({actual_seconds}s > {max_time}s 限制)")

    # 计算偏差率
    if estimated_seconds > 0:
        deviation = (actual_seconds - estimated_seconds) / estimated_seconds
    else:
        deviation = 0

    # 偏差判断
    if deviation > 2.0:  # 超过预估 3 倍
        diagnosis = f"严重超时: 实际 {actual_seconds}s vs 预估 {estimated_seconds}s (偏差 {deviation:.0%})"
        return ("abnormal", diagnosis)
    elif deviation > 1.0:  # 超过预估 2 倍
        diagnosis = f"执行偏慢: 实际 {actual_seconds}s vs 预估 {estimated_seconds}s (偏差 {deviation:.0%})"
        return ("slow", diagnosis)
    elif deviation < -0.5:  # 比预估快 50% 以上
        diagnosis = f"执行过快: 实际 {actual_seconds}s vs 预估 {estimated_seconds}s (可能未完成)"
        return ("abnormal", diagnosis)
    else:
        return ("normal", f"正常: {actual_seconds}s (预估 {estimated_seconds}s)")


def diagnose_timeout(task: str, actual_seconds: int, estimated_seconds: int) -> Dict[str, Any]:
    """
    诊断超时原因，给出建议

    返回诊断报告
    """
    status, message = check_timeout(actual_seconds, estimated_seconds)

    diagnosis = {
        "status": status,
        "message": message,
        "actual_seconds": actual_seconds,
        "estimated_seconds": estimated_seconds,
        "task": task,
        "possible_causes": [],
        "recommendations": [],
    }

    if status in ("timeout", "abnormal", "slow"):
        # 分析可能原因
        if "node_modules" in task.lower() or "依赖" in task:
            diagnosis["possible_causes"].append("可能读取了 node_modules 等大目录")
            diagnosis["recommendations"].append("在 prompt 中明确禁止读取 node_modules")

        if has_multiple_verbs(task):
            diagnosis["possible_causes"].append("任务包含多个操作，应该拆分")
            diagnosis["recommendations"].append("将任务拆分为单一职责的子任务")

        if count_target_files(task) > 1:
            diagnosis["possible_causes"].append("任务涉及多个文件")
            diagnosis["recommendations"].append("每个子任务只处理一个文件")

        if estimated_lines_changed(task) > 100:
            diagnosis["possible_causes"].append("预估代码变更量过大")
            diagnosis["recommendations"].append("减小任务范围，分步实现")

        # 通用建议
        if not diagnosis["possible_causes"]:
            diagnosis["possible_causes"].append("任务描述可能不够具体")
            diagnosis["recommendations"].append("提供更具体的任务描述和参考代码")

        diagnosis["recommendations"].append("考虑在 prompt 中内联必要的参考代码")
        diagnosis["recommendations"].append("明确限定需要读取的文件列表")

    return diagnosis


# ==================== 拆分输出 ====================

def format_subtasks_yaml(subtasks: List[Dict[str, Any]]) -> str:
    """
    格式化子任务为 YAML
    """
    lines = ["子任务:"]
    for t in subtasks:
        lines.append(f"  - id: {t['id']}")
        lines.append(f"    描述: {t['desc']}")
        lines.append(f"    文件: {t['file']}")
        lines.append(f"    验证: \"{t['verify']}\"")
        deps = t.get("deps", [])
        lines.append(f"    依赖: {deps}")
        lines.append("")
    return "\n".join(lines)


def format_batches(batches: List[List[int]]) -> str:
    """
    格式化执行批次
    """
    lines = []
    for i, batch in enumerate(batches, 1):
        parallel_mark = "并发" if len(batch) > 1 else "串行"
        tasks = ", ".join(f"任务 {tid}" for tid in batch)
        lines.append(f"批次 {i} ({parallel_mark}): [{tasks}]")
    return "\n".join(lines)


# ==================== CLI ====================

def main():
    if len(sys.argv) < 2:
        print("用法: python task-logic.py <command> [args]")
        print("命令:")
        print("  should-split <task>       判断任务是否需要拆分")
        print("  analyze-deps <json>       分析依赖关系 (JSON 格式)")
        print("  verify <exit_code> <stdout> [expected]  判断验证是否失败")
        print("  estimate <task>           预估任务执行时间")
        print("  check-timeout <actual> <estimated>  检查超时状态")
        print("  diagnose <task> <actual> <estimated>  诊断超时原因")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "should-split":
        task = sys.argv[2] if len(sys.argv) > 2 else ""
        result = should_split(task)
        print(json.dumps({"should_split": result}))

    elif cmd == "analyze-deps":
        subtasks_json = sys.argv[2] if len(sys.argv) > 2 else "[]"
        subtasks = json.loads(subtasks_json)
        batches = analyze_dependencies(subtasks)
        print(json.dumps({"batches": batches}))
        print(format_batches(batches))

    elif cmd == "verify":
        exit_code = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        stdout = sys.argv[3] if len(sys.argv) > 3 else ""
        expected = sys.argv[4] if len(sys.argv) > 4 else None
        result = is_verification_failed(exit_code, stdout, expected)
        print(json.dumps({"failed": result}))

    elif cmd == "estimate":
        task = sys.argv[2] if len(sys.argv) > 2 else ""
        seconds, risk, need_split = estimate_task_time(task)
        result = {
            "estimated_seconds": seconds,
            "risk_level": risk,
            "need_split": need_split,
            "timeout_limit": TIME_LIMITS["max_subtask"],
        }
        print(json.dumps(result, ensure_ascii=False))

        # 人类可读输出
        risk_emoji = {"ok": "✅", "warning": "⚠️", "reject": "🚫"}[risk]
        print(f"\n预估时间: {seconds}s {risk_emoji}")
        if need_split:
            print("建议: 任务过大，需要拆分")

    elif cmd == "check-timeout":
        actual = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        estimated = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        status, message = check_timeout(actual, estimated)
        print(json.dumps({"status": status, "message": message}, ensure_ascii=False))

    elif cmd == "diagnose":
        task = sys.argv[2] if len(sys.argv) > 2 else ""
        actual = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        estimated = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        diagnosis = diagnose_timeout(task, actual, estimated)
        print(json.dumps(diagnosis, ensure_ascii=False, indent=2))

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
