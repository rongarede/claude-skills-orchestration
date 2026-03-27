"""测试 trigger_tracker.py — 触发效率追踪与权重调整"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


# ==================== 触发记录 ====================

def test_record_trigger_success(tmp_path):
    """记录一次成功触发，stats 文件更新"""
    from trigger_tracker import record_trigger
    stats_path = tmp_path / "trigger-stats.json"
    result = record_trigger("规则A", "success", stats_path=stats_path)
    assert result["success"] == 1
    assert result["failure"] == 0
    assert result["skip"] == 0
    assert stats_path.exists()


def test_record_trigger_failure(tmp_path):
    """记录一次失败触发"""
    from trigger_tracker import record_trigger
    stats_path = tmp_path / "trigger-stats.json"
    result = record_trigger("规则A", "failure", stats_path=stats_path)
    assert result["failure"] == 1
    assert result["success"] == 0


def test_record_trigger_skip(tmp_path):
    """记录一次跳过触发"""
    from trigger_tracker import record_trigger
    stats_path = tmp_path / "trigger-stats.json"
    result = record_trigger("规则A", "skip", stats_path=stats_path)
    assert result["skip"] == 1
    assert result["success"] == 0
    assert result["failure"] == 0


def test_record_multiple_triggers(tmp_path):
    """同一规则多次触发，计数累加"""
    from trigger_tracker import record_trigger
    stats_path = tmp_path / "trigger-stats.json"
    record_trigger("规则A", "success", stats_path=stats_path)
    record_trigger("规则A", "success", stats_path=stats_path)
    record_trigger("规则A", "failure", stats_path=stats_path)
    result = record_trigger("规则A", "skip", stats_path=stats_path)
    assert result["success"] == 2
    assert result["failure"] == 1
    assert result["skip"] == 1


# ==================== 效率计算 ====================

def test_get_efficiency_all_success(tmp_path):
    """全成功 → 效率 1.0"""
    from trigger_tracker import record_trigger, get_efficiency
    stats_path = tmp_path / "trigger-stats.json"
    record_trigger("规则B", "success", stats_path=stats_path)
    record_trigger("规则B", "success", stats_path=stats_path)
    eff = get_efficiency("规则B", stats_path=stats_path)
    assert eff == 1.0


def test_get_efficiency_mixed(tmp_path):
    """混合 → 正确比率"""
    from trigger_tracker import record_trigger, get_efficiency
    stats_path = tmp_path / "trigger-stats.json"
    # 3 success, 1 failure, 1 skip → efficiency = 3/4 = 0.75
    record_trigger("规则C", "success", stats_path=stats_path)
    record_trigger("规则C", "success", stats_path=stats_path)
    record_trigger("规则C", "success", stats_path=stats_path)
    record_trigger("规则C", "failure", stats_path=stats_path)
    record_trigger("规则C", "skip", stats_path=stats_path)
    eff = get_efficiency("规则C", stats_path=stats_path)
    assert abs(eff - 0.75) < 1e-9


def test_get_efficiency_no_records(tmp_path):
    """无记录 → 效率 0.5（默认中性）"""
    from trigger_tracker import get_efficiency
    stats_path = tmp_path / "trigger-stats.json"
    eff = get_efficiency("不存在的规则", stats_path=stats_path)
    assert eff == 0.5


# ==================== 权重调整 ====================

def test_adjust_weight_high_efficiency(tmp_path):
    """效率 > 80% → 权重 +0.1"""
    from trigger_tracker import record_trigger, adjust_weight
    stats_path = tmp_path / "trigger-stats.json"
    # 9 success, 1 failure → efficiency = 0.9
    for _ in range(9):
        record_trigger("规则D", "success", stats_path=stats_path)
    record_trigger("规则D", "failure", stats_path=stats_path)
    new_weight, suggestion = adjust_weight("规则D", current_weight=1.0, stats_path=stats_path)
    assert abs(new_weight - 1.1) < 1e-9
    assert suggestion is None


def test_adjust_weight_low_efficiency(tmp_path):
    """效率 < 40% → 权重 -0.2"""
    from trigger_tracker import record_trigger, adjust_weight
    stats_path = tmp_path / "trigger-stats.json"
    # 1 success, 4 failure → efficiency = 0.2
    record_trigger("规则E", "success", stats_path=stats_path)
    for _ in range(4):
        record_trigger("规则E", "failure", stats_path=stats_path)
    new_weight, suggestion = adjust_weight("规则E", current_weight=1.0, stats_path=stats_path)
    assert abs(new_weight - 0.8) < 1e-9


def test_adjust_weight_ceiling(tmp_path):
    """权重上限 1.5"""
    from trigger_tracker import record_trigger, adjust_weight
    stats_path = tmp_path / "trigger-stats.json"
    # all success → efficiency 1.0
    for _ in range(5):
        record_trigger("规则F", "success", stats_path=stats_path)
    new_weight, suggestion = adjust_weight("规则F", current_weight=1.5, stats_path=stats_path)
    assert new_weight <= 1.5
    assert new_weight == 1.5


def test_adjust_weight_floor(tmp_path):
    """权重下限 0.3"""
    from trigger_tracker import record_trigger, adjust_weight
    stats_path = tmp_path / "trigger-stats.json"
    # 1 success, 4 failure → efficiency = 0.2 < 0.4
    record_trigger("规则G", "success", stats_path=stats_path)
    for _ in range(4):
        record_trigger("规则G", "failure", stats_path=stats_path)
    new_weight, suggestion = adjust_weight("规则G", current_weight=0.3, stats_path=stats_path)
    assert new_weight >= 0.3
    assert new_weight == 0.3


def test_suggest_disable_persistent_failure(tmp_path):
    """效率 < 20% 持续 5 次 → 建议禁用"""
    from trigger_tracker import record_trigger, adjust_weight
    stats_path = tmp_path / "trigger-stats.json"
    # 0 success, 5 failure → efficiency = 0.0 < 0.2, count >= 5
    for _ in range(5):
        record_trigger("规则H", "failure", stats_path=stats_path)
    _, suggestion = adjust_weight("规则H", current_weight=0.5, stats_path=stats_path)
    assert suggestion == "disable"


# ==================== Stats 持久化 ====================

def test_stats_file_created(tmp_path):
    """首次记录时自动创建 stats 文件"""
    from trigger_tracker import record_trigger
    stats_path = tmp_path / "subdir" / "trigger-stats.json"
    assert not stats_path.exists()
    record_trigger("规则I", "success", stats_path=stats_path)
    assert stats_path.exists()


def test_stats_file_load_existing(tmp_path):
    """读取已有 stats 文件"""
    from trigger_tracker import record_trigger, get_efficiency
    stats_path = tmp_path / "trigger-stats.json"
    # 先写入
    record_trigger("规则J", "success", stats_path=stats_path)
    record_trigger("规则J", "success", stats_path=stats_path)
    # 再读取（模拟新进程）
    eff = get_efficiency("规则J", stats_path=stats_path)
    assert eff == 1.0


def test_stats_file_concurrent_safe(tmp_path):
    """并发安全（基本写入不丢失）"""
    from trigger_tracker import record_trigger
    import threading
    stats_path = tmp_path / "trigger-stats.json"
    errors = []

    def write_trigger():
        try:
            record_trigger("并发规则", "success", stats_path=stats_path)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=write_trigger) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    data = json.loads(stats_path.read_text())
    assert "rules" in data
    assert "并发规则" in data["rules"]
    assert data["rules"]["并发规则"]["success"] == 10
