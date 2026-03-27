"""Memory store: Markdown frontmatter-based storage for associative memories."""

import os
import shutil
import tempfile
from dataclasses import dataclass, field, asdict, replace as dc_replace
from typing import Optional
from pathlib import Path
from datetime import datetime

import yaml


@dataclass
class Memory:
    """A single memory note, inspired by A-MEM's Zettelkasten model."""
    id: str                          # mem_YYYYMMDD_NNN 或 {agent}_{YYYYMMDD}_{NNN}
    content: str                     # task description + outcome
    timestamp: str                   # ISO format
    keywords: list[str]              # >= 3, ordered by importance
    tags: list[str]                  # broad categories
    context: str                     # one-line summary
    importance: int                  # 1-10 (Generative Agents style)
    related_ids: list[str] = field(default_factory=list)  # A-MEM links
    access_count: int = 0
    last_accessed: Optional[str] = None
    # Phase 6b: 多角色记忆层
    owner: str = ""                                       # 角色名，如 "kaze"
    scope: str = "personal"                               # "personal" | "shared"
    accessed_by: list = field(default_factory=list)       # 哪些角色检索过
    # Phase 7: 邻居演化历史
    evolution_history: list = field(default_factory=list) # 该记忆被演化更新的历史记录
    # Claude Code auto-memory style metadata
    name: str = ""                                         # 人类可读短名
    description: str = ""                                  # 一句话摘要（用于索引）
    type: str = "task"                                     # user|feedback|task|knowledge|project|reference
    # Phase 1B: Retrieval Feedback
    positive_feedback: int = 0                             # 有用反馈次数
    negative_feedback: int = 0                             # 无用反馈次数
    # Phase 1C: Retrieval Usage Feedback Loop
    retrieval_count: int = 0                               # 被检索次数
    last_retrieved: str = ""                               # 最近一次被检索的时间（ISO format）
    usefulness_score: float = 0.5                          # 有用性评分 [0, 1]，默认中性
    # Phase 8: 4-layer memory hierarchy
    layer: str = "L1"                                      # L0=working, L1=episodic, L2=semantic, L3=core

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Memory':
        # 只取 dataclass 已知字段，兼容旧数据格式（不含 owner/scope/accessed_by）
        known = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known}
        # 为新字段设置默认值，保证旧数据可正常加载
        filtered.setdefault('owner', '')
        filtered.setdefault('scope', 'personal')
        filtered.setdefault('accessed_by', [])
        filtered.setdefault('evolution_history', [])
        filtered.setdefault('name', '')
        filtered.setdefault('description', '')
        filtered.setdefault('type', 'task')
        filtered.setdefault('positive_feedback', 0)
        filtered.setdefault('negative_feedback', 0)
        filtered.setdefault('retrieval_count', 0)
        filtered.setdefault('last_retrieved', '')
        filtered.setdefault('usefulness_score', 0.5)
        filtered.setdefault('layer', 'L1')
        return cls(**filtered)


class MemoryStore:
    """Markdown-based memory storage, one memory per .md file.

    三种构造模式：
    1. store_path 指定  → 使用指定目录（新语义）
    2. agent_name 指定  → personal 模式，目录为 ~/.claude/memory/agents/{name}/
    3. 两者都不指定     → 默认目录 ~/.claude/memory/
    """

    def __init__(self, store_path: str = None, agent_name: str = None, agent_type: str = None):
        self.agent_name = agent_name
        self.agent_type = agent_type

        if store_path is not None:
            path = Path(store_path).expanduser()
            # 兼容旧调用：若传入 .jsonl 文件路径，退化为其父目录
            if path.suffix == ".jsonl":
                path = path.parent
            self.store_path = path
        elif agent_name is not None:
            base = Path(os.path.expanduser("~/.claude/memory"))
            self.store_path = base / "agents" / agent_name
        else:
            self.store_path = Path(os.path.expanduser("~/.claude/memory"))

        self.store_path.mkdir(parents=True, exist_ok=True)

    def _memory_file(self, memory_id: str) -> Path:
        # 对 id 做安全文件名处理：替换 / 和其他非法字符，防止路径穿越
        safe_id = memory_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.store_path / f"{safe_id}.md"

    def _memory_to_frontmatter(self, memory: Memory) -> str:
        """Serialize a Memory object into markdown with YAML frontmatter."""
        related = [f"[[{rid}]]" for rid in (memory.related_ids or [])]
        frontmatter = {
            "id": memory.id,
            "name": memory.name or "",
            "description": memory.description or "",
            "type": memory.type or "task",
            "owner": memory.owner,
            "scope": memory.scope,
            "importance": memory.importance,
            "access_count": memory.access_count,
            "last_accessed": memory.last_accessed,
            "keywords": memory.keywords or [],
            "tags": memory.tags or [],
            "context": memory.context,
            "timestamp": memory.timestamp,
            "related": related,
            "accessed_by": memory.accessed_by or [],
            "evolution_history": memory.evolution_history or [],
            "positive_feedback": memory.positive_feedback,
            "negative_feedback": memory.negative_feedback,
            "retrieval_count": memory.retrieval_count,
            "last_retrieved": memory.last_retrieved or "",
            "usefulness_score": memory.usefulness_score,
            "layer": memory.layer or "L1",
        }

        yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_text.rstrip()}\n---\n\n{memory.content}\n"

    def _frontmatter_to_memory(self, text: str) -> Memory:
        """Parse markdown frontmatter content into a Memory object."""
        text = text.strip()
        # Ensure trailing newline so split("\n---\n") works even for empty body
        if text.endswith("\n---") or text.endswith("---"):
            text = text + "\n"
        # 兼容 ---\n 和 ---\r\n 开头
        if not (text.startswith("---\n") or text.startswith("---\r\n")):
            raise ValueError("Invalid memory markdown: missing frontmatter start")

        # 统一换行符后 split
        text = text.replace("\r\n", "\n")
        parts = text.split("\n---\n", 1)
        if len(parts) != 2:
            raise ValueError("Invalid memory markdown: missing frontmatter end")

        fm_text = parts[0][4:]  # drop first "---\n"
        body = parts[1]
        body = body.lstrip("\n")
        if body.endswith("\n"):
            body = body[:-1]

        meta = yaml.safe_load(fm_text) or {}

        raw_related = meta.get("related", []) or []
        related_ids = []
        for item in raw_related:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if s.startswith("[[") and s.endswith("]]"):
                related_ids.append(s[2:-2].strip())
            else:
                related_ids.append(s)

        data = {
            "id": meta.get("title") or meta.get("id") or "",
            "content": body,
            "timestamp": meta.get("timestamp") or "",
            "name": meta.get("name") or "",
            "description": meta.get("description") or "",
            "type": meta.get("type") or "task",
            "keywords": meta.get("keywords") or [],
            "tags": meta.get("tags") or [],
            "context": meta.get("context") or "",
            "importance": int(meta.get("importance") or 0),
            "related_ids": related_ids,
            "access_count": int(meta.get("access_count") or 0),
            "last_accessed": meta.get("last_accessed"),
            "owner": meta.get("owner") or "",
            "scope": meta.get("scope") or "personal",
            "accessed_by": meta.get("accessed_by") or [],
            "evolution_history": meta.get("evolution_history") or [],
            "positive_feedback": max(0, int(meta.get("positive_feedback") or 0)),
            "negative_feedback": max(0, int(meta.get("negative_feedback") or 0)),
            "retrieval_count": max(0, int(meta.get("retrieval_count") or 0)),
            "last_retrieved": meta.get("last_retrieved") or "",
            "usefulness_score": max(0.0, min(1.0, float(meta.get("usefulness_score") if meta.get("usefulness_score") is not None else 0.5))),
            "layer": meta.get("layer") or "L1",
        }
        return Memory.from_dict(data)

    def add(self, memory: Memory) -> Memory:
        """Write a memory into {memory.id}.md."""
        target = self._memory_file(memory.id)
        target.write_text(self._memory_to_frontmatter(memory), encoding='utf-8')
        return memory

    @property
    def _corrupted_log_path(self) -> Path:
        """损坏记忆日志文件路径（store 目录下的隐藏文件）。"""
        return self.store_path / ".corrupted_memories.log"

    def _log_corrupted(self, file_path: Path, error: Exception) -> None:
        """向损坏日志追加一条记录。格式：{timestamp} | {file_path} | {error_message}"""
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"{timestamp} | {file_path} | {error}\n"
        with open(self._corrupted_log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def load_all(self) -> list[Memory]:
        """Load all memories from *.md files under the store directory.

        容错机制：YAML frontmatter 解析失败的文件跳过（不 crash），
        错误记录到 .corrupted_memories.log（追加模式）。
        日志格式：{timestamp} | {file_path} | {error_message}
        """
        if not self.store_path.exists():
            return []

        memories = []
        for path in sorted(self.store_path.glob("*.md")):
            text = path.read_text(encoding='utf-8')
            try:
                memories.append(self._frontmatter_to_memory(text))
            except Exception as e:
                # 跳过损坏文件，记录到日志，保持读取健壮性
                self._log_corrupted(path, e)
                continue
        return memories

    def get(self, memory_id: str) -> Optional[Memory]:
        """Get a specific memory by ID in O(1) file lookup."""
        path = self._memory_file(memory_id)
        if not path.exists():
            return None
        try:
            return self._frontmatter_to_memory(path.read_text(encoding='utf-8'))
        except Exception:
            return None

    def update(self, memory: Memory) -> None:
        """Update memory by replacing its corresponding .md file."""
        self._memory_file(memory.id).write_text(self._memory_to_frontmatter(memory), encoding='utf-8')

    def generate_id(self, id_prefix: str = None, name: str = "", memory_type: str = "task") -> str:
        """Generate a unique memory ID by scanning existing file names."""
        # 语义化命名：仅当 name 非空时启用
        if name and name.strip():
            slug = "_".join(name.strip().lower().split())
            slug = slug.replace("/", "_").replace("\\", "_").replace(":", "_")
            normalized_type = (memory_type or "task").strip().lower() or "task"
            if slug:
                semantic_id = f"{normalized_type}_{slug}"
                if not self._memory_file(semantic_id).exists():
                    return semantic_id

        today = datetime.now().strftime("%Y%m%d")
        if id_prefix is not None:
            prefix = id_prefix
        elif self.agent_name:
            prefix = f"{self.agent_name}_{today}"
        else:
            prefix = f"mem_{today}"

        max_seq = 0
        for path in self.store_path.glob("*.md"):
            mid = path.stem
            if not mid.startswith(prefix + "_"):
                continue
            suffix = mid[len(prefix) + 1:]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))

        seq = max_seq + 1
        return f"{prefix}_{seq:03d}"

    def count(self) -> int:
        """Return the number of memories."""
        return len(list(self.store_path.glob("*.md")))

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted, False if not found."""
        path = self._memory_file(memory_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ==================== Phase 6b: 多角色合并检索 ====================

    def retrieve_merged(self, query: str, top_k: int = 3, spread: bool = True,
                        spread_decay: float = 0.5, now=None) -> list:
        """合并检索：个人记忆 + 同类型其他角色记忆 + shared 记忆。

        扩散激活仅在同类型角色间生效。
        返回 list[tuple[Memory, float]]，与 retriever.retrieve() 格式一致。
        """
        from retriever import retrieve as _retrieve
        from registry import AgentRegistry

        all_memories = []

        # 1. 个人记忆
        personal = self.load_all()
        all_memories.extend(personal)

        # 2. 同类型其他角色的记忆
        if self.agent_name and self.agent_type:
            registry = AgentRegistry()
            same_type_agents = registry.get_agents_by_type(self.agent_type)
            base = Path(os.path.expanduser("~/.claude/memory"))
            for agent in same_type_agents:
                if agent != self.agent_name:
                    other_path = base / "agents" / agent
                    if other_path.exists():
                        other_store = MemoryStore(store_path=str(other_path))
                        all_memories.extend(other_store.load_all())

        # 3. Shared 记忆
        shared_path = Path(os.path.expanduser("~/.claude/memory/shared"))
        if shared_path.exists():
            shared_store = MemoryStore(store_path=str(shared_path))
            all_memories.extend(shared_store.load_all())

        if not all_memories:
            return []

        # 将所有记忆写入临时目录存储，统一评分
        tmp_dir = tempfile.mkdtemp(prefix="memory-merged-")
        try:
            merged_store = MemoryStore(store_path=tmp_dir)
            for m in all_memories:
                merged_store.add(m)
            results = _retrieve(query, merged_store, top_k=top_k, spread=spread,
                                spread_decay=spread_decay, now=now)

            # 对原始存储中的记忆更新访问追踪
            for mem, score in results:
                self._track_access(mem)

            return results
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _track_access(self, memory: Memory) -> None:
        """更新访问追踪，检查晋升条件。"""
        if not self.agent_name:
            return

        # 若记忆属于其他角色，更新对方存储中的 accessed_by
        if memory.owner and memory.owner != self.agent_name:
            base = Path(os.path.expanduser("~/.claude/memory"))
            owner_path = base / "agents" / memory.owner
            if owner_path.exists():
                owner_store = MemoryStore(store_path=str(owner_path))
                original = owner_store.get(memory.id)
                if original and self.agent_name not in original.accessed_by:
                    original = dc_replace(original, accessed_by=[*original.accessed_by, self.agent_name])
                    owner_store.update(original)
                    self.check_promotion(memory.id, owner_store, original)

    def check_promotion(self, memory_id: str, source_store: 'MemoryStore' = None,
                        memory: Memory = None) -> bool:
        """检查记忆是否应晋升到 shared（被 >= 3 个不同角色检索过）。

        晋升条件达成时，将记忆复制到 shared 层并标记原记忆 scope="shared"。
        返回是否发生了晋升。
        """
        store = source_store or self
        mem = memory or store.get(memory_id)
        if not mem or mem.scope == "shared":
            return False

        if len(mem.accessed_by) >= 3:
            # 晋升到 shared 层
            shared_path = Path(os.path.expanduser("~/.claude/memory/shared"))
            shared_path.mkdir(parents=True, exist_ok=True)
            shared_store = MemoryStore(store_path=str(shared_path))

            # 生成 shared ID：使用 shared_ 前缀 + 今日日期，序号自动递增
            today = datetime.now().strftime("%Y%m%d")
            shared_id = shared_store.generate_id(id_prefix=f"shared_{today}")

            promoted = Memory(
                id=shared_id,
                content=mem.content,
                timestamp=mem.timestamp,
                keywords=mem.keywords,
                tags=mem.tags,
                context=mem.context,
                importance=mem.importance,
                related_ids=[],          # shared 层不保留个人关联
                access_count=mem.access_count,
                last_accessed=mem.last_accessed,
                owner="shared",
                scope="shared",
                accessed_by=mem.accessed_by[:],
            )
            shared_store.add(promoted)

            # 标记原记忆已晋升
            mem = dc_replace(mem, scope="shared")
            store.update(mem)
            return True

        return False
