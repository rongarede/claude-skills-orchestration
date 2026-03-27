"""
Codex Bridge Script for Claude Agent Skills.
Wraps the Codex CLI to provide a JSON-based interface for Claude.
Supports agent role injection from ~/.claude/agents/ directory.
"""
from __future__ import annotations

import json
import re
import os
import sys
import queue
import subprocess
import threading
import time
import shutil
import argparse
import tempfile
import atexit
from pathlib import Path
from typing import Generator, List, Optional, Tuple

# 全局临时文件列表，用于清理
_temp_files: List[Path] = []


def _cleanup_temp_files() -> None:
    """清理所有临时文件"""
    for f in _temp_files:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass


# 注册退出时清理
atexit.register(_cleanup_temp_files)


def parse_agent_file(agent_path: Path) -> Tuple[dict, str]:
    """
    解析 agent 文件，提取 YAML frontmatter 和 markdown 内容。

    Returns:
        Tuple[dict, str]: (frontmatter 字典, markdown 内容)
    """
    content = agent_path.read_text(encoding='utf-8')

    # 检查是否有 YAML frontmatter
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            markdown_content = parts[2].strip()

            # 简单解析 YAML（避免依赖 pyyaml）
            frontmatter = {}
            for line in frontmatter_str.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    frontmatter[key.strip()] = value.strip()

            return frontmatter, markdown_content

    # 没有 frontmatter，整个文件作为内容
    return {}, content


def load_agent_instructions(agent_name: str, agent_dir: Path) -> Tuple[Optional[Path], Optional[str], dict]:
    """
    加载 agent 指令文件并创建临时文件。

    Args:
        agent_name: agent 名称（如 'planner'）
        agent_dir: agent 目录路径

    Returns:
        Tuple[Optional[Path], Optional[str], dict]:
            (临时文件路径, 错误信息, frontmatter)
    """
    agent_file = agent_dir / f"{agent_name}.md"

    if not agent_file.exists():
        available = [f.stem for f in agent_dir.glob("*.md")]
        return None, f"Agent '{agent_name}' not found. Available: {', '.join(available)}", {}

    try:
        frontmatter, content = parse_agent_file(agent_file)

        # 创建临时文件存储指令
        fd, temp_path = tempfile.mkstemp(suffix='.md', prefix=f'codex_agent_{agent_name}_')
        temp_file = Path(temp_path)
        _temp_files.append(temp_file)

        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)

        return temp_file, None, frontmatter

    except Exception as e:
        return None, f"Failed to load agent '{agent_name}': {e}", {}


def list_available_agents(agent_dir: Path) -> List[str]:
    """列出可用的 agent"""
    if not agent_dir.exists():
        return []
    return sorted([f.stem for f in agent_dir.glob("*.md")])


def _get_windows_npm_paths() -> List[Path]:
    """Return candidate directories for npm global installs on Windows."""
    if os.name != "nt":
        return []
    paths: List[Path] = []
    env = os.environ
    if prefix := env.get("NPM_CONFIG_PREFIX") or env.get("npm_config_prefix"):
        paths.append(Path(prefix))
    if appdata := env.get("APPDATA"):
        paths.append(Path(appdata) / "npm")
    if localappdata := env.get("LOCALAPPDATA"):
        paths.append(Path(localappdata) / "npm")
    if programfiles := env.get("ProgramFiles"):
        paths.append(Path(programfiles) / "nodejs")
    return paths


def _augment_path_env(env: dict) -> None:
    """Prepend npm global directories to PATH if missing."""
    if os.name != "nt":
        return
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_entries = [p for p in env.get(path_key, "").split(os.pathsep) if p]
    lower_set = {p.lower() for p in path_entries}
    for candidate in _get_windows_npm_paths():
        if candidate.is_dir() and str(candidate).lower() not in lower_set:
            path_entries.insert(0, str(candidate))
            lower_set.add(str(candidate).lower())
    env[path_key] = os.pathsep.join(path_entries)


def _resolve_executable(name: str, env: dict) -> str:
    """Resolve executable path, checking npm directories for .cmd/.bat on Windows."""
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return name
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_val = env.get(path_key)
    win_exts = {".exe", ".cmd", ".bat", ".com"}
    if resolved := shutil.which(name, path=path_val):
        if os.name == "nt":
            suffix = Path(resolved).suffix.lower()
            if not suffix:
                resolved_dir = str(Path(resolved).parent)
                for ext in (".cmd", ".bat", ".exe", ".com"):
                    candidate = Path(resolved_dir) / f"{name}{ext}"
                    if candidate.is_file():
                        return str(candidate)
            elif suffix not in win_exts:
                return resolved
        return resolved
    if os.name == "nt":
        for base in _get_windows_npm_paths():
            for ext in (".cmd", ".bat", ".exe", ".com"):
                candidate = base / f"{name}{ext}"
                if candidate.is_file():
                    return str(candidate)
    return name


def run_shell_command(cmd: List[str]) -> Generator[str, None, None]:
    """Execute a command and stream its output line-by-line."""
    env = os.environ.copy()
    _augment_path_env(env)

    popen_cmd = cmd.copy()
    exe_path = _resolve_executable(cmd[0], env)
    popen_cmd[0] = exe_path

    # Windows .cmd/.bat files need cmd.exe wrapper (avoid shell=True for security)
    if os.name == "nt" and Path(exe_path).suffix.lower() in {".cmd", ".bat"}:
        # Escape shell metacharacters for cmd.exe
        def _cmd_quote(arg: str) -> str:
            if not arg:
                return '""'
            # For Windows batch files, % and ^ must be escaped before quoting
            arg = arg.replace('%', '%%')
            arg = arg.replace('^', '^^')
            if any(c in arg for c in '&|<>()^" \t'):
                # To safely escape " inside "...", close quote, escape ", reopen
                escaped = arg.replace('"', '"^""')
                return f'"{escaped}"'
            return arg
        cmdline = " ".join(_cmd_quote(a) for a in popen_cmd)
        comspec = env.get("COMSPEC", "cmd.exe")
        popen_cmd = f'"{comspec}" /d /s /c "{cmdline}"'

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )

    output_queue: queue.Queue[Optional[str]] = queue.Queue()
    GRACEFUL_SHUTDOWN_DELAY = 0.3

    def is_turn_completed(line: str) -> bool:
        try:
            data = json.loads(line)
            return data.get("type") == "turn.completed"
        except (json.JSONDecodeError, AttributeError, TypeError):
            return False

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.strip()
                output_queue.put(stripped)
                if is_turn_completed(stripped):
                    time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                    process.terminate()
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output)
    thread.start()

    while True:
        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    thread.join(timeout=5)

    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break

def configure_windows_stdio() -> None:
    """Configure stdout/stderr to use UTF-8 encoding on Windows."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main():
    configure_windows_stdio()
    parser = argparse.ArgumentParser(description="Codex Bridge with Agent Role Injection")
    parser.add_argument("--PROMPT", required=True, help="Instruction for the task to send to codex.")
    parser.add_argument("--cd", required=True, help="Set the workspace root for codex before executing the task.")
    parser.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write", "danger-full-access"], help="Sandbox policy for model-generated commands. Defaults to `read-only`.")
    parser.add_argument("--SESSION_ID", default="", help="Resume the specified session of the codex. Defaults to `None`, start a new session.")
    parser.add_argument("--skip-git-repo-check", action="store_true", default=True, help="Allow codex running outside a Git repository (useful for one-off directories).")
    parser.add_argument("--return-all-messages", action="store_true", help="Return all messages (e.g. reasoning, tool calls, etc.) from the codex session. Set to `False` by default, only the agent's final reply message is returned.")
    parser.add_argument("--image", action="append", default=[], help="Attach one or more image files to the initial prompt. Separate multiple paths with commas or repeat the flag.")
    parser.add_argument("--model", default="gpt-5.3-codex", help="The model to use for the codex session. Defaults to gpt-5.3-codex; falls back to gpt-5.3-codex-spark on failure.")
    parser.add_argument("--yolo", action="store_true", help="Run every command without approvals or sandboxing. Only use when `sandbox` couldn't be applied.")
    parser.add_argument("--profile", default="", help="Configuration profile name to load from `~/.codex/config.toml`. This parameter is strictly prohibited unless explicitly specified by the user.")

    # Agent 角色注入参数
    parser.add_argument("--agent", default="", help="Agent name from ~/.claude/agents/ (e.g., 'planner', 'architect', 'security-reviewer'). Injects agent role as system instructions.")
    parser.add_argument("--agent-file", default="", help="Custom agent file path. Overrides --agent if both specified.")
    parser.add_argument("--agent-dir", default=str(Path.home() / ".claude" / "agents"), help="Directory containing agent files. Defaults to ~/.claude/agents/")
    parser.add_argument("--list-agents", action="store_true", help="List available agents and exit.")
    parser.add_argument("--instructions", default="", help="Direct system instructions string. Overrides --agent and --agent-file.")
    parser.add_argument("--instructions-file", default="", help="Path to custom instructions file. Overrides --agent.")

    # Workspace 日志参数
    parser.add_argument("--workspace", default="", help="Workspace root directory. Defaults to ~/agent-workspace. Set to 'none' to disable logging.")
    parser.add_argument("--plan", default="", help="Plan file name (in workspace plans/ dir) for log association.")
    parser.add_argument("--task-num", type=int, default=0, help="Task number within the plan (for log association).")
    parser.add_argument("--project", default="", help="Project slug in workspace. Auto-detected from --cd if omitted.")

    # 进程管理参数
    parser.add_argument("--ps", action="store_true", help="List running Codex processes.")
    parser.add_argument("--kill", default="", help="Kill Codex process by PID or 'all' to kill all exec processes.")
    parser.add_argument("--sessions", action="store_true", help="List recent Codex sessions.")

    args = parser.parse_args()

    agent_dir = Path(args.agent_dir).expanduser()

    # 处理 --ps（列出进程）
    if args.ps:
        result = list_codex_processes()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 处理 --kill（终止进程）
    if args.kill:
        result = kill_codex_process(args.kill)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 处理 --sessions（列出会话）
    if args.sessions:
        result = list_codex_sessions()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 处理 --list-agents
    if args.list_agents:
        agents = list_available_agents(agent_dir)
        result = {
            "success": True,
            "available_agents": agents,
            "agent_dir": str(agent_dir)
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    cmd = ["codex", "exec", "--sandbox", args.sandbox, "--cd", args.cd, "--json"]

    # 处理 Agent 角色注入（优先级：instructions > instructions-file > agent-file > agent）
    instructions_temp_file = None
    agent_frontmatter = {}

    if args.instructions:
        # 直接使用 instructions 字符串
        fd, temp_path = tempfile.mkstemp(suffix='.md', prefix='codex_instructions_')
        instructions_temp_file = Path(temp_path)
        _temp_files.append(instructions_temp_file)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(args.instructions)

    elif args.instructions_file:
        # 使用指定的 instructions 文件
        instructions_path = Path(args.instructions_file).expanduser()
        if not instructions_path.exists():
            result = {"success": False, "error": f"Instructions file not found: {instructions_path}"}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        instructions_temp_file = instructions_path  # 直接使用，不创建临时文件

    elif args.agent_file:
        # 使用指定的 agent 文件
        agent_path = Path(args.agent_file).expanduser()
        if not agent_path.exists():
            result = {"success": False, "error": f"Agent file not found: {agent_path}"}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        agent_frontmatter, content = parse_agent_file(agent_path)
        fd, temp_path = tempfile.mkstemp(suffix='.md', prefix='codex_agent_')
        instructions_temp_file = Path(temp_path)
        _temp_files.append(instructions_temp_file)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)

    elif args.agent:
        # 从 agent 目录加载
        instructions_temp_file, error, agent_frontmatter = load_agent_instructions(args.agent, agent_dir)
        if error:
            result = {"success": False, "error": error}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return

    # 添加 instructions 文件到命令
    if instructions_temp_file:
        cmd.extend(["-c", f'model_instructions_file="{instructions_temp_file}"'])

    # 如果 agent frontmatter 指定了 model 且用户未指定，使用 agent 的 model
    if not args.model and agent_frontmatter.get("model"):
        agent_model = agent_frontmatter["model"]
        # 映射 Claude 模型名到 Codex 支持的模型
        model_mapping = {
            "opus": "gpt-5.3-codex",
            "sonnet": "gpt-5.3-codex",
            "haiku": "gpt-5.3-codex-spark",
        }
        args.model = model_mapping.get(agent_model, agent_model)

    if args.image:
        cmd.extend(["--image", ",".join(args.image)])

    if args.model:
        cmd.extend(["--model", args.model])

    if args.profile:
        cmd.extend(["--profile", args.profile])

    if args.yolo:
        cmd.append("--yolo")

    if args.skip_git_repo_check:
        cmd.append("--skip-git-repo-check")

    if args.SESSION_ID:
        cmd.extend(["resume", args.SESSION_ID])

    PROMPT = args.PROMPT
    # Escape shell metacharacters on all platforms.
    # codex exec internally passes the prompt through zsh eval, so unescaped
    # single quotes, backticks and backslashes cause parsing errors on macOS.
    PROMPT = PROMPT.replace('\\', '\\\\')   # backslash first to avoid double-escaping
    PROMPT = PROMPT.replace("'", "\\'")
    PROMPT = PROMPT.replace('`', '\\`')
    PROMPT = PROMPT.replace('\n', '\\n')
    PROMPT = PROMPT.replace('\r', '\\r')
    PROMPT = PROMPT.replace('\t', '\\t')
    PROMPT = PROMPT.replace('"', '\\"')

    cmd += ['--', PROMPT]

    # --- Workspace logging: task_start ---
    _ws_log_path = None
    _ws_start_time = None
    if args.workspace != "none":
        try:
            from workspace_utils import (
                get_workspace_root, resolve_project, get_project_dir,
                now_iso, now_iso_full, write_log_event, slugify,
            )
            _ws_root = get_workspace_root(args.workspace or None)
            if _ws_root.exists():
                _ws_project = args.project or slugify(args.cd)
                _ws_proj_dir = get_project_dir(_ws_root, _ws_project)
                _ws_log_name = f"{now_iso()}_{args.SESSION_ID or 'new'}.jsonl"
                _ws_log_path = _ws_proj_dir / "logs" / _ws_log_name
                _ws_start_time = time.time()
                write_log_event(_ws_log_path, {
                    "ts": now_iso_full(),
                    "event": "task_start",
                    "plan": args.plan,
                    "task_num": args.task_num,
                    "prompt": PROMPT[:2000],
                    "session_id": args.SESSION_ID or "",
                    "working_dir": args.cd,
                    "model": args.model,
                })
        except Exception as e:
            sys.stderr.write(f"[workspace] Failed to write start log: {e}\n")

    # Execution Logic with model fallback
    FALLBACK_MODEL = "gpt-5.3-codex-spark"
    models_to_try = [args.model]
    if args.model != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    all_messages = []
    agent_messages = ""
    success = True
    err_message = ""
    thread_id = None

    for model_attempt in models_to_try:
        # 替换 cmd 中的 --model 参数值
        if "--model" in cmd:
            idx = cmd.index("--model")
            cmd[idx + 1] = model_attempt

        all_messages = []
        agent_messages = ""
        success = True
        err_message = ""
        thread_id = None

        for line in run_shell_command(cmd):
            try:
                line_dict = json.loads(line.strip())
                all_messages.append(line_dict)
                item = line_dict.get("item", {})
                item_type = item.get("type", "")
                if item_type == "agent_message":
                    agent_messages = agent_messages + item.get("text", "")
                if line_dict.get("thread_id") is not None:
                    thread_id = line_dict.get("thread_id")
                if "fail" in line_dict.get("type", ""):
                    success = False if len(agent_messages) == 0 else success
                    err_message += "\n\n[codex error] " + line_dict.get("error", {}).get("message", "")
                if "error" in line_dict.get("type", ""):
                    error_msg = line_dict.get("message", "")
                    is_reconnecting = bool(re.match(r'^Reconnecting\.\.\.\s+\d+/\d+$', error_msg))

                    if not is_reconnecting:
                        success = False if len(agent_messages) == 0 else success
                        err_message += "\n\n[codex error] " + error_msg

            except json.JSONDecodeError:
                err_message += "\n\n[json decode error] " + line
                continue

            except Exception as error:
                err_message += "\n\n[unexpected error] " + f"Unexpected error: {error}. Line: {line!r}"
                success = False
                break

        if thread_id is None:
            success = False
            err_message = "Failed to get `SESSION_ID` from the codex session. \n\n" + err_message

        if len(agent_messages) == 0:
            success = False
            err_message = "Failed to get `agent_messages` from the codex session. \n\n You can try to set `return_all_messages` to `True` to get the full reasoning information. " + err_message

        if success:
            break  # 成功，不需要 fallback
        elif model_attempt != models_to_try[-1]:
            sys.stderr.write(f"[codex_bridge] Model '{model_attempt}' failed, falling back to '{FALLBACK_MODEL}'...\n")

    if success:
        result = {
            "success": True,
            "SESSION_ID": thread_id,
            "agent_messages": agent_messages,
        }

    else:
        result = {"success": False, "error": err_message}

    if args.return_all_messages:
        result["all_messages"] = all_messages

    # --- Workspace logging: task_end ---
    if _ws_log_path is not None:
        try:
            from workspace_utils import write_log_event, now_iso_full
            _duration = time.time() - _ws_start_time if _ws_start_time else 0
            write_log_event(_ws_log_path, {
                "ts": now_iso_full(),
                "event": "task_end",
                "session_id": thread_id or "",
                "status": "success" if success else "failed",
                "duration_s": round(_duration, 2),
                "error": err_message[:500] if err_message else "",
            })
        except Exception as e:
            sys.stderr.write(f"[workspace] Failed to write end log: {e}\n")

    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
