"""测试：损坏记忆文件自动恢复（R5-C）。

覆盖场景：
- 正常文件不受影响
- YAML 损坏的文件被跳过
- 损坏日志文件被创建
- 日志包含文件路径和错误信息
- 混合场景：有效文件正常加载，损坏文件跳过
- 空文件被跳过
- 缺少 frontmatter 的文件被跳过
- repair 子命令报告损坏文件
- --fix 修复常见问题
- 干净 store 报告无问题
- 多个损坏文件全部记录到日志
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore


# ==================== 辅助函数 ====================

def _make_memory(**kwargs) -> Memory:
    """返回一条最小化默认 Memory，可被 kwargs 覆盖。"""
    defaults = dict(
        id="mem_20260315_001",
        content="测试记忆内容",
        timestamp="2026-03-15T10:00:00",
        keywords=["测试", "记忆", "恢复"],
        tags=["test"],
        context="R5-C 测试",
        importance=5,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


def _write_raw(store: MemoryStore, filename: str, content: str) -> Path:
    """直接向 store 目录写入原始内容（绕过序列化，用于构造损坏文件）。"""
    path = store.store_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def _corrupted_log_path(store: MemoryStore) -> Path:
    return store.store_path / ".corrupted_memories.log"


# ==================== 测试类 ====================

class TestValidFilesLoadedNormally:
    """test_valid_files_loaded_normally：正常文件加载不受容错机制影响。"""

    def test_valid_files_loaded_normally(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        mem1 = _make_memory(id="mem_20260315_001", content="内容1")
        mem2 = _make_memory(id="mem_20260315_002", content="内容2")
        store.add(mem1)
        store.add(mem2)

        results = store.load_all()
        ids = [m.id for m in results]
        assert "mem_20260315_001" in ids
        assert "mem_20260315_002" in ids
        assert len(results) == 2

    def test_valid_file_content_preserved(self, tmp_path):
        """正常文件加载后内容完整。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = _make_memory(id="mem_20260315_003", content="重要的技术决策记录", importance=9)
        store.add(mem)

        results = store.load_all()
        assert len(results) == 1
        assert results[0].content == "重要的技术决策记录"
        assert results[0].importance == 9


class TestCorruptedYamlSkipped:
    """test_corrupted_yaml_skipped：YAML 损坏的文件被跳过，不导致 crash。"""

    def test_corrupted_yaml_skipped(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        # 写入一个有效记忆
        mem = _make_memory(id="mem_valid_001", content="有效记忆")
        store.add(mem)
        # 写入损坏文件：YAML 语法错误
        _write_raw(store, "mem_corrupted_001.md", "---\nid: broken\n  invalid: yaml: ::::\n---\n\n内容")

        results = store.load_all()
        ids = [m.id for m in results]
        # 有效文件正常加载
        assert "mem_valid_001" in ids
        # 损坏文件不在结果中
        assert len(results) == 1

    def test_invalid_yaml_does_not_crash(self, tmp_path):
        """任意 YAML 损坏都不应导致异常。"""
        store = MemoryStore(store_path=str(tmp_path))
        # 多种不同损坏形式
        _write_raw(store, "mem_corrupt_a.md", "---\n{invalid json-like}\n---\n\n内容")
        _write_raw(store, "mem_corrupt_b.md", "---\nkey: [unclosed\n---\n\n内容")

        # 不应抛出异常
        results = store.load_all()
        assert isinstance(results, list)


class TestCorruptedLogCreated:
    """test_corrupted_log_created：损坏日志文件被创建在 store 目录。"""

    def test_corrupted_log_created(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_bad_001.md", "---\nbad: yaml: : :\n---\n内容")

        store.load_all()

        log_path = _corrupted_log_path(store)
        assert log_path.exists(), f"日志文件未创建：{log_path}"

    def test_log_not_created_for_clean_store(self, tmp_path):
        """干净 store（无损坏文件）不应创建日志文件。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = _make_memory(id="mem_clean_001")
        store.add(mem)

        store.load_all()

        log_path = _corrupted_log_path(store)
        # 如果存在则内容应为空（或不存在）
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8").strip()
            assert content == "", f"干净 store 的日志不应有内容：{content}"


class TestLogContainsErrorDetails:
    """test_log_contains_error_details：日志包含时间戳、文件路径和错误信息。"""

    def test_log_contains_file_path(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_path_test.md", "---\nbroken: yaml: :\n---\n内容")

        store.load_all()

        log_path = _corrupted_log_path(store)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "mem_path_test.md" in log_content

    def test_log_contains_timestamp(self, tmp_path):
        """日志条目包含时间戳（格式：YYYY-MM-DD 或 ISO 8601）。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_ts_test.md", "---\n: broken\n---\n内容")

        store.load_all()

        log_path = _corrupted_log_path(store)
        log_content = log_path.read_text(encoding="utf-8")
        # 检查日志中包含年份（时间戳的基本特征）
        current_year = str(datetime.now().year)
        assert current_year in log_content, f"日志应包含当前年份 {current_year}"

    def test_log_contains_error_message(self, tmp_path):
        """日志包含错误信息描述。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_err_msg.md", "not a frontmatter at all")

        store.load_all()

        log_path = _corrupted_log_path(store)
        log_content = log_path.read_text(encoding="utf-8")
        # 日志至少有 3 个 | 分隔字段
        assert "|" in log_content, "日志应使用 | 分隔字段"
        parts = [p.strip() for p in log_content.strip().split("|")]
        assert len(parts) >= 3, f"日志应有至少 3 个字段，实际: {parts}"

    def test_log_appends_multiple_errors(self, tmp_path):
        """多次加载损坏文件，日志追加（不覆盖）。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_append_test.md", "---\nbad_yaml: :\n---\n内容")

        store.load_all()
        store.load_all()

        log_path = _corrupted_log_path(store)
        log_content = log_path.read_text(encoding="utf-8")
        # 两次加载应有两条记录
        lines = [l for l in log_content.strip().splitlines() if l.strip()]
        assert len(lines) >= 2, f"日志应追加，实际行数: {len(lines)}"


class TestMixedValidAndCorrupted:
    """test_mixed_valid_and_corrupted：混合场景正确处理。"""

    def test_mixed_valid_and_corrupted(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))

        # 添加 3 个有效记忆
        for i in range(1, 4):
            store.add(_make_memory(id=f"mem_valid_{i:03d}", content=f"有效内容 {i}"))

        # 添加 2 个损坏文件
        _write_raw(store, "mem_broken_001.md", "---\nbad: yaml: :\n---\n损坏内容1")
        _write_raw(store, "mem_broken_002.md", "not frontmatter")

        results = store.load_all()

        # 只有 3 个有效记忆被加载
        assert len(results) == 3
        ids = [m.id for m in results]
        for i in range(1, 4):
            assert f"mem_valid_{i:03d}" in ids

        # 日志记录了 2 个损坏文件
        log_path = _corrupted_log_path(store)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "mem_broken_001.md" in log_content
        assert "mem_broken_002.md" in log_content


class TestEmptyFileSkipped:
    """test_empty_file_skipped：空文件被跳过（不 crash）。"""

    def test_empty_file_skipped(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_empty.md", "")

        results = store.load_all()
        assert isinstance(results, list)
        # 空文件不产生记忆
        assert len(results) == 0

    def test_empty_file_logged(self, tmp_path):
        """空文件被记录到日志。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_empty_logged.md", "")

        store.load_all()

        log_path = _corrupted_log_path(store)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "mem_empty_logged.md" in log_content


class TestMissingFrontmatterSkipped:
    """test_missing_frontmatter_skipped：缺少 frontmatter 的文件被跳过。"""

    def test_missing_frontmatter_skipped(self, tmp_path):
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_no_fm.md", "这是普通 Markdown 内容\n没有 frontmatter")

        results = store.load_all()
        assert len(results) == 0

    def test_missing_frontmatter_logged(self, tmp_path):
        """缺少 frontmatter 的文件被记录到日志。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_no_fm_log.md", "普通内容，无 frontmatter")

        store.load_all()

        log_path = _corrupted_log_path(store)
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "mem_no_fm_log.md" in log_content

    def test_only_opening_dashes(self, tmp_path):
        """只有开头 --- 但没有结束 --- 的文件被跳过。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_partial_fm.md", "---\nid: test\nno closing dashes\n内容")

        results = store.load_all()
        assert len(results) == 0


class TestCliRepairReports:
    """test_cli_repair_reports：repair 子命令报告损坏文件。"""

    def _cli_path(self):
        return str(Path(__file__).parent.parent / "scripts" / "cli.py")

    def test_cli_repair_reports_corrupted(self, tmp_path):
        """repair 命令扫描并报告损坏文件。"""
        store = MemoryStore(store_path=str(tmp_path))
        store.add(_make_memory(id="mem_valid_001"))
        _write_raw(store, "mem_bad.md", "---\nbad: yaml: :\n---\n内容")

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair"],
            capture_output=True, text=True
        )
        output = result.stdout + result.stderr
        # repair 应报告损坏文件
        assert "mem_bad.md" in output or "损坏" in output or "corrupted" in output.lower()

    def test_cli_repair_exits_zero(self, tmp_path):
        """repair 命令在有损坏文件时仍以 0 退出（报告不报错）。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_broken.md", "---\nbad yaml\n内容")

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair"],
            capture_output=True, text=True
        )
        assert result.returncode == 0

    def test_cli_repair_shows_error_reason(self, tmp_path):
        """repair 输出包含错误原因。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_reason.md", "no frontmatter at all")

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair"],
            capture_output=True, text=True
        )
        output = result.stdout + result.stderr
        assert "mem_reason.md" in output


class TestCliRepairFix:
    """test_cli_repair_fix：--fix 选项修复常见损坏问题。"""

    def _cli_path(self):
        return str(Path(__file__).parent.parent / "scripts" / "cli.py")

    def test_cli_repair_fix_missing_closing_delimiter(self, tmp_path):
        """--fix 修复缺少结束 --- 的文件。"""
        store = MemoryStore(store_path=str(tmp_path))
        # 创建一个只缺少结束 --- 的文件（frontmatter 格式接近正确）
        _write_raw(
            store,
            "mem_fixable.md",
            "---\nid: fixable_mem\ncontent: 可修复内容\ntimestamp: '2026-03-15T10:00:00'\n"
            "keywords: [test]\ntags: [fix]\ncontext: 修复测试\nimportance: 5\n\n内容文本"
        )

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair", "--fix"],
            capture_output=True, text=True
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0
        # 输出应说明尝试了修复
        assert "修复" in output or "fix" in output.lower() or "repair" in output.lower()

    def test_cli_repair_fix_reports_unfixable(self, tmp_path):
        """--fix 报告无法修复的文件（不删除）。"""
        store = MemoryStore(store_path=str(tmp_path))
        _write_raw(store, "mem_unfixable.md", "completely broken content no yaml")

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair", "--fix"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        # 无法修复的文件仍然存在
        assert (tmp_path / "mem_unfixable.md").exists()


class TestCliRepairCleanStore:
    """test_cli_repair_clean_store：干净 store 报告无问题。"""

    def _cli_path(self):
        return str(Path(__file__).parent.parent / "scripts" / "cli.py")

    def test_cli_repair_clean_store(self, tmp_path):
        """干净 store 运行 repair 输出无问题提示。"""
        store = MemoryStore(store_path=str(tmp_path))
        store.add(_make_memory(id="mem_clean_001", content="干净记忆1"))
        store.add(_make_memory(id="mem_clean_002", content="干净记忆2"))

        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # 应有"无问题"或"0 个"的提示
        assert (
            "0" in output
            or "无" in output
            or "clean" in output.lower()
            or "no corrupted" in output.lower()
            or "ok" in output.lower()
        ), f"干净 store 应报告无问题，实际输出: {output}"

    def test_cli_repair_empty_store(self, tmp_path):
        """空 store 运行 repair 不 crash。"""
        result = subprocess.run(
            [sys.executable, self._cli_path(), "--store", str(tmp_path), "repair"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
