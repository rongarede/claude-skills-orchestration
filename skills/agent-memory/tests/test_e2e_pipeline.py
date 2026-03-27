"""
端到端全链路测试

验证 feedback + retriever + trigger_tracker 的完整交互管道。
每个场景测试跨越多个模块的完整数据流。
"""
import pytest
import tempfile
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import MemoryStore, Memory
from feedback_loop import (
    infer_memory_feedback, check_memory_health, filter_by_health,
    check_escalation, apply_escalation
)
from retriever import retrieve
from trigger_tracker import record_trigger, get_efficiency, adjust_weight, reset_stats


# ==================== 辅助函数 ====================

def make_memory(
    mem_id: str,
    content: str = "测试记忆内容",
    keywords: list = None,
    importance: int = 5,
    positive_feedback: int = 0,
    negative_feedback: int = 0,
) -> Memory:
    """创建测试用 Memory，设置必填字段默认值。"""
    return Memory(
        id=mem_id,
        content=content,
        timestamp=datetime.now().isoformat(),
        keywords=keywords or ["测试", "记忆", "内容"],
        tags=["test", "e2e"],
        context="端到端测试上下文",
        importance=importance,
        positive_feedback=positive_feedback,
        negative_feedback=negative_feedback,
    )


# ==================== S1: 正常任务流 ====================

class TestS1NormalTaskFlow:
    """task → auto-feedback → memory score 变化。

    验证正面反馈提升检索排名，audit_pass 给记忆 +2 正面反馈。
    """

    def test_feedback_improves_retrieval_rank(self):
        """创建 2 条相似记忆，对 mem_a 大量给正面反馈，验证 importance score 提升。

        数据流：add memories → 10× infer_memory_feedback(task_success) → 验证 importance score 提升
        → 直接对比 importance 评分（绕过 BM25 相关度的不确定性）

        验证策略：比较 compute_importance_score(mem_a) vs compute_importance_score(mem_b)，
        而非检索结果排序（后者受 BM25 随机性影响，不稳定）。
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建 2 条内容相同的记忆（排除 BM25 相关度干扰）
            mem_a = make_memory(
                "e2e_s1_mem_a",
                content="Python 异步编程最佳实践，使用 asyncio 和 await",
                keywords=["Python", "异步", "asyncio", "await", "编程"],
                importance=5,
            )
            mem_b = make_memory(
                "e2e_s1_mem_b",
                content="Python 异步编程最佳实践，使用 asyncio 和 await",
                keywords=["Python", "异步", "asyncio", "await", "编程"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            # 2. 对 mem_a 施加 10 次 task_success 正面反馈（positive_feedback 累积到 10）
            # 大量正面反馈确保 feedback_adj 显著高于 mem_b（无反馈，默认 0.5 ratio）
            for _ in range(10):
                infer_memory_feedback("e2e_s1_mem_a", "task_success", store)

            # 3. 获取更新后的记忆
            updated_a = store.get("e2e_s1_mem_a")
            updated_b = store.get("e2e_s1_mem_b")

            # 4. 直接计算 importance score（绕过 BM25 随机性）
            from retriever import compute_importance_score
            score_a = compute_importance_score(updated_a)
            score_b = compute_importance_score(updated_b)

            # 5. 验证 mem_a 的 importance score 高于 mem_b
            assert score_a > score_b, (
                f"10 次正面反馈的 mem_a importance_score ({score_a:.4f}) 应高于"
                f" 无反馈的 mem_b ({score_b:.4f})"
            )

            # 6. 验证 positive_feedback 已正确累积
            assert updated_a.positive_feedback == 10, (
                f"10 次 task_success 后 positive_feedback 应为 10，实际：{updated_a.positive_feedback}"
            )
            assert updated_b.positive_feedback == 0, (
                f"未获反馈的 mem_b positive_feedback 应为 0，实际：{updated_b.positive_feedback}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_audit_pass_boosts_memory(self):
        """audit_pass 事件给记忆 +2 正面反馈，并验证健康状态仍为 healthy。

        数据流：add memory → infer_memory_feedback(audit_pass) → get memory → check_memory_health
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建记忆
            mem = make_memory(
                "e2e_s1_audit_mem",
                content="代码审查通过，架构设计符合 SOLID 原则",
                keywords=["代码审查", "SOLID", "架构", "审计"],
            )
            store.add(mem)

            # 2. 触发 audit_pass 事件（权重 +2 positive）
            result = infer_memory_feedback("e2e_s1_audit_mem", "audit_pass", store)

            # 3. 验证反馈数值
            assert result["delta_positive"] == 2, (
                f"audit_pass 应 delta_positive=2，实际：{result['delta_positive']}"
            )

            # 4. 验证 store 中实际记忆已更新
            updated = store.get("e2e_s1_audit_mem")
            assert updated.positive_feedback == 2, (
                f"audit_pass 后 positive_feedback 应为 2，实际：{updated.positive_feedback}"
            )

            # 5. 验证记忆健康状态（2 次正面反馈，总反馈 < 3，应为 healthy）
            health = check_memory_health(updated)
            assert health == "healthy", (
                f"2 次正面反馈的记忆健康状态应为 healthy，实际：{health}"
            )
        finally:
            shutil.rmtree(tmp_dir)


# ==================== S2: 重复失败升级 ====================

class TestS2RepeatedFailureEscalation:
    """3次失败 → warning 升级 → retriever 降权。

    验证失败反馈的渐进式升级机制，以及 retriever 对 warning 记忆的降权处理。
    """

    def test_three_failures_trigger_warning(self):
        """3 次 task_retry → negative_feedback >= 3 → check_memory_health 返回 warning。

        数据流：add memory → 3× infer_memory_feedback(task_retry) → check_memory_health
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建记忆
            mem = make_memory(
                "e2e_s2_warning_mem",
                content="数据库连接池配置，每次都需要重试才能成功",
                keywords=["数据库", "连接池", "重试", "配置"],
            )
            store.add(mem)

            # 2. 循环 3 次 task_retry → 每次 negative_feedback +1
            for _ in range(3):
                infer_memory_feedback("e2e_s2_warning_mem", "task_retry", store)

            # 3. 重新获取记忆（验证持久化）
            updated = store.get("e2e_s2_warning_mem")
            assert updated.negative_feedback == 3, (
                f"3 次 task_retry 后 negative_feedback 应为 3，实际：{updated.negative_feedback}"
            )

            # 4. 验证健康状态升级为 warning
            # 条件：ratio = 0/3 = 0.0 <= 0.4，negative = 3 >= 3
            health = check_memory_health(updated)
            assert health == "warning", (
                f"3 次失败后健康状态应为 warning，实际：{health}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_warning_memory_retrieval_downweighted(self):
        """warning 记忆在检索中 score ×0.5，低于同等 healthy 记忆。

        数据流：add 2 memories → 触发 warning → retrieve → 验证 warning 记忆 score 更低
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建 2 条内容相似的记忆
            mem_a = make_memory(
                "e2e_s2_warn_a",
                content="Redis 缓存策略，使用 LRU 淘汰算法优化内存使用",
                keywords=["Redis", "缓存", "LRU", "内存", "优化"],
                importance=5,
            )
            mem_b = make_memory(
                "e2e_s2_warn_b",
                content="Redis 缓存配置，LRU 内存管理和缓存过期策略",
                keywords=["Redis", "缓存", "LRU", "内存", "过期"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            # 2. 对 mem_a 触发 3 次 task_retry 使其成为 warning 状态
            # task_retry 权重：(0, 1)，3 次后 negative=3，ratio=0.0，触发 warning
            for _ in range(3):
                infer_memory_feedback("e2e_s2_warn_a", "task_retry", store)

            # 3. 验证 mem_a 确实是 warning
            warn_mem = store.get("e2e_s2_warn_a")
            assert check_memory_health(warn_mem) == "warning", "mem_a 应已进入 warning 状态"

            # 4. 检索
            now = datetime.now()
            results = retrieve("Redis 缓存内存管理", store, top_k=2, now=now)

            score_map = {mem.id: score for mem, score in results}

            # 5. 验证两条记忆都出现在结果中
            assert "e2e_s2_warn_a" in score_map, "warning 记忆应出现在检索结果中（未被排除）"
            assert "e2e_s2_warn_b" in score_map, "healthy 记忆应出现在检索结果中"

            # 6. warning 记忆因 ×0.5 降权，得分应低于 healthy 记忆
            assert score_map["e2e_s2_warn_a"] < score_map["e2e_s2_warn_b"], (
                f"warning 记忆 ({score_map['e2e_s2_warn_a']:.4f}) 应低于"
                f" healthy 记忆 ({score_map['e2e_s2_warn_b']:.4f})"
            )
        finally:
            shutil.rmtree(tmp_dir)


# ==================== S3: 触发效率权重 ====================

class TestS3TriggerEfficiencyWeight:
    """触发成功 → 权重上升；触发失败 → 权重下降；持续失败 → disable 建议。"""

    def test_successful_triggers_increase_weight(self):
        """10 次成功 → 效率 100% → weight 从 1.0 升至 1.1。

        数据流：10× record_trigger(success) → get_efficiency → adjust_weight
        """
        tmp_dir = tempfile.mkdtemp()
        stats_path = Path(tmp_dir) / "trigger-stats.json"
        try:
            rule = "记忆保存规则"

            # 1. 循环 10 次记录成功触发
            for _ in range(10):
                record_trigger(rule, "success", stats_path=stats_path)

            # 2. 验证效率为 1.0（全成功）
            eff = get_efficiency(rule, stats_path=stats_path)
            assert eff == 1.0, f"10 次全成功效率应为 1.0，实际：{eff}"

            # 3. 调整权重：效率 > 80% → weight +0.1
            new_weight, suggestion = adjust_weight(rule, current_weight=1.0, stats_path=stats_path)
            assert abs(new_weight - 1.1) < 1e-9, (
                f"效率 100% 应权重 +0.1 变为 1.1，实际：{new_weight}"
            )
            assert suggestion is None, f"高效率不应有 disable 建议，实际：{suggestion}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_failed_triggers_decrease_weight(self):
        """10 次失败 → 效率 0% → weight 从 1.0 降至 0.8。

        数据流：10× record_trigger(failure) → adjust_weight
        """
        tmp_dir = tempfile.mkdtemp()
        stats_path = Path(tmp_dir) / "trigger-stats.json"
        try:
            rule = "低效触发规则"

            # 1. 循环 10 次记录失败触发
            for _ in range(10):
                record_trigger(rule, "failure", stats_path=stats_path)

            # 2. 调整权重：效率 0% < 40% → weight -0.2
            new_weight, _ = adjust_weight(rule, current_weight=1.0, stats_path=stats_path)
            assert abs(new_weight - 0.8) < 1e-9, (
                f"效率 0% 应权重 -0.2 变为 0.8，实际：{new_weight}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_persistent_failure_suggests_disable(self):
        """效率 < 20% 且触发次数 >= 5 → 建议禁用。

        数据流：1 success + 5 failure → adjust_weight → suggestion=="disable"
        """
        tmp_dir = tempfile.mkdtemp()
        stats_path = Path(tmp_dir) / "trigger-stats.json"
        try:
            rule = "持续失败规则"

            # 1. 记录 1 次成功 + 5 次失败
            # 效率 = 1/(1+5) ≈ 0.167 < 0.2，且总触发 = 6 >= 5
            record_trigger(rule, "success", stats_path=stats_path)
            for _ in range(5):
                record_trigger(rule, "failure", stats_path=stats_path)

            # 2. 验证效率低于禁用阈值
            eff = get_efficiency(rule, stats_path=stats_path)
            assert eff < 0.2, f"效率应 < 0.2，实际：{eff:.4f}"

            # 3. 调整权重：应给出 "disable" 建议
            _, suggestion = adjust_weight(rule, current_weight=1.0, stats_path=stats_path)
            assert suggestion == "disable", (
                f"持续低效率规则应建议 disable，实际：{suggestion}"
            )
        finally:
            shutil.rmtree(tmp_dir)


# ==================== S4: 阻断测试 ====================

class TestS4BlockedMemory:
    """5次负面 → blocked → retriever 排除。

    验证记忆从健康 → 阻断的完整路径，以及检索时的排除逻辑。
    """

    def test_five_negatives_block_memory(self):
        """5 次 user_negative → blocked（每次 -3，共 -15 negative_feedback）。

        user_negative 权重是 3，5 次 = negative_feedback 15，ratio = 0/15 = 0.0 ≤ 0.2，
        且 negative >= 5 → blocked。

        数据流：add memory → 5× infer_memory_feedback(user_negative) → check_memory_health
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建记忆
            mem = make_memory(
                "e2e_s4_block_mem",
                content="过时的 API 调用方式，已废弃不推荐使用",
                keywords=["API", "废弃", "过时", "调用"],
            )
            store.add(mem)

            # 2. 循环 5 次 user_negative（每次 negative_feedback +3）
            for i in range(5):
                infer_memory_feedback("e2e_s4_block_mem", "user_negative", store)

            # 3. 验证 negative_feedback 累计值
            updated = store.get("e2e_s4_block_mem")
            assert updated.negative_feedback == 15, (
                f"5 次 user_negative（权重 3）后 negative_feedback 应为 15，实际：{updated.negative_feedback}"
            )

            # 4. 验证 check_memory_health → blocked
            # ratio = 0/15 = 0.0 ≤ 0.2，negative = 15 >= 5
            health = check_memory_health(updated)
            assert health == "blocked", (
                f"5 次 user_negative 后健康状态应为 blocked，实际：{health}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_blocked_memory_excluded_from_retrieval(self):
        """blocked 记忆不出现在检索结果中。

        数据流：add 2 memories → block mem_a → retrieve → 验证 mem_a 不在结果中
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建 2 条记忆：一条将被 blocked，一条保持 healthy
            mem_a = make_memory(
                "e2e_s4_blocked",
                content="Git rebase 强制推送操作，可能破坏公共分支历史",
                keywords=["git", "rebase", "强制推送", "历史", "破坏"],
                importance=5,
            )
            mem_b = make_memory(
                "e2e_s4_healthy",
                content="Git 分支管理最佳实践，使用 feature branch 工作流",
                keywords=["git", "分支", "feature", "工作流", "管理"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            # 2. 将 mem_a 设为 blocked：触发 2 次 user_negative
            # 2次 × 3 = 6 negative_feedback，ratio = 0/6 = 0.0 ≤ 0.2，negative = 6 >= 5
            for _ in range(2):
                infer_memory_feedback("e2e_s4_blocked", "user_negative", store)

            # 验证确实是 blocked
            blocked_mem = store.get("e2e_s4_blocked")
            assert check_memory_health(blocked_mem) == "blocked", "mem_a 应已进入 blocked 状态"

            # 3. 检索 git 相关内容
            now = datetime.now()
            results = retrieve("git 分支操作历史", store, top_k=5, now=now)
            result_ids = [mem.id for mem, _ in results]

            # 4. 验证 blocked 记忆不在结果中，healthy 记忆在结果中
            assert "e2e_s4_blocked" not in result_ids, (
                "blocked 记忆不应出现在检索结果中"
            )
            assert "e2e_s4_healthy" in result_ids, (
                "healthy 记忆应出现在检索结果中"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_escalation_pipeline(self):
        """检测模式升级：记录 5 个失败 pattern → check_escalation → block。

        数据流：创建 5 个 pattern_*.md 文件 → check_escalation("pattern") → "block"
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            # 1. 在临时目录下创建 patterns/ 目录
            patterns_dir = Path(tmp_dir) / "patterns"
            patterns_dir.mkdir(parents=True, exist_ok=True)

            # 2. 创建 5 个 pattern_*.md 文件（模拟 5 次同类失败记录）
            for i in range(5):
                pattern_file = patterns_dir / f"pattern_{i:03d}.md"
                pattern_file.write_text(
                    f"---\npattern: pattern\ncount: 1\n---\n\n第 {i+1} 次重复错误记录\n",
                    encoding='utf-8'
                )

            # 3. check_escalation 应返回 "block"（>= 5 次）
            level = check_escalation("pattern", store_path=tmp_dir)
            assert level == "block", (
                f"5 次失败模式应升级为 block，实际：{level}"
            )
        finally:
            shutil.rmtree(tmp_dir)


# ==================== S5: 恢复测试 ====================

class TestS5Recovery:
    """blocked 记忆手动恢复 → 重新参与检索；trigger reset 清除效率数据。"""

    def test_manual_recovery_restores_retrieval(self):
        """手动将 blocked 记忆的 negative_feedback 清零后，恢复检索。

        数据流：block memory → 验证被排除 → 手动更新 feedback → 验证重新出现
        """
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            # 1. 创建记忆并使其进入 blocked 状态
            mem = make_memory(
                "e2e_s5_recover_mem",
                content="机器学习模型训练技巧，使用梯度裁剪防止梯度爆炸",
                keywords=["机器学习", "模型", "训练", "梯度裁剪", "优化"],
                importance=7,
            )
            store.add(mem)

            # 触发 2 次 user_negative → 6 negative_feedback → blocked
            for _ in range(2):
                infer_memory_feedback("e2e_s5_recover_mem", "user_negative", store)

            blocked = store.get("e2e_s5_recover_mem")
            assert check_memory_health(blocked) == "blocked", "应已进入 blocked 状态"

            # 2. 验证被排除（被 blocked，不出现在检索结果中）
            now = datetime.now()
            results_before = retrieve("机器学习模型训练", store, top_k=5, now=now)
            ids_before = [m.id for m, _ in results_before]
            assert "e2e_s5_recover_mem" not in ids_before, (
                "blocked 状态下记忆应被排除出检索结果"
            )

            # 3. 手动恢复：清零 negative_feedback，设置 positive_feedback 为 1
            import dataclasses
            recovered = dataclasses.replace(
                blocked,
                negative_feedback=0,
                positive_feedback=1,
            )
            store.update(recovered)

            # 4. 验证 check_memory_health → "healthy"
            restored = store.get("e2e_s5_recover_mem")
            health = check_memory_health(restored)
            assert health == "healthy", (
                f"清零 negative_feedback 后记忆应恢复为 healthy，实际：{health}"
            )

            # 5. 验证记忆重新出现在检索结果中
            results_after = retrieve("机器学习模型训练", store, top_k=5, now=now)
            ids_after = [m.id for m, _ in results_after]
            assert "e2e_s5_recover_mem" in ids_after, (
                "恢复后记忆应重新出现在检索结果中"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_trigger_reset_clears_efficiency(self):
        """reset_stats 清除效率数据后，weight 回到默认中性值。

        数据流：记录多次失败 → adjust_weight 验证低权重 → reset_stats → get_efficiency 验证中性
        """
        tmp_dir = tempfile.mkdtemp()
        stats_path = Path(tmp_dir) / "trigger-stats.json"
        try:
            rule = "待重置的规则"

            # 1. 记录多次失败触发（使效率降低）
            for _ in range(8):
                record_trigger(rule, "failure", stats_path=stats_path)

            # 2. 验证 adjust_weight 返回低权重
            low_weight, _ = adjust_weight(rule, current_weight=1.0, stats_path=stats_path)
            assert low_weight < 1.0, (
                f"多次失败后权重应低于 1.0，实际：{low_weight}"
            )

            # 3. reset_stats 清除该规则的统计数据
            deleted = reset_stats(rule, stats_path=stats_path)
            assert deleted is True, "reset_stats 应返回 True（规则存在）"

            # 4. 验证 get_efficiency → 0.5（无记录时返回中性默认值）
            eff_after_reset = get_efficiency(rule, stats_path=stats_path)
            assert eff_after_reset == 0.5, (
                f"reset_stats 后效率应回到默认中性值 0.5，实际：{eff_after_reset}"
            )

            # 5. 再次 adjust_weight 时权重保持中性（效率在 0.4-0.8 区间，不变）
            # 注意：reset 后规则不在 stats 中，adjust_weight 不会持久化，只返回计算结果
            new_weight, suggestion = adjust_weight(rule, current_weight=1.0, stats_path=stats_path)
            assert new_weight == 1.0, (
                f"中性效率下权重应保持 1.0，实际：{new_weight}"
            )
            assert suggestion is None, f"中性效率不应有 disable 建议，实际：{suggestion}"
        finally:
            shutil.rmtree(tmp_dir)
