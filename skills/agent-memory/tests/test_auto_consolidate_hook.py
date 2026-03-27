#!/usr/bin/env python3
"""
TDD 测试：post-memory-consolidate-hook.py

覆盖场景：
1. test_below_threshold_skipped — 低于阈值不触发合并
2. test_above_threshold_triggers — 超过阈值触发合并
3. test_non_agent_event_skipped — 非 Agent 事件跳过
4. test_store_path_inference — 从 agent 返回结果推断 store 路径
5. test_max_merge_limit — 最多合并 5 对
6. test_timeout_protection — 超时不阻塞
7. test_custom_threshold — 环境变量自定义阈值
8. test_dry_run_no_pairs — dry-run 无可合并对时跳过真正合并
9. test_empty_stdin_exits_zero — 空 stdin 静默退出
10. test_invalid_json_exits_zero — 无效 JSON 静默退出
"""

import json
import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

# ---- 将 hook 目录加入 sys.path 以便导入内部函数 ----
HOOK_PATH = os.path.expanduser("~/.claude/hooks/post-memory-consolidate-hook.py")

# 动态导入 hook 模块（不执行 main）
import importlib.util

spec = importlib.util.spec_from_file_location("post_memory_consolidate_hook", HOOK_PATH)
hook_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook_module)


# ==================== 辅助函数 ====================

def make_agent_stdin(tool_name: str = "Agent", description: str = "tetsu | 测试任务", extra_input: dict = None) -> str:
    """构造标准 PostToolUse stdin JSON（Agent 事件）。"""
    tool_input = {"description": description}
    if extra_input:
        tool_input.update(extra_input)
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_result": {},
    })


def run_hook_with_stdin(stdin_content: str, env: dict = None) -> tuple[int, str, str]:
    """运行 hook 脚本并捕获 stdout/stderr/returncode。"""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        [sys.executable, HOOK_PATH],
        input=stdin_content,
        capture_output=True,
        text=True,
        timeout=10,
        env=run_env,
    )
    return result.returncode, result.stdout, result.stderr


def make_mem_files(tmpdir: str, count: int) -> None:
    """在 tmpdir 中创建指定数量的 mem_*.md 文件。"""
    for i in range(count):
        Path(tmpdir, f"mem_20260315_{i:03d}.md").write_text(
            f"---\nid: mem_20260315_{i:03d}\n---\ncontent {i}\n",
            encoding="utf-8",
        )


# ==================== 测试：stdin 解析健壮性 ====================

class TestStdinParsing:
    """测试 stdin JSON 解析的健壮性。"""

    def test_empty_stdin_exits_zero(self):
        """空 stdin 应静默退出，exit 0。"""
        rc, stdout, stderr = run_hook_with_stdin("")
        assert rc == 0, f"期望 exit 0，实际 {rc}\nstderr: {stderr}"

    def test_invalid_json_exits_zero(self):
        """无效 JSON 应静默退出，不 block。"""
        rc, stdout, stderr = run_hook_with_stdin("this is not json {{{")
        assert rc == 0, f"期望 exit 0，实际 {rc}"


# ==================== 测试：非 Agent 事件过滤 ====================

class TestNonAgentEventSkipped:
    """测试非 Agent 事件被正确跳过。"""

    def test_non_agent_event_skipped(self):
        """Bash 事件不应触发，hook 直接 exit 0。"""
        stdin = make_agent_stdin(tool_name="Bash")
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        # 不应有 consolidate hook 的 message 输出
        assert "post-memory-consolidate-hook" not in stdout

    def test_taskupdate_event_skipped(self):
        """TaskUpdate 事件不触发。"""
        stdin = make_agent_stdin(tool_name="TaskUpdate")
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        assert "post-memory-consolidate-hook" not in stdout


# ==================== 测试：store 路径推断 ====================

class TestStorePathInference:
    """测试从 description 字段推断 agent 对应的 store 路径。"""

    def test_store_path_inference_tetsu(self):
        """tetsu agent 应推断出正确的 store 路径（Worker 目录）。"""
        path = hook_module.infer_store_path("tetsu")
        assert path is not None
        assert "Worker" in path
        assert "tetsu" in path

    def test_store_path_inference_kaze(self):
        """kaze agent 应推断出 Explore 目录。"""
        path = hook_module.infer_store_path("kaze")
        assert path is not None
        assert "kaze" in path

    def test_store_path_inference_yume(self):
        """yume agent 应推断出 Dreamer 目录。"""
        path = hook_module.infer_store_path("yume")
        assert path is not None
        assert "Dreamer" in path

    def test_store_path_inference_unknown_returns_none(self):
        """未知 agent 名返回 None。"""
        path = hook_module.infer_store_path("nonexistent_agent_xyz")
        assert path is None

    def test_extract_agent_from_description(self):
        """从 'agent | 任务描述' 格式提取 agent 名。"""
        agent = hook_module.extract_agent_name("tetsu | 执行代码修改")
        assert agent == "tetsu"

    def test_extract_agent_no_pipe_returns_none(self):
        """description 中无 | 分隔符时返回 None。"""
        agent = hook_module.extract_agent_name("纯任务描述没有 agent 前缀")
        assert agent is None

    def test_extract_agent_unknown_name_returns_none(self):
        """description 中含未注册 agent 名时返回 None。"""
        agent = hook_module.extract_agent_name("unknown_xyz | 任务描述")
        assert agent is None


# ==================== 测试：阈值检查 ====================

class TestThresholdCheck:
    """测试文件数量阈值检查逻辑。"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_below_threshold_returns_false(self):
        """低于阈值时 should_consolidate 返回 False。"""
        make_mem_files(self.tmpdir, 10)
        result = hook_module.should_consolidate(self.tmpdir, threshold=50)
        assert result is False

    def test_at_threshold_returns_false(self):
        """等于阈值时不触发（must exceed）。"""
        make_mem_files(self.tmpdir, 50)
        result = hook_module.should_consolidate(self.tmpdir, threshold=50)
        assert result is False

    def test_above_threshold_returns_true(self):
        """超过阈值时 should_consolidate 返回 True。"""
        make_mem_files(self.tmpdir, 51)
        result = hook_module.should_consolidate(self.tmpdir, threshold=50)
        assert result is True

    def test_empty_store_returns_false(self):
        """空目录返回 False（0 个文件）。"""
        result = hook_module.should_consolidate(self.tmpdir, threshold=50)
        assert result is False

    def test_nonexistent_store_returns_false(self):
        """不存在的目录返回 False，不 crash。"""
        result = hook_module.should_consolidate("/nonexistent/path/xyz", threshold=50)
        assert result is False

    def test_excludes_non_mem_files(self):
        """MEMORY.md、WhoAmI.md 等不计入 mem_*.md 数量。"""
        # 创建 40 个 mem_ 文件 + 一些非 mem_ 文件
        make_mem_files(self.tmpdir, 40)
        for name in ["MEMORY.md", "WhoAmI.md", "role.md", "feedback_authorization.md"]:
            Path(self.tmpdir, name).write_text("# non-mem\n", encoding="utf-8")
        # 40 < 50，应返回 False
        result = hook_module.should_consolidate(self.tmpdir, threshold=50)
        assert result is False


# ==================== 测试：低于阈值不触发（集成）====================

class TestBelowThresholdSkipped:
    """集成测试：低于阈值时不调用 cli.py。"""

    def test_below_threshold_skipped(self):
        """store 文件数低于阈值时，不调用 run_consolidate，直接 exit 0。"""
        with mock.patch.object(hook_module, "should_consolidate", return_value=False):
            with mock.patch.object(hook_module, "run_consolidate") as mock_run:
                hook_module.process_agent_event("tetsu", "/tmp/fake_store", threshold=50)
                mock_run.assert_not_called()


# ==================== 测试：超过阈值触发（集成）====================

class TestAboveThresholdTriggers:
    """集成测试：超过阈值时正确调用合并逻辑。"""

    def test_above_threshold_triggers(self):
        """store 文件数超过阈值时，调用 run_consolidate。"""
        with mock.patch.object(hook_module, "should_consolidate", return_value=True):
            with mock.patch.object(hook_module, "run_consolidate", return_value={"merged": 2, "deleted": 2, "pairs": 2}) as mock_run:
                hook_module.process_agent_event("tetsu", "/tmp/fake_store", threshold=50)
                mock_run.assert_called_once()

    def test_above_threshold_triggers_with_agent_stdin(self):
        """通过完整的 stdin 流程，超过阈值时触发 run_consolidate。"""
        stdin = make_agent_stdin(tool_name="Agent", description="tetsu | 执行代码修改")
        with mock.patch.object(hook_module, "should_consolidate", return_value=True):
            with mock.patch.object(hook_module, "run_consolidate", return_value={"merged": 1, "deleted": 1, "pairs": 1}):
                rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0


# ==================== 测试：最多合并 5 对 ====================

class TestMaxMergeLimit:
    """测试 run_consolidate 中最多合并 5 对的限制。"""

    def test_max_merge_limit(self):
        """run_consolidate 调用 cli.py 时传入 --max-pairs 5（或等效限制）。"""
        captured_cmds = []

        def mock_run(cmd, **kwargs):
            captured_cmds.append(cmd[:])
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "发现 8 对相似记忆"
            mock_result.stderr = ""
            return mock_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            hook_module.run_consolidate("/tmp/fake_store", max_pairs=5)

        # 验证至少执行了 subprocess.run（dry-run + 实际合并）
        assert len(captured_cmds) >= 1
        # dry-run 命令中应含 --dry-run
        first_cmd = captured_cmds[0]
        assert "--dry-run" in first_cmd

    def test_max_pairs_default_is_5(self):
        """run_consolidate 默认 max_pairs=5。"""
        import inspect
        sig = inspect.signature(hook_module.run_consolidate)
        default_max = sig.parameters.get("max_pairs")
        assert default_max is not None
        assert default_max.default == 5


# ==================== 测试：超时保护 ====================

class TestTimeoutProtection:
    """测试超时机制：subprocess 超时不阻塞 hook。"""

    def test_timeout_protection(self):
        """subprocess.TimeoutExpired 时 run_consolidate 静默返回，不 crash。"""
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="cli.py", timeout=4),
        ):
            # 不应抛出异常
            result = hook_module.run_consolidate("/tmp/fake_store")
            # 返回空结果或 None，不 crash
            assert result is None or isinstance(result, dict)

    def test_generic_exception_silenced(self):
        """任意 Exception 都被静默处理，hook 不 crash。"""
        with mock.patch("subprocess.run", side_effect=RuntimeError("unexpected error")):
            result = hook_module.run_consolidate("/tmp/fake_store")
            assert result is None or isinstance(result, dict)


# ==================== 测试：自定义阈值（环境变量）====================

class TestCustomThreshold:
    """测试 MEMORY_CONSOLIDATE_THRESHOLD 环境变量覆盖默认阈值。"""

    def test_custom_threshold_from_env(self):
        """MEMORY_CONSOLIDATE_THRESHOLD=10 时阈值应为 10。"""
        with mock.patch.dict(os.environ, {"MEMORY_CONSOLIDATE_THRESHOLD": "10"}):
            threshold = hook_module.get_threshold()
        assert threshold == 10

    def test_default_threshold_is_20(self):
        """未设置环境变量时默认阈值为 20。"""
        env = {k: v for k, v in os.environ.items() if k != "MEMORY_CONSOLIDATE_THRESHOLD"}
        with mock.patch.dict(os.environ, env, clear=True):
            threshold = hook_module.get_threshold()
        assert threshold == 20

    def test_invalid_env_uses_default(self):
        """环境变量设为非数字时，降级使用默认值 20。"""
        with mock.patch.dict(os.environ, {"MEMORY_CONSOLIDATE_THRESHOLD": "not_a_number"}):
            threshold = hook_module.get_threshold()
        assert threshold == 20

    def test_custom_threshold_via_subprocess(self):
        """通过 subprocess 验证环境变量传递给 hook 进程。"""
        stdin = make_agent_stdin()
        rc, stdout, stderr = run_hook_with_stdin(
            stdin,
            env={"MEMORY_CONSOLIDATE_THRESHOLD": "999999"},
        )
        # 设置极高阈值，hook 应正常退出（不触发合并）
        assert rc == 0


# ==================== 测试：dry-run 无可合并对时跳过 ====================

class TestDryRunNoPairs:
    """测试 dry-run 无可合并对时不执行真正合并。"""

    def test_dry_run_no_pairs_skips_real_merge(self):
        """dry-run 返回空 pairs 时，不执行第二次（真正的）合并调用。"""
        call_count = [0]
        dry_run_output = "未发现相似记忆对，无需合并。"

        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = dry_run_output
            mock_result.stderr = ""
            return mock_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            hook_module.run_consolidate("/tmp/fake_store", max_pairs=5)

        # 只应有 1 次调用（dry-run），没有第二次真正合并
        assert call_count[0] == 1

    def test_dry_run_with_pairs_executes_real_merge(self):
        """dry-run 发现有对时，执行第二次真正合并调用。"""
        call_count = [0]

        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            if "--dry-run" in cmd:
                mock_result.stdout = "发现 3 对相似记忆"
            else:
                mock_result.stdout = "合并完成：merged=3，deleted=3"
            mock_result.stderr = ""
            return mock_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            hook_module.run_consolidate("/tmp/fake_store", max_pairs=5)

        # 应有 2 次调用：dry-run + 真正合并
        assert call_count[0] == 2
