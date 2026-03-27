# Agent Memory Project

## Overview
Associative memory system for Claude Code subagents. Fuses A-MEM (Zettelkasten) + Generative Agents (3D scoring) + BM25.

## Architecture
- `scripts/memory_store.py` — Memory dataclass + JSONL store
- `scripts/retriever.py` — BM25 + recency/importance/relevance scoring + spreading activation
- `scripts/associator.py` — Bidirectional link management
- `scripts/extractor.py` — Claude API memory extraction (K/G/X/importance)
- `tests/` — Unit tests (run with `python3 tests/test_retriever.py`)

## Development Rules
- **TDD**: Write tests FIRST, then implement
- **All tests must pass** before marking a step complete
- **Gate checks**: Each phase has verification gates — don't skip them
- **Update plan.md**: Check off completed steps
- **Update project log**: Append progress to Obsidian project homepage

## Key APIs
```python
from scripts.memory_store import Memory, MemoryStore
from scripts.retriever import retrieve, format_for_prompt
from scripts.associator import link_memory

store = MemoryStore("path/to/memories.jsonl")
results = retrieve("query", store, top_k=3, spread=True)
prompt_text = format_for_prompt(results)
```

## Testing
```bash
cd ~/.claude/skills/agent-memory
python3 tests/test_retriever.py
python3 tests/test_extractor.py  # after Phase 2
```
