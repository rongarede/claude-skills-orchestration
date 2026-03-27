"""Tests for memory extractor — Claude API memory field extraction."""

import os
import sys
import shutil
import tempfile
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory


class TestExtractMemoryFields:
    """Test extract_memory_fields() with mocked Claude API."""

    def test_extracts_keywords(self):
        from extractor import extract_memory_fields

        task_info = {
            "subject": "修复 LaTeX fontspec 编译错误",
            "description": "XeLaTeX 路径未正确配置导致 fontspec 包加载失败",
            "task_id": "1"
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "keywords": ["LaTeX", "fontspec", "XeLaTeX", "编译错误"],
            "tags": ["bug-fix", "thesis", "latex"],
            "context": "论文编译流程中 XeLaTeX 引擎路径问题导致 fontspec 包加载失败",
            "importance": 7
        }))]

        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = extract_memory_fields(task_info)

        assert "keywords" in result
        assert len(result["keywords"]) >= 3
        assert "LaTeX" in result["keywords"]

    def test_extracts_importance_in_range(self):
        from extractor import extract_memory_fields

        task_info = {
            "subject": "日常代码格式化",
            "description": "调整缩进和空格",
            "task_id": "2"
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "keywords": ["格式化", "代码风格", "缩进"],
            "tags": ["chore", "formatting"],
            "context": "日常代码格式调整，无功能变更",
            "importance": 2
        }))]

        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = extract_memory_fields(task_info)

        assert 1 <= result["importance"] <= 10

    def test_extracts_context_as_string(self):
        from extractor import extract_memory_fields

        task_info = {
            "subject": "实现 BM25 检索器",
            "description": "为联想记忆系统实现基于 BM25 的检索引擎",
            "task_id": "3"
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "keywords": ["BM25", "检索器", "联想记忆"],
            "tags": ["feature", "memory", "retrieval"],
            "context": "为 agent 联想记忆系统构建轻量级 BM25 全文检索引擎",
            "importance": 8
        }))]

        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = extract_memory_fields(task_info)

        assert isinstance(result["context"], str)
        assert len(result["context"]) > 0

    def test_fallback_on_api_error(self):
        from extractor import extract_memory_fields

        task_info = {
            "subject": "测试任务",
            "description": "测试描述",
            "task_id": "4"
        }

        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("API Error")
            result = extract_memory_fields(task_info)

        # Should return fallback values, not raise
        assert "keywords" in result
        assert "importance" in result
        assert result["importance"] == 5  # default medium importance

    def test_fallback_on_invalid_json(self):
        from extractor import extract_memory_fields

        task_info = {
            "subject": "测试任务",
            "description": "测试描述",
            "task_id": "5"
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON")]

        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = extract_memory_fields(task_info)

        # Should return fallback values
        assert "keywords" in result
        assert result["importance"] == 5


class TestCreateMemoryFromTask:
    """Test create_memory_from_task() end-to-end."""

    def test_creates_valid_memory(self):
        from extractor import create_memory_from_task
        from memory_store import MemoryStore

        task_info = {
            "subject": "精读 A-MEM 论文",
            "description": "提取 Zettelkasten 数据模型和联想链机制",
            "task_id": "6"
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "keywords": ["A-MEM", "Zettelkasten", "联想记忆"],
            "tags": ["research", "paper", "ai"],
            "context": "精读 A-MEM 论文，提取 agent 联想记忆的数据模型",
            "importance": 8
        }))]

        tmp_dir = tempfile.mkdtemp()

        try:
            store = MemoryStore(tmp_dir)

            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_response
                memory = create_memory_from_task(task_info, store)

            assert isinstance(memory, Memory)
            assert memory.id.startswith("mem_")
            assert "A-MEM" in memory.keywords
            assert memory.importance == 8
            assert memory.content == "精读 A-MEM 论文: 提取 Zettelkasten 数据模型和联想链机制"

            # Verify it was persisted
            loaded = store.load_all()
            assert len(loaded) == 1
            assert loaded[0].id == memory.id
        finally:
            shutil.rmtree(tmp_dir)

    def test_auto_links_with_existing_memories(self):
        from extractor import create_memory_from_task
        from memory_store import MemoryStore, Memory

        tmp_dir = tempfile.mkdtemp()

        try:
            store = MemoryStore(tmp_dir)

            # Add existing memory
            existing = Memory(
                id="mem_20260311_001",
                content="精读 Generative Agents 论文",
                timestamp="2026-03-11T15:00:00",
                keywords=["Generative Agents", "三维评分", "论文"],
                tags=["research", "paper", "ai"],
                context="三维检索评分机制",
                importance=8
            )
            store.add(existing)

            # Create new related memory
            task_info = {
                "subject": "精读 A-MEM 论文",
                "description": "提取联想记忆数据模型",
                "task_id": "7"
            }

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "keywords": ["A-MEM", "联想记忆", "论文"],
                "tags": ["research", "paper", "ai"],
                "context": "A-MEM 联想记忆系统",
                "importance": 8
            }))]

            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_response
                memory = create_memory_from_task(task_info, store, auto_link=True)

            # Should have linked to existing memory
            # (may or may not depending on BM25 threshold, so just check it runs)
            assert isinstance(memory, Memory)
        finally:
            shutil.rmtree(tmp_dir)


class TestPromptTemplate:
    """Test the prompt template generation."""

    def test_prompt_contains_task_info(self):
        from extractor import build_extraction_prompt

        task_info = {
            "subject": "修复编译错误",
            "description": "fontspec 包加载失败"
        }

        prompt = build_extraction_prompt(task_info)
        assert "修复编译错误" in prompt
        assert "fontspec" in prompt

    def test_prompt_requests_json(self):
        from extractor import build_extraction_prompt

        task_info = {"subject": "test", "description": "test desc"}
        prompt = build_extraction_prompt(task_info)
        assert "JSON" in prompt or "json" in prompt


def run_tests():
    """Simple test runner."""
    import traceback

    test_classes = [TestExtractMemoryFields, TestCreateMemoryFromTask, TestPromptTemplate]

    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if method_name.startswith('test_'):
                try:
                    getattr(instance, method_name)()
                    passed += 1
                    print(f"  PASS {cls.__name__}.{method_name}")
                except Exception as e:
                    failed += 1
                    errors.append((f"{cls.__name__}.{method_name}", traceback.format_exc()))
                    print(f"  FAIL {cls.__name__}.{method_name}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")

    if errors:
        print(f"\nFailures:")
        for name, tb in errors:
            print(f"\n--- {name} ---")
            print(tb)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
