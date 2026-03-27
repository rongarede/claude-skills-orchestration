"""R4-B Scheduled Decay Hook 测试

TDD 流程：
1. RED: 先运行确认失败（session-start-decay-hook.py 尚未创建）
2. GREEN: 创建 hook 让测试通过
3. REFACTOR: 清理

测试覆盖：
  - test_first_run_executes        — 无 timestamp 文件时执行衰减
  - test_within_24h_skipped        — 24h 内跳过
  - test_after_24h_executes        — 超过 24h 执行
  - test_timestamp_updated         — 执行后更新 timestamp
  - test_max_stores_limit          — 最多处理 10 个 store
  - test_empty_stores_skipped      — 空 store 跳过（无 .md 文件）
  - test_timeout_protection        — 超时不阻塞主流程
  - test_store_discovery           — 正确发现所有 agent store 目录
"""

import os
import sys
import time
import shutil
import tempfile
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from typing import List

import pytest

# ==================== 导入目标模块（RED 阶段会 ImportError）====================

HOOK_PATH = Path(os.path.expanduser("~/.claude/hooks/session-start-decay-hook.py"))

# 动态导入 hook 模块（路径不在 sys.path 中，需要 importlib）
def _import_hook():
    """动态导入 session-start-decay-hook.py"""
    spec = importlib.util.spec_from_file_location(
        "session_start_decay_hook", str(HOOK_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==================== 辅助函数 ====================

def _make_store_dir(base_dir: Path, agent_type: str, agent_name: str, add_memories: bool = True) -> Path:
    """在 base_dir 下创建 agents/{agent_type}/{agent_name}/ store 目录。

    add_memories=True 时添加一个 .md 文件（非空 store）。
    """
    store_path = base_dir / "agents" / agent_type / agent_name
    store_path.mkdir(parents=True, exist_ok=True)

    if add_memories:
        # 创建一个简单的记忆文件（MEMORY.md 不算记忆）
        mem_file = store_path / "mem_test_001.md"
        mem_file.write_text(
            "---\nid: mem_test_001\nimportance: 5\ntimestamp: 2026-01-01T00:00:00\n---\n",
            encoding="utf-8",
        )

    return store_path


def _write_timestamp(timestamp_file: Path, dt: datetime):
    """写入 timestamp 文件（ISO 格式）。"""
    timestamp_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp_file.write_text(dt.isoformat(), encoding="utf-8")


# ==================== 测试类 ====================

class TestFirstRunExecutes:
    """test_first_run_executes — 无 timestamp 文件时执行衰减。"""

    def test_first_run_executes(self, tmp_path):
        """首次运行（无 timestamp 文件）应执行衰减并创建 timestamp 文件。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 创建一个有记忆的 store
        store_path = _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is True, "首次运行（无 timestamp）应返回 True（执行了衰减）"
        assert timestamp_file.exists(), "执行后应创建 timestamp 文件"
        assert len(decay_calls) > 0, "至少应对一个 store 执行衰减"


class TestWithin24hSkipped:
    """test_within_24h_skipped — 24h 内跳过。"""

    def test_within_24h_skipped(self, tmp_path):
        """距上次衰减 < 24h 时，应跳过并返回 False。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 写入 1 小时前的 timestamp
        recent_time = datetime.now() - timedelta(hours=1)
        _write_timestamp(timestamp_file, recent_time)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is False, "24h 内应跳过，返回 False"
        assert len(decay_calls) == 0, "24h 内不应调用任何衰减"

    def test_exactly_24h_executes(self, tmp_path):
        """恰好 24h 时，应执行衰减。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 写入 24h + 1 分钟前的 timestamp
        old_time = datetime.now() - timedelta(hours=24, minutes=1)
        _write_timestamp(timestamp_file, old_time)

        _make_store_dir(mem_base, "Explore", "kaze", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is True, "超过 24h 应执行衰减"


class TestAfter24hExecutes:
    """test_after_24h_executes — 超过 24h 执行。"""

    def test_after_24h_executes(self, tmp_path):
        """距上次衰减 > 24h 时，应执行衰减并返回 True。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 写入 25 小时前的 timestamp
        old_time = datetime.now() - timedelta(hours=25)
        _write_timestamp(timestamp_file, old_time)

        _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is True, "超过 24h 应执行衰减，返回 True"
        assert len(decay_calls) > 0, "超过 24h 应调用衰减函数"

    def test_very_old_timestamp_executes(self, tmp_path):
        """很久之前的 timestamp（如 7 天前）也应正常执行。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        old_time = datetime.now() - timedelta(days=7)
        _write_timestamp(timestamp_file, old_time)

        _make_store_dir(mem_base, "梦者", "yume", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is True, "7 天前的 timestamp 也应执行衰减"


class TestTimestampUpdated:
    """test_timestamp_updated — 执行后更新 timestamp。"""

    def test_timestamp_updated_after_execution(self, tmp_path):
        """执行衰减后，timestamp 文件应更新为当前时间。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 写入 25 小时前的旧 timestamp
        old_time = datetime.now() - timedelta(hours=25)
        _write_timestamp(timestamp_file, old_time)

        _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)

        before_run = datetime.now()

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        after_run = datetime.now()

        assert timestamp_file.exists(), "执行后 timestamp 文件应存在"

        new_ts_str = timestamp_file.read_text(encoding="utf-8").strip()
        new_ts = datetime.fromisoformat(new_ts_str)

        assert new_ts >= before_run, (
            f"更新后的 timestamp ({new_ts}) 应 >= 执行前时间 ({before_run})"
        )
        assert new_ts <= after_run + timedelta(seconds=1), (
            f"更新后的 timestamp ({new_ts}) 应 <= 执行后时间 ({after_run})"
        )

    def test_timestamp_not_updated_when_skipped(self, tmp_path):
        """24h 内跳过时，timestamp 文件不应被更新。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 写入 1 小时前的 timestamp
        recent_time = datetime.now() - timedelta(hours=1)
        _write_timestamp(timestamp_file, recent_time)

        original_content = timestamp_file.read_text(encoding="utf-8")

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        current_content = timestamp_file.read_text(encoding="utf-8")
        assert current_content == original_content, (
            "跳过时 timestamp 文件内容不应改变"
        )


class TestMaxStoresLimit:
    """test_max_stores_limit — 最多处理 10 个 store。"""

    def test_max_stores_limit(self, tmp_path):
        """当 agent store 超过 max_stores 时，只处理 max_stores 个。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 创建 15 个 store
        for i in range(15):
            _make_store_dir(mem_base, "Explore", f"agent_{i:02d}", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert len(decay_calls) <= 10, (
            f"max_stores=10 时最多处理 10 个，实际处理了 {len(decay_calls)} 个"
        )

    def test_max_stores_processes_all_when_fewer(self, tmp_path):
        """当 agent store 少于 max_stores 时，全部处理。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 创建 3 个 store
        for i in range(3):
            _make_store_dir(mem_base, "蚁工", f"worker_{i}", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert len(decay_calls) == 3, (
            f"store 少于 max_stores 时应全部处理，期望 3，实际 {len(decay_calls)}"
        )


class TestEmptyStoresSkipped:
    """test_empty_stores_skipped — 空 store（无 .md 记忆文件）跳过。"""

    def test_empty_store_skipped(self, tmp_path):
        """无 .md 记忆文件的 store 应被跳过，不调用衰减。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 创建一个空 store（无记忆文件）
        _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=False)

        # 再创建一个有记忆的 store
        _make_store_dir(mem_base, "Explore", "kaze", add_memories=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(Path(store_dir).name)
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        # 只有 kaze 有记忆，tetsu 空 store 应跳过
        assert "kaze" in decay_calls, "有记忆的 store（kaze）应被处理"
        assert "tetsu" not in decay_calls, "空 store（tetsu）应被跳过"

    def test_no_stores_at_all(self, tmp_path):
        """agents 目录为空时，应正常完成（不崩溃），返回 True（执行了扫描）。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 不创建任何 store
        (mem_base / "agents").mkdir(parents=True, exist_ok=True)

        decay_calls = []

        def mock_run_decay(store_dir: Path, timeout: float = 1.0) -> bool:
            decay_calls.append(str(store_dir))
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay):
            # 不应抛出异常
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )

        assert executed is True, "无 store 时也应返回 True（执行了扫描，只是无需衰减）"
        assert len(decay_calls) == 0, "无 store 时不应调用衰减"


class TestTimeoutProtection:
    """test_timeout_protection — 超时不阻塞主流程。"""

    def test_single_store_timeout_does_not_block(self, tmp_path):
        """单个 store 超时不阻塞整体流程，继续处理其他 store。"""
        hook = _import_hook()

        timestamp_file = tmp_path / ".last-decay-timestamp"
        mem_base = tmp_path

        # 创建 3 个 store
        _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)
        _make_store_dir(mem_base, "Explore", "kaze", add_memories=True)
        _make_store_dir(mem_base, "梦者", "yume", add_memories=True)

        decay_calls = []

        def mock_run_decay_with_timeout(store_dir: Path, timeout: float = 1.0) -> bool:
            """第一个 store 模拟超时（返回 False），其他正常。"""
            decay_calls.append(Path(store_dir).name)
            if Path(store_dir).name == "tetsu":
                return False  # 模拟超时失败
            return True

        with patch.object(hook, "_run_decay_for_store", side_effect=mock_run_decay_with_timeout):
            start = time.time()
            executed = hook.run_scheduled_decay(
                timestamp_file=timestamp_file,
                mem_base=mem_base,
                max_stores=10,
                cooldown_hours=24,
            )
            elapsed = time.time() - start

        # 超时不应导致整体阻塞超过 4 秒（hook 总超时）
        assert elapsed < 4.0, f"总执行时间 {elapsed:.2f}s 超过 4s 限制"
        # 其他 store 应继续处理
        assert len(decay_calls) >= 2, (
            f"一个 store 超时后，其他 store 应继续处理，实际处理了 {len(decay_calls)} 个"
        )

    def test_run_decay_for_store_respects_timeout(self, tmp_path):
        """_run_decay_for_store 内部应对慢速进程设置超时保护。"""
        hook = _import_hook()

        store_path = _make_store_dir(tmp_path, "蚁工", "tetsu", add_memories=True)

        # 使用真实的 _run_decay_for_store，但 mock subprocess 慢响应
        import subprocess

        def slow_process(*args, **kwargs):
            """模拟慢进程（超时）"""
            mock_proc = MagicMock()
            mock_proc.wait.side_effect = subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))
            mock_proc.returncode = None
            return mock_proc

        with patch("subprocess.Popen", side_effect=slow_process):
            start = time.time()
            result = hook._run_decay_for_store(store_path, timeout=0.1)
            elapsed = time.time() - start

        # 超时后函数应返回（不阻塞），时间应远小于 1 秒
        assert elapsed < 1.0, f"超时后函数应快速返回，实际耗时 {elapsed:.2f}s"
        assert result is False, "超时后应返回 False"


class TestStoreDiscovery:
    """test_store_discovery — 正确发现所有 agent store 目录。"""

    def test_discovers_all_agent_stores(self, tmp_path):
        """应发现 agents/{type}/{name}/ 格式的所有 store 目录。"""
        hook = _import_hook()

        mem_base = tmp_path

        # 创建多种类型的 agent store
        expected_stores = set()
        for type_name, agent_name in [
            ("蚁工", "tetsu"),
            ("Explore", "kaze"),
            ("Explore", "mirin"),
            ("梦者", "yume"),
            ("Auditor", "shin"),
        ]:
            store = _make_store_dir(mem_base, type_name, agent_name, add_memories=True)
            expected_stores.add(store.name)  # 用 name 比较（最后一层目录名）

        discovered = hook.discover_stores(mem_base)
        discovered_names = {Path(s).name for s in discovered}

        for expected in expected_stores:
            assert expected in discovered_names, (
                f"store {expected} 应被发现，但未找到。发现的 stores: {discovered_names}"
            )

    def test_does_not_discover_type_dirs(self, tmp_path):
        """不应将 agents/{type}/ 本身（类型目录）视为 store 目录。"""
        hook = _import_hook()

        mem_base = tmp_path

        # 创建 agents/蚁工/tetsu/（只有 tetsu 是真正的 store）
        _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)

        discovered = hook.discover_stores(mem_base)
        discovered_names = {Path(s).name for s in discovered}

        assert "蚁工" not in discovered_names, (
            "类型目录（蚁工）不应被识别为 store"
        )
        assert "tetsu" in discovered_names, "tetsu store 应被发现"

    def test_discovers_deeply_nested_agents(self, tmp_path):
        """测试发现深层嵌套的 agent store（agents/{type}/{name}/）。"""
        hook = _import_hook()

        mem_base = tmp_path

        # 创建一些边缘情况：不同中英文 type 名
        types_and_agents = [
            ("吞食者", "raiga"),
            ("母体", "norna"),
            ("Operator", "sora"),
        ]
        for type_name, agent_name in types_and_agents:
            _make_store_dir(mem_base, type_name, agent_name, add_memories=True)

        discovered = hook.discover_stores(mem_base)
        discovered_names = {Path(s).name for s in discovered}

        for _, agent_name in types_and_agents:
            assert agent_name in discovered_names, (
                f"agent {agent_name} 应被发现"
            )

    def test_nonexistent_mem_base_returns_empty(self, tmp_path):
        """mem_base 不存在时，discover_stores 应返回空列表，不崩溃。"""
        hook = _import_hook()

        non_existent = tmp_path / "nonexistent"

        result = hook.discover_stores(non_existent)

        assert result == [], (
            f"mem_base 不存在时应返回空列表，实际: {result}"
        )

    def test_sort_by_modification_time(self, tmp_path):
        """discover_stores 应按修改时间排序，最久未修改的优先（冷数据先衰减）。"""
        hook = _import_hook()

        mem_base = tmp_path

        # 创建 3 个 store，控制修改时间
        store1 = _make_store_dir(mem_base, "Explore", "kaze", add_memories=True)
        time.sleep(0.01)
        store2 = _make_store_dir(mem_base, "蚁工", "tetsu", add_memories=True)
        time.sleep(0.01)
        store3 = _make_store_dir(mem_base, "梦者", "yume", add_memories=True)

        discovered = hook.discover_stores(mem_base)
        discovered_names = [Path(s).name for s in discovered]

        # 最久未修改的（kaze）应排在前面
        assert discovered_names.index("kaze") < discovered_names.index("yume"), (
            "最久未修改的 store（kaze）应排在最新的（yume）之前"
        )
