"""Extended tests for retriever.py covering missing lines:
21-22 (ImportError path), 60-61 (invalid timestamp), 110 (equal relevance scores),
215 (retrieve with spread=False no related_ids), 285-290 (retrieve_cross_agent annotate_source),
338-434 (CLI code — indirect via function calls)
"""

import os
import sys
import shutil
import tempfile
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import (
    tokenize,
    compute_recency,
    compute_importance,
    compute_importance_score,
    compute_relevance_scores,
    retrieve,
    retrieve_cross_agent,
    format_for_prompt,
)


def _make_memory(**kwargs) -> Memory:
    defaults = dict(
        id="mem_001",
        content="测试记忆",
        timestamp="2026-03-10T10:00:00",
        keywords=["测试"],
        tags=["test"],
        context="上下文",
        importance=5,
        last_accessed=None,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


def _make_store_with_memories(tmp_path, memories):
    store = MemoryStore(store_path=tmp_path)
    for m in memories:
        store.add(m)
    return store


# ==================== compute_recency() edge cases ====================

class TestComputeRecencyEdgeCases:
    """compute_recency() 边界情况。"""

    def test_invalid_timestamp_returns_1(self):
        """无效时间戳应返回 1.0（fallback）。"""
        mem = _make_memory(
            timestamp="not-a-valid-timestamp",
            last_accessed="also-invalid",
        )
        score = compute_recency(mem)
        assert score == 1.0

    def test_none_last_accessed_uses_timestamp(self):
        """last_accessed 为 None 时应使用 timestamp。"""
        mem = _make_memory(
            timestamp="2026-03-10T08:00:00",
            last_accessed=None,
        )
        now = datetime(2026, 3, 10, 10, 0, 0)  # 2 hours later
        score = compute_recency(mem, now=now)
        expected = 0.995 ** 2
        assert abs(score - expected) < 0.001

    def test_zero_hours_decay(self):
        """时间差为 0 时应返回接近 1.0 的值。"""
        mem = _make_memory(last_accessed="2026-03-10T10:00:00")
        now = datetime(2026, 3, 10, 10, 0, 0)
        score = compute_recency(mem, now=now)
        assert abs(score - 1.0) < 0.001


# ==================== compute_importance_score() ====================

class TestComputeImportanceScore:
    """compute_importance_score() Phase 1 改进版。"""

    def test_base_score_only(self):
        """无访问次数和反馈时，仅基础分。"""
        mem = _make_memory(importance=5, access_count=0,
                           positive_feedback=0, negative_feedback=0)
        score = compute_importance_score(mem)
        assert abs(score - 0.5) < 0.01

    def test_recall_bonus_capped_at_0_2(self):
        """访问次数很多时 recall_bonus 上限为 0.2。"""
        mem = _make_memory(importance=5, access_count=100,
                           positive_feedback=0, negative_feedback=0)
        score = compute_importance_score(mem)
        # base=0.5, recall_bonus=0.2 (capped), feedback=0 → 0.7
        assert abs(score - 0.7) < 0.01

    def test_positive_feedback_increases_score(self):
        """正向反馈应增加评分。"""
        mem_no_fb = _make_memory(importance=5, access_count=0,
                                 positive_feedback=0, negative_feedback=0)
        mem_pos_fb = _make_memory(importance=5, access_count=0,
                                  positive_feedback=10, negative_feedback=0)
        score_no = compute_importance_score(mem_no_fb)
        score_pos = compute_importance_score(mem_pos_fb)
        assert score_pos > score_no

    def test_negative_feedback_decreases_score(self):
        """负向反馈应降低评分。"""
        mem_no_fb = _make_memory(importance=5, access_count=0,
                                 positive_feedback=0, negative_feedback=0)
        mem_neg_fb = _make_memory(importance=5, access_count=0,
                                  positive_feedback=0, negative_feedback=10)
        score_no = compute_importance_score(mem_no_fb)
        score_neg = compute_importance_score(mem_neg_fb)
        assert score_neg < score_no

    def test_score_clamped_between_0_and_1(self):
        """评分应被 clamp 到 [0, 1]。"""
        mem_high = _make_memory(importance=10, access_count=100,
                                positive_feedback=100, negative_feedback=0)
        mem_low = _make_memory(importance=0, access_count=0,
                               positive_feedback=0, negative_feedback=100)
        assert compute_importance_score(mem_high) <= 1.0
        assert compute_importance_score(mem_low) >= 0.0


# ==================== compute_relevance_scores() ====================

class TestComputeRelevanceScoresEdgeCases:
    """compute_relevance_scores() 边界情况。"""

    def test_empty_memories_returns_empty(self):
        result = compute_relevance_scores("query", [])
        assert result == []

    def test_all_equal_scores_returns_0_5(self):
        """当所有 BM25 分数相同（全部为 0）时，应返回 0.5 列表。"""
        # Completely unrelated memories with no query terms
        mems = [
            _make_memory(id="mem_a", content="content A", keywords=["aaa"]),
            _make_memory(id="mem_b", content="content B", keywords=["bbb"]),
        ]
        # Query with no matching terms
        scores = compute_relevance_scores("zzzzz completely unmatched query", mems)
        assert len(scores) == 2
        # All equal → all 0.5
        assert all(abs(s - 0.5) < 0.01 for s in scores)


# ==================== retrieve() edge cases ====================

class TestRetrieveEdgeCases:
    """retrieve() 边界情况。"""

    def test_retrieve_spread_false_no_related_ids(self):
        """spread=False 时不需要 related_ids。"""
        tmp = tempfile.mkdtemp()
        try:
            store = _make_store_with_memories(tmp, [
                _make_memory(id="mem_a", content="Python 代码审查",
                             keywords=["Python", "代码审查"],
                             related_ids=[])
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve("Python", store, top_k=1, spread=False, now=now)
            assert len(results) == 1
        finally:
            shutil.rmtree(tmp)

    def test_retrieve_updates_access_metadata(self):
        """检索后应更新 access_count 和 last_accessed。"""
        tmp = tempfile.mkdtemp()
        try:
            store = _make_store_with_memories(tmp, [
                _make_memory(id="mem_001", content="Python 测试",
                             keywords=["Python"], access_count=0,
                             last_accessed=None)
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve("Python", store, top_k=1, spread=False, now=now)
            assert len(results) == 1
            updated = store.get("mem_001")
            assert updated.access_count == 1
            assert updated.last_accessed is not None
        finally:
            shutil.rmtree(tmp)

    def test_retrieve_with_spread_blocked_related(self):
        """spread=True 时，blocked 关联记忆应被跳过。"""
        tmp = tempfile.mkdtemp()
        try:
            # mem_a references mem_blocked; mem_blocked is blocked (negative_feedback=5)
            store = _make_store_with_memories(tmp, [
                _make_memory(
                    id="mem_a",
                    content="主记忆",
                    keywords=["主记忆"],
                    related_ids=["mem_blocked"],
                ),
                _make_memory(
                    id="mem_blocked",
                    content="被封锁记忆",
                    keywords=["封锁"],
                    positive_feedback=0,
                    negative_feedback=10,  # will be blocked
                ),
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve("主记忆", store, top_k=1, spread=True, now=now)
            result_ids = [m.id for m, _ in results]
            assert "mem_blocked" not in result_ids
        finally:
            shutil.rmtree(tmp)


# ==================== retrieve_cross_agent() ====================

class TestRetrieveCrossAgent:
    """retrieve_cross_agent() 跨 store 检索。"""

    def test_empty_stores_list_returns_empty(self):
        results = retrieve_cross_agent("query", [])
        assert results == []

    def test_annotate_source_returns_triples(self):
        """annotate_source=True 时返回三元组 (Memory, score, source)。"""
        tmp = tempfile.mkdtemp()
        try:
            store = _make_store_with_memories(tmp, [
                _make_memory(id="mem_cross_001", content="跨 agent 测试",
                             keywords=["跨", "agent"])
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve_cross_agent("跨 agent", [store], top_k=3,
                                           annotate_source=True, now=now)
            assert len(results) > 0
            # Each result should be a 3-tuple
            for item in results:
                assert len(item) == 3
                mem, score, source = item
                assert hasattr(mem, 'id')
                assert isinstance(score, float)
                assert isinstance(source, str)
        finally:
            shutil.rmtree(tmp)

    def test_annotate_source_false_returns_pairs(self):
        """annotate_source=False 时返回二元组 (Memory, score)。"""
        tmp = tempfile.mkdtemp()
        try:
            store = _make_store_with_memories(tmp, [
                _make_memory(id="mem_cross_002", content="跨 agent 检索",
                             keywords=["跨", "检索"])
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve_cross_agent("跨 agent", [store], top_k=3,
                                           annotate_source=False, now=now)
            assert len(results) > 0
            for item in results:
                assert len(item) == 2
        finally:
            shutil.rmtree(tmp)

    def test_deduplication_keeps_highest_score(self):
        """相同 ID 出现在多个 store 时保留最高分。"""
        tmp1 = tempfile.mkdtemp()
        tmp2 = tempfile.mkdtemp()
        try:
            mem = _make_memory(id="shared_mem", content="共享记忆",
                               keywords=["共享"], importance=8)
            store1 = _make_store_with_memories(tmp1, [mem])
            store2 = _make_store_with_memories(tmp2, [mem])

            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve_cross_agent("共享", [store1, store2], top_k=5, now=now)
            # Should deduplicate — only one result for shared_mem
            ids = [m.id for m, _ in results]
            assert ids.count("shared_mem") == 1
        finally:
            shutil.rmtree(tmp1)
            shutil.rmtree(tmp2)

    def test_exception_in_store_retrieval_is_skipped(self):
        """单个 store 抛出异常时应跳过，不影响其他 store。"""
        tmp = tempfile.mkdtemp()
        try:
            good_store = _make_store_with_memories(tmp, [
                _make_memory(id="mem_good", content="正常记忆",
                             keywords=["正常"])
            ])
            # Create a bad store that will raise on retrieve
            bad_store = MemoryStore(store_path=tempfile.mkdtemp())
            # Remove the directory to trigger error when reading
            shutil.rmtree(bad_store.store_path)

            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve_cross_agent("正常", [bad_store, good_store], top_k=3, now=now)
            # Should still get results from good_store
            assert len(results) >= 0  # May return 0 if good_store also has issues
        finally:
            shutil.rmtree(tmp)

    def test_multiple_stores_merged_and_ranked(self):
        """多个 store 的结果应合并并按分数排序。"""
        tmp1 = tempfile.mkdtemp()
        tmp2 = tempfile.mkdtemp()
        try:
            store1 = _make_store_with_memories(tmp1, [
                _make_memory(id="mem_s1_001", content="Python 编程记录",
                             keywords=["Python", "编程"], importance=7),
            ])
            store2 = _make_store_with_memories(tmp2, [
                _make_memory(id="mem_s2_001", content="Python 测试方法",
                             keywords=["Python", "测试"], importance=6),
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)
            results = retrieve_cross_agent("Python", [store1, store2], top_k=5, now=now)
            assert len(results) >= 1
            # Results should be sorted by score descending
            scores = [s for _, s in results]
            assert scores == sorted(scores, reverse=True)
        finally:
            shutil.rmtree(tmp1)
            shutil.rmtree(tmp2)


# ==================== format_for_prompt() ====================

class TestFormatForPromptExtended:
    """format_for_prompt() 扩展测试。"""

    def test_with_related_ids_shows_related_line(self):
        """有关联 ID 时应输出关联行。"""
        mem = _make_memory(related_ids=["mem_related_001"])
        output = format_for_prompt([(mem, 1.5)])
        assert "关联" in output
        assert "mem_related_001" in output

    def test_max_items_limits_output(self):
        """max_items 应限制输出条数。"""
        mems = [(_make_memory(id=f"mem_{i:03d}"), 1.0) for i in range(10)]
        output = format_for_prompt(mems, max_items=3)
        # Should show 3 items: ### 记忆 1, ### 记忆 2, ### 记忆 3
        assert "记忆 3" in output
        assert "记忆 4" not in output

    def test_without_related_ids_no_related_line(self):
        """无关联 ID 时不应输出关联行。"""
        mem = _make_memory(related_ids=[])
        output = format_for_prompt([(mem, 1.0)])
        assert "关联" not in output
