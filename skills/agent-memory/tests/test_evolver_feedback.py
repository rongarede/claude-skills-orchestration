"""evolver + feedback_loop 联动测试。

测试演化过程参考 feedback 信息：
- blocked 记忆跳过演化（不浪费资源）
- warning 记忆降低演化优先级
- 正面反馈记忆优先演化（提升重要性、优先参与合并）
"""

import os
import sys
import json
import tempfile
import traceback
from datetime import datetime
from unittest.mock import patch, MagicMock

# 将 scripts 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
import evolver
from evolver import (
    _filter_and_prioritize,
    execute_evolution,
    evolve_neighbors,
)
from feedback_loop import check_memory_health, get_feedback_ratio


# ==================== 辅助函数 ====================

def _new_tmp_store():
    """创建隔离的临时 JSONL 文件，返回 (path, store)。"""
    tmp = tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False)
    tmp.close()
    return tmp.name, MemoryStore(tmp.name)


def _make_memory(
    mem_id,
    content,
    keywords,
    tags=None,
    context="",
    importance=5,
    positive_feedback=0,
    negative_feedback=0,
):
    """快速构造 Memory 对象，支持 feedback 参数。"""
    return Memory(
        id=mem_id,
        content=content,
        timestamp=datetime.now().isoformat(),
        keywords=keywords,
        tags=tags or [],
        context=context,
        importance=importance,
        positive_feedback=positive_feedback,
        negative_feedback=negative_feedback,
    )


def _make_blocked_memory(mem_id, content="阻断记忆"):
    """构造 blocked 状态的记忆：ratio<=0.2 且 negative>=5。"""
    return _make_memory(
        mem_id, content,
        keywords=["blocked"],
        positive_feedback=1,
        negative_feedback=9,   # ratio=0.1, neg=9 → blocked
    )


def _make_warning_memory(mem_id, content="警告记忆"):
    """构造 warning 状态的记忆：ratio<=0.4 且 negative>=3。"""
    return _make_memory(
        mem_id, content,
        keywords=["warning"],
        positive_feedback=2,
        negative_feedback=4,   # ratio=0.333, neg=4 → warning
    )


def _make_healthy_memory(mem_id, content="健康记忆"):
    """构造 healthy 状态的记忆（正面反馈占多数）。"""
    return _make_memory(
        mem_id, content,
        keywords=["healthy"],
        positive_feedback=8,
        negative_feedback=2,   # ratio=0.8 → healthy
    )


def _make_positive_memory(mem_id, content="高正面反馈记忆"):
    """构造高正面反馈的记忆（ratio > 0.8）。"""
    return _make_memory(
        mem_id, content,
        keywords=["positive"],
        positive_feedback=10,
        negative_feedback=0,   # ratio=1.0 → healthy, high positive
    )


# ==================== 测试类 ====================

class TestFilterAndPrioritize:
    """_filter_and_prioritize() 函数测试。"""

    def test_blocked_memory_skipped_in_evolution(self):
        """blocked 记忆不参与演化，被过滤掉。"""
        blocked = _make_blocked_memory("mem_b_001")
        healthy = _make_healthy_memory("mem_h_001")

        result = _filter_and_prioritize([blocked, healthy])

        ids = [m.id for m in result]
        assert "mem_b_001" not in ids, f"blocked 记忆不应出现在结果中，实际 {ids}"
        assert "mem_h_001" in ids, f"healthy 记忆应在结果中，实际 {ids}"

    def test_warning_memory_deprioritized(self):
        """warning 记忆排在 healthy 记忆之后（优先级降低）。"""
        healthy = _make_healthy_memory("mem_h_002")
        warning = _make_warning_memory("mem_w_002")

        result = _filter_and_prioritize([warning, healthy])

        assert len(result) == 2, f"warning 和 healthy 都应保留，实际 {len(result)}"
        # healthy 应排在前面（优先级更高）
        assert result[0].id == "mem_h_002", (
            f"healthy 记忆应排在首位，实际首位是 {result[0].id}"
        )
        assert result[1].id == "mem_w_002", (
            f"warning 记忆应排在末位，实际末位是 {result[1].id}"
        )

    def test_positive_feedback_boosts_priority(self):
        """正面反馈比率高的记忆排在前面。"""
        positive = _make_positive_memory("mem_p_001")  # ratio=1.0
        healthy = _make_healthy_memory("mem_h_003")    # ratio=0.8
        warning = _make_warning_memory("mem_w_003")    # ratio=0.333

        result = _filter_and_prioritize([warning, healthy, positive])

        assert len(result) == 3, f"应保留 3 条记忆，实际 {len(result)}"
        assert result[0].id == "mem_p_001", (
            f"ratio=1.0 的记忆应排首位，实际首位是 {result[0].id}"
        )

    def test_no_feedback_memory_normal_priority(self):
        """无 feedback 记忆（total=0，ratio=0.5）正常参与演化，不被过滤。"""
        no_feedback = _make_memory("mem_nf_001", "无反馈记忆", keywords=["test"])
        healthy = _make_healthy_memory("mem_h_004")

        result = _filter_and_prioritize([no_feedback, healthy])

        ids = [m.id for m in result]
        assert "mem_nf_001" in ids, f"无 feedback 记忆应正常保留，实际 {ids}"

    def test_all_blocked_returns_empty(self):
        """全部 blocked 时返回空列表。"""
        b1 = _make_blocked_memory("mem_b_101")
        b2 = _make_blocked_memory("mem_b_102")
        b3 = _make_blocked_memory("mem_b_103")

        result = _filter_and_prioritize([b1, b2, b3])

        assert result == [], f"全部 blocked 时应返回空列表，实际 {result}"

    def test_mixed_health_prioritization(self):
        """混合健康状态按 healthy > warning（blocked 过滤）排序。"""
        blocked = _make_blocked_memory("mem_b_200")
        warning = _make_warning_memory("mem_w_200")
        positive = _make_positive_memory("mem_p_200")
        healthy = _make_healthy_memory("mem_h_200")

        result = _filter_and_prioritize([warning, blocked, healthy, positive])

        ids = [m.id for m in result]
        # blocked 被过滤
        assert "mem_b_200" not in ids, f"blocked 不应出现在结果中"
        # 其余 3 条保留
        assert len(result) == 3, f"应保留 3 条（blocking 过滤 1 条），实际 {len(result)}"
        # positive（ratio=1.0）或 healthy（ratio=0.8）在前
        assert result[-1].id == "mem_w_200", (
            f"warning 应排在末尾，实际末尾是 {result[-1].id}"
        )

    def test_empty_input_returns_empty(self):
        """空列表输入返回空列表。"""
        result = _filter_and_prioritize([])
        assert result == [], f"空输入应返回空列表，实际 {result}"


class TestFeedbackRatioBoostInEvolution:
    """feedback ratio 影响演化时的重要性提升。"""

    def test_positive_feedback_boosts_importance_in_execute(self):
        """正面反馈记忆在演化执行后获得额外 +0.1 importance boost。"""
        store_path, store = _new_tmp_store()

        try:
            # 高正面反馈记忆（ratio=1.0）
            mem = _make_positive_memory("mem_boost_001")
            mem = Memory(
                id="mem_boost_001",
                content="高正面反馈记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["positive"],
                tags=[],
                context="原始上下文",
                importance=5,
                positive_feedback=10,
                negative_feedback=0,
            )
            store.add(mem)

            plan = [
                {
                    "neighbor_id": "mem_boost_001",
                    "new_context": "演化后的上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]

            execute_evolution(plan, store, triggered_by_id="mem_trigger_boost")

            reloaded = store.get("mem_boost_001")
            # 正面反馈 ratio=1.0 > 0.7，应获得 importance boost
            assert reloaded.importance > 5, (
                f"正面反馈记忆演化后 importance 应提升，原始 5，实际 {reloaded.importance}"
            )

        finally:
            os.unlink(store_path)

    def test_feedback_ratio_affects_importance_boost(self):
        """feedback ratio <= 0.5 的记忆不获得 importance boost。"""
        store_path, store = _new_tmp_store()

        try:
            # 低 ratio 记忆（warning 状态，ratio=0.333）
            mem = Memory(
                id="mem_no_boost_001",
                content="低 ratio 记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["warning"],
                tags=[],
                context="原始上下文",
                importance=5,
                positive_feedback=2,
                negative_feedback=4,
            )
            store.add(mem)

            plan = [
                {
                    "neighbor_id": "mem_no_boost_001",
                    "new_context": "演化后的上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]

            execute_evolution(plan, store, triggered_by_id="mem_trigger_no_boost")

            reloaded = store.get("mem_no_boost_001")
            # ratio=0.333 <= 0.5，不应获得 boost
            assert reloaded.importance == 5, (
                f"低 ratio 记忆演化后 importance 不应变化，实际 {reloaded.importance}"
            )

        finally:
            os.unlink(store_path)

    def test_evolution_preserves_feedback_metadata(self):
        """演化后 positive_feedback 和 negative_feedback 字段保持不变。"""
        store_path, store = _new_tmp_store()

        try:
            mem = Memory(
                id="mem_meta_001",
                content="某项记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["test"],
                tags=[],
                context="原始上下文",
                importance=5,
                positive_feedback=7,
                negative_feedback=3,
            )
            store.add(mem)

            plan = [
                {
                    "neighbor_id": "mem_meta_001",
                    "new_context": "演化更新的上下文",
                    "add_tags": ["evolved"],
                    "add_keywords": [],
                }
            ]

            execute_evolution(plan, store, triggered_by_id="mem_trigger_meta")

            reloaded = store.get("mem_meta_001")
            assert reloaded.positive_feedback == 7, (
                f"演化不应修改 positive_feedback，实际 {reloaded.positive_feedback}"
            )
            assert reloaded.negative_feedback == 3, (
                f"演化不应修改 negative_feedback，实际 {reloaded.negative_feedback}"
            )

        finally:
            os.unlink(store_path)

    def test_merged_memory_inherits_best_feedback(self):
        """合并两条记忆时，结果继承 positive_feedback 较高的那条的 feedback 数据。"""
        store_path, store = _new_tmp_store()

        try:
            # 记忆 A：高正面反馈
            mem_a = Memory(
                id="mem_merge_a",
                content="记忆 A",
                timestamp=datetime.now().isoformat(),
                keywords=["merge"],
                tags=[],
                context="上下文 A",
                importance=5,
                positive_feedback=10,
                negative_feedback=1,
            )
            # 记忆 B：低正面反馈
            mem_b = Memory(
                id="mem_merge_b",
                content="记忆 B",
                timestamp=datetime.now().isoformat(),
                keywords=["merge"],
                tags=[],
                context="上下文 B",
                importance=5,
                positive_feedback=2,
                negative_feedback=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            # 使用 execute_evolution 模拟"合并"：用 mem_a 的 feedback 更新 mem_b
            merged = evolver.merge_feedback(mem_a, mem_b)

            # 合并结果应继承较好的 feedback（mem_a 的）
            assert merged.positive_feedback == 10, (
                f"合并后应继承高 positive_feedback=10，实际 {merged.positive_feedback}"
            )
            assert merged.negative_feedback == 1, (
                f"合并后应继承低 negative_feedback=1，实际 {merged.negative_feedback}"
            )

        finally:
            os.unlink(store_path)


class TestEvolveNeighborsFeedbackIntegration:
    """evolve_neighbors() 集成 feedback 过滤的完整流程。"""

    def test_evolve_neighbors_skips_blocked(self):
        """evolve_neighbors 中 blocked 邻居被过滤，不参与演化。"""
        store_path, store = _new_tmp_store()

        try:
            # blocked 邻居
            blocked = Memory(
                id="mem_bl_integ_001",
                content="被阻断的记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["LaTeX", "error"],
                tags=[],
                context="已阻断的上下文",
                importance=3,
                positive_feedback=1,
                negative_feedback=9,
            )
            # 正常邻居
            normal = Memory(
                id="mem_nm_integ_001",
                content="正常记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["LaTeX", "config"],
                tags=[],
                context="正常上下文",
                importance=5,
                positive_feedback=5,
                negative_feedback=1,
            )
            store.add(blocked)
            store.add(normal)

            new_memory = _make_memory(
                "mem_new_integ_001",
                "LaTeX 解决方案",
                keywords=["LaTeX", "solution"],
            )

            should_evolve_resp = json.dumps(
                {"should_evolve": True, "reason": "包含解决方案"}
            )
            plan_resp = json.dumps({
                "updates": [
                    {
                        "neighbor_id": "mem_nm_integ_001",
                        "new_context": "正常上下文；解决方案已知",
                        "add_tags": ["solved"],
                        "add_keywords": ["solution"],
                    }
                ]
            })

            call_count = [0]

            def mock_create(**kwargs):
                call_count[0] += 1
                mock_response = MagicMock()
                if call_count[0] == 1:
                    mock_response.content = [MagicMock(text=should_evolve_resp)]
                else:
                    mock_response.content = [MagicMock(text=plan_resp)]
                return mock_response

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = mock_create

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations',
                       return_value=["mem_bl_integ_001", "mem_nm_integ_001"]):
                updated = evolve_neighbors(new_memory, store)

            # blocked 不在更新列表
            assert "mem_bl_integ_001" not in updated, (
                f"blocked 记忆不应被更新，实际 {updated}"
            )
            # normal 被更新
            assert "mem_nm_integ_001" in updated, (
                f"正常记忆应被更新，实际 {updated}"
            )

            # 验证 blocked 记忆未被修改
            reloaded_blocked = store.get("mem_bl_integ_001")
            assert len(reloaded_blocked.evolution_history) == 0, (
                f"blocked 记忆不应有演化历史，实际 {len(reloaded_blocked.evolution_history)}"
            )

        finally:
            os.unlink(store_path)

    def test_evolution_with_health_cache(self):
        """多次调用 _filter_and_prioritize 时，相同记忆的 health 结果一致（幂等性验证）。"""
        memories = [
            _make_blocked_memory("mem_cache_001"),
            _make_warning_memory("mem_cache_002"),
            _make_healthy_memory("mem_cache_003"),
        ]

        result1 = _filter_and_prioritize(memories)
        result2 = _filter_and_prioritize(memories)

        # 两次调用结果一致
        ids1 = [m.id for m in result1]
        ids2 = [m.id for m in result2]
        assert ids1 == ids2, (
            f"多次调用结果应一致，第一次 {ids1}，第二次 {ids2}"
        )
        # blocked 被过滤
        assert "mem_cache_001" not in ids1
        # warning 和 healthy 都保留
        assert len(ids1) == 2


# ==================== 测试运行器 ====================

def run_tests():
    """按顺序运行所有测试，输出详细结果。"""
    test_classes = [
        TestFilterAndPrioritize,
        TestFeedbackRatioBoostInEvolution,
        TestEvolveNeighborsFeedbackIntegration,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("Evolver + Feedback 联动单元测试")
    print("=" * 60)

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

    print()
    print("=" * 60)
    print(f"结果: {passed} 通过 / {failed} 失败")
    print("=" * 60)

    if errors:
        print("\n详细错误信息:")
        for label, trace in errors:
            print(f"\n--- {label} ---")
            print(trace)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
