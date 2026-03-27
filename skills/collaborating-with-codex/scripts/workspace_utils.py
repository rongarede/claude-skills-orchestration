"""
Workspace utilities for Claude-Codex Agent Workspace.
Provides core functions for project resolution, log writing, and config management.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_WORKSPACE = Path.home() / "agent-workspace"
CONFIG_FILENAME = "config.json"


def get_workspace_root(workspace_arg: Optional[str] = None) -> Path:
    """Resolve workspace root directory."""
    if workspace_arg:
        return Path(workspace_arg).expanduser().resolve()
    env_val = os.environ.get("AGENT_WORKSPACE")
    if env_val:
        return Path(env_val).expanduser().resolve()
    return DEFAULT_WORKSPACE


def load_config(workspace: Path) -> Dict[str, Any]:
    """Load workspace config.json. Returns empty dict if not found."""
    cfg_path = workspace / CONFIG_FILENAME
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    return {}


def save_config(workspace: Path, config: Dict[str, Any]) -> None:
    """Save workspace config.json."""
    cfg_path = workspace / CONFIG_FILENAME
    cfg_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def slugify(name: str) -> str:
    """Convert a project path or name to a slug (lowercase, hyphens)."""
    # 取最后一个路径组件
    base = Path(name).name if "/" in name or "\\" in name else name
    slug = base.lower().replace("_", "-").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "default"


def resolve_project(workspace: Path, project: Optional[str] = None) -> str:
    """Resolve project slug. Uses default_project from config if not specified."""
    if project:
        return project
    config = load_config(workspace)
    return config.get("default_project", "default")


def get_project_dir(workspace: Path, project: str) -> Path:
    """Get project directory, creating it if needed."""
    proj_dir = workspace / "projects" / project
    for sub in ("plans", "logs", "artifacts"):
        (proj_dir / sub).mkdir(parents=True, exist_ok=True)
    return proj_dir


def now_iso() -> str:
    """Current time as ISO string safe for filenames."""
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def now_iso_full() -> str:
    """Current time as full ISO string for log entries."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def write_log_event(log_path: Path, event: Dict[str, Any]) -> None:
    """Append a single JSON event to a JSONL log file."""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def init_project(workspace: Path, slug: str, path: str, description: str = "") -> Dict[str, Any]:
    """Initialize a new project in the workspace."""
    get_project_dir(workspace, slug)
    config = load_config(workspace)
    if "projects" not in config:
        config["projects"] = {}
    config["projects"][slug] = {
        "path": path,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "description": description,
    }
    if not config.get("default_project"):
        config["default_project"] = slug
    config["version"] = config.get("version", 1)
    config["workspace_root"] = str(workspace)
    save_config(workspace, config)
    return config
