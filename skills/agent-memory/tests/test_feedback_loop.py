"""Phase 3 反馈学习循环测试：feedback_loop.py TDD 测试套件。

覆盖：
- 记忆层反馈（infer_memory_feedback / get_feedback_ratio / check_memory_health）
- 决策链层反馈（score_workflow_run / get_path_efficiency）
- 渐进式学习（check_escalation / apply_escalation）
- 检索集成（filter_by_health）
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore


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
    )
    defaults.update(kwargs)
    return Memory(**defaults)


# ==================== 记忆层反馈 ====================

class TestInferMemoryFeedback:
    """测试 infer_memory_feedback：根据事件推断并更新记忆反馈。"""

    def test_infer_memory_feedback_task_success(self):
        """task_success 事件 → positive_feedback += 1。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_ts_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_ts_001", "task_success", store)

            updated = store.get("mem_ts_001")
            assert updated.positive_feedback == 1, (
                f"task_success 应 +1 positive，实际：{updated.positive_feedback}"
            )
            assert updated.negative_feedback == 0
            assert result["event"] == "task_success"
            assert result["delta_positive"] == 1
            assert result["delta_negative"] == 0
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_memory_feedback_task_retry(self):
        """task_retry 事件 → negative_feedback += 1。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_tr_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_tr_001", "task_retry", store)

            updated = store.get("mem_tr_001")
            assert updated.negative_feedback == 1, (
                f"task_retry 应 +1 negative，实际：{updated.negative_feedback}"
            )
            assert updated.positive_feedback == 0
            assert result["delta_negative"] == 1
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_memory_feedback_audit_pass(self):
        """audit_pass 事件 → positive_feedback += 2。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_ap_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_ap_001", "audit_pass", store)

            updated = store.get("mem_ap_001")
            assert updated.positive_feedback == 2, (
                f"audit_pass 应 +2 positive，实际：{updated.positive_feedback}"
            )
            assert result["delta_positive"] == 2
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_memory_feedback_audit_fail(self):
        """audit_fail 事件 → negative_feedback += 2。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_af_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_af_001", "audit_fail", store)

            updated = store.get("mem_af_001")
            assert updated.negative_feedback == 2, (
                f"audit_fail 应 +2 negative，实际：{updated.negative_feedback}"
            )
            assert result["delta_negative"] == 2
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_memory_feedback_user_positive(self):
        """user_positive 事件 → positive_feedback += 3。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_up_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_up_001", "user_positive", store)

            updated = store.get("mem_up_001")
            assert updated.positive_feedback == 3, (
                f"user_positive 应 +3 positive，实际：{updated.positive_feedback}"
            )
            assert result["delta_positive"] == 3
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_memory_feedback_user_negative(self):
        """user_negative 事件 → negative_feedback += 3。"""
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_un_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            result = infer_memory_feedback("mem_un_001", "user_negative", store)

            updated = store.get("mem_un_001")
            assert updated.negative_feedback == 3, (
                f"user_negative 应 +3 negative，实际：{updated.negative_feedback}"
            )
            assert result["delta_negative"] == 3
        finally:
            shutil.rmtree(tmp_dir)


class TestGetFeedbackRatio:
    """测试 get_feedback_ratio：计算反馈比率。"""

    def test_get_feedback_ratio_no_feedback(self):
        """无反馈时返回 0.5（中性）。"""
        from feedback_loop import get_feedback_ratio

        mem = make_memory(positive_feedback=0, negative_feedback=0)
        ratio = get_feedback_ratio(mem)
        assert ratio == 0.5, f"无反馈应返回 0.5，实际：{ratio}"

    def test_get_feedback_ratio_mixed(self):
        """混合反馈：3 positive + 1 negative → 0.75。"""
        from feedback_loop import get_feedback_ratio

        mem = make_memory(positive_feedback=3, negative_feedback=1)
        ratio = get_feedback_ratio(mem)
        assert abs(ratio - 0.75) < 1e-9, f"3正1负应为 0.75，实际：{ratio}"

    def test_get_feedback_ratio_all_positive(self):
        """全正反馈 → 1.0。"""
        from feedback_loop import get_feedback_ratio

        mem = make_memory(positive_feedback=5, negative_feedback=0)
        ratio = get_feedback_ratio(mem)
        assert ratio == 1.0, f"全正反馈应为 1.0，实际：{ratio}"

    def test_get_feedback_ratio_all_negative(self):
        """全负反馈 → 0.0。"""
        from feedback_loop import get_feedback_ratio

        mem = make_memory(positive_feedback=0, negative_feedback=5)
        ratio = get_feedback_ratio(mem)
        assert ratio == 0.0, f"全负反馈应为 0.0，实际：{ratio}"


class TestCheckMemoryHealth:
    """测试 check_memory_health：判断记忆健康状态。"""

    def test_check_memory_health_healthy(self):
        """总反馈 < 3 → healthy（不管比率）。"""
        from feedback_loop import check_memory_health

        mem = make_memory(positive_feedback=0, negative_feedback=2)
        health = check_memory_health(mem)
        assert health == "healthy", f"总反馈<3 应为 healthy，实际：{health}"

    def test_check_memory_health_warning(self):
        """ratio <= 0.4 且 negative >= 3 → warning。"""
        from feedback_loop import check_memory_health

        # ratio = 1/4 = 0.25, negative=3
        mem = make_memory(positive_feedback=1, negative_feedback=3)
        health = check_memory_health(mem)
        assert health == "warning", f"低比率+3负反馈 应为 warning，实际：{health}"

    def test_check_memory_health_blocked(self):
        """ratio <= 0.2 且 negative >= 5 → blocked。"""
        from feedback_loop import check_memory_health

        # ratio = 1/6 ≈ 0.17, negative=5
        mem = make_memory(positive_feedback=1, negative_feedback=5)
        health = check_memory_health(mem)
        assert health == "blocked", f"极低比率+5负反馈 应为 blocked，实际：{health}"

    def test_check_memory_health_high_ratio_with_many_negatives(self):
        """ratio > 0.4 → healthy，即使有一些负反馈。"""
        from feedback_loop import check_memory_health

        # ratio = 7/10 = 0.7, negative=3
        mem = make_memory(positive_feedback=7, negative_feedback=3)
        health = check_memory_health(mem)
        assert health == "healthy", f"高比率应为 healthy，实际：{health}"


# ==================== 决策链层反馈 ====================

class TestScoreWorkflowRun:
    """测试 score_workflow_run：评分决策链执行记录。"""

    def _create_run_file(self, tmp_dir: str, filename: str, content: str) -> str:
        """辅助：创建 workflow run MD 文件。"""
        path = os.path.join(tmp_dir, filename)
        Path(path).write_text(content, encoding='utf-8')
        return path

    def test_score_workflow_run_no_retry(self):
        """no_retry 事件 → score +2。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\n---\n\n执行记录内容\n"
            run_path = self._create_run_file(tmp_dir, "run_001.md", run_md)

            result = score_workflow_run(run_path, "no_retry")

            assert result["score"] == 2, f"no_retry 应得分 2，实际：{result['score']}"
            assert result["event"] == "no_retry"

            # 验证写回文件
            import yaml
            content = Path(run_path).read_text(encoding='utf-8')
            parts = content.split("\n---\n", 1)
            fm = yaml.safe_load(parts[0][4:])
            assert fm.get("score") == 2, f"文件中 score 应为 2，实际：{fm.get('score')}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_score_workflow_run_degraded(self):
        """degraded 事件 → score -1。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\n---\n\n执行记录内容\n"
            run_path = self._create_run_file(tmp_dir, "run_002.md", run_md)

            result = score_workflow_run(run_path, "degraded")

            assert result["score"] == -1, f"degraded 应得分 -1，实际：{result['score']}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_score_workflow_run_user_override(self):
        """score_override 不为 None → 使用用户指定分数。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\nscore: 1\n---\n\n内容\n"
            run_path = self._create_run_file(tmp_dir, "run_003.md", run_md)

            result = score_workflow_run(run_path, "no_retry", score_override=5)

            assert result["score"] == 5, f"用户覆盖应为 5，实际：{result['score']}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_score_workflow_run_accumulates_existing_score(self):
        """已有 score 时，新事件应累加（不是覆盖）。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\nscore: 1\n---\n\n内容\n"
            run_path = self._create_run_file(tmp_dir, "run_004.md", run_md)

            # 已有 score=1，再加 no_retry (+2) → 3
            result = score_workflow_run(run_path, "no_retry")

            assert result["score"] == 3, f"累加后应为 3，实际：{result['score']}"
        finally:
            shutil.rmtree(tmp_dir)


class TestGetPathEfficiency:
    """测试 get_path_efficiency：统计 workflow 历史效率。"""

    def _create_run_with_score(self, store_path: str, name: str, workflow: str, score: int):
        """辅助：创建带 score 的 run 文件。"""
        content = f"---\nworkflow: {workflow}\nscore: {score}\n---\n\n内容\n"
        Path(store_path, name).write_text(content, encoding='utf-8')

    def test_get_path_efficiency(self):
        """统计历史效率：平均分、总次数、成功率。"""
        from feedback_loop import get_path_efficiency

        tmp_dir = tempfile.mkdtemp()
        try:
            # 创建 3 条同 workflow 的 run
            self._create_run_with_score(tmp_dir, "run_a.md", "explore_implement", 2)
            self._create_run_with_score(tmp_dir, "run_b.md", "explore_implement", 0)
            self._create_run_with_score(tmp_dir, "run_c.md", "explore_implement", -1)
            # 不同 workflow，不应被统计
            self._create_run_with_score(tmp_dir, "run_d.md", "other_workflow", 5)

            result = get_path_efficiency("explore_implement", store_path=tmp_dir)

            assert result["total_runs"] == 3, f"应有 3 次 run，实际：{result['total_runs']}"
            expected_avg = (2 + 0 + (-1)) / 3
            assert abs(result["avg_score"] - expected_avg) < 1e-9, (
                f"平均分应为 {expected_avg:.3f}，实际：{result['avg_score']:.3f}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_get_path_efficiency_no_runs(self):
        """无历史记录 → total_runs=0, avg_score=0.0。"""
        from feedback_loop import get_path_efficiency

        tmp_dir = tempfile.mkdtemp()
        try:
            result = get_path_efficiency("nonexistent_workflow", store_path=tmp_dir)
            assert result["total_runs"] == 0
            assert result["avg_score"] == 0.0
        finally:
            shutil.rmtree(tmp_dir)


# ==================== 渐进式学习 ====================

class TestCheckEscalation:
    """测试 check_escalation：检查失败模式是否需要升级。"""

    def _create_pattern_files(self, patterns_dir: str, pattern: str, count: int):
        """辅助：创建 count 个同名模式文件。"""
        Path(patterns_dir).mkdir(parents=True, exist_ok=True)
        for i in range(count):
            Path(patterns_dir, f"{pattern}_{i:03d}.md").write_text(
                f"---\npattern: {pattern}\ncount: 1\n---\n\n记录 {i}\n",
                encoding='utf-8'
            )

    def test_check_escalation_none(self):
        """无模式文件 → 'none'。"""
        from feedback_loop import check_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            patterns_dir = os.path.join(tmp_dir, "patterns")
            result = check_escalation("skip_exploration", store_path=tmp_dir)
            assert result == "none", f"无记录应为 none，实际：{result}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_check_escalation_downweight(self):
        """1-2 次负反馈 → 'downweight'。"""
        from feedback_loop import check_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            patterns_dir = os.path.join(tmp_dir, "patterns")
            self._create_pattern_files(patterns_dir, "skip_exploration", 2)

            result = check_escalation("skip_exploration", store_path=tmp_dir)
            assert result == "downweight", f"2次应为 downweight，实际：{result}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_check_escalation_warning(self):
        """3-4 次负反馈 → 'warning'。"""
        from feedback_loop import check_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            patterns_dir = os.path.join(tmp_dir, "patterns")
            self._create_pattern_files(patterns_dir, "skip_exploration", 3)

            result = check_escalation("skip_exploration", store_path=tmp_dir)
            assert result == "warning", f"3次应为 warning，实际：{result}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_check_escalation_block(self):
        """>= 5 次负反馈 → 'block'。"""
        from feedback_loop import check_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            patterns_dir = os.path.join(tmp_dir, "patterns")
            self._create_pattern_files(patterns_dir, "skip_exploration", 5)

            result = check_escalation("skip_exploration", store_path=tmp_dir)
            assert result == "block", f"5次应为 block，实际：{result}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_check_escalation_4_times_warning(self):
        """4 次 → 'warning'（边界测试）。"""
        from feedback_loop import check_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            patterns_dir = os.path.join(tmp_dir, "patterns")
            self._create_pattern_files(patterns_dir, "bad_pattern", 4)

            result = check_escalation("bad_pattern", store_path=tmp_dir)
            assert result == "warning", f"4次应为 warning，实际：{result}"
        finally:
            shutil.rmtree(tmp_dir)


class TestApplyEscalation:
    """测试 apply_escalation：执行升级动作。"""

    def test_apply_escalation_block_writes_file(self):
        """block 级别 → 写入 blocked-paths.md。"""
        from feedback_loop import apply_escalation

        tmp_dir = tempfile.mkdtemp()
        blocked_file = os.path.join(tmp_dir, "blocked-paths.md")
        try:
            result = apply_escalation(
                "skip_exploration_before_implement",
                "block",
                "path:直接实现前不做探索",
                blocked_paths_file=blocked_file
            )

            assert result["level"] == "block"
            assert Path(blocked_file).exists(), "blocked-paths.md 应已创建"
            content = Path(blocked_file).read_text(encoding='utf-8')
            assert "skip_exploration_before_implement" in content, (
                "blocked-paths.md 应包含 pattern 名"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_apply_escalation_warning_writes_file(self):
        """warning 级别 → 写入 warnings/{pattern}.md。"""
        from feedback_loop import apply_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            result = apply_escalation(
                "audit_skip",
                "warning",
                "workflow:explore_implement",
                warnings_dir=os.path.join(tmp_dir, "warnings")
            )

            assert result["level"] == "warning"
            warning_file = Path(tmp_dir, "warnings", "audit_skip.md")
            assert warning_file.exists(), f"告警文件应已创建：{warning_file}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_apply_escalation_downweight(self):
        """downweight 级别 → 降低记忆 importance 30%。"""
        from feedback_loop import apply_escalation

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="downweight_mem_001", importance=10)
            store.add(mem)

            result = apply_escalation(
                "bad_pattern",
                "downweight",
                f"memory:downweight_mem_001",
                store=store
            )

            assert result["level"] == "downweight"
            updated = store.get("downweight_mem_001")
            # importance 降低 30%：10 * 0.7 = 7
            assert updated.importance == 7, (
                f"importance 应降至 7，实际：{updated.importance}"
            )
        finally:
            shutil.rmtree(tmp_dir)

    def test_apply_escalation_block_appends_to_existing(self):
        """blocked-paths.md 已存在时，追加而非覆盖。"""
        from feedback_loop import apply_escalation

        tmp_dir = tempfile.mkdtemp()
        blocked_file = os.path.join(tmp_dir, "blocked-paths.md")
        try:
            # 预先写入一些内容
            Path(blocked_file).write_text(
                "# 已阻断路径\n\n- existing_pattern\n", encoding='utf-8'
            )

            apply_escalation(
                "new_bad_pattern",
                "block",
                "path:新问题路径",
                blocked_paths_file=blocked_file
            )

            content = Path(blocked_file).read_text(encoding='utf-8')
            assert "existing_pattern" in content, "原有内容应被保留"
            assert "new_bad_pattern" in content, "新 pattern 应被追加"
        finally:
            shutil.rmtree(tmp_dir)


# ==================== 检索集成 ====================

class TestFilterByHealth:
    """测试 filter_by_health：检索时过滤 blocked 记忆。"""

    def test_filter_by_health_removes_blocked(self):
        """blocked 记忆被排除。"""
        from feedback_loop import filter_by_health

        memories = [
            make_memory(id="healthy_001", positive_feedback=5, negative_feedback=1),
            # blocked: ratio=0/5=0.0 <= 0.2, negative=5
            make_memory(id="blocked_001", positive_feedback=0, negative_feedback=5),
            make_memory(id="healthy_002", positive_feedback=3, negative_feedback=1),
        ]

        result = filter_by_health(memories, include_warning=True)

        result_ids = [m.id for m in result]
        assert "blocked_001" not in result_ids, "blocked 记忆应被排除"
        assert "healthy_001" in result_ids, "healthy 记忆应被保留"
        assert "healthy_002" in result_ids, "healthy 记忆应被保留"

    def test_filter_by_health_keeps_warning(self):
        """warning 记忆在 include_warning=True 时保留。"""
        from feedback_loop import filter_by_health

        memories = [
            make_memory(id="healthy_001", positive_feedback=5, negative_feedback=1),
            # warning: ratio=1/4=0.25 <= 0.4, negative=3
            make_memory(id="warning_001", positive_feedback=1, negative_feedback=3),
        ]

        result = filter_by_health(memories, include_warning=True)

        result_ids = [m.id for m in result]
        assert "warning_001" in result_ids, "warning 记忆在 include_warning=True 时应保留"

    def test_filter_by_health_excludes_warning_when_flag_false(self):
        """warning 记忆在 include_warning=False 时被排除。"""
        from feedback_loop import filter_by_health

        memories = [
            make_memory(id="healthy_001", positive_feedback=5, negative_feedback=1),
            make_memory(id="warning_001", positive_feedback=1, negative_feedback=3),
        ]

        result = filter_by_health(memories, include_warning=False)

        result_ids = [m.id for m in result]
        assert "warning_001" not in result_ids, "warning 记忆在 include_warning=False 时应被排除"
        assert "healthy_001" in result_ids, "healthy 记忆应被保留"

    def test_filter_by_health_empty_list(self):
        """空列表 → 返回空列表。"""
        from feedback_loop import filter_by_health

        result = filter_by_health([], include_warning=True)
        assert result == [], "空输入应返回空列表"

    def test_filter_by_health_all_healthy(self):
        """全部 healthy → 全部返回。"""
        from feedback_loop import filter_by_health

        memories = [
            make_memory(id=f"mem_{i}", positive_feedback=5, negative_feedback=0)
            for i in range(5)
        ]

        result = filter_by_health(memories, include_warning=True)
        assert len(result) == 5, f"5条 healthy 记忆应全部返回，实际：{len(result)}"


# ==================== CLI 集成测试 ====================

class TestCLIHealthCheck:
    """测试 CLI health-check 子命令。"""

    def test_cli_health_check_subcommand(self):
        """health-check 子命令应输出正确格式（healthy/warning/blocked 统计行）。"""
        import subprocess

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem1 = make_memory(id="mem_hc_001", positive_feedback=5, negative_feedback=0)
            store.add(mem1)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [sys.executable, cli_path, "--store", tmp_dir, "health-check"],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"health-check 应成功退出，stderr: {result.stderr}"
            assert "healthy" in output.lower(), f"输出应包含 healthy 统计，实际输出：{output}"
            assert "总计" in output, f"输出应包含总计行，实际输出：{output}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_cli_health_check_shows_blocked(self):
        """health-check 应标记并显示 blocked 记忆。"""
        import subprocess

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            blocked_mem = make_memory(
                id="mem_blocked_cli_001",
                positive_feedback=0,
                negative_feedback=5,
            )
            store.add(blocked_mem)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [sys.executable, cli_path, "--store", tmp_dir, "health-check"],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"health-check 应成功退出，stderr: {result.stderr}"
            assert "BLOCKED" in output.upper(), (
                f"blocked 记忆应被标记为 BLOCKED，实际输出：{output}"
            )
            assert "mem_blocked_cli_001" in output, (
                f"输出应包含 blocked 记忆 ID，实际输出：{output}"
            )
        finally:
            shutil.rmtree(tmp_dir)


class TestCLIFeedbackAutoInfer:
    """测试 CLI feedback --auto --event 自动推断模式。"""

    def test_cli_feedback_auto_infer(self):
        """feedback --auto --event task_success --memory-id X 应正确调用 infer_memory_feedback。"""
        import subprocess

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(
                id="mem_autofeedback_001",
                positive_feedback=0,
                negative_feedback=0,
            )
            store.add(mem)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [
                    sys.executable, cli_path,
                    "--store", tmp_dir,
                    "feedback",
                    "--memory-id", "mem_autofeedback_001",
                    "--auto",
                    "--event", "task_success",
                ],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"feedback --auto 应成功退出，stderr: {result.stderr}"

            # 验证记忆实际被更新（task_success → +1 positive）
            updated = store.get("mem_autofeedback_001")
            assert updated.positive_feedback == 1, (
                f"task_success 应 positive_feedback +1，实际：{updated.positive_feedback}\n输出：{output}"
            )
        finally:
            shutil.rmtree(tmp_dir)


# ==================== 边界测试（补充覆盖） ====================

class TestEdgeCases:
    """补充边界测试：未知事件、不存在记忆、score_override=0、with_retry delta。"""

    def test_infer_unknown_event(self):
        """传入未知事件名 → 抛出 ValueError。"""
        import pytest
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_edge_001")
            store.add(mem)

            with pytest.raises(ValueError, match="未知事件类型"):
                infer_memory_feedback("mem_edge_001", "invalid_event", store)
        finally:
            shutil.rmtree(tmp_dir)

    def test_infer_nonexistent_memory(self):
        """传入不存在的 memory_id → 抛出 KeyError。"""
        import pytest
        from feedback_loop import infer_memory_feedback

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            with pytest.raises(KeyError):
                infer_memory_feedback("nonexistent_id_xyz", "task_success", store)
        finally:
            shutil.rmtree(tmp_dir)

    def test_score_workflow_override_zero(self):
        """score_override=0 时返回结果不为 None，score 应为 0。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\nscore: 5\n---\n\n内容\n"
            run_path = os.path.join(tmp_dir, "run_override_zero.md")
            Path(run_path).write_text(run_md, encoding='utf-8')

            result = score_workflow_run(run_path, "no_retry", score_override=0)

            assert result is not None, "score_override=0 时结果不应为 None"
            assert result["score"] == 0, f"score_override=0 时 score 应为 0，实际：{result['score']}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_feedback_ratio_with_retry_event(self):
        """with_retry 事件 delta=0：score 不变（delta 为 0）。"""
        from feedback_loop import score_workflow_run

        tmp_dir = tempfile.mkdtemp()
        try:
            run_md = "---\nworkflow: test_wf\nscore: 3\n---\n\n内容\n"
            run_path = os.path.join(tmp_dir, "run_with_retry.md")
            Path(run_path).write_text(run_md, encoding='utf-8')

            result = score_workflow_run(run_path, "with_retry")

            # with_retry delta=0，分数不变
            assert result["score"] == 3, f"with_retry delta=0，score 应不变（3），实际：{result['score']}"
            assert result["previous_score"] == 3
        finally:
            shutil.rmtree(tmp_dir)


# ==================== CLI dashboard 测试 ====================

class TestCLIDashboard:
    """测试 dashboard 子命令。"""

    def test_dashboard_basic_output(self):
        """dashboard 输出包含四个核心区域：记忆健康、触发效率、反馈统计、系统概要。"""
        import subprocess
        import json

        tmp_dir = tempfile.mkdtemp()
        trigger_stats_file = os.path.join(tmp_dir, "trigger-stats.json")
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="mem_dash_001", positive_feedback=3, negative_feedback=1, importance=7)
            store.add(mem)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [
                    sys.executable, cli_path,
                    "--store", tmp_dir,
                    "dashboard",
                    "--trigger-stats", trigger_stats_file,
                ],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"dashboard 应成功退出，stderr: {result.stderr}"
            assert "记忆健康" in output, f"输出应包含记忆健康区域，实际：{output}"
            assert "反馈统计" in output, f"输出应包含反馈统计区域，实际：{output}"
            assert "系统概要" in output, f"输出应包含系统概要区域，实际：{output}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_dashboard_with_mixed_health(self):
        """dashboard 正确显示混合健康状态的计数。"""
        import subprocess
        import json

        tmp_dir = tempfile.mkdtemp()
        trigger_stats_file = os.path.join(tmp_dir, "trigger-stats.json")
        try:
            store = MemoryStore(store_path=tmp_dir)
            # healthy: pos=5, neg=0
            store.add(make_memory(id="mem_healthy_001", positive_feedback=5, negative_feedback=0))
            # warning: pos=1, neg=3
            store.add(make_memory(id="mem_warning_001", positive_feedback=1, negative_feedback=3))
            # blocked: pos=0, neg=5
            store.add(make_memory(id="mem_blocked_001", positive_feedback=0, negative_feedback=5))

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [
                    sys.executable, cli_path,
                    "--store", tmp_dir,
                    "dashboard",
                    "--trigger-stats", trigger_stats_file,
                ],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"dashboard 应成功退出，stderr: {result.stderr}"
            assert "Healthy: 1" in output, f"应显示 Healthy: 1，实际：{output}"
            assert "Warning: 1" in output, f"应显示 Warning: 1，实际：{output}"
            assert "Blocked: 1" in output, f"应显示 Blocked: 1，实际：{output}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_dashboard_with_trigger_stats(self):
        """dashboard 显示触发规则效率排名。"""
        import subprocess
        import json

        tmp_dir = tempfile.mkdtemp()
        trigger_stats_file = os.path.join(tmp_dir, "trigger-stats.json")
        try:
            store = MemoryStore(store_path=tmp_dir)
            store.add(make_memory(id="mem_trigger_001"))

            # 预写 trigger stats 文件
            stats_data = {
                "rules": {
                    "memory_flush": {
                        "success": 8,
                        "failure": 2,
                        "skip": 0,
                        "weight": 1.2,
                        "last_triggered": "2026-03-14T10:00:00",
                    }
                },
                "updated_at": "2026-03-14T10:00:00",
            }
            Path(trigger_stats_file).write_text(
                json.dumps(stats_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [
                    sys.executable, cli_path,
                    "--store", tmp_dir,
                    "dashboard",
                    "--trigger-stats", trigger_stats_file,
                ],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"dashboard 应成功退出，stderr: {result.stderr}"
            assert "触发效率" in output, f"输出应包含触发效率区域，实际：{output}"
            assert "memory_flush" in output, f"规则名应出现在输出中，实际：{output}"
            assert "80%" in output, f"应显示 80% 效率，实际：{output}"
        finally:
            shutil.rmtree(tmp_dir)

    def test_dashboard_empty_store(self):
        """空 store 时 dashboard 不崩溃，正常输出。"""
        import subprocess

        tmp_dir = tempfile.mkdtemp()
        trigger_stats_file = os.path.join(tmp_dir, "trigger-stats.json")
        try:
            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                [
                    sys.executable, cli_path,
                    "--store", tmp_dir,
                    "dashboard",
                    "--trigger-stats", trigger_stats_file,
                ],
                capture_output=True, text=True
            )
            output = result.stdout + result.stderr

            assert result.returncode == 0, f"空 store 时 dashboard 应成功退出，stderr: {result.stderr}"
            assert "Dashboard" in output, f"输出应包含 Dashboard 标题，实际：{output}"
            assert "0 条" in output, f"应显示 0 条记忆，实际：{output}"
        finally:
            shutil.rmtree(tmp_dir)
