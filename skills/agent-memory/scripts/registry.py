"""
角色注册与分配系统

管理子代理角色的命名、分配、释放和持久化。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

MEMORY_BASE = Path(os.path.expanduser("~/.claude/memory"))
REGISTRY_PATH = MEMORY_BASE / "registry.json"
NAMES_PATH = MEMORY_BASE / "names.json"

# 名字池：每个 subagent_type 5 个候选名
NAME_POOLS = {
    "Explore": ["Kaze", "Mirin", "Soren", "Vento", "Cirro"],
    "Worker": ["Tetsu", "Aspen", "Ember", "Riven", "Cobalt"],
    "Operator": ["Sora", "Nimba", "Prism", "Helix", "Pulse"],
    "Auditor": ["Shin", "Onyx", "Argon", "Quartz", "Flint"],
    "Analyst": ["Yomi", "Lyric", "Astra", "Cipher", "Nexus"],
    "Inspector": ["Haku", "Rune", "Velox", "Ignis", "Terra"],
    "Raiga": ["Raiga"],       # 吞噬者（单例）：拆分书籍/文档、创建 skill
    "Fumio": ["Fumio"],       # 图书管理员（单例）：管理本地书籍文档
    "Norna": ["Norna"],       # 母体（单例）：创建 subagent 角色
    "Yume": ["Yume"],         # 梦者（单例）：管理所有角色的记忆
}

# 单例角色类型：每类只有一个唯一个体，不可重复创建
SINGLETON_TYPES = {"Raiga", "Fumio", "Norna", "Yume"}

# subagent_type 映射（用户使用的 type → 内部 type）
TYPE_ALIASES = {
    "Explore": "Explore",
    "worker": "Worker",
    "general-purpose": "Operator",
    "code-reviewer": "Auditor",
    "worker-researcher": "Analyst",
    "worker-reviewer": "Inspector",
    "devourer": "Raiga",
    "吞噬者": "Raiga",
    "raiga": "Raiga",
    "librarian": "Fumio",
    "图书管理员": "Fumio",
    "fumio": "Fumio",
    "matrix": "Norna",
    "母体": "Norna",
    "norna": "Norna",
    "yume": "Yume",
    "梦者": "Yume",
    "dreamer": "Yume",
}


class AgentRegistry:
    """角色注册表：管理角色分配与释放"""

    def __init__(self, base_path: Optional[str] = None):
        self.base = Path(base_path) if base_path else MEMORY_BASE
        self.registry_path = self.base / "registry.json"
        self.names_path = self.base / "names.json"
        self._ensure_dirs()
        self._ensure_files()

    def _ensure_dirs(self):
        """确保目录结构存在"""
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "shared").mkdir(exist_ok=True)
        (self.base / "agents").mkdir(exist_ok=True)

    def _ensure_files(self):
        """确保 registry.json 和 names.json 存在"""
        if not self.registry_path.exists():
            self._write_json(self.registry_path, {"agents": {}})
        if not self.names_path.exists():
            self._write_json(self.names_path, {
                agent_type: {"available": names[:], "used": []}
                for agent_type, names in NAME_POOLS.items()
            })

    def _read_json(self, path: Path) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_json(self, path: Path, data: dict):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _resolve_type(self, agent_type: str) -> str:
        """将用户传入的 subagent_type 转换为内部类型名"""
        return TYPE_ALIASES.get(agent_type, agent_type)

    def assign(self, agent_type: str) -> str:
        """
        从指定类型的名字池中分配一个角色。
        优先分配已存在但 idle 的角色，其次创建新角色。
        单例类型（Raiga/Fumio/Norna）若已存在则直接返回，不创建新的。
        返回角色名（小写）。
        """
        # 标准化类型名
        resolved_type = TYPE_ALIASES.get(agent_type, agent_type)

        # 单例检查：如果类型是 singleton，检查是否已存在
        if resolved_type in SINGLETON_TYPES:
            singleton_registry = self._read_json(self.registry_path)
            for name, info in singleton_registry.get('agents', {}).items():
                if info.get('type') == resolved_type:
                    # 已存在，直接返回该角色名（不创建新的）
                    return name

        registry = self._read_json(self.registry_path)
        agents = registry.get("agents", {})

        # 优先找 idle 的同类型角色
        for name, info in agents.items():
            if info["type"] == resolved_type and info["status"] == "idle":
                info["status"] = "busy"
                self._write_json(self.registry_path, registry)
                # 更新 profile
                self._update_profile(name, resolved_type)
                return name

        # 没有 idle 的，从名字池取一个新名字
        names = self._read_json(self.names_path)
        pool = names.get(resolved_type, {"available": [], "used": []})

        if not pool["available"]:
            raise RuntimeError(f"名字池已耗尽: {resolved_type} (已用: {pool['used']})")

        new_name = pool["available"].pop(0).lower()
        pool["used"].append(new_name)
        names[resolved_type] = pool
        self._write_json(self.names_path, names)

        # 注册到 registry
        agents[new_name] = {
            "type": resolved_type,
            "status": "busy",
            "created": datetime.now().strftime("%Y-%m-%d"),
        }
        registry["agents"] = agents
        self._write_json(self.registry_path, registry)

        # 创建角色目录和 profile
        self._create_agent_dir(new_name, resolved_type)

        return new_name

    def release(self, agent_name: str):
        """释放角色回 idle 状态"""
        registry = self._read_json(self.registry_path)
        agents = registry.get("agents", {})
        name = agent_name.lower()

        if name not in agents:
            return

        agents[name]["status"] = "idle"
        self._write_json(self.registry_path, registry)

    def get_agent_type(self, agent_name: str) -> Optional[str]:
        """获取角色的类型"""
        registry = self._read_json(self.registry_path)
        info = registry.get("agents", {}).get(agent_name.lower())
        return info["type"] if info else None

    def get_agents_by_type(self, agent_type: str) -> list:
        """返回指定类型的所有角色名"""
        resolved_type = self._resolve_type(agent_type)
        registry = self._read_json(self.registry_path)
        return [
            name for name, info in registry.get("agents", {}).items()
            if info["type"] == resolved_type
        ]

    def get_all_agents(self) -> dict:
        """返回所有角色信息"""
        registry = self._read_json(self.registry_path)
        return registry.get("agents", {})

    def _create_agent_dir(self, name: str, agent_type: str):
        """创建角色目录和初始文件"""
        agent_dir = self.base / "agents" / name
        agent_dir.mkdir(parents=True, exist_ok=True)

        # 创建 profile.json
        profile = {
            "name": name,
            "type": agent_type,
            "created": datetime.now().isoformat(),
            "task_count": 0,
            "last_active": datetime.now().isoformat(),
        }
        self._write_json(agent_dir / "profile.json", profile)

        # 创建空的 memories.jsonl（兼容旧格式检测）
        memories_path = agent_dir / "memories.jsonl"
        if not memories_path.exists():
            memories_path.touch()

    def _update_profile(self, name: str, agent_type: str):
        """更新角色的 profile（task_count + last_active）"""
        profile_path = self.base / "agents" / name / "profile.json"
        if profile_path.exists():
            profile = self._read_json(profile_path)
            profile["task_count"] = profile.get("task_count", 0) + 1
            profile["last_active"] = datetime.now().isoformat()
            self._write_json(profile_path, profile)
