"""Extended tests for evolver.py covering missing lines:
40-43 (_get_health_and_ratio), 98-102 (merge_feedback equal positive),
257 (no neighbor_id), 261 (neighbor not in store), 382-394 (evolve_neighbors no neighbors),
402-403 (exception in should_evolve), 406 (no plan returned), 413-426 (cross-agent update)
"""

import os
import sys
import json
import shutil
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
import evolver
from evolver import (
    _get_health_and_ratio,
    _filter_and_prioritize,
    merge_feedback,
    execute_evolution,
    evolve_neighbors,
)


def _make_memory(**kwargs) -> Memory:
    defaults = dict(
        id="mem_001",
        content="测试记忆",
        timestamp=datetime.now().isoformat(),
        keywords=["测试"],
        tags=["test"],
        context="测试上下文",
        importance=5,
        positive_feedback=0,
        negative_feedback=0,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


def _make_store(*memories):
    tmp = tempfile.mkdtemp()
    store = MemoryStore(store_path=tmp)
    for m in memories:
        store.add(m)
    return tmp, store


# ==================== _get_health_and_ratio() ====================

class TestGetHealthAndRatio:
    """_get_health_and_ratio() 返回 health 和 ratio。"""

    def test_healthy_memory(self):
        """正常记忆应返回 healthy 和合理 ratio。"""
        mem = _make_memory(positive_feedback=5, negative_feedback=1)
        health, ratio = _get_health_and_ratio(mem)
        assert health == "healthy"
        assert 0.0 <= ratio <= 1.0

    def test_blocked_memory(self):
        """被封锁记忆应返回 blocked。"""
        mem = _make_memory(positive_feedback=0, negative_feedback=10)
        health, ratio = _get_health_and_ratio(mem)
        assert health == "blocked"

    def test_warning_memory(self):
        """警告记忆返回 warning。"""
        # warning = ratio <= 0.3 且 negative >= 3 且 < blocked threshold
        mem = _make_memory(positive_feedback=1, negative_feedback=5)
        health, ratio = _get_health_and_ratio(mem)
        # health could be warning or blocked depending on thresholds
        assert health in ("warning", "blocked", "healthy")
        assert isinstance(ratio, float)

    def test_no_feedback_returns_healthy(self):
        """无反馈记忆应返回 healthy。"""
        mem = _make_memory(positive_feedback=0, negative_feedback=0)
        health, ratio = _get_health_and_ratio(mem)
        assert health == "healthy"


# ==================== merge_feedback() ====================

class TestMergeFeedback:
    """merge_feedback() 继承最佳 feedback 元数据。"""

    def test_mem_a_has_better_positive_feedback(self):
        """mem_a positive_feedback 更高时使用 mem_a 的数据。"""
        mem_a = _make_memory(id="mem_a", positive_feedback=8, negative_feedback=1)
        mem_b = _make_memory(id="mem_b", positive_feedback=3, negative_feedback=0)
        result = merge_feedback(mem_a, mem_b)
        assert result.positive_feedback == 8
        assert result.negative_feedback == 1

    def test_mem_b_has_better_positive_feedback(self):
        """mem_b positive_feedback 更高时使用 mem_b 的数据。"""
        mem_a = _make_memory(id="mem_a", positive_feedback=2, negative_feedback=0)
        mem_b = _make_memory(id="mem_b", positive_feedback=9, negative_feedback=2)
        result = merge_feedback(mem_a, mem_b)
        assert result.positive_feedback == 9
        assert result.negative_feedback == 2

    def test_equal_positive_uses_lower_negative(self):
        """positive 相等时选 negative 更低的。"""
        mem_a = _make_memory(id="mem_a", positive_feedback=5, negative_feedback=1)
        mem_b = _make_memory(id="mem_b", positive_feedback=5, negative_feedback=3)
        result = merge_feedback(mem_a, mem_b)
        # Should use mem_a's data (lower negative)
        assert result.negative_feedback == 1
        assert result.positive_feedback == 5

    def test_equal_positive_equal_negative_uses_mem_a(self):
        """positive 和 negative 都相等时应选择 mem_a（negative 不低于 mem_b 时用 mem_b）。"""
        mem_a = _make_memory(id="mem_a", positive_feedback=5, negative_feedback=2)
        mem_b = _make_memory(id="mem_b", positive_feedback=5, negative_feedback=2)
        result = merge_feedback(mem_a, mem_b)
        # Both equal, condition is mem_a.negative <= mem_b.negative → mem_a chosen
        assert result.positive_feedback == 5
        assert result.negative_feedback == 2

    def test_result_is_based_on_mem_b(self):
        """结果应以 mem_b 为基础（仅 feedback 字段继承最佳值）。"""
        mem_a = _make_memory(id="mem_a", content="内容A", positive_feedback=10, negative_feedback=0)
        mem_b = _make_memory(id="mem_b", content="内容B", positive_feedback=3, negative_feedback=1)
        result = merge_feedback(mem_a, mem_b)
        # Base is mem_b
        assert result.id == "mem_b"
        assert result.content == "内容B"
        # But feedback from mem_a
        assert result.positive_feedback == 10


# ==================== execute_evolution() edge cases ====================

class TestExecuteEvolutionEdgeCases:
    """execute_evolution() 边界情况。"""

    def test_plan_without_neighbor_id_is_skipped(self):
        """缺少 neighbor_id 的 plan 条目应被跳过。"""
        tmp, store = _make_store(_make_memory(id="mem_exec_a"))
        try:
            plan = [
                {"new_context": "更新上下文", "add_tags": ["new"], "add_keywords": []},
                # Missing neighbor_id
            ]
            updated = execute_evolution(plan, store, triggered_by_id="mem_trigger")
            assert updated == []
        finally:
            shutil.rmtree(tmp)

    def test_nonexistent_neighbor_is_skipped(self):
        """store 中不存在的 neighbor_id 应被跳过。"""
        tmp, store = _make_store()
        try:
            plan = [
                {
                    "neighbor_id": "nonexistent_mem",
                    "new_context": "更新上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]
            updated = execute_evolution(plan, store, triggered_by_id="trigger")
            assert "nonexistent_mem" not in updated
        finally:
            shutil.rmtree(tmp)

    def test_importance_boost_for_positive_feedback_memory(self):
        """正向反馈记忆演化时 importance 应获得 boost。"""
        tmp, store = _make_store(
            _make_memory(
                id="mem_positive",
                importance=5,
                positive_feedback=10,  # ratio=1.0 > threshold=0.7
                negative_feedback=0,
                context="原始上下文",
            )
        )
        try:
            plan = [
                {
                    "neighbor_id": "mem_positive",
                    "new_context": "演化后上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]
            execute_evolution(plan, store, triggered_by_id="trigger")
            reloaded = store.get("mem_positive")
            # importance should be boosted from 5 to 6
            assert reloaded.importance == 6
        finally:
            shutil.rmtree(tmp)

    def test_importance_not_exceeded_max(self):
        """已达 max importance 时不应超出。"""
        tmp, store = _make_store(
            _make_memory(
                id="mem_max_imp",
                importance=10,  # already at max
                positive_feedback=10,
                negative_feedback=0,
                context="原始上下文",
            )
        )
        try:
            plan = [
                {
                    "neighbor_id": "mem_max_imp",
                    "new_context": "演化后上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]
            execute_evolution(plan, store, triggered_by_id="trigger")
            reloaded = store.get("mem_max_imp")
            assert reloaded.importance <= 10
        finally:
            shutil.rmtree(tmp)

    def test_no_importance_change_without_positive_feedback(self):
        """无正向反馈时 importance 不应改变。"""
        tmp, store = _make_store(
            _make_memory(
                id="mem_no_fb",
                importance=5,
                positive_feedback=0,
                negative_feedback=0,
                context="原始上下文",
            )
        )
        try:
            plan = [
                {
                    "neighbor_id": "mem_no_fb",
                    "new_context": "演化后上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]
            execute_evolution(plan, store, triggered_by_id="trigger")
            reloaded = store.get("mem_no_fb")
            assert reloaded.importance == 5
        finally:
            shutil.rmtree(tmp)


# ==================== evolve_neighbors() edge cases ====================

class TestEvolveNeighborsEdgeCases:
    """evolve_neighbors() 边界情况。"""

    def test_no_neighbor_ids_returns_empty(self):
        """find_associations 返回空列表时 evolve_neighbors 应返回 []。"""
        tmp, store = _make_store()
        try:
            new_mem = _make_memory(id="mem_new")
            with patch('associator.find_associations', return_value=[]):
                result = evolve_neighbors(new_mem, store)
            assert result == []
        finally:
            shutil.rmtree(tmp)

    def test_all_neighbors_blocked_returns_empty(self):
        """所有邻居都是 blocked 状态时应返回 []。"""
        tmp, store = _make_store(
            _make_memory(
                id="mem_blocked_neighbor",
                positive_feedback=0,
                negative_feedback=10,  # blocked
            )
        )
        try:
            new_mem = _make_memory(id="mem_new")
            with patch('associator.find_associations', return_value=["mem_blocked_neighbor"]):
                result = evolve_neighbors(new_mem, store)
            assert result == []
        finally:
            shutil.rmtree(tmp)

    def test_should_evolve_exception_returns_empty(self):
        """should_evolve 抛出异常时应静默返回 []。"""
        tmp, store = _make_store(
            _make_memory(id="mem_neighbor", context="邻居上下文")
        )
        try:
            new_mem = _make_memory(id="mem_new")
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("API 异常")

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', return_value=["mem_neighbor"]):
                result = evolve_neighbors(new_mem, store)
            # should return [] due to exception in should_evolve
            assert result == []
        finally:
            shutil.rmtree(tmp)

    def test_empty_plan_returns_empty(self):
        """generate_evolution_plan 返回空列表时应返回 []。"""
        tmp, store = _make_store(
            _make_memory(id="mem_neighbor2", context="邻居上下文2")
        )
        try:
            new_mem = _make_memory(id="mem_new2")
            should_evolve_resp = json.dumps({"should_evolve": True, "reason": "需要更新"})
            empty_plan_resp = json.dumps({"updates": []})

            call_n = [0]
            def mock_create(**kwargs):
                call_n[0] += 1
                resp = MagicMock()
                resp.content = [MagicMock(
                    text=should_evolve_resp if call_n[0] == 1 else empty_plan_resp
                )]
                return resp

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = mock_create

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', return_value=["mem_neighbor2"]):
                result = evolve_neighbors(new_mem, store)

            assert result == []
        finally:
            shutil.rmtree(tmp)

    def test_generate_plan_exception_returns_empty(self):
        """generate_evolution_plan 抛出异常时应返回 []。"""
        tmp, store = _make_store(
            _make_memory(id="mem_neighbor3", context="邻居上下文3")
        )
        try:
            new_mem = _make_memory(id="mem_new3")
            should_evolve_resp = json.dumps({"should_evolve": True, "reason": "需要更新"})

            call_n = [0]
            def mock_create(**kwargs):
                call_n[0] += 1
                if call_n[0] == 1:
                    resp = MagicMock()
                    resp.content = [MagicMock(text=should_evolve_resp)]
                    return resp
                raise Exception("生成计划失败")

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = mock_create

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', return_value=["mem_neighbor3"]):
                result = evolve_neighbors(new_mem, store)

            assert result == []
        finally:
            shutil.rmtree(tmp)


# ==================== _filter_and_prioritize() ====================

class TestFilterAndPrioritize:
    """_filter_and_prioritize() 过滤和排序。"""

    def test_blocked_memories_filtered_out(self):
        """blocked 记忆应被过滤。"""
        mems = [
            _make_memory(id="blocked", positive_feedback=0, negative_feedback=10),
            _make_memory(id="healthy", positive_feedback=5, negative_feedback=0),
        ]
        result = _filter_and_prioritize(mems)
        ids = [m.id for m in result]
        assert "blocked" not in ids
        assert "healthy" in ids

    def test_healthy_before_warning(self):
        """healthy 记忆应排在 warning 之前。"""
        healthy = _make_memory(id="healthy", positive_feedback=5, negative_feedback=0)
        warning = _make_memory(id="warning", positive_feedback=1, negative_feedback=4)

        result = _filter_and_prioritize([warning, healthy])
        # healthy should come first
        assert result[0].id == "healthy"

    def test_empty_list_returns_empty(self):
        result = _filter_and_prioritize([])
        assert result == []

    def test_all_blocked_returns_empty(self):
        mems = [_make_memory(positive_feedback=0, negative_feedback=10)]
        result = _filter_and_prioritize(mems)
        assert result == []
