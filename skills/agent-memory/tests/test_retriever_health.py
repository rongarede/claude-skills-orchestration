"""测试 retriever.py 与 feedback health 过滤的集成。

Phase B TDD — Step 1: RED 测试（集成测试）
覆盖：
- blocked 记忆被排除
- warning 记忆默认包含
- warning 记忆 score 降权 ×0.5
- 全 healthy 时行为不变
- 全 blocked 时返回空列表
- spread=True 时 health 过滤不影响关联展开
"""

import os
import sys
import shutil
import tempfile
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import retrieve


def make_memory(**kwargs) -> Memory:
    """辅助函数：创建测试用 Memory，设置必填字段默认值。"""
    defaults = dict(
        id="test_mem_001",
        content="测试记忆内容",
        timestamp="2026-03-14T10:00:00",
        keywords=["测试", "记忆"],
        tags=["test"],
        context="测试上下文",
        importance=5,
        positive_feedback=0,
        negative_feedback=0,
        access_count=0,
        last_accessed=None,
        related_ids=[],
    )
    defaults.update(kwargs)
    return Memory(**defaults)


class TestRetrieveExcludesBlockedMemories:
    """test_retrieve_excludes_blocked_memories

    创建 3 条记忆（1 healthy, 1 warning, 1 blocked），检索后 blocked 不在结果中。
    """

    def test_retrieve_excludes_blocked_memories(self):
        """blocked 记忆（ratio<=0.2, neg>=5）不应出现在检索结果中。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # healthy: 无负反馈
            healthy_mem = make_memory(
                id="healthy_001",
                content="Python 异步编程最佳实践",
                keywords=["Python", "异步", "async"],
                positive_feedback=5,
                negative_feedback=0,
            )
            # warning: ratio=1/4=0.25 <= 0.4, neg=3
            warning_mem = make_memory(
                id="warning_001",
                content="Python 装饰器使用技巧",
                keywords=["Python", "装饰器", "decorator"],
                positive_feedback=1,
                negative_feedback=3,
            )
            # blocked: ratio=0/5=0.0 <= 0.2, neg=5
            blocked_mem = make_memory(
                id="blocked_001",
                content="Python 旧版本兼容注意事项",
                keywords=["Python", "兼容性", "版本"],
                positive_feedback=0,
                negative_feedback=5,
            )

            store.add(healthy_mem)
            store.add(warning_mem)
            store.add(blocked_mem)

            now = datetime(2026, 3, 15, 10, 0, 0)
            results = retrieve("Python", store, top_k=5, spread=False, now=now)

            result_ids = [mem.id for mem, _ in results]
            assert "blocked_001" not in result_ids, (
                f"blocked 记忆不应出现在结果中，实际结果 IDs：{result_ids}"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestRetrieveIncludesWarningByDefault:
    """test_retrieve_includes_warning_by_default

    warning 记忆默认包含在结果中（include_warning=True 是默认行为）。
    """

    def test_retrieve_includes_warning_by_default(self):
        """warning 记忆应默认出现在检索结果中。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            healthy_mem = make_memory(
                id="healthy_001",
                content="Python 并发编程技巧",
                keywords=["Python", "并发", "threading"],
                positive_feedback=5,
                negative_feedback=0,
            )
            # warning 记忆
            warning_mem = make_memory(
                id="warning_001",
                content="Python 多线程注意事项",
                keywords=["Python", "多线程", "GIL"],
                positive_feedback=1,
                negative_feedback=3,
            )

            store.add(healthy_mem)
            store.add(warning_mem)

            now = datetime(2026, 3, 15, 10, 0, 0)
            results = retrieve("Python", store, top_k=5, spread=False, now=now)

            result_ids = [mem.id for mem, _ in results]
            assert "warning_001" in result_ids, (
                f"warning 记忆应默认包含在结果中，实际结果 IDs：{result_ids}"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestRetrieveWarningScoreReduced:
    """test_retrieve_warning_score_reduced

    warning 记忆的 score 被降权（×0.5）。
    """

    def test_retrieve_warning_score_reduced(self):
        """warning 记忆在结果中的 score 应比 healthy 同质记忆低（降权 ×0.5）。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 两条内容相近、keywords 相同，但 health 状态不同的记忆
            healthy_mem = make_memory(
                id="healthy_ref",
                content="Python 编程技巧指南",
                keywords=["Python", "编程", "技巧"],
                importance=5,
                positive_feedback=5,
                negative_feedback=0,
            )
            warning_mem = make_memory(
                id="warning_ref",
                content="Python 编程技巧指南",
                keywords=["Python", "编程", "技巧"],
                importance=5,
                positive_feedback=1,
                negative_feedback=3,
            )

            store.add(healthy_mem)
            store.add(warning_mem)

            now = datetime(2026, 3, 15, 10, 0, 0)
            results = retrieve("Python 技巧", store, top_k=5, spread=False, now=now)

            result_dict = {mem.id: score for mem, score in results}

            assert "healthy_ref" in result_dict, "healthy 记忆应在结果中"
            assert "warning_ref" in result_dict, "warning 记忆应在结果中（默认包含）"

            healthy_score = result_dict["healthy_ref"]
            warning_score = result_dict["warning_ref"]

            # warning 记忆的分数应该比 healthy 低（降权 ×0.5）
            # 考虑到两条记忆内容完全相同，基础分应该一样，降权后 warning 应低于 healthy
            assert warning_score < healthy_score, (
                f"warning 记忆（score={warning_score:.4f}）应低于 healthy 记忆（score={healthy_score:.4f}）"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestRetrieveAllHealthyUnchanged:
    """test_retrieve_all_healthy_unchanged

    全部 healthy 时，retrieve 行为与原始行为一致（无降权）。
    """

    def test_retrieve_all_healthy_unchanged(self):
        """全 healthy 记忆时，检索结果数量和内容不受 health 过滤影响。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            mems = [
                make_memory(
                    id=f"healthy_{i:03d}",
                    content=f"Python 健康记忆 {i}",
                    keywords=["Python", f"topic{i}"],
                    importance=5,
                    positive_feedback=5,
                    negative_feedback=0,
                )
                for i in range(3)
            ]

            for m in mems:
                store.add(m)

            now = datetime(2026, 3, 15, 10, 0, 0)
            results = retrieve("Python", store, top_k=3, spread=False, now=now)

            # 所有记忆都应该保留（无 blocked/warning）
            assert len(results) == 3, (
                f"全 healthy 时应返回 3 条，实际：{len(results)}"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestRetrieveAllBlockedReturnsEmpty:
    """test_retrieve_all_blocked_returns_empty

    全部 blocked 时返回空列表。
    """

    def test_retrieve_all_blocked_returns_empty(self):
        """全部 blocked 记忆时，检索应返回空列表。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            blocked_mems = [
                make_memory(
                    id=f"blocked_{i:03d}",
                    content=f"Python 被阻断记忆 {i}",
                    keywords=["Python", f"blocked{i}"],
                    importance=5,
                    positive_feedback=0,
                    negative_feedback=5,
                )
                for i in range(3)
            ]

            for m in blocked_mems:
                store.add(m)

            now = datetime(2026, 3, 15, 10, 0, 0)
            results = retrieve("Python", store, top_k=5, spread=False, now=now)

            assert results == [], (
                f"全 blocked 时应返回空列表，实际：{[(m.id, s) for m, s in results]}"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestRetrieveWithSpreadAndHealth:
    """test_retrieve_with_spread_and_health

    spread=True 时 health 过滤不影响关联展开（spread 仍然工作，但 blocked 不展开）。
    """

    def test_retrieve_with_spread_and_health(self):
        """spread=True 时，healthy 记忆的关联展开依然工作；blocked 关联不展开。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 主记忆（healthy）：使用唯一查询词 "xylophone" 确保它一定是 top-1
            # 关联到两个相关记忆
            primary = make_memory(
                id="primary_001",
                content="xylophone 音阶编排系统",
                keywords=["xylophone", "音阶", "编排"],
                importance=8,
                positive_feedback=5,
                negative_feedback=0,
                related_ids=["spread_healthy_001", "spread_blocked_001"],
            )
            # 关联的 healthy 记忆（不含 xylophone 关键词）
            spread_healthy = make_memory(
                id="spread_healthy_001",
                content="乐器音色分析方法",
                keywords=["乐器", "音色", "分析"],
                importance=6,
                positive_feedback=3,
                negative_feedback=0,
            )
            # 关联的 blocked 记忆（不应被展开）
            spread_blocked = make_memory(
                id="spread_blocked_001",
                content="过时音乐软件使用记录",
                keywords=["音乐", "软件", "过时"],
                importance=3,
                positive_feedback=0,
                negative_feedback=5,
            )

            store.add(primary)
            store.add(spread_healthy)
            store.add(spread_blocked)

            now = datetime(2026, 3, 15, 10, 0, 0)
            # 查询 xylophone，primary_001 必然是 top-1
            results = retrieve("xylophone", store, top_k=1, spread=True, now=now)

            result_ids = [mem.id for mem, _ in results]

            # primary 应在结果中
            assert "primary_001" in result_ids, (
                f"主记忆应在结果中，实际结果 IDs：{result_ids}"
            )
            # healthy 关联应被展开
            assert "spread_healthy_001" in result_ids, (
                f"healthy 关联记忆应被展开，实际结果 IDs：{result_ids}"
            )
            # blocked 关联不应被展开
            assert "spread_blocked_001" not in result_ids, (
                f"blocked 关联记忆不应被展开，实际结果 IDs：{result_ids}"
            )
        finally:
            shutil.rmtree(tmp_dir)
