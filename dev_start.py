#!/usr/bin/env python3
"""
Game Assets Maker development launcher.
Starts the frontend dev server and PyWebView together.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def get_script_dir() -> Path:
    return Path(__file__).parent.resolve()


def get_npm_cmd():
    """Return npm command suitable for subprocess on current platform."""
    if sys.platform == "win32":
        # On Windows npm is a .cmd file; CreateProcess can't execute it directly.
        return ["cmd", "/c", "npm"]
    return ["npm"]


def run_npm(args, cwd, check=False):
    """Run an npm command cross-platform."""
    cmd = get_npm_cmd() + args
    return subprocess.run(cmd, cwd=cwd, check=check)


def kill_port_processes(port: int):
    """Kill processes listening on the given port."""
    current_platform = sys.platform
    try:
        if current_platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids.add(pid)
            for pid in pids:
                print(f"  Killing PID {pid} on port {port}...")
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, check=False)
        else:
            result = subprocess.run(
                ["lsof", f"-ti:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
            for pid in result.stdout.strip().split():
                if pid.isdigit():
                    print(f"  Killing PID {pid} on port {port}...")
                    subprocess.run(["kill", "-9", pid], capture_output=True, check=False)
    except Exception as e:
        print(f"  Warning: failed to clean port {port}: {e}")


def kill_process_tree(pid: int):
    """Kill a process and its children (Windows only)."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)


def main():
    script_dir = get_script_dir()
    os.chdir(script_dir)

    print("🚀 启动 Game Assets Maker (PyWebView + Vue3)...")
    print(f"📁 工作目录: {os.getcwd()}")

    # Clean port 5173
    print("🧹 清理占用端口...")
    kill_port_processes(5173)
    time.sleep(1)

    # Install frontend dependencies if needed
    node_modules = script_dir / "frontend" / "node_modules"
    if not node_modules.exists():
        print("📦 安装前端依赖...")
        run_npm(["install"], cwd=script_dir / "frontend", check=True)

    # Start frontend dev server
    print("🌐 启动前端开发服务器...")
    frontend_cmd = get_npm_cmd() + ["run", "dev"]
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=script_dir / "frontend",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    time.sleep(3)

    # Start PyWebView
    print("🖥️  启动 PyWebView...")
    env = os.environ.copy()
    env["DEV_MODE"] = "1"

    try:
        subprocess.run(
            [sys.executable, "-m", "backend.main"],
            env=env,
            check=True,
            cwd=script_dir,
        )
    except KeyboardInterrupt:
        print("\n⚠️  收到中断信号，正在关闭...")
    finally:
        print("🛑 关闭前端开发服务器...")
        if sys.platform == "win32":
            kill_process_tree(frontend_proc.pid)
        else:
            frontend_proc.terminate()
        try:
            frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            frontend_proc.kill()
            frontend_proc.wait()
        print("👋 已关闭")


if __name__ == "__main__":
    main()
