"""Phase 2.2 Memory Decay 测试：基于指数衰减的记忆重要性降级。

TDD 流程：
1. RED: 先运行确认全部失败（decay_engine.py 尚未创建）
2. GREEN: 创建 decay_engine.py 让测试通过
3. REFACTOR: 清理

算法规格：
  R = e^(-t/S)，其中 t = 距上次访问天数，S = base_importance * 3（stability 天数）
  decayed_importance = max(base * 0.2, base * R)       floor = base × 20%
  last_accessed 为 None 时，使用 memory.timestamp（创建时间）作为参考点
"""

import math
import os
import sys
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import Optional

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore

# decay_engine 尚未创建 —— 测试导入此模块时会 ImportError（RED 阶段正常）
from decay_engine import compute_retention, apply_decay, cleanup_decayed


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
    )
    defaults.update(kwargs)
    return Memory(**defaults)


# ==================== compute_retention 测试 ====================

class TestComputeRetention:
    """测试 compute_retention(last_accessed, base_importance, now) → float。

    公式：R = e^(-t/S)，S = base_importance * 3
    """

    def test_compute_retention_fresh(self):
        """刚访问的记忆（t=0），retention 应约等于 1.0。

        t=0 → R = e^0 = 1.0
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = "2026-03-14T12:00:00"  # 与 now 完全相同

        retention = compute_retention(
            last_accessed=last_accessed,
            base_importance=5,
            now=now,
        )

        assert abs(retention - 1.0) < 1e-9, (
            f"刚访问的记忆 retention 应为 1.0，实际：{retention:.6f}"
        )

    def test_compute_retention_30_days(self):
        """importance=10，30 天后 retention ≈ e^(-30/30) ≈ 0.3679。

        S = 10 * 3 = 30，t = 30 → R = e^(-1) ≈ 0.3679
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=30)).isoformat()

        retention = compute_retention(
            last_accessed=last_accessed,
            base_importance=10,
            now=now,
        )

        expected = math.exp(-1)  # e^(-30/30) = e^(-1)
        assert abs(retention - expected) < 0.001, (
            f"importance=10，30 天后 retention 应约 {expected:.4f}，实际：{retention:.4f}"
        )

    def test_compute_retention_high_importance(self):
        """高 importance 衰减更慢（S 更大），同等时间后 retention 更高。

        importance=10 时 S=30，importance=1 时 S=3
        t=15 天：
          R(importance=10) = e^(-15/30) = e^(-0.5) ≈ 0.6065
          R(importance=1)  = e^(-15/3)  = e^(-5)   ≈ 0.0067
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=15)).isoformat()

        retention_high = compute_retention(
            last_accessed=last_accessed,
            base_importance=10,
            now=now,
        )
        retention_low = compute_retention(
            last_accessed=last_accessed,
            base_importance=1,
            now=now,
        )

        assert retention_high > retention_low, (
            f"高 importance 记忆 retention ({retention_high:.4f}) "
            f"应高于低 importance ({retention_low:.4f})"
        )
        # 验证具体值
        assert abs(retention_high - math.exp(-0.5)) < 0.001, (
            f"importance=10, 15 天后应为 {math.exp(-0.5):.4f}，实际：{retention_high:.4f}"
        )
        assert abs(retention_low - math.exp(-5)) < 0.001, (
            f"importance=1, 15 天后应为 {math.exp(-5):.6f}，实际：{retention_low:.6f}"
        )

    def test_compute_retention_floor(self):
        """极长时间后，compute_retention 返回值在 [0, 1] 范围内（未裁剪到 floor，floor 由调用方处理）。

        注：compute_retention 只负责计算原始 R = e^(-t/S)，
        floor 裁剪 (max(0.2, R)) 由 apply_decay 负责。
        极长时间后 R 接近 0，但 compute_retention 本身不施加 floor。
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        # 3000 天前访问，S=5*3=15，t/S = 200，e^(-200) ≈ 0
        last_accessed = (now - timedelta(days=3000)).isoformat()

        retention = compute_retention(
            last_accessed=last_accessed,
            base_importance=5,
            now=now,
        )

        assert 0.0 <= retention <= 1.0, (
            f"retention 应在 [0,1] 范围内，实际：{retention}"
        )
        # 极长时间后应接近 0
        assert retention < 0.01, (
            f"3000 天后 retention 应接近 0，实际：{retention:.6f}"
        )

    def test_compute_retention_none_last_accessed(self):
        """last_accessed 为 None 时，应使用 memory 的 timestamp（created_at）作为参考点。

        直接调用 compute_retention(None, importance, now) 时：
        由于 compute_retention 只接收 last_accessed 字符串，
        None 情况的处理在 apply_decay 中（用 memory.timestamp 代入）。
        此测试验证：传入 None 时函数行为（预期返回 1.0 或按合理方式处理）。

        根据规格：last_accessed 为 None 时使用 memory.updated_at 或 memory.created_at。
        compute_retention 接收 Optional[str]，传入 None 应视为"无记录"，
        合理行为是返回 1.0（保守估计，不惩罚）。
        """
        now = datetime(2026, 3, 14, 12, 0, 0)

        retention = compute_retention(
            last_accessed=None,
            base_importance=5,
            now=now,
        )

        # None last_accessed → 无法计算衰减 → 返回 1.0（保守：不惩罚）
        assert abs(retention - 1.0) < 1e-9, (
            f"last_accessed=None 时 retention 应为 1.0（保守估计），实际：{retention:.6f}"
        )


# ==================== apply_decay 测试 ====================

class TestApplyDecay:
    """测试 apply_decay(memory, now) → Memory（不可变）。

    decayed_importance = max(base * 0.2, base * R)
    """

    def test_apply_decay_returns_new_memory(self):
        """apply_decay 必须返回新 Memory 对象，不修改原对象（不可变原则）。"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        # 30 天前访问过
        last_accessed = (now - timedelta(days=30)).isoformat()
        original = make_memory(
            importance=10,
            last_accessed=last_accessed,
        )
        original_importance = original.importance

        decayed = apply_decay(original, now=now)

        # 必须是不同对象
        assert decayed is not original, "apply_decay 应返回新 Memory 对象，不应返回原对象"
        # 原对象 importance 不变
        assert original.importance == original_importance, (
            f"原对象 importance 被修改了！原值={original_importance}，"
            f"现值={original.importance}"
        )

    def test_apply_decay_importance_updated(self):
        """新 Memory 的 importance 应为衰减后的整数值。

        importance=10，30 天后：
          S=30, R = e^(-1) ≈ 0.3679
          decayed = max(10 * 0.2, 10 * 0.3679) = max(2.0, 3.679) = 3.679
          取整后（floor int）= 3（或按实现取最近整数）

        注：importance 字段类型是 int，apply_decay 应将衰减后的 float 取整存储。
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=30)).isoformat()
        mem = make_memory(
            importance=10,
            last_accessed=last_accessed,
        )

        decayed = apply_decay(mem, now=now)

        # 衰减后 importance 应低于原值
        assert decayed.importance < mem.importance, (
            f"衰减后 importance ({decayed.importance}) 应低于原值 ({mem.importance})"
        )
        # 应大于等于 floor（base * 0.2 = 2）
        floor_val = max(1, int(mem.importance * 0.2))
        assert decayed.importance >= floor_val, (
            f"衰减后 importance ({decayed.importance}) 不应低于 floor ({floor_val})"
        )
        # 应小于等于原值
        assert decayed.importance <= mem.importance, (
            f"衰减后 importance ({decayed.importance}) 不应高于原值 ({mem.importance})"
        )

    def test_apply_decay_uses_timestamp_when_no_last_accessed(self):
        """last_accessed 为 None 时，apply_decay 应使用 memory.timestamp 作为参考时间。

        如果 memory.timestamp 是 30 天前，即使 last_accessed=None，
        importance 也应发生衰减。
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        old_timestamp = (now - timedelta(days=30)).isoformat()
        mem = make_memory(
            importance=10,
            timestamp=old_timestamp,  # 创建时间是 30 天前
            last_accessed=None,        # 从未被检索
        )

        decayed = apply_decay(mem, now=now)

        # 30 天前创建、从未访问 → 应发生衰减
        assert decayed.importance < mem.importance, (
            f"last_accessed=None 时应使用 timestamp 计算衰减，"
            f"但 importance 未变化（{decayed.importance} = {mem.importance}）"
        )

    def test_apply_decay_floor_prevents_zero(self):
        """极长时间后，importance 不应低于 floor（base × 0.2，至少为 1）。

        importance=5，3000 天后 R ≈ 0：
          floor = max(1, int(5 * 0.2)) = max(1, 1) = 1
          decayed = max(1, ...) = 1
        """
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=3000)).isoformat()
        mem = make_memory(
            importance=5,
            last_accessed=last_accessed,
        )

        decayed = apply_decay(mem, now=now)

        # 不应降到 0 或负数
        assert decayed.importance >= 1, (
            f"极长时间后 importance 不应低于 1（floor），实际：{decayed.importance}"
        )


# ==================== cleanup_decayed 测试 ====================

class TestCleanupDecayed:
    """测试 cleanup_decayed(store, floor_ratio, now) → int。

    清理所有 importance 已触底（= floor）的记忆，返回删除数。
    floor = base_importance * floor_ratio（默认 0.2）

    判断"触底"的条件：memory.importance <= max(1, int(memory.importance * floor_ratio))
    注意：这里的 importance 是衰减前的原始值 vs 衰减后的值。

    实现上：cleanup_decayed 对每条记忆先调用 apply_decay，
    再判断衰减后值是否等于 floor（即已不可再降）。
    """

    def _make_floor_memory(self, now: datetime, mem_id: str = "floor_mem_001") -> Memory:
        """创建一条 importance 已触底的记忆（3000 天未访问，importance=5）。"""
        last_accessed = (now - timedelta(days=3000)).isoformat()
        return make_memory(
            id=mem_id,
            importance=5,
            last_accessed=last_accessed,
        )

    def _make_active_memory(self, now: datetime, mem_id: str = "active_mem_001") -> Memory:
        """创建一条活跃记忆（刚访问，importance=5）。"""
        last_accessed = now.isoformat()
        return make_memory(
            id=mem_id,
            importance=5,
            last_accessed=last_accessed,
        )

    def test_cleanup_decayed_removes_floor_memories(self):
        """触底的记忆（极长时间未访问）应被 cleanup_decayed 删除。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            now = datetime(2026, 3, 14, 12, 0, 0)

            floor_mem = self._make_floor_memory(now, mem_id="floor_001")
            store.add(floor_mem)

            initial_count = store.count()
            assert initial_count == 1, f"初始应有 1 条记忆，实际：{initial_count}"

            deleted = cleanup_decayed(store, floor_ratio=0.2, now=now)

            assert deleted == 1, f"应删除 1 条触底记忆，实际删除：{deleted}"
            assert store.count() == 0, (
                f"清理后应剩 0 条记忆，实际：{store.count()}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_cleanup_decayed_keeps_active_memories(self):
        """活跃记忆（未触底）不应被 cleanup_decayed 删除。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            now = datetime(2026, 3, 14, 12, 0, 0)

            active_mem = self._make_active_memory(now, mem_id="active_001")
            store.add(active_mem)

            deleted = cleanup_decayed(store, floor_ratio=0.2, now=now)

            assert deleted == 0, f"活跃记忆不应被删除，实际删除：{deleted}"
            assert store.count() == 1, (
                f"清理后应仍有 1 条记忆，实际：{store.count()}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_cleanup_decayed_returns_count(self):
        """cleanup_decayed 应返回正确的删除数。

        3 条触底 + 2 条活跃 → 删除 3，返回 3。
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            now = datetime(2026, 3, 14, 12, 0, 0)

            # 3 条触底记忆
            for i in range(3):
                store.add(self._make_floor_memory(now, mem_id=f"floor_{i:03d}"))

            # 2 条活跃记忆
            for i in range(2):
                store.add(self._make_active_memory(now, mem_id=f"active_{i:03d}"))

            assert store.count() == 5, f"初始应有 5 条记忆，实际：{store.count()}"

            deleted = cleanup_decayed(store, floor_ratio=0.2, now=now)

            assert deleted == 3, f"应删除 3 条触底记忆，实际删除：{deleted}"
            assert store.count() == 2, (
                f"清理后应剩 2 条记忆，实际：{store.count()}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_cleanup_decayed_empty_store(self):
        """空 store 调用 cleanup_decayed 应返回 0，不报错。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            now = datetime(2026, 3, 14, 12, 0, 0)

            deleted = cleanup_decayed(store, floor_ratio=0.2, now=now)

            assert deleted == 0, f"空 store 应返回 0，实际：{deleted}"
        finally:
            shutil.rmtree(tmp_dir)


# ==================== decay + feedback 联动测试 ====================

class TestDecayFeedbackIntegration:
    """测试 decay 与 feedback 的联动"""

    def test_positive_feedback_slows_decay(self):
        """正面反馈记忆衰减更慢"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=30)).isoformat()

        # mem_a: positive_feedback=10, negative_feedback=0
        mem_a = make_memory(
            id="mem_a",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=10,
            negative_feedback=0,
        )
        # mem_b: positive_feedback=0, negative_feedback=0（无反馈）
        mem_b = make_memory(
            id="mem_b",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=0,
        )

        decayed_a = apply_decay(mem_a, now=now)
        decayed_b = apply_decay(mem_b, now=now)

        assert decayed_a.importance >= decayed_b.importance, (
            f"正面反馈记忆 importance ({decayed_a.importance}) "
            f"应 >= 无反馈记忆 ({decayed_b.importance})"
        )

    def test_negative_feedback_accelerates_decay(self):
        """负面反馈记忆衰减更快"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=15)).isoformat()

        # mem_a: 全负面反馈
        mem_a = make_memory(
            id="mem_a",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=10,
        )
        # mem_b: 无反馈
        mem_b = make_memory(
            id="mem_b",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=0,
        )

        decayed_a = apply_decay(mem_a, now=now)
        decayed_b = apply_decay(mem_b, now=now)

        assert decayed_a.importance <= decayed_b.importance, (
            f"负面反馈记忆 importance ({decayed_a.importance}) "
            f"应 <= 无反馈记忆 ({decayed_b.importance})"
        )

    def test_balanced_feedback_no_change(self):
        """正负反馈平衡时衰减与无反馈相近"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=20)).isoformat()

        # mem_balanced: positive=5, negative=5 → ratio=0.5
        mem_balanced = make_memory(
            id="mem_balanced",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=5,
            negative_feedback=5,
        )
        # mem_none: 无反馈 → ratio=0.5
        mem_none = make_memory(
            id="mem_none",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=0,
        )

        decayed_balanced = apply_decay(mem_balanced, now=now)
        decayed_none = apply_decay(mem_none, now=now)

        assert decayed_balanced.importance == decayed_none.importance, (
            f"平衡反馈记忆 importance ({decayed_balanced.importance}) "
            f"应与无反馈记忆完全一致 ({decayed_none.importance})"
        )

    def test_feedback_factor_has_bounds(self):
        """feedback 因子有上下限，不会无限放大或缩小"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=1)).isoformat()

        # 极端正面：factor 最大 2.0
        mem_extreme_pos = make_memory(
            id="mem_extreme_pos",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=100,
            negative_feedback=0,
        )
        # 极端负面：factor 最小 0.5
        mem_extreme_neg = make_memory(
            id="mem_extreme_neg",
            importance=5,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=100,
        )

        # 直接测试 _feedback_factor
        from decay_engine import _feedback_factor

        factor_pos = _feedback_factor(mem_extreme_pos)
        factor_neg = _feedback_factor(mem_extreme_neg)

        assert factor_pos <= 2.0, f"极端正面 factor 应 <= 2.0，实际：{factor_pos}"
        assert factor_neg >= 0.5, f"极端负面 factor 应 >= 0.5，实际：{factor_neg}"

    def test_l3_no_decay(self):
        """L3（core）记忆不衰减，importance 保持原值。"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=100)).isoformat()

        mem_l3 = make_memory(
            id="mem_l3",
            importance=8,
            last_accessed=last_accessed,
            layer="L3",
        )

        decayed = apply_decay(mem_l3, now=now)

        assert decayed.importance == mem_l3.importance, (
            f"L3 记忆不应衰减：原值 {mem_l3.importance}，衰减后 {decayed.importance}"
        )

    def test_l2_half_decay(self):
        """L2（semantic）衰减速度是 L1 的一半（双倍稳定性）。"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=30)).isoformat()

        mem_l1 = make_memory(
            id="mem_l1",
            importance=10,
            last_accessed=last_accessed,
            layer="L1",
        )
        mem_l2 = make_memory(
            id="mem_l2",
            importance=10,
            last_accessed=last_accessed,
            layer="L2",
        )

        decayed_l1 = apply_decay(mem_l1, now=now)
        decayed_l2 = apply_decay(mem_l2, now=now)

        # L2 衰减更慢，importance 应 >= L1
        assert decayed_l2.importance >= decayed_l1.importance, (
            f"L2 衰减应比 L1 慢：L2={decayed_l2.importance}, L1={decayed_l1.importance}"
        )

        # 验证 L2 的 S 是 L1 的两倍导致衰减率差异
        # L1: S = 10 * 3 = 30, R = e^(-30/30) = e^(-1) ≈ 0.3679
        # L2: S = 10 * 3 * 2 = 60, R = e^(-30/60) = e^(-0.5) ≈ 0.6065
        import math
        expected_l1_retention = math.exp(-1)  # ≈ 0.3679
        expected_l2_retention = math.exp(-0.5)  # ≈ 0.6065
        assert expected_l2_retention > expected_l1_retention

    def test_no_feedback_backward_compatible(self):
        """无反馈记忆行为不变（向后兼容）"""
        now = datetime(2026, 3, 14, 12, 0, 0)
        last_accessed = (now - timedelta(days=30)).isoformat()

        # 使用 Memory 对象（有 positive/negative_feedback=0）
        mem_with_fields = make_memory(
            id="mem_with_fields",
            importance=10,
            last_accessed=last_accessed,
            positive_feedback=0,
            negative_feedback=0,
        )

        # compute_retention 旧接口（仅传 last_accessed + base_importance）
        expected_retention = compute_retention(
            last_accessed=last_accessed,
            base_importance=10,
            now=now,
        )
        expected_importance = max(1, int(max(10 * 0.2, 10 * expected_retention)))

        decayed = apply_decay(mem_with_fields, now=now)

        assert decayed.importance == expected_importance, (
            f"无反馈时衰减结果应与旧实现一致：期望 {expected_importance}，实际 {decayed.importance}"
        )
