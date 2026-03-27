"""Extended tests for obsidian_export.py covering missing lines:
173, 179-182, 208-211, 220, 223, 247-263

Key scenarios:
- export_mermaid_graph: high/medium/low importance nodes + edges
- export_all: empty store, with agent_name, with output_dir
- export_memory_note: various memory configurations
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from obsidian_export import (
    export_memory_note,
    export_moc,
    export_mermaid_graph,
    export_all,
)


def _make_memory(**kwargs) -> Memory:
    defaults = dict(
        id="mem_20260310_001",
        content="测试记忆",
        timestamp="2026-03-10T10:00:00",
        keywords=["测试"],
        tags=["test"],
        context="测试上下文",
        importance=5,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


# ==================== export_mermaid_graph() ====================

class TestExportMermaidGraph:
    """export_mermaid_graph() 各重要性级别和边生成。"""

    def test_high_importance_node(self):
        """importance >= 8 应生成 :::high 样式。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory(id="high_mem", importance=9, related_ids=[])]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            assert ":::high" in content
        finally:
            shutil.rmtree(tmp)

    def test_medium_importance_node(self):
        """importance 5-7 应生成 :::medium 样式。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory(id="med_mem", importance=6, related_ids=[])]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            assert ":::medium" in content
        finally:
            shutil.rmtree(tmp)

    def test_low_importance_node(self):
        """importance < 5 应生成 :::low 样式。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory(id="low_mem", importance=3, related_ids=[])]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            assert ":::low" in content
        finally:
            shutil.rmtree(tmp)

    def test_edge_generated_for_related_ids(self):
        """related_ids 不为空时应生成边。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [
                _make_memory(id="mem_a", related_ids=["mem_b"]),
                _make_memory(id="mem_b", related_ids=["mem_a"]),
            ]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            # Edge should appear exactly once (deduplication)
            assert "mem_a --- mem_b" in content or "mem_b --- mem_a" in content
        finally:
            shutil.rmtree(tmp)

    def test_no_duplicate_edges(self):
        """双向关联的边应去重，只出现一次。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [
                _make_memory(id="node1", related_ids=["node2"]),
                _make_memory(id="node2", related_ids=["node1"]),
            ]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            # Count edges — should only be one edge line
            edge_lines = [l for l in content.split('\n')
                         if ' --- ' in l and 'node1' in l and 'node2' in l]
            assert len(edge_lines) == 1
        finally:
            shutil.rmtree(tmp)

    def test_output_file_path(self):
        """输出文件应命名为 memory_graph.md。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory()]
            path = export_mermaid_graph(mems, out_dir)
            assert path.name == "memory_graph.md"
        finally:
            shutil.rmtree(tmp)

    def test_styles_in_output(self):
        """classDef 样式块应包含在输出中。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory()]
            path = export_mermaid_graph(mems, out_dir)
            content = path.read_text()
            assert "classDef high" in content
            assert "classDef medium" in content
            assert "classDef low" in content
        finally:
            shutil.rmtree(tmp)


# ==================== export_all() ====================

class TestExportAll:
    """export_all() 各种调用模式。"""

    def test_export_all_empty_store_returns_empty_status(self):
        """空 store 时返回 empty 状态。"""
        tmp = tempfile.mkdtemp()
        out_tmp = tempfile.mkdtemp()
        try:
            result = export_all(store_path=tmp, output_dir=out_tmp)
            assert result["status"] == "empty"
            assert result["count"] == 0
        finally:
            shutil.rmtree(tmp)
            shutil.rmtree(out_tmp)

    def test_export_all_with_memories(self):
        """有记忆时返回 success 状态，包含 count, notes, moc, graph。"""
        tmp_store = tempfile.mkdtemp()
        tmp_out = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_store)
            store.add(_make_memory(id="mem_export_001"))
            store.add(_make_memory(id="mem_export_002"))

            result = export_all(store_path=tmp_store, output_dir=tmp_out)
            assert result["status"] == "success"
            assert result["count"] == 2
            assert "moc" in result
            assert "graph" in result
            assert len(result["notes"]) == 2
        finally:
            shutil.rmtree(tmp_store)
            shutil.rmtree(tmp_out)

    def test_export_all_with_agent_name(self):
        """指定 agent_name 时使用 MemoryStore(agent_name=...) 构造。"""
        tmp_out = tempfile.mkdtemp()
        try:
            # AgentRegistry is imported inside function, patch via registry module
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
            import registry as registry_mod

            mock_registry = MagicMock()
            mock_registry.get_agent_type.return_value = "Explore"

            mock_store = MagicMock()
            mock_store.load_all.return_value = []

            with patch.object(registry_mod, 'AgentRegistry', return_value=mock_registry), \
                 patch('obsidian_export.MemoryStore', return_value=mock_store):
                result = export_all(agent_name="kaze", output_dir=tmp_out)

            assert result["status"] == "empty"
        finally:
            shutil.rmtree(tmp_out)

    def test_export_all_agent_name_subdirectory(self):
        """指定 agent_name 但不指定 output_dir 时，输出到角色专属子目录。"""
        tmp_store = tempfile.mkdtemp()
        tmp_out = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_store)
            store.add(_make_memory(id="mem_agent_001"))

            import registry as registry_mod
            mock_registry = MagicMock()
            mock_registry.get_agent_type.return_value = "Explore"

            with patch.object(registry_mod, 'AgentRegistry', return_value=mock_registry), \
                 patch('obsidian_export.MemoryStore', return_value=store), \
                 patch('obsidian_export.MEMORY_DIR', Path(tmp_out)):
                result = export_all(agent_name="kaze")

            assert result["status"] == "success"
            # The notes should be in kaze subdirectory
            assert "kaze" in result["notes"][0]
        finally:
            shutil.rmtree(tmp_store)
            shutil.rmtree(tmp_out)


# ==================== export_memory_note() ====================

class TestExportMemoryNote:
    """export_memory_note() 各种记忆配置。"""

    def test_basic_export(self):
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mem = _make_memory()
            path = export_memory_note(mem, out_dir)
            assert path.exists()
            content = path.read_text()
            assert mem.id in content
        finally:
            shutil.rmtree(tmp)

    def test_export_with_related_links(self):
        """related_ids 应以 wikilink 形式输出。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mem = _make_memory(
                id="mem_link_001",
                related_ids=["mem_link_002", "mem_link_003"],
            )
            path = export_memory_note(mem, out_dir)
            content = path.read_text()
            assert "[[mem_link_002]]" in content
            assert "[[mem_link_003]]" in content
        finally:
            shutil.rmtree(tmp)

    def test_export_no_related_shows_none(self):
        """无关联记忆时应显示"无"。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mem = _make_memory(related_ids=[])
            path = export_memory_note(mem, out_dir)
            content = path.read_text()
            assert "无" in content
        finally:
            shutil.rmtree(tmp)

    def test_export_with_short_timestamp(self):
        """时间戳不足 10 字符时使用 datetime.now() 替代。"""
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mem = _make_memory(timestamp="short")  # < 10 chars
            path = export_memory_note(mem, out_dir)
            assert path.exists()
        finally:
            shutil.rmtree(tmp)


# ==================== export_moc() ====================

class TestExportMoc:
    """export_moc() MOC 内容验证。"""

    def test_moc_contains_memory_count(self):
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [_make_memory(id=f"mem_{i:03d}") for i in range(3)]
            path = export_moc(mems, out_dir)
            content = path.read_text()
            assert "3" in content
        finally:
            shutil.rmtree(tmp)

    def test_moc_groups_by_tags(self):
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            mems = [
                _make_memory(id="mem_001", tags=["latex", "thesis"]),
                _make_memory(id="mem_002", tags=["python"]),
            ]
            path = export_moc(mems, out_dir)
            content = path.read_text()
            assert "latex" in content
            assert "python" in content
        finally:
            shutil.rmtree(tmp)

    def test_moc_filename(self):
        tmp = tempfile.mkdtemp()
        try:
            out_dir = Path(tmp)
            path = export_moc([_make_memory()], out_dir)
            assert path.name == "_agent_memory_moc.md"
        finally:
            shutil.rmtree(tmp)
