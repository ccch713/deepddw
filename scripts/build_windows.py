#!/usr/bin/env python3
"""deepDDW Windows 打包脚本（PyInstaller one-dir）。

用法（在 Windows 上执行；跨平台可写、语法检查可过）:
    pip install -r requirements.txt pyinstaller
    python scripts/build_windows.py

产出: dist/deepddw/deepddw.exe + _internal/（绿色版，升级可局部替换 _internal）。
数据目录独立在 %USERPROFILE%\\.deepddw（DDW_DATA_DIR 环境变量可覆盖），
exe 升级不碰用户数据。详细评估见 docs/windows-packaging.md。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    # Windows 控制台默认 GBK：PyInstaller 输出含中文会 UnicodeEncodeError。
    # 强制 UTF-8 输出；Python 3.7+ 支持 PYTHONUTF8=1。
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    repo = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "deepddw",
        "--onedir",  # one-dir：升级可局部替换，优于 onefile
        # uvicorn 动态导入的模块（打包必列，否则启动 404/循环导入）
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        # MCP SDK 动态加载
        "--hidden-import", "mcp.server.fastmcp",
        "--hidden-import", "mcp.server.streamable_http",
        # SQLAlchemy 方言动态加载（'sqlite+aiosqlite' 是字符串引用，
        # PyInstaller 静态分析发现不了——必须显式收集）
        "--hidden-import", "aiosqlite",
        "--hidden-import", "greenlet",
        # 业务包完整收集（含插件目录）
        "--collect-submodules", "core",
        "--collect-submodules", "plugins",
        # 数据文件（Windows 用 ; 分隔）
        "--add-data", f"frontend{';' if sys.platform == 'win32' else ':'}frontend",
        "--add-data", f"config{';' if sys.platform == 'win32' else ':'}config",
        "--add-data", f"VERSION{';' if sys.platform == 'win32' else ':'}.",
        "entry_win.py",
    ]
    print("PyInstaller building... (1-3 min)")
    result = subprocess.run(cmd, cwd=str(repo), check=False)
    if result.returncode != 0:
        print("Build FAILED, see PyInstaller output above", file=sys.stderr)
        return result.returncode
    print("Build OK: dist/deepddw/deepddw.exe")
    print("Verify: start deepddw.exe, then open http://127.0.0.1:8500/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
