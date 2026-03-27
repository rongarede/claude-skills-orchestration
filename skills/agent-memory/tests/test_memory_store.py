"""Tests for MemoryStore: directory + .md file storage backend."""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore


def _make_memory(**kwargs) -> Memory:
    """Return a minimal Memory with sensible defaults, overridden by kwargs."""
    defaults = dict(
        id="mem_20260310_001",
        content="修复 LaTeX fontspec 编译错误",
        timestamp="2026-03-10T10:00:00",
        keywords=["LaTeX", "fontspec", "编译错误"],
        tags=["bug-fix", "thesis"],
        context="XeLaTeX 路径配置问题",
        importance=7,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


class TestMemoryStoreInit:
    """MemoryStore 初始化行为。"""

    def test_accepts_directory_path(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            assert store.store_path == Path(tmp)
        finally:
            shutil.rmtree(tmp)

    def test_compat_jsonl_path_redirects_to_parent(self):
        """传入 .jsonl 路径时，自动降级为其父目录（兼容旧调用）。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            jsonl_path = os.path.join(tmp_dir, "memories.jsonl")
            store = MemoryStore(store_path=jsonl_path)
            assert store.store_path == Path(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir)

    def test_creates_directory_if_missing(self):
        tmp_dir = tempfile.mkdtemp()
        shutil.rmtree(tmp_dir)
        try:
            store = MemoryStore(store_path=tmp_dir)
            assert store.store_path.exists()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_agent_name_resolves_to_agents_subdir(self):
        store = MemoryStore(agent_name="test_agent_xyz")
        expected = Path(os.path.expanduser("~/.claude/memory/agents/test_agent_xyz"))
        try:
            assert store.store_path == expected
        finally:
            shutil.rmtree(str(expected), ignore_errors=True)


class TestMemoryStoreAdd:
    """add() 写入 .md 文件。"""

    def test_creates_md_file(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory()
            store.add(mem)
            md_path = Path(tmp) / f"{mem.id}.md"
            assert md_path.exists(), f"应创建 {md_path}"
        finally:
            shutil.rmtree(tmp)

    def test_md_file_has_frontmatter(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory()
            store.add(mem)
            content = (Path(tmp) / f"{mem.id}.md").read_text(encoding='utf-8')
            assert content.startswith("---\n"), "文件应以 YAML frontmatter 开头"
            assert "\n---\n" in content, "frontmatter 应以 --- 结尾"
        finally:
            shutil.rmtree(tmp)

    def test_frontmatter_contains_required_fields(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(importance=9, access_count=0)
            store.add(mem)
            content = (Path(tmp) / f"{mem.id}.md").read_text(encoding='utf-8')
            assert "importance: 9" in content
            assert "access_count: 0" in content
            assert "LaTeX" in content       # keyword
            assert "bug-fix" in content    # tag
        finally:
            shutil.rmtree(tmp)

    def test_frontmatter_content_body(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(content="这是记忆正文")
            store.add(mem)
            content = (Path(tmp) / f"{mem.id}.md").read_text(encoding='utf-8')
            assert "这是记忆正文" in content
        finally:
            shutil.rmtree(tmp)

    def test_related_ids_serialized_as_wikilinks(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(related_ids=["mem_20260310_002", "mem_20260311_001"])
            store.add(mem)
            content = (Path(tmp) / f"{mem.id}.md").read_text(encoding='utf-8')
            assert "[[mem_20260310_002]]" in content
            assert "[[mem_20260311_001]]" in content
        finally:
            shutil.rmtree(tmp)


class TestMemoryStoreGet:
    """get() 按 ID 读取单条记忆。"""

    def test_returns_none_for_missing_id(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            assert store.get("nonexistent_id") is None
        finally:
            shutil.rmtree(tmp)

    def test_roundtrip_preserves_all_fields(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(
                id="mem_20260310_001",
                importance=7,
                access_count=3,
                related_ids=["mem_20260310_002"],
                last_accessed="2026-03-10T16:00:00",
                owner="kaze",
                scope="personal",
            )
            store.add(mem)
            loaded = store.get(mem.id)

            assert loaded is not None
            assert loaded.id == mem.id
            assert loaded.content == mem.content
            assert loaded.timestamp == mem.timestamp
            assert loaded.keywords == mem.keywords
            assert loaded.tags == mem.tags
            assert loaded.context == mem.context
            assert loaded.importance == mem.importance
            assert loaded.access_count == mem.access_count
            assert loaded.related_ids == mem.related_ids
            assert loaded.last_accessed == mem.last_accessed
            assert loaded.owner == mem.owner
            assert loaded.scope == mem.scope
        finally:
            shutil.rmtree(tmp)


class TestMemoryStoreLoadAll:
    """load_all() 批量加载所有 .md 文件。"""

    def test_empty_directory_returns_empty_list(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            assert store.load_all() == []
        finally:
            shutil.rmtree(tmp)

    def test_loads_multiple_memories(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            m1 = _make_memory(id="mem_20260310_001", content="记忆 A")
            m2 = _make_memory(id="mem_20260310_002", content="记忆 B")
            store.add(m1)
            store.add(m2)
            all_mems = store.load_all()
            assert len(all_mems) == 2
            ids = {m.id for m in all_mems}
            assert "mem_20260310_001" in ids
            assert "mem_20260310_002" in ids
        finally:
            shutil.rmtree(tmp)

    def test_skips_non_frontmatter_files(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            # Write a broken .md file (no frontmatter)
            (Path(tmp) / "bad.md").write_text("no frontmatter here", encoding='utf-8')
            m = _make_memory()
            store.add(m)
            all_mems = store.load_all()
            # Only the valid memory should load
            assert len(all_mems) == 1
            assert all_mems[0].id == m.id
        finally:
            shutil.rmtree(tmp)

    def test_count_reflects_number_of_md_files(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            store.add(_make_memory(id="mem_20260310_001"))
            store.add(_make_memory(id="mem_20260310_002"))
            assert store.count() == 2
        finally:
            shutil.rmtree(tmp)


class TestMemoryStoreUpdate:
    """update() 覆写 .md 文件，持久化变更。"""

    def test_update_persists_changes(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(access_count=0)
            store.add(mem)

            mem.access_count = 5
            mem.context = "已更新的语境"
            store.update(mem)

            reloaded = store.get(mem.id)
            assert reloaded.access_count == 5
            assert reloaded.context == "已更新的语境"
        finally:
            shutil.rmtree(tmp)

    def test_update_does_not_create_duplicate_files(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory()
            store.add(mem)
            store.update(mem)
            md_files = list(Path(tmp).glob("*.md"))
            assert len(md_files) == 1
        finally:
            shutil.rmtree(tmp)


class TestMemoryStoreGenerateId:
    """generate_id() 自动生成不重复的 ID。"""

    def test_first_id_ends_with_001(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            today = datetime.now().strftime("%Y%m%d")
            mem_id = store.generate_id()
            assert mem_id == f"mem_{today}_001"
        finally:
            shutil.rmtree(tmp)

    def test_second_id_increments(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            today = datetime.now().strftime("%Y%m%d")
            # Simulate first memory already exists
            store.add(_make_memory(id=f"mem_{today}_001"))
            mem_id = store.generate_id()
            assert mem_id == f"mem_{today}_002"
        finally:
            shutil.rmtree(tmp)

    def test_custom_prefix(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem_id = store.generate_id(id_prefix="kaze_20260310")
            assert mem_id == "kaze_20260310_001"
        finally:
            shutil.rmtree(tmp)


class TestFrontmatterFormat:
    """YAML frontmatter 格式正确性验证。"""

    def test_unicode_content_preserved(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(
                content="梳理工作量证明、权益证明、委托权益证明三种共识机制",
                keywords=["区块链", "共识算法", "工作量证明"],
            )
            store.add(mem)
            reloaded = store.get(mem.id)
            assert reloaded.content == mem.content
            assert "区块链" in reloaded.keywords
        finally:
            shutil.rmtree(tmp)

    def test_empty_related_ids(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(related_ids=[])
            store.add(mem)
            reloaded = store.get(mem.id)
            assert reloaded.related_ids == []
        finally:
            shutil.rmtree(tmp)

    def test_none_last_accessed(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            mem = _make_memory(last_accessed=None)
            store.add(mem)
            reloaded = store.get(mem.id)
            assert reloaded.last_accessed is None
        finally:
            shutil.rmtree(tmp)

    def test_evolution_history_roundtrip(self):
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            history = [{"timestamp": "2026-03-10T10:00:00", "triggered_by": "mem_001",
                        "changes": {"context": {"old": "旧语境", "new": "新语境"}}}]
            mem = _make_memory(evolution_history=history)
            store.add(mem)
            reloaded = store.get(mem.id)
            assert len(reloaded.evolution_history) == 1
            assert reloaded.evolution_history[0]["triggered_by"] == "mem_001"
        finally:
            shutil.rmtree(tmp)


class TestLayerField:
    """Phase 8: layer 字段测试。"""

    def test_layer_field_default(self):
        """新创建的 Memory 默认 layer 为 L1。"""
        mem = _make_memory()
        assert mem.layer == "L1", f"默认 layer 应为 'L1'，实际：{mem.layer}"

    def test_layer_field_roundtrip(self):
        """L2/L3 记忆存取一致。"""
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            for layer_val in ["L0", "L1", "L2", "L3"]:
                mem = _make_memory(id=f"mem_layer_{layer_val}", layer=layer_val)
                store.add(mem)
                loaded = store.get(mem.id)
                assert loaded is not None
                assert loaded.layer == layer_val, (
                    f"layer 应为 '{layer_val}'，实际：{loaded.layer}"
                )
        finally:
            shutil.rmtree(tmp)

    def test_legacy_memory_no_layer(self):
        """旧记忆（无 layer 字段）加载时默认 L1。"""
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            # 手写一个不含 layer 字段的 frontmatter 文件
            legacy_content = """---
id: legacy_mem_001
name: ''
description: ''
type: task
owner: ''
scope: personal
importance: 5
access_count: 0
last_accessed: null
keywords:
- test
tags:
- test
context: 旧记忆
timestamp: '2026-03-10T10:00:00'
related: []
accessed_by: []
evolution_history: []
positive_feedback: 0
negative_feedback: 0
---

旧记忆内容
"""
            (Path(tmp) / "legacy_mem_001.md").write_text(legacy_content, encoding='utf-8')
            loaded = store.get("legacy_mem_001")
            assert loaded is not None
            assert loaded.layer == "L1", (
                f"旧记忆无 layer 字段时应默认 'L1'，实际：{loaded.layer}"
            )
        finally:
            shutil.rmtree(tmp)


class TestEmptyContentEdgeCase:
    """空 content 边界情况测试。"""

    def test_empty_content_roundtrip(self):
        """Memory with empty content should survive add→get roundtrip."""
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp)
            m = Memory(
                id="mem_20260315_999",
                name="empty test",
                description="test empty content",
                content="",
                keywords=["test"],
                tags=["test"],
                context="",
                importance=5,
                timestamp=datetime.now().isoformat(),
            )
            store.add(m)
            loaded = store.get("mem_20260315_999")
            assert loaded is not None, "Memory with empty content was lost!"
            assert loaded.id == "mem_20260315_999"
            assert loaded.content == ""
        finally:
            shutil.rmtree(tmp)


def run_tests():
    """Simple test runner (for direct execution without pytest)."""
    import traceback

    test_classes = [
        TestMemoryStoreInit,
        TestMemoryStoreAdd,
        TestMemoryStoreGet,
        TestMemoryStoreLoadAll,
        TestMemoryStoreUpdate,
        TestMemoryStoreGenerateId,
        TestFrontmatterFormat,
        TestEmptyContentEdgeCase,
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith('test_'):
                continue
            label = f"{cls.__name__}.{method_name}"
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  PASS  {label}")
            except Exception as exc:
                failed += 1
                errors.append((label, traceback.format_exc()))
                print(f"  FAIL  {label}: {exc}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        for name, tb in errors:
            print(f"\n--- {name} ---\n{tb}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
