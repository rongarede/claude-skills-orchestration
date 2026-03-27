#!/usr/bin/env python3
"""TDD 测试：generate-index 增量更新机制。

覆盖场景：
- 首次运行生成完整索引
- 无变化时跳过重新解析
- 新文件被添加到索引
- 修改文件被重新解析
- 删除文件从索引移除
- .index-meta.json 被创建并维护
- --force 强制全量重建
- meta 损坏时回退全量
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

# ---- 将 scripts 目录加入 sys.path ----
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

from memory_store import Memory, MemoryStore


# ==================== 辅助函数 ====================

def make_memory(store: MemoryStore, mem_id: str, name: str, mem_type: str = "task") -> Memory:
    """在 store 中创建一条记忆并返回。"""
    mem = Memory(
        id=mem_id,
        content=f"内容：{name}",
        timestamp=datetime.now().isoformat(),
        name=name,
        description=f"描述：{name}",
        type=mem_type,
        keywords=[name, "test"],
        tags=["test"],
        context="测试上下文",
        importance=5,
    )
    store.add(mem)
    return mem


def get_meta(store_path: Path) -> dict:
    """读取 .index-meta.json，返回 dict。"""
    meta_path = store_path / ".index-meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def get_index_content(store_path: Path) -> str:
    """读取 MEMORY.md 内容。"""
    index_path = store_path / "MEMORY.md"
    if not index_path.exists():
        return ""
    return index_path.read_text(encoding="utf-8")


def run_generate_index(store_path: Path, force: bool = False) -> dict:
    """调用 _generate_index_incremental 并返回结果统计。

    返回 dict 包含 keys: processed, skipped, removed
    """
    import cli as cli_module
    return cli_module._generate_index_incremental(store_path, force=force)


# ==================== 测试类 ====================

class TestFirstRun:
    """首次运行：无 meta 文件时生成完整索引。"""

    def test_first_run_generates_full_index(self, tmp_path):
        """首次运行时，所有 mem_*.md 文件都被解析，生成完整 MEMORY.md。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_first", "first-task", "task")
        make_memory(store, "mem_002_knowledge_second", "second-knowledge", "knowledge")

        result = run_generate_index(tmp_path)

        # MEMORY.md 存在
        assert (tmp_path / "MEMORY.md").exists()

        # 包含两条记忆
        content = get_index_content(tmp_path)
        assert "first-task" in content
        assert "second-knowledge" in content

        # 统计信息：处理了 2 个文件，跳过 0 个
        assert result["processed"] == 2
        assert result["skipped"] == 0

    def test_first_run_creates_meta_file(self, tmp_path):
        """首次运行后 .index-meta.json 被创建。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_alpha", "alpha", "task")

        run_generate_index(tmp_path)

        meta_path = tmp_path / ".index-meta.json"
        assert meta_path.exists(), ".index-meta.json 应当被创建"

        meta = get_meta(tmp_path)
        # meta 应记录文件 mtime
        assert len(meta) >= 1
        # key 应是文件名，value 应是 mtime（数字）
        for filename, mtime in meta.items():
            assert isinstance(filename, str)
            assert isinstance(mtime, (int, float))

    def test_first_run_empty_store(self, tmp_path):
        """首次运行时 store 为空，MEMORY.md 被创建（仅含标题）。"""
        run_generate_index(tmp_path)

        # MEMORY.md 应存在但内容仅含标题
        assert (tmp_path / "MEMORY.md").exists()
        content = get_index_content(tmp_path)
        assert "# Memory Index" in content

        result_stats = run_generate_index(tmp_path)
        assert result_stats["processed"] == 0


class TestNoChangesSkips:
    """无变化时跳过重新解析。"""

    def test_no_changes_skips_all_files(self, tmp_path):
        """第二次运行，文件未修改，processed=0，skipped=文件数。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_beta", "beta", "task")
        make_memory(store, "mem_002_task_gamma", "gamma", "task")

        # 首次运行
        run_generate_index(tmp_path)

        # 等待一点时间确保时间戳区分
        time.sleep(0.05)

        # 第二次运行（文件未变化）
        result = run_generate_index(tmp_path)

        # 两个文件都应被跳过
        assert result["skipped"] == 2
        assert result["processed"] == 0

    def test_no_changes_preserves_existing_index(self, tmp_path):
        """无变化时，MEMORY.md 内容保持不变。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_delta", "delta", "task")

        run_generate_index(tmp_path)
        content_before = get_index_content(tmp_path)

        run_generate_index(tmp_path)
        content_after = get_index_content(tmp_path)

        assert content_before == content_after


class TestNewFileAdded:
    """新文件被添加到索引。"""

    def test_new_file_added_to_index(self, tmp_path):
        """新增记忆文件后，generate-index 只处理新文件并更新索引。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_existing", "existing", "task")

        # 首次运行
        result1 = run_generate_index(tmp_path)
        assert result1["processed"] == 1

        # 添加新记忆
        time.sleep(0.05)
        make_memory(store, "mem_002_task_newfile", "newfile", "task")

        # 第二次运行：只处理新文件
        result2 = run_generate_index(tmp_path)
        assert result2["processed"] == 1
        assert result2["skipped"] == 1

        # 新文件出现在索引中
        content = get_index_content(tmp_path)
        assert "existing" in content
        assert "newfile" in content

    def test_new_file_updates_meta(self, tmp_path):
        """新文件被处理后，meta 中应记录新文件的 mtime。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_oldfile", "oldfile", "task")
        run_generate_index(tmp_path)

        meta_before = get_meta(tmp_path)
        count_before = len(meta_before)

        time.sleep(0.05)
        make_memory(store, "mem_002_task_freshfile", "freshfile", "task")
        run_generate_index(tmp_path)

        meta_after = get_meta(tmp_path)
        assert len(meta_after) == count_before + 1


class TestModifiedFileUpdated:
    """修改文件被重新解析。"""

    def test_modified_file_reprocessed(self, tmp_path):
        """文件 mtime 变化后，该文件被重新解析。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = make_memory(store, "mem_001_task_modtest", "original-name", "task")

        run_generate_index(tmp_path)

        # 确认 original-name 在索引中
        assert "original-name" in get_index_content(tmp_path)

        # 等待并修改文件（直接写入新内容，mtime 会变）
        time.sleep(0.05)
        mem_file = tmp_path / f"{mem.id}.md"
        original_content = mem_file.read_text(encoding="utf-8")
        # 在文件末尾加一个注释来改变 mtime
        mem_file.write_text(original_content + "\n<!-- modified -->", encoding="utf-8")

        # 第二次运行
        result = run_generate_index(tmp_path)
        assert result["processed"] == 1
        assert result["skipped"] == 0

    def test_modified_file_updates_meta_mtime(self, tmp_path):
        """修改文件后，meta 中该文件的 mtime 应被更新。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = make_memory(store, "mem_001_task_mtimetest", "mtime-test", "task")

        run_generate_index(tmp_path)
        meta_before = get_meta(tmp_path)
        mem_filename = f"{mem.id}.md"
        old_mtime = meta_before.get(mem_filename)
        assert old_mtime is not None

        # 修改文件 mtime
        time.sleep(0.05)
        mem_file = tmp_path / mem_filename
        mem_file.write_text(mem_file.read_text(encoding="utf-8") + "\n<!-- touched -->", encoding="utf-8")

        run_generate_index(tmp_path)
        meta_after = get_meta(tmp_path)
        new_mtime = meta_after.get(mem_filename)

        assert new_mtime != old_mtime, "meta 中的 mtime 应被更新"
        assert new_mtime > old_mtime


class TestDeletedFileRemoved:
    """删除文件从索引移除。"""

    def test_deleted_file_removed_from_index(self, tmp_path):
        """删除 mem_*.md 文件后，generate-index 从索引中移除该条目。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_keep", "keep-me", "task")
        mem_del = make_memory(store, "mem_002_task_delete", "delete-me", "task")

        run_generate_index(tmp_path)
        assert "delete-me" in get_index_content(tmp_path)

        # 删除文件
        (tmp_path / f"{mem_del.id}.md").unlink()
        time.sleep(0.05)

        result = run_generate_index(tmp_path)

        # 索引中不再包含被删除的记忆
        content = get_index_content(tmp_path)
        assert "delete-me" not in content
        assert "keep-me" in content

        # 统计中记录了移除数
        assert result["removed"] == 1

    def test_deleted_file_removed_from_meta(self, tmp_path):
        """删除文件后，meta 中对应条目被清除。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = make_memory(store, "mem_001_task_todelete", "to-delete", "task")

        run_generate_index(tmp_path)
        meta_before = get_meta(tmp_path)
        assert f"{mem.id}.md" in meta_before

        # 删除文件
        (tmp_path / f"{mem.id}.md").unlink()
        run_generate_index(tmp_path)

        meta_after = get_meta(tmp_path)
        assert f"{mem.id}.md" not in meta_after


class TestMetaFileCreated:
    """测试 .index-meta.json 文件的创建与维护。"""

    def test_meta_file_created_on_first_run(self, tmp_path):
        """generate-index 首次运行后创建 .index-meta.json。"""
        assert not (tmp_path / ".index-meta.json").exists()

        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_metacheck", "meta-check", "task")
        run_generate_index(tmp_path)

        assert (tmp_path / ".index-meta.json").exists()

    def test_meta_contains_correct_mtime(self, tmp_path):
        """meta 文件中记录的 mtime 与文件系统实际 mtime 一致。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = make_memory(store, "mem_001_task_precise", "precise", "task")

        run_generate_index(tmp_path)

        mem_file = tmp_path / f"{mem.id}.md"
        actual_mtime = mem_file.stat().st_mtime

        meta = get_meta(tmp_path)
        recorded_mtime = meta.get(f"{mem.id}.md")
        assert recorded_mtime is not None
        assert abs(recorded_mtime - actual_mtime) < 0.001, "meta 中的 mtime 应与文件系统一致"

    def test_meta_only_tracks_mem_files(self, tmp_path):
        """meta 只追踪 mem_*.md 文件，不包含其他文件（如 MEMORY.md、.index-meta.json）。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_onlymem", "only-mem", "task")
        run_generate_index(tmp_path)

        meta = get_meta(tmp_path)
        for filename in meta:
            assert filename.startswith("mem_"), f"meta 中不应包含非 mem_ 文件：{filename}"
            assert filename.endswith(".md")


class TestForceRebuild:
    """--force 选项强制全量重建。"""

    def test_force_rebuilds_all_files(self, tmp_path):
        """--force 时即使文件未变化也全量处理。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_force1", "force1", "task")
        make_memory(store, "mem_002_task_force2", "force2", "task")

        # 首次运行
        run_generate_index(tmp_path)

        # 再次运行（无 force）：应跳过
        result_normal = run_generate_index(tmp_path)
        assert result_normal["skipped"] == 2
        assert result_normal["processed"] == 0

        # --force 运行：应全量处理
        result_force = run_generate_index(tmp_path, force=True)
        assert result_force["processed"] == 2
        assert result_force["skipped"] == 0

    def test_force_preserves_correct_content(self, tmp_path):
        """--force 重建后 MEMORY.md 内容仍然正确。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_forcecontent", "force-content", "task")

        run_generate_index(tmp_path)
        content_normal = get_index_content(tmp_path)

        run_generate_index(tmp_path, force=True)
        content_force = get_index_content(tmp_path)

        assert content_normal == content_force

    def test_force_updates_meta(self, tmp_path):
        """--force 运行后 meta 被完整更新。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_forcemeta", "force-meta", "task")

        run_generate_index(tmp_path)
        meta_before = get_meta(tmp_path)

        time.sleep(0.05)
        run_generate_index(tmp_path, force=True)
        meta_after = get_meta(tmp_path)

        # meta 文件的条目数量应相同
        assert len(meta_before) == len(meta_after)


class TestCorruptedMetaFallback:
    """meta 损坏时回退全量重建。"""

    def test_corrupted_json_fallback_to_full(self, tmp_path):
        """meta 文件包含无效 JSON 时，回退到全量重建。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_corrupt1", "corrupt1", "task")
        make_memory(store, "mem_002_task_corrupt2", "corrupt2", "task")

        # 首次正常运行
        run_generate_index(tmp_path)

        # 损坏 meta 文件
        meta_path = tmp_path / ".index-meta.json"
        meta_path.write_text("{invalid json{{", encoding="utf-8")

        # 应回退到全量重建，不报错
        result = run_generate_index(tmp_path)
        assert result["processed"] == 2
        assert result["skipped"] == 0

        # MEMORY.md 内容应正确
        content = get_index_content(tmp_path)
        assert "corrupt1" in content
        assert "corrupt2" in content

    def test_corrupted_meta_gets_recreated(self, tmp_path):
        """meta 损坏后全量重建，meta 文件应被重新创建为有效 JSON。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_recreate", "recreate", "task")

        run_generate_index(tmp_path)

        # 损坏 meta
        (tmp_path / ".index-meta.json").write_text("not-valid-json", encoding="utf-8")

        run_generate_index(tmp_path)

        # meta 应被重新创建为有效 JSON
        meta_path = tmp_path / ".index-meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert isinstance(meta, dict)

    def test_empty_meta_file_fallback(self, tmp_path):
        """meta 文件为空时，回退到全量重建。"""
        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_emptymeta", "empty-meta", "task")

        run_generate_index(tmp_path)

        # 清空 meta 文件（不是有效 JSON 对象）
        (tmp_path / ".index-meta.json").write_text("", encoding="utf-8")

        result = run_generate_index(tmp_path)
        assert result["processed"] >= 1


class TestCLIIntegration:
    """通过 CLI 子命令集成测试 generate-index 增量功能。"""

    def test_generate_index_via_cli(self, tmp_path):
        """通过 CLI generate-index 子命令验证增量机制可用。"""
        import subprocess
        import sys

        cli_path = os.path.join(SCRIPTS_DIR, 'cli.py')

        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_clicmd", "cli-cmd", "task")

        result = subprocess.run(
            [sys.executable, cli_path, '--store', str(tmp_path), 'generate-index'],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert (tmp_path / "MEMORY.md").exists()

    def test_generate_index_force_via_cli(self, tmp_path):
        """通过 CLI generate-index --force 验证强制重建可用。"""
        import subprocess
        import sys

        cli_path = os.path.join(SCRIPTS_DIR, 'cli.py')

        store = MemoryStore(store_path=str(tmp_path))
        make_memory(store, "mem_001_task_cliforcetest", "cli-force-test", "task")

        # 首次运行
        subprocess.run(
            [sys.executable, cli_path, '--store', str(tmp_path), 'generate-index'],
            capture_output=True, text=True, timeout=30
        )

        # 强制重建
        result = subprocess.run(
            [sys.executable, cli_path, '--store', str(tmp_path), 'generate-index', '--force'],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        assert "cli-force-test" in get_index_content(tmp_path)
