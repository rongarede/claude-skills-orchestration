"""Tests for the associative memory retrieval system."""

import os
import sys
import shutil
import tempfile
import json
from datetime import datetime, timedelta

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import (
    tokenize, compute_recency, compute_importance,
    compute_relevance_scores, retrieve, format_for_prompt
)
from associator import find_associations, link_memory


def create_test_store(tmp_path: str) -> MemoryStore:
    """Create a store with 5 sample memories for testing."""
    store = MemoryStore(tmp_path)

    samples = [
        Memory(
            id="mem_20260310_001",
            content="修复 LaTeX fontspec 编译错误，原因是 XeLaTeX 路径未正确配置",
            timestamp="2026-03-10T10:00:00",
            keywords=["LaTeX", "fontspec", "XeLaTeX", "编译错误", "路径配置"],
            tags=["bug-fix", "thesis", "latex"],
            context="论文编译流程中 XeLaTeX 引擎路径问题导致 fontspec 包加载失败",
            importance=7,
            related_ids=["mem_20260310_002"],
            access_count=2,
            last_accessed="2026-03-11T14:00:00"
        ),
        Memory(
            id="mem_20260310_002",
            content="配置 latexmk 自动编译流程，添加 -xelatex 参数和 synctex 支持",
            timestamp="2026-03-10T14:00:00",
            keywords=["latexmk", "自动编译", "xelatex", "synctex"],
            tags=["config", "thesis", "latex"],
            context="设置 latexmk 配置文件实现保存即编译的 LaTeX 工作流",
            importance=5,
            related_ids=["mem_20260310_001"],
            access_count=1,
            last_accessed="2026-03-10T16:00:00"
        ),
        Memory(
            id="mem_20260311_001",
            content="实现 Claude Code task-complete-hook，自动记录任务完成到 changelog",
            timestamp="2026-03-11T09:00:00",
            keywords=["hook", "task-complete", "changelog", "自动化"],
            tags=["feature", "claude-code", "automation"],
            context="PostToolUse hook 在 TaskUpdate completed 时自动追加记录到每日 changelog",
            importance=6,
            related_ids=[],
            access_count=0,
            last_accessed=None
        ),
        Memory(
            id="mem_20260311_002",
            content="精读 A-MEM 论文，提取 Zettelkasten 数据模型和联想链机制",
            timestamp="2026-03-11T15:00:00",
            keywords=["A-MEM", "Zettelkasten", "联想记忆", "数据模型", "论文"],
            tags=["research", "memory", "ai"],
            context="A-MEM 使用 Note 结构(content/keywords/tags/context/links)实现 agent 联想记忆",
            importance=8,
            related_ids=["mem_20260311_003"],
            access_count=1,
            last_accessed="2026-03-11T18:00:00"
        ),
        Memory(
            id="mem_20260311_003",
            content="精读 Generative Agents 论文，提取三维评分检索机制",
            timestamp="2026-03-11T18:00:00",
            keywords=["Generative Agents", "三维评分", "recency", "importance", "relevance"],
            tags=["research", "memory", "ai"],
            context="三维检索: recency(0.995^h) + importance(1-10) + relevance(cosine) 等权重min-max归一化",
            importance=8,
            related_ids=["mem_20260311_002"],
            access_count=0,
            last_accessed=None
        ),
    ]

    for m in samples:
        store.add(m)

    return store


class TestTokenizer:
    def test_english_tokens(self):
        tokens = tokenize("Hello World test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_chinese_tokens(self):
        tokens = tokenize("编译错误修复")
        assert "编" in tokens
        assert "译" in tokens
        # Bigrams
        assert "编译" in tokens
        assert "译错" in tokens

    def test_mixed_tokens(self):
        tokens = tokenize("LaTeX 编译错误")
        assert "latex" in tokens
        assert "编" in tokens
        assert "编译" in tokens


class TestRecency:
    def test_just_accessed(self):
        mem = Memory(id="test", content="test", timestamp="2026-03-12T10:00:00",
                     keywords=["test"], tags=["test"], context="test", importance=5,
                     last_accessed="2026-03-12T10:00:00")
        now = datetime(2026, 3, 12, 10, 0, 0)
        score = compute_recency(mem, now=now)
        assert abs(score - 1.0) < 0.001

    def test_decay_after_24h(self):
        mem = Memory(id="test", content="test", timestamp="2026-03-11T10:00:00",
                     keywords=["test"], tags=["test"], context="test", importance=5,
                     last_accessed="2026-03-11T10:00:00")
        now = datetime(2026, 3, 12, 10, 0, 0)
        score = compute_recency(mem, now=now)
        expected = 0.995 ** 24
        assert abs(score - expected) < 0.001

    def test_never_accessed_uses_timestamp(self):
        mem = Memory(id="test", content="test", timestamp="2026-03-12T08:00:00",
                     keywords=["test"], tags=["test"], context="test", importance=5,
                     last_accessed=None)
        now = datetime(2026, 3, 12, 10, 0, 0)
        score = compute_recency(mem, now=now)
        expected = 0.995 ** 2  # 2 hours
        assert abs(score - expected) < 0.001


class TestImportance:
    def test_max_importance(self):
        mem = Memory(id="test", content="test", timestamp="now",
                     keywords=["test"], tags=["test"], context="test", importance=10)
        assert compute_importance(mem) == 1.0

    def test_min_importance(self):
        mem = Memory(id="test", content="test", timestamp="now",
                     keywords=["test"], tags=["test"], context="test", importance=1)
        assert abs(compute_importance(mem) - 0.1) < 0.001

    def test_clamp(self):
        mem = Memory(id="test", content="test", timestamp="now",
                     keywords=["test"], tags=["test"], context="test", importance=15)
        assert compute_importance(mem) == 1.0


class TestRetriever:
    def test_retrieve_latex_query(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = create_test_store(tmp_dir)
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve("LaTeX 编译错误怎么修", store, top_k=3, spread=False, now=now)

            assert len(results) > 0
            # Top result should be the LaTeX fontspec fix
            top_mem, top_score = results[0]
            assert "fontspec" in top_mem.content or "LaTeX" in top_mem.content
            assert top_score > 0
        finally:
            shutil.rmtree(tmp_dir)

    def test_retrieve_memory_query(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = create_test_store(tmp_dir)
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve("联想记忆系统", store, top_k=3, spread=False, now=now)

            assert len(results) > 0
            # Should find A-MEM or Generative Agents memories
            top_ids = [m.id for m, _ in results]
            assert "mem_20260311_002" in top_ids or "mem_20260311_003" in top_ids
        finally:
            shutil.rmtree(tmp_dir)

    def test_spread_activation(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = create_test_store(tmp_dir)
            now = datetime(2026, 3, 12, 10, 0, 0)

            # Without spread
            results_no_spread = retrieve("A-MEM 论文", store, top_k=1, spread=False, now=now)
            # With spread
            results_spread = retrieve("A-MEM 论文", store, top_k=1, spread=True, now=now)

            # Spread should return more results (linked memories)
            assert len(results_spread) >= len(results_no_spread)
        finally:
            shutil.rmtree(tmp_dir)

    def test_empty_store(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(tmp_dir)
            results = retrieve("anything", store, top_k=3)
            assert results == []
        finally:
            shutil.rmtree(tmp_dir)


class TestAssociator:
    def test_find_associations(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = create_test_store(tmp_dir)
            new_mem = Memory(
                id="mem_20260312_001",
                content="修复 LaTeX biber 引用编译错误",
                timestamp="2026-03-12T10:00:00",
                keywords=["LaTeX", "biber", "引用", "编译错误"],
                tags=["bug-fix", "thesis", "latex"],
                context="参考文献编译时 biber 后端报错",
                importance=6
            )

            associated = find_associations(new_mem, store, threshold=0.1)
            # Should find LaTeX-related memories
            assert len(associated) > 0
        finally:
            shutil.rmtree(tmp_dir)

    def test_link_bidirectional(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            store = create_test_store(tmp_dir)
            new_mem = Memory(
                id="mem_20260312_001",
                content="修复 LaTeX biber 引用编译错误",
                timestamp="2026-03-12T10:00:00",
                keywords=["LaTeX", "biber", "引用", "编译错误"],
                tags=["bug-fix", "thesis", "latex"],
                context="参考文献编译时 biber 后端报错",
                importance=6
            )

            linked = link_memory(new_mem, store, threshold=0.1)

            # New memory should have related_ids
            assert len(linked.related_ids) > 0

            # Check bidirectional: linked memories should reference new memory
            for rid in linked.related_ids:
                related = store.get(rid)
                if related:
                    assert new_mem.id in related.related_ids
        finally:
            shutil.rmtree(tmp_dir)


class TestLayerBonusScoring:
    """Phase 8: 层级加成评分测试。"""

    def test_layer_bonus_scoring(self):
        """L3 记忆得分应高于同等条件的 L1 记忆。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(tmp_dir)
            now = datetime(2026, 3, 12, 10, 0, 0)

            # 创建两条完全相同内容/关键词/importance 的记忆，只有 layer 不同
            mem_l1 = Memory(
                id="mem_l1_001",
                content="LaTeX fontspec 编译错误修复方法",
                timestamp="2026-03-11T10:00:00",
                keywords=["LaTeX", "fontspec", "编译错误"],
                tags=["bug-fix"],
                context="XeLaTeX 路径配置修复",
                importance=7,
                access_count=1,
                last_accessed="2026-03-11T14:00:00",
                layer="L1",
            )
            mem_l3 = Memory(
                id="mem_l3_001",
                content="LaTeX fontspec 编译错误修复方法",
                timestamp="2026-03-11T10:00:00",
                keywords=["LaTeX", "fontspec", "编译错误"],
                tags=["bug-fix"],
                context="XeLaTeX 路径配置修复",
                importance=7,
                access_count=1,
                last_accessed="2026-03-11T14:00:00",
                layer="L3",
            )
            store.add(mem_l1)
            store.add(mem_l3)

            results = retrieve("LaTeX fontspec 编译", store, top_k=2, spread=False, now=now)

            assert len(results) == 2
            # L3 记忆应排在前面（得分更高）
            top_mem, top_score = results[0]
            second_mem, second_score = results[1]
            assert top_mem.layer == "L3", (
                f"L3 记忆应排在第一位，实际第一位 layer={top_mem.layer}"
            )
            assert top_score > second_score, (
                f"L3 得分 ({top_score:.3f}) 应高于 L1 ({second_score:.3f})"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestFormatForPrompt:
    def test_format_output(self):
        mem = Memory(
            id="mem_20260310_001",
            content="修复 LaTeX fontspec 编译错误",
            timestamp="2026-03-10T10:00:00",
            keywords=["LaTeX", "fontspec"],
            tags=["bug-fix"],
            context="XeLaTeX 路径问题",
            importance=7
        )
        output = format_for_prompt([(mem, 2.5)])
        assert "联想记忆" in output
        assert "fontspec" in output
        assert "2.50" in output

    def test_empty_results(self):
        output = format_for_prompt([])
        assert output == ""


def run_tests():
    """Simple test runner."""
    import traceback

    test_classes = [
        TestTokenizer, TestRecency, TestImportance,
        TestRetriever, TestAssociator, TestFormatForPrompt
    ]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                try:
                    getattr(instance, method_name)()
                    passed += 1
                    print(f"  ✓ {cls.__name__}.{method_name}")
                except Exception as e:
                    failed += 1
                    errors.append((f"{cls.__name__}.{method_name}", traceback.format_exc()))
                    print(f"  ✗ {cls.__name__}.{method_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")

    if errors:
        print(f"\nFailures:")
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
