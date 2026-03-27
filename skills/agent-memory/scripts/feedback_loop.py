"""Phase 3 反馈学习循环：记忆权重动态调整 + 决策链路径效率评分 + 渐进式升级。

两层反馈 + 混合信号 + 渐进式学习：
1. 记忆层：单条记忆的权重随使用反馈动态调整
2. 决策链层：workflow 路径效率评分指导未来路由
3. 混合模式：自动推断（80%）+ b1 手动覆盖（高权重）
4. 渐进式：降权 → 告警 → 硬约束
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dataclasses
from pathlib import Path
from typing import Optional

import yaml

from memory_store import Memory, MemoryStore


# ==================== 信号权重表 ====================

# event → (delta_positive, delta_negative)
_MEMORY_WEIGHTS = {
    "task_success":  (1, 0),
    "task_retry":    (0, 1),
    "audit_pass":    (2, 0),
    "audit_fail":    (0, 2),
    "user_positive": (3, 0),
    "user_negative": (0, 3),
}

# event → run_score_delta（无覆盖时）
_WORKFLOW_SCORE_DELTAS = {
    "no_retry":      2,
    "with_retry":    0,
    "degraded":      -1,
    "failed":        -2,
    "user_override": 0,   # 用户覆盖时忽略此值，直接使用 score_override
}


# ==================== 记忆层反馈 ====================

def infer_memory_feedback(
    memory_id: str,
    event: str,
    store: MemoryStore,
) -> dict:
    """根据事件自动推断反馈并更新记忆的 positive/negative_feedback。

    Args:
        memory_id: 目标记忆 ID
        event: 事件类型 — "task_success" | "task_retry" | "audit_pass" |
               "audit_fail" | "user_positive" | "user_negative"
        store: 记忆存储实例

    Returns:
        dict: {
            "memory_id": str,
            "event": str,
            "delta_positive": int,
            "delta_negative": int,
            "new_positive": int,
            "new_negative": int,
        }
    """
    if event not in _MEMORY_WEIGHTS:
        raise ValueError(f"未知事件类型: {event!r}，支持：{list(_MEMORY_WEIGHTS.keys())}")

    memory = store.get(memory_id)
    if memory is None:
        raise KeyError(f"记忆 {memory_id!r} 不存在")

    delta_pos, delta_neg = _MEMORY_WEIGHTS[event]
    updated = dataclasses.replace(
        memory,
        positive_feedback=memory.positive_feedback + delta_pos,
        negative_feedback=memory.negative_feedback + delta_neg,
    )
    store.update(updated)

    return {
        "memory_id": memory_id,
        "event": event,
        "delta_positive": delta_pos,
        "delta_negative": delta_neg,
        "new_positive": updated.positive_feedback,
        "new_negative": updated.negative_feedback,
    }


def get_feedback_ratio(memory: Memory) -> float:
    """计算反馈比率：positive / (positive + negative)，无反馈返回 0.5。"""
    total = memory.positive_feedback + memory.negative_feedback
    if total == 0:
        return 0.5
    return memory.positive_feedback / total


def check_memory_health(memory: Memory) -> str:
    """返回记忆健康状态：'healthy' | 'warning' | 'blocked'。

    规则（优先级从高到低）：
    - blocked: ratio <= 0.2 且 negative >= 5
    - warning: ratio <= 0.4 且 negative >= 3
    - healthy: 其他情况（包括总反馈 < 3）
    """
    total = memory.positive_feedback + memory.negative_feedback
    if total < 3:
        return "healthy"

    ratio = get_feedback_ratio(memory)
    neg = memory.negative_feedback

    if ratio <= 0.2 and neg >= 5:
        return "blocked"
    if ratio <= 0.4 and neg >= 3:
        return "warning"
    return "healthy"


# ==================== 决策链层反馈 ====================

def _read_frontmatter(path: str) -> tuple[dict, str]:
    """读取 MD 文件，返回 (frontmatter_dict, body_text)。"""
    content = Path(path).read_text(encoding='utf-8')
    if not content.startswith("---\n"):
        return {}, content

    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, content

    fm_text = parts[0][4:]   # 去掉首行 "---\n"
    body = parts[1]
    fm = yaml.safe_load(fm_text) or {}
    return fm, body


def _write_frontmatter(path: str, fm: dict, body: str) -> None:
    """将 frontmatter + body 写回 MD 文件。"""
    yaml_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    Path(path).write_text(f"---\n{yaml_text}---\n{body}", encoding='utf-8')


def score_workflow_run(
    run_path: str,
    event: str,
    score_override: Optional[int] = None,
) -> dict:
    """评分决策链执行记录，写入 score 字段到 MD frontmatter。

    score 字段：累加（非覆盖），除非使用 score_override。

    Args:
        run_path: workflows/runs/*.md 文件路径
        event: "no_retry" | "with_retry" | "degraded" | "failed" | "user_override"
        score_override: b1 手动覆盖时使用（直接设置绝对值）

    Returns:
        dict: {"run_path": str, "event": str, "score": int, "previous_score": int}
    """
    fm, body = _read_frontmatter(run_path)
    previous_score = int(fm.get("score") or 0)

    if score_override is not None:
        new_score = score_override
    else:
        if event not in _WORKFLOW_SCORE_DELTAS:
            raise ValueError(f"未知 workflow 事件: {event!r}")
        delta = _WORKFLOW_SCORE_DELTAS[event]
        new_score = previous_score + delta

    fm["score"] = new_score
    _write_frontmatter(run_path, fm, body)

    return {
        "run_path": run_path,
        "event": event,
        "previous_score": previous_score,
        "score": new_score,
    }


def get_path_efficiency(
    workflow_name: str,
    store_path: str = "~/.claude/memory/workflows/runs/",
) -> dict:
    """统计某 workflow 模板的历史效率。

    扫描 store_path 下所有 *.md 文件，筛选 frontmatter.workflow == workflow_name。

    Returns:
        dict: {
            "workflow_name": str,
            "total_runs": int,
            "avg_score": float,
            "success_rate": float,   # score > 0 的比率
            "common_failures": list, # 负分 run 的文件名列表
        }
    """
    runs_dir = Path(os.path.expanduser(store_path))

    scores = []
    common_failures = []

    if runs_dir.exists():
        for md_file in sorted(runs_dir.glob("*.md")):
            try:
                fm, _ = _read_frontmatter(str(md_file))
            except Exception:
                continue

            if fm.get("workflow") != workflow_name:
                continue

            score = int(fm.get("score") or 0)
            scores.append(score)
            if score < 0:
                common_failures.append(md_file.name)

    if not scores:
        return {
            "workflow_name": workflow_name,
            "total_runs": 0,
            "avg_score": 0.0,
            "success_rate": 0.0,
            "common_failures": [],
        }

    avg = sum(scores) / len(scores)
    success_rate = sum(1 for s in scores if s > 0) / len(scores)

    return {
        "workflow_name": workflow_name,
        "total_runs": len(scores),
        "avg_score": avg,
        "success_rate": success_rate,
        "common_failures": common_failures,
    }


# ==================== 渐进式学习 ====================

def check_escalation(
    pattern: str,
    store_path: str = "~/.claude/memory/root/",
) -> str:
    """检查某个失败模式是否需要升级。

    扫描 {store_path}/patterns/ 下匹配 {pattern}_*.md 的文件计数。

    返回：'none' | 'downweight' | 'warning' | 'block'
    - 0 次           → none
    - 1-2 次同类负反馈 → downweight
    - 3-4 次         → warning
    - >= 5 次         → block
    """
    base = Path(os.path.expanduser(store_path))
    patterns_dir = base / "patterns"

    if not patterns_dir.exists():
        return "none"

    count = sum(
        1 for f in patterns_dir.iterdir()
        if f.is_file() and f.name.startswith(f"{pattern}_") and f.suffix == ".md"
    )

    if count == 0:
        return "none"
    elif count < 3:
        return "downweight"
    elif count < 5:
        return "warning"
    else:
        return "block"


def apply_escalation(
    pattern: str,
    level: str,
    target: str,
    store: Optional[MemoryStore] = None,
    warnings_dir: Optional[str] = None,
    blocked_paths_file: Optional[str] = None,
) -> dict:
    """执行升级动作。

    Args:
        pattern: 失败模式描述（如 "skip_exploration_before_implement"）
        level: "downweight" | "warning" | "block"
        target: 影响目标 — "memory:{id}" | "workflow:{name}" | "path:{description}"
        store: MemoryStore 实例（downweight memory 时必须）
        warnings_dir: 告警目录（warning 级别，默认 ~/.claude/memory/root/warnings/）
        blocked_paths_file: blocked-paths.md 路径（block 级别，默认 ~/.claude/docs/blocked-paths.md）

    Returns:
        dict: {"pattern": str, "level": str, "target": str, "action": str}
    """
    if level == "downweight":
        return _apply_downweight(pattern, target, store)
    elif level == "warning":
        return _apply_warning(pattern, target, warnings_dir)
    elif level == "block":
        return _apply_block(pattern, target, blocked_paths_file)
    else:
        raise ValueError(f"未知升级级别: {level!r}，支持：downweight / warning / block")


def _apply_downweight(pattern: str, target: str, store: Optional[MemoryStore]) -> dict:
    """降低记忆 importance 30%（向下取整，最低为 1）。"""
    action = "downweight:no-op"

    if target.startswith("memory:") and store is not None:
        memory_id = target[len("memory:"):]
        memory = store.get(memory_id)
        if memory:
            old_importance = memory.importance
            # 降低 30%，最小为 1
            new_importance = max(1, int(old_importance * 0.7))
            updated = dataclasses.replace(memory, importance=new_importance)
            store.update(updated)
            action = f"downweight:importance {old_importance} → {new_importance}"

    return {
        "pattern": pattern,
        "level": "downweight",
        "target": target,
        "action": action,
    }


def _apply_warning(pattern: str, target: str, warnings_dir: Optional[str]) -> dict:
    """写入 warnings/{pattern}.md 告警文件。"""
    if warnings_dir is None:
        warnings_dir = os.path.expanduser("~/.claude/memory/root/warnings")

    dir_path = Path(os.path.expanduser(warnings_dir))
    dir_path.mkdir(parents=True, exist_ok=True)

    warning_file = dir_path / f"{pattern}.md"
    fm = {"pattern": pattern, "level": "warning", "target": target}
    yaml_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    content = (
        f"---\n{yaml_text}---\n\n"
        f"# 告警：{pattern}\n\n"
        f"- 失败模式：{pattern}\n"
        f"- 影响目标：{target}\n"
        f"- 处理：此路径历史表现差，执行时请注意。\n"
    )
    warning_file.write_text(content, encoding='utf-8')

    return {
        "pattern": pattern,
        "level": "warning",
        "target": target,
        "action": f"warning:written to {warning_file}",
    }


def _apply_block(pattern: str, target: str, blocked_paths_file: Optional[str]) -> dict:
    """写入 blocked-paths.md，追加而非覆盖。"""
    if blocked_paths_file is None:
        blocked_paths_file = os.path.expanduser("~/.claude/docs/blocked-paths.md")

    file_path = Path(os.path.expanduser(blocked_paths_file))
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式
    if file_path.exists():
        existing = file_path.read_text(encoding='utf-8')
    else:
        existing = "# 已阻断路径\n\n"

    entry = f"- **{pattern}**: {target}\n"
    if entry.strip() not in existing:
        updated = existing.rstrip("\n") + "\n" + entry
        file_path.write_text(updated, encoding='utf-8')

    return {
        "pattern": pattern,
        "level": "block",
        "target": target,
        "action": f"block:appended to {file_path}",
    }


# ==================== 检索时集成 ====================

def filter_by_health(
    memories: list,
    include_warning: bool = True,
) -> list:
    """检索时过滤：blocked 记忆被排除，warning 记忆按标志保留或排除。

    Args:
        memories: Memory 列表
        include_warning: True 保留 warning 记忆（默认），False 排除

    Returns:
        过滤后的 Memory 列表
    """
    result = []
    for mem in memories:
        health = check_memory_health(mem)
        if health == "blocked":
            continue
        if health == "warning" and not include_warning:
            continue
        result.append(mem)
    return result


# ==================== Phase 1C: Stale Memory Detection ====================

def identify_stale_memories(
    store: MemoryStore,
    min_days: int = 30,
    min_retrievals: int = 0,
    now=None,
) -> list:
    """找出长期未被检索的低价值记忆。

    判定条件（全部满足）：
    - retrieval_count <= min_retrievals
    - importance < 5
    - 创建至今 >= min_days 天

    Args:
        store: MemoryStore 实例
        min_days: 最少创建天数（默认 30）
        min_retrievals: 最大允许检索次数（默认 0，即从未被检索）
        now: 当前时间（用于测试）

    Returns:
        list[Memory]: 符合过期条件的记忆列表
    """
    from datetime import datetime as _dt

    if now is None:
        now = _dt.now()

    stale = []
    for mem in store.load_all():
        retrieval_count = getattr(mem, 'retrieval_count', 0)
        importance = mem.importance
        if retrieval_count <= min_retrievals and importance < 5:
            try:
                created = _dt.fromisoformat(mem.timestamp)
                age_days = (now - created).days
                if age_days >= min_days:
                    stale.append(mem)
            except (ValueError, TypeError):
                continue
    return stale
