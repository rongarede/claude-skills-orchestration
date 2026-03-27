"""
触发效率追踪器

追踪 trigger-map 规则的触发结果（成功/失败/跳过），
基于历史效率动态调整触发权重。

数据存储：~/mem/mem/workflows/trigger-stats.json
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

DEFAULT_STATS_PATH = Path(os.path.expanduser("~/mem/mem/workflows/trigger-stats.json"))

# 线程锁，用于基本的并发安全
_lock = threading.Lock()

VALID_RESULTS = {"success", "failure", "skip"}
WEIGHT_CEILING = 1.5
WEIGHT_FLOOR = 0.3
WEIGHT_HIGH_DELTA = 0.1
WEIGHT_LOW_DELTA = 0.2
EFFICIENCY_HIGH = 0.8
EFFICIENCY_LOW = 0.4
EFFICIENCY_DISABLE = 0.2
DISABLE_MIN_TRIGGERS = 5


# ==================== 内部辅助函数 ====================

def _load_stats(stats_path: Path) -> dict:
    """加载 stats 文件，不存在时返回空结构。"""
    if not stats_path.exists():
        return {"rules": {}, "updated_at": datetime.now().isoformat()}
    try:
        return json.loads(stats_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"rules": {}, "updated_at": datetime.now().isoformat()}


def _save_stats(data: dict, stats_path: Path) -> None:
    """保存 stats 文件，自动创建父目录。"""
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    stats_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_rule_defaults() -> dict:
    """返回规则的默认统计结构。"""
    return {
        "success": 0,
        "failure": 0,
        "skip": 0,
        "last_triggered": datetime.now().isoformat(),
        "weight": 1.0,
    }


# ==================== 公共 API ====================

def record_trigger(
    rule_name: str,
    result: str,
    stats_path: Path = DEFAULT_STATS_PATH,
) -> dict:
    """记录一次触发结果。

    Args:
        rule_name: 规则名称
        result: "success" | "failure" | "skip"
        stats_path: stats 文件路径

    Returns:
        更新后的规则统计字典
    """
    if result not in VALID_RESULTS:
        raise ValueError(f"result 必须是 {VALID_RESULTS}，实际收到: {result!r}")

    with _lock:
        data = _load_stats(stats_path)
        rules = data.setdefault("rules", {})
        rule = rules.setdefault(rule_name, _get_rule_defaults())
        rule[result] += 1
        rule["last_triggered"] = datetime.now().isoformat()
        _save_stats(data, stats_path)
        return dict(rule)


def get_efficiency(
    rule_name: str,
    stats_path: Path = DEFAULT_STATS_PATH,
) -> float:
    """计算规则的触发效率。

    效率 = success / (success + failure)，skip 不计入。
    无记录时返回 0.5（默认中性值）。

    Args:
        rule_name: 规则名称
        stats_path: stats 文件路径

    Returns:
        0.0 ~ 1.0 的效率值
    """
    data = _load_stats(stats_path)
    rule = data.get("rules", {}).get(rule_name)
    if rule is None:
        return 0.5

    success = rule.get("success", 0)
    failure = rule.get("failure", 0)
    total = success + failure
    if total == 0:
        return 0.5

    return success / total


def adjust_weight(
    rule_name: str,
    current_weight: float = 1.0,
    stats_path: Path = DEFAULT_STATS_PATH,
) -> tuple:
    """根据历史效率调整触发权重。

    规则：
    - 效率 > 80% → weight + 0.1，上限 1.5
    - 效率 40-80% → weight 不变
    - 效率 < 40% → weight - 0.2，下限 0.3
    - 效率 < 20% 且触发次数 >= 5 → suggestion = "disable"

    Args:
        rule_name: 规则名称
        current_weight: 当前权重（默认 1.0）
        stats_path: stats 文件路径

    Returns:
        (new_weight, suggestion)，suggestion 为 None 或 "disable"
    """
    efficiency = get_efficiency(rule_name, stats_path=stats_path)

    # 计算总触发次数（success + failure，skip 不算）
    data = _load_stats(stats_path)
    rule = data.get("rules", {}).get(rule_name, {})
    total_triggers = rule.get("success", 0) + rule.get("failure", 0)

    suggestion: Optional[str] = None

    if efficiency > EFFICIENCY_HIGH:
        new_weight = min(current_weight + WEIGHT_HIGH_DELTA, WEIGHT_CEILING)
    elif efficiency < EFFICIENCY_LOW:
        new_weight = max(current_weight - WEIGHT_LOW_DELTA, WEIGHT_FLOOR)
    else:
        new_weight = current_weight

    # 检查是否建议禁用
    if efficiency < EFFICIENCY_DISABLE and total_triggers >= DISABLE_MIN_TRIGGERS:
        suggestion = "disable"

    # 持久化 weight
    with _lock:
        stats = _load_stats(stats_path)
        if rule_name in stats.get("rules", {}):
            stats["rules"][rule_name]["weight"] = new_weight
            stats["updated_at"] = datetime.now().isoformat()
            _save_stats(stats, stats_path)

    return (new_weight, suggestion)


def get_all_stats(stats_path: Path = DEFAULT_STATS_PATH) -> dict:
    """返回所有规则的统计数据。

    Args:
        stats_path: stats 文件路径

    Returns:
        完整的 stats 数据字典
    """
    return _load_stats(stats_path)


def reset_stats(
    rule_name: str,
    stats_path: Path = DEFAULT_STATS_PATH,
) -> bool:
    """清除某条规则的统计数据。

    Args:
        rule_name: 规则名称
        stats_path: stats 文件路径

    Returns:
        True 如果规则存在并被删除，False 如果规则不存在
    """
    with _lock:
        data = _load_stats(stats_path)
        rules = data.get("rules", {})
        if rule_name not in rules:
            return False
        del rules[rule_name]
        _save_stats(data, stats_path)
        return True
