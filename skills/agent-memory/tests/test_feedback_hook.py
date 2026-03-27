#!/usr/bin/env python3
"""
TDD 测试：post-task-feedback-hook.py

覆盖场景：
1. 非 TaskUpdate 事件被跳过
2. status != completed 被跳过
3. 无法推断 agent 时跳过并输出 stderr 提醒
4. 推断 agent 成功：从 description 解析
5. 推断 agent 成功：从 tool_result 字段解析
6. 无记忆文件时跳过并输出 stderr 提醒
7. 正常触发时调用 cli.py 的命令构造正确
8. cli.py 超时保护机制
9. stdin JSON 解析失败时静默退出（不 block）
10. stdin 为空时静默退出
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
HOOK_PATH = os.path.expanduser("~/.claude/hooks/post-task-feedback-hook.py")
HOOK_DIR = os.path.dirname(HOOK_PATH)

# 动态导入 hook 模块（不执行 main）
import importlib.util

spec = importlib.util.spec_from_file_location("post_task_feedback_hook", HOOK_PATH)
hook_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook_module)


# ==================== 辅助函数 ====================

def make_stdin_json(tool_name: str, status: str = "completed", extra_input: dict = None, extra_result: dict = None) -> str:
    """构造标准 PostToolUse stdin JSON。"""
    tool_input = {"taskId": "task-001", "status": status}
    if extra_input:
        tool_input.update(extra_input)
    tool_result = {}
    if extra_result:
        tool_result.update(extra_result)
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_result": tool_result,
    })


def run_hook_with_stdin(stdin_content: str) -> tuple[int, str, str]:
    """运行 hook 脚本并捕获 stdout/stderr/returncode。"""
    result = subprocess.run(
        [sys.executable, HOOK_PATH],
        input=stdin_content,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


# ==================== 测试：stdin 解析 ====================

class TestStdinParsing:
    """测试 stdin JSON 解析的健壮性。"""

    def test_empty_stdin_exits_zero(self):
        """空 stdin 应静默退出，不抛异常。"""
        rc, stdout, stderr = run_hook_with_stdin("")
        assert rc == 0, f"期望 exit 0，实际 {rc}\nstderr: {stderr}"

    def test_invalid_json_exits_zero(self):
        """无效 JSON 应静默退出，不 block。"""
        rc, stdout, stderr = run_hook_with_stdin("this is not json {{{")
        assert rc == 0, f"期望 exit 0，实际 {rc}"


# ==================== 测试：过滤条件 ====================

class TestFilterConditions:
    """测试非目标事件/状态被正确跳过。"""

    def test_non_taskupdate_is_skipped(self):
        """非 TaskUpdate 工具事件应直接跳过，不输出 message。"""
        stdin = make_stdin_json(tool_name="Bash", status="completed")
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        # 不应有 feedback hook 的 message 输出
        assert "post-task-feedback-hook" not in stdout

    def test_taskupdate_in_progress_is_skipped(self):
        """status=in_progress 不触发。"""
        stdin = make_stdin_json(tool_name="TaskUpdate", status="in_progress")
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        assert "post-task-feedback-hook" not in stdout

    def test_taskupdate_pending_is_skipped(self):
        """status=pending 不触发。"""
        stdin = make_stdin_json(tool_name="TaskUpdate", status="pending")
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        assert "post-task-feedback-hook" not in stdout


# ==================== 测试：agent 推断 ====================

class TestAgentInference:
    """测试 infer_agent_from_task 函数的推断逻辑。"""

    def test_infer_from_description_pipe_format(self):
        """从 description 的 '角色名 | 任务' 格式解析 agent。"""
        tool_input = {"description": "tetsu | 执行代码修改"}
        tool_result = {}
        agent = hook_module.infer_agent_from_task(tool_input, tool_result)
        assert agent == "tetsu"

    def test_infer_from_tool_result_assigned_to(self):
        """从 tool_result.assignedTo 字段解析 agent。"""
        tool_input = {}
        tool_result = {"assignedTo": "kaze"}
        agent = hook_module.infer_agent_from_task(tool_input, tool_result)
        assert agent == "kaze"

    def test_infer_from_tool_input_owner(self):
        """从 tool_input.owner 字段解析 agent。"""
        tool_input = {"owner": "shin"}
        tool_result = {}
        agent = hook_module.infer_agent_from_task(tool_input, tool_result)
        assert agent == "shin"

    def test_infer_returns_none_when_no_info(self):
        """无法推断时返回 None。"""
        tool_input = {}
        tool_result = {}
        agent = hook_module.infer_agent_from_task(tool_input, tool_result)
        assert agent is None

    def test_infer_unknown_agent_in_description_returns_none(self):
        """description 中含未知 agent 名时返回 None。"""
        tool_input = {"description": "unknown_agent_xyz | 任务描述"}
        tool_result = {}
        agent = hook_module.infer_agent_from_task(tool_input, tool_result)
        assert agent is None


# ==================== 测试：最新记忆查找 ====================

class TestGetLatestMemoryId:
    """测试 get_latest_memory_id 函数。"""

    def setup_method(self):
        """每个测试创建临时目录。"""
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        """清理临时目录。"""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_none_for_empty_store(self):
        """空 store 目录返回 None。"""
        result = hook_module.get_latest_memory_id(self.tmpdir)
        assert result is None

    def test_returns_none_for_nonexistent_store(self):
        """不存在的路径返回 None。"""
        result = hook_module.get_latest_memory_id("/nonexistent/path/that/does/not/exist")
        assert result is None

    def test_returns_latest_memory_id(self):
        """有多个记忆文件时返回最新（按文件名字母序最大）的记忆 ID。"""
        for name in ["mem_20260314_001.md", "mem_20260314_002.md", "mem_20260315_001.md"]:
            Path(self.tmpdir, name).write_text("---\nid: " + name[:-3] + "\n---\n", encoding="utf-8")
        result = hook_module.get_latest_memory_id(self.tmpdir)
        assert result == "mem_20260315_001"

    def test_excludes_non_memory_files(self):
        """排除 MEMORY.md、role.md 等非记忆文件。"""
        for name in ["MEMORY.md", "role.md", "WhoAmI.md"]:
            Path(self.tmpdir, name).write_text("# non-memory\n", encoding="utf-8")
        result = hook_module.get_latest_memory_id(self.tmpdir)
        assert result is None


# ==================== 测试：cli.py 调用构造 ====================

class TestCallFeedbackCli:
    """测试 call_feedback_cli 函数的命令构造和超时保护。"""

    def test_cli_not_exist_returns_false(self):
        """cli.py 不存在时返回 False，不 crash。"""
        with mock.patch.object(hook_module, "CLI_PATH", "/nonexistent/cli.py"):
            result = hook_module.call_feedback_cli("tetsu", "~/mem/mem/agents/蚁工/tetsu", "mem_001")
        assert result is False

    def test_timeout_protection(self):
        """subprocess.TimeoutExpired 时返回 False，不 block。"""
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="cli.py", timeout=3)):
            result = hook_module.call_feedback_cli("tetsu", "~/mem/mem/agents/蚁工/tetsu", "mem_001")
        assert result is False

    def test_command_construction(self):
        """验证调用 cli.py 时的参数构造正确（含 --auto --event task_success）。"""
        captured_cmd = []

        def mock_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            return mock_result

        with mock.patch("subprocess.run", side_effect=mock_run):
            hook_module.call_feedback_cli("tetsu", "~/mem/mem/agents/蚁工/tetsu", "mem_test_001")

        # 验证关键参数存在
        assert "feedback" in captured_cmd
        assert "--memory-id" in captured_cmd
        assert "mem_test_001" in captured_cmd
        assert "--auto" in captured_cmd
        assert "--event" in captured_cmd
        assert "task_success" in captured_cmd

    def test_nonzero_returncode_returns_false(self):
        """cli.py 返回非零时 call_feedback_cli 返回 False。"""
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"
        with mock.patch("subprocess.run", return_value=mock_result):
            result = hook_module.call_feedback_cli("tetsu", "~/mem/mem/agents/蚁工/tetsu", "mem_001")
        assert result is False


# ==================== 集成测试：无 agent 时输出 stderr ====================

class TestNoAgentOutput:
    """集成测试：无法推断 agent 时 stderr 有提示，不 block。"""

    def test_no_agent_outputs_stderr_warning(self):
        """task completed 但无法推断 agent，hook 应输出 stderr 警告，exit 0。"""
        stdin = make_stdin_json(
            tool_name="TaskUpdate",
            status="completed",
            extra_input={"taskId": "task-999"},  # 无 description/assignedTo
        )
        rc, stdout, stderr = run_hook_with_stdin(stdin)
        assert rc == 0
        # stderr 中应有提示
        assert "无法推断" in stderr or "post-task-feedback-hook" in stderr
