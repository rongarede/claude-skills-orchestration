"""Tests for memory injection into subagent prompts."""

import os
import sys
import shutil
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore


def _create_test_store(tmp_dir):
    store = MemoryStore(tmp_dir)
    store.add(Memory(
        id="mem_20260310_001",
        content="修复 LaTeX fontspec 编译错误",
        timestamp="2026-03-10T10:00:00",
        keywords=["LaTeX", "fontspec", "编译错误"],
        tags=["bug-fix", "thesis"],
        context="XeLaTeX 路径配置问题",
        importance=7,
        related_ids=["mem_20260310_002"]
    ))
    store.add(Memory(
        id="mem_20260310_002",
        content="配置 latexmk 自动编译",
        timestamp="2026-03-10T14:00:00",
        keywords=["latexmk", "自动编译", "xelatex"],
        tags=["config", "thesis"],
        context="latexmk 编译配置",
        importance=5,
        related_ids=["mem_20260310_001"]
    ))
    return store


class TestBuildInjectionContext:
    def test_returns_string(self):
        from inject import build_injection_context
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            result = build_injection_context("LaTeX 编译", store)
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            shutil.rmtree(tmp)

    def test_contains_memory_content(self):
        from inject import build_injection_context
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            result = build_injection_context("LaTeX 编译", store)
            assert "fontspec" in result or "LaTeX" in result
        finally:
            shutil.rmtree(tmp)

    def test_empty_store_returns_empty(self):
        from inject import build_injection_context
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(tmp)
            result = build_injection_context("anything", store)
            assert result == ""
        finally:
            shutil.rmtree(tmp)

    def test_respects_max_tokens(self):
        from inject import build_injection_context
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            short = build_injection_context("LaTeX", store, max_chars=100)
            full = build_injection_context("LaTeX", store, max_chars=10000)
            assert len(short) <= len(full)
        finally:
            shutil.rmtree(tmp)


class TestEnrichAgentPrompt:
    def test_adds_memory_section(self):
        from inject import enrich_agent_prompt
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            original = "请修复 LaTeX 编译错误"
            enriched = enrich_agent_prompt(original, store)
            assert "联想记忆" in enriched
            assert original in enriched
        finally:
            shutil.rmtree(tmp)

    def test_no_memories_returns_original(self):
        from inject import enrich_agent_prompt
        tmp = tempfile.mkdtemp()
        try:
            store = MemoryStore(tmp)
            original = "请修复 LaTeX 编译错误"
            result = enrich_agent_prompt(original, store)
            assert result == original
        finally:
            shutil.rmtree(tmp)


class TestMarkMemoryUsed:
    def test_updates_access_count(self):
        from inject import mark_memories_used
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            mark_memories_used(["mem_20260310_001"], store)
            mem = store.get("mem_20260310_001")
            assert mem.access_count == 1
            assert mem.last_accessed is not None
        finally:
            shutil.rmtree(tmp)


class TestEvolveMemory:
    def test_update_context(self):
        from inject import evolve_memory
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            evolve_memory("mem_20260310_001", store, context="更新后的语境描述")
            mem = store.get("mem_20260310_001")
            assert mem.context == "更新后的语境描述"
        finally:
            shutil.rmtree(tmp)

    def test_update_tags(self):
        from inject import evolve_memory
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            evolve_memory("mem_20260310_001", store, tags=["updated", "new-tag"])
            mem = store.get("mem_20260310_001")
            assert "updated" in mem.tags
        finally:
            shutil.rmtree(tmp)

    def test_add_keywords(self):
        from inject import evolve_memory
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            evolve_memory("mem_20260310_001", store, add_keywords=["新关键词"])
            mem = store.get("mem_20260310_001")
            assert "新关键词" in mem.keywords
        finally:
            shutil.rmtree(tmp)

    def test_nonexistent_memory_returns_none(self):
        from inject import evolve_memory
        tmp = tempfile.mkdtemp()
        try:
            store = _create_test_store(tmp)
            result = evolve_memory("nonexistent", store, context="test")
            assert result is None
        finally:
            shutil.rmtree(tmp)


def run_tests():
    import traceback
    test_classes = [TestBuildInjectionContext, TestEnrichAgentPrompt, TestMarkMemoryUsed, TestEvolveMemory]
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
                    print(f"  ✓ {cls.__name__}.{method_name}")
                except Exception as e:
                    failed += 1
                    errors.append((f"{cls.__name__}.{method_name}", traceback.format_exc()))
                    print(f"  ✗ {cls.__name__}.{method_name}: {e}")
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        for name, tb in errors:
            print(f"\n--- {name} ---\n{tb}")
    return failed == 0

if __name__ == "__main__":
    exit(0 if run_tests() else 1)
