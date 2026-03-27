#!/usr/bin/env python3
"""
Workspace Manager for Claude-Codex Agent Workspace.
Commands: init, list, logs, status, clean
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from workspace_utils import (
    get_workspace_root, load_config, save_config, slugify,
    init_project, get_project_dir, resolve_project,
)


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new project in the workspace."""
    ws = get_workspace_root(args.workspace or None)
    ws.mkdir(parents=True, exist_ok=True)
    slug = args.project or slugify(args.path)
    config = init_project(ws, slug, args.path, args.description)
    print(json.dumps({
        "success": True,
        "project": slug,
        "workspace": str(ws),
        "config": config,
    }, indent=2, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    """List all projects."""
    ws = get_workspace_root(args.workspace or None)
    config = load_config(ws)
    projects = config.get("projects", {})
    default = config.get("default_project", "")
    rows = []
    for slug, info in projects.items():
        rows.append({
            "slug": slug,
            "path": info.get("path", ""),
            "created": info.get("created", ""),
            "default": slug == default,
        })
    print(json.dumps({"projects": rows}, indent=2, ensure_ascii=False))


def cmd_logs(args: argparse.Namespace) -> None:
    """Show recent log entries for a project."""
    ws = get_workspace_root(args.workspace or None)
    project = resolve_project(ws, args.project)
    log_dir = ws / "projects" / project / "logs"
    if not log_dir.exists():
        print(json.dumps({"error": f"No logs for project '{project}'"}))
        return

    # 收集所有日志文件，按修改时间倒序
    log_files = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    entries = []
    for lf in log_files[:args.last]:
        for line in lf.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    # 按时间倒序
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    entries = entries[:args.last * 2]  # 每个文件约 2 条

    print(json.dumps({"project": project, "entries": entries}, indent=2, ensure_ascii=False))


def cmd_status(args: argparse.Namespace) -> None:
    """Show execution status for a plan."""
    ws = get_workspace_root(args.workspace or None)
    project = resolve_project(ws, args.project)
    log_dir = ws / "projects" / project / "logs"
    if not log_dir.exists():
        print(json.dumps({"error": "No logs found"}))
        return

    plan_name = args.plan
    results = []
    for lf in sorted(log_dir.glob("*.jsonl")):
        for line in lf.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("plan", "") == plan_name:
                    results.append(entry)
            except json.JSONDecodeError:
                pass

    print(json.dumps({
        "plan": plan_name,
        "project": project,
        "events": results,
    }, indent=2, ensure_ascii=False))


def cmd_clean(args: argparse.Namespace) -> None:
    """Clean old artifacts and logs."""
    ws = get_workspace_root(args.workspace or None)
    project = resolve_project(ws, args.project)
    proj_dir = ws / "projects" / project

    # 解析 --before (如 "30d")
    before_str = args.before
    days = int(before_str.rstrip("d"))
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()

    removed = []
    for subdir in ("logs", "artifacts"):
        target = proj_dir / subdir
        if not target.exists():
            continue
        for f in target.iterdir():
            if f.name == ".gitkeep":
                continue
            if f.stat().st_mtime < cutoff_ts:
                removed.append(str(f.relative_to(ws)))
                if not args.dry_run:
                    f.unlink()

    print(json.dumps({
        "project": project,
        "removed": removed,
        "dry_run": args.dry_run,
    }, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Workspace Manager")
    parser.add_argument("--workspace", default="", help="Workspace root. Defaults to ~/agent-workspace")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a project")
    p_init.add_argument("--project", default="", help="Project slug")
    p_init.add_argument("--path", required=True, help="Project filesystem path")
    p_init.add_argument("--description", default="", help="Project description")

    # list
    sub.add_parser("list", help="List all projects")

    # logs
    p_logs = sub.add_parser("logs", help="Show recent logs")
    p_logs.add_argument("--project", default="", help="Project slug")
    p_logs.add_argument("--last", type=int, default=10, help="Number of recent log files")

    # status
    p_status = sub.add_parser("status", help="Show plan execution status")
    p_status.add_argument("--plan", required=True, help="Plan name to query")
    p_status.add_argument("--project", default="", help="Project slug")

    # clean
    p_clean = sub.add_parser("clean", help="Clean old files")
    p_clean.add_argument("--project", default="", help="Project slug")
    p_clean.add_argument("--before", default="30d", help="Remove files older than (e.g. '30d')")
    p_clean.add_argument("--dry-run", action="store_true", help="Show what would be removed")

    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "list": cmd_list,
        "logs": cmd_logs,
        "status": cmd_status,
        "clean": cmd_clean,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
