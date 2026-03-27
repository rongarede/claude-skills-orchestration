#!/usr/bin/env python3
"""
TDD Phase 1 (RED): 验证 yume 记忆保存路径正确性
预期：当前实现下全部 FAIL（--store 被 --agent 覆盖）
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

CLI_PATH = os.path.expanduser("~/.claude/skills/agent-memory/scripts/cli.py")

# 11 个 agent 的路径映射
AGENTS = [
    {"name": "tetsu", "type_dir": "蚁工"},
    {"name": "shin", "type_dir": "Auditor"},
    {"name": "kaze", "type_dir": "Explore"},
    {"name": "mirin", "type_dir": "Explore"},
    {"name": "sora", "type_dir": "Operator"},
    {"name": "yomi", "type_dir": "斥候"},
    {"name": "haku", "type_dir": "药师"},
    {"name": "raiga", "type_dir": "吞食者"},
    {"name": "fumio", "type_dir": "织者"},
    {"name": "norna", "type_dir": "母体"},
    {"name": "yume", "type_dir": "梦者"},
]


class TestStorePathPriority:
    """验证 --store 路径优先于 --agent 的默认路径"""

    def setup_method(self):
        """每个测试创建临时目录"""
        self.tmp_dir = tempfile.mkdtemp(prefix="yume_test_")

    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def _run_quick_add(self, agent_name: str, store_path: str) -> subprocess.CompletedProcess:
        """调用 cli.py quick-add"""
        cmd = [
            sys.executable, CLI_PATH,
            "--agent", agent_name,
            "--store", store_path,
            "quick-add",
            "--name", f"test_{agent_name}",
            "--description", f"测试 {agent_name} 记忆保存",
            "--type", "task",
            "--keywords", "test,yume,验证",
            f"测试记忆内容：{agent_name} 的记忆应写入 {store_path}",
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    def _has_memory_in_dir(self, dir_path: str) -> bool:
        """检查目录中是否有记忆文件（.jsonl 或 .md）"""
        p = Path(dir_path)
        if not p.exists():
            return False
        jsonl_files = list(p.glob("*.jsonl"))
        md_files = [f for f in p.glob("*.md") if f.name != "MEMORY.md"]
        return len(jsonl_files) > 0 or len(md_files) > 0

    @pytest.mark.parametrize("agent", AGENTS, ids=[a["name"] for a in AGENTS])
    def test_store_path_respected(self, agent):
        """--store 路径应被尊重，记忆文件写入指定目录"""
        store_path = os.path.join(self.tmp_dir, agent["type_dir"], agent["name"])
        os.makedirs(store_path, exist_ok=True)

        result = self._run_quick_add(agent["name"], store_path)

        # CLI 应成功执行
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # 记忆文件应在 --store 指定的路径中
        assert self._has_memory_in_dir(store_path), (
            f"Agent {agent['name']}: 记忆未写入 --store 路径 {store_path}。"
            f"可能写入了 ~/.claude/memory/agents/{agent['name']}/ "
            f"（--store 被 --agent 覆盖的 bug）"
        )


class TestStoreOnlyMode:
    """验证只使用 --store（不带 --agent）时的行为"""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yume_test_store_only_")

    def teardown_method(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_store_only_writes_to_path(self):
        """只使用 --store 时，记忆应写入指定路径"""
        cmd = [
            sys.executable, CLI_PATH,
            "--store", self.tmp_dir,
            "quick-add",
            "--name", "test_store_only",
            "--description", "仅使用 --store 测试",
            "--type", "task",
            "--keywords", "test",
            "测试内容",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        # 检查文件写入
        p = Path(self.tmp_dir)
        files = list(p.glob("*.jsonl")) + [f for f in p.glob("*.md") if f.name != "MEMORY.md"]
        assert len(files) > 0, f"--store only 模式未写入任何文件到 {self.tmp_dir}"


class TestRetrieveAfterSave:
    """验证保存后可通过 retrieve 检索"""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yume_test_retrieve_")

    def teardown_method(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_save_then_retrieve(self):
        """保存记忆后应可通过 retrieve 命令检索到"""
        store_path = self.tmp_dir

        # 保存
        save_cmd = [
            sys.executable, CLI_PATH,
            "--store", store_path,
            "quick-add",
            "--name", "retrievable_test",
            "--description", "可检索测试",
            "--type", "task",
            "--keywords", "unique_keyword_xyz",
            "这是一条可检索的测试记忆",
        ]
        result = subprocess.run(save_cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0

        # 检索（retrieve 的 query 是 positional argument，不是 --query）
        retrieve_cmd = [
            sys.executable, CLI_PATH,
            "--store", store_path,
            "retrieve",
            "unique_keyword_xyz",
        ]
        result = subprocess.run(retrieve_cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        assert "retrievable_test" in result.stdout or "unique_keyword_xyz" in result.stdout, (
            f"保存后检索失败，输出: {result.stdout}"
        )
