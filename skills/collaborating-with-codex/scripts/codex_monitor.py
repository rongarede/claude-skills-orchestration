#!/usr/bin/env python3
"""
Codex 进程监控工具
用于查看正在运行的 Codex 进程及其对话内容
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
import argparse


def get_running_codex_processes():
    """获取正在运行的 Codex 进程"""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        processes = []
        for line in result.stdout.split('\n'):
            if 'codex' in line.lower() and 'grep' not in line:
                parts = line.split()
                if len(parts) >= 11:
                    pid = parts[1]
                    cpu = parts[2]
                    mem = parts[3]
                    cmd = ' '.join(parts[10:])

                    # 判断进程类型
                    if 'codex exec' in cmd:
                        proc_type = 'exec'
                    elif 'app-server' in cmd:
                        proc_type = 'app-server'
                    elif 'codex_bridge' in cmd:
                        proc_type = 'bridge'
                    else:
                        proc_type = 'other'

                    # 提取 PROMPT（如果有）
                    prompt = ""
                    if '--PROMPT' in cmd or '-- ' in cmd:
                        try:
                            if '-- ' in cmd:
                                prompt = cmd.split('-- ', 1)[1][:100]
                        except:
                            pass

                    processes.append({
                        'pid': pid,
                        'type': proc_type,
                        'cpu': cpu,
                        'mem': mem,
                        'prompt': prompt,
                        'cmd': cmd[:200]
                    })
        return processes
    except Exception as e:
        return []


def get_latest_session_file():
    """获取最新的会话文件"""
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return None

    # 查找最新的 jsonl 文件
    latest = None
    latest_time = 0

    for jsonl in sessions_dir.rglob("*.jsonl"):
        mtime = jsonl.stat().st_mtime
        if mtime > latest_time:
            latest_time = mtime
            latest = jsonl

    return latest


def get_session_by_id(session_id: str):
    """根据 session_id 查找会话文件"""
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return None

    for jsonl in sessions_dir.rglob("*.jsonl"):
        if session_id in jsonl.name:
            return jsonl
    return None


def parse_session_messages(session_file: Path, limit: int = 50):
    """解析会话文件中的消息"""
    messages = []
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())

                    # 提取 session_meta
                    if data.get('type') == 'session_meta':
                        messages.append({
                            'type': 'meta',
                            'session_id': data.get('payload', {}).get('id'),
                            'cwd': data.get('payload', {}).get('cwd'),
                            'model': data.get('payload', {}).get('model_provider'),
                            'timestamp': data.get('timestamp')
                        })

                    # 提取 event_msg
                    elif data.get('type') == 'event_msg':
                        payload = data.get('payload', {})
                        msg_type = payload.get('type')

                        if msg_type == 'user_message':
                            messages.append({
                                'type': 'user',
                                'text': payload.get('message', '')
                            })
                        elif msg_type == 'agent_message':
                            messages.append({
                                'type': 'agent',
                                'text': payload.get('text', '')
                            })
                        elif msg_type == 'agent_reasoning':
                            messages.append({
                                'type': 'reasoning',
                                'text': payload.get('text', '')
                            })
                        elif msg_type == 'exec_command':
                            messages.append({
                                'type': 'command',
                                'command': payload.get('command', ''),
                                'cwd': payload.get('cwd', '')
                            })
                        elif msg_type == 'exec_command_output':
                            messages.append({
                                'type': 'command_output',
                                'output': payload.get('output', '')[:500]
                            })

                    # 提取 response_item (tool calls)
                    elif data.get('type') == 'response_item':
                        payload = data.get('payload', {})
                        item_type = payload.get('type')

                        if item_type == 'function_call':
                            messages.append({
                                'type': 'tool_call',
                                'name': payload.get('name'),
                                'arguments': str(payload.get('arguments', ''))[:200]
                            })
                        elif item_type == 'function_call_output':
                            output = payload.get('output', '')
                            messages.append({
                                'type': 'tool_output',
                                'output': output[:500] if isinstance(output, str) else str(output)[:500]
                            })

                except json.JSONDecodeError:
                    continue

    except Exception as e:
        messages.append({'type': 'error', 'message': str(e)})

    return messages[-limit:] if len(messages) > limit else messages


def watch_session(session_file: Path, interval: float = 1.0):
    """实时监控会话文件"""
    print(f"监控会话: {session_file.name}")
    print("-" * 60)

    last_size = 0
    last_messages = []

    try:
        while True:
            current_size = session_file.stat().st_size
            if current_size > last_size:
                messages = parse_session_messages(session_file, limit=100)
                new_messages = messages[len(last_messages):]

                for msg in new_messages:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if msg['type'] == 'user':
                        print(f"\n[{timestamp}] [User]: {msg['text'][:200]}...")
                    elif msg['type'] == 'agent':
                        print(f"\n[{timestamp}] [Agent]: {msg['text']}")
                    elif msg['type'] == 'reasoning':
                        print(f"\n[{timestamp}] [Thinking]: {msg['text'][:150]}...")
                    elif msg['type'] == 'command':
                        print(f"\n[{timestamp}] [Command]: {msg['command'][:100]}")
                    elif msg['type'] == 'tool_call':
                        print(f"\n[{timestamp}] [Tool]: {msg['name']}")
                    elif msg['type'] == 'meta':
                        print(f"\n[{timestamp}] [Session]: {msg['session_id']}")
                        print(f"[{timestamp}] [CWD]: {msg['cwd']}")

                last_messages = messages
                last_size = current_size

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n监控已停止")


def kill_process(pid: str):
    """终止进程"""
    try:
        if pid.lower() == 'all':
            result = subprocess.run(
                ["pkill", "-f", "codex exec"],
                capture_output=True,
                text=True
            )
            return {"success": True, "message": "已终止所有 codex exec 进程"}
        else:
            result = subprocess.run(
                ["kill", pid],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return {"success": True, "message": f"已终止进程 {pid}"}
            else:
                return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Codex 进程监控工具")
    parser.add_argument("--ps", action="store_true", help="列出运行中的 Codex 进程")
    parser.add_argument("--kill", default="", help="终止进程 (PID 或 'all')")
    parser.add_argument("--session", default="", help="查看指定会话 (session_id 或 'latest')")
    parser.add_argument("--watch", action="store_true", help="实时监控最新会话")
    parser.add_argument("--messages", type=int, default=20, help="显示消息数量")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    # 列出进程
    if args.ps:
        processes = get_running_codex_processes()
        if args.json:
            print(json.dumps({"processes": processes}, indent=2, ensure_ascii=False))
        else:
            if not processes:
                print("没有运行中的 Codex 进程")
            else:
                print(f"{'PID':<8} {'类型':<12} {'CPU':<6} {'MEM':<6} {'任务'}")
                print("-" * 70)
                for p in processes:
                    prompt = p['prompt'][:40] + "..." if len(p['prompt']) > 40 else p['prompt']
                    print(f"{p['pid']:<8} {p['type']:<12} {p['cpu']:<6} {p['mem']:<6} {prompt}")
        return

    # 终止进程
    if args.kill:
        result = kill_process(args.kill)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 查看会话
    if args.session:
        if args.session == 'latest':
            session_file = get_latest_session_file()
        else:
            session_file = get_session_by_id(args.session)

        if not session_file:
            print(json.dumps({"success": False, "error": "会话文件未找到"}, ensure_ascii=False))
            return

        messages = parse_session_messages(session_file, limit=args.messages)

        if args.json:
            print(json.dumps({
                "success": True,
                "session_file": str(session_file),
                "messages": messages
            }, indent=2, ensure_ascii=False))
        else:
            print(f"会话文件: {session_file.name}")
            print("-" * 60)
            for msg in messages:
                if msg['type'] == 'meta':
                    print(f"[Session] {msg['session_id']}")
                    print(f"[CWD] {msg['cwd']}")
                elif msg['type'] == 'agent':
                    print(f"\n[Agent] {msg['text']}")
                elif msg['type'] == 'tool_call':
                    print(f"\n[Tool] {msg['name']}: {msg['arguments'][:100]}...")
        return

    # 实时监控
    if args.watch:
        session_file = get_latest_session_file()
        if session_file:
            watch_session(session_file)
        else:
            print("没有找到会话文件")
        return

    # 默认：显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
