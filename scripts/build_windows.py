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

import subprocess
import sys
from pathlib import Path


def main() -> int:
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
        # 业务包完整收集（含插件目录）
        "--collect-submodules", "core",
        "--collect-submodules", "plugins",
        # 数据文件（Windows 用 ; 分隔）
        "--add-data", f"frontend{';' if sys.platform == 'win32' else ':'}frontend",
        "--add-data", f"config{';' if sys.platform == 'win32' else ':'}config",
        "--add-data", f"VERSION{';' if sys.platform == 'win32' else ':'}.",
        "entry_win.py",
    ]
    print("PyInstaller 构建中……（约 1-3 分钟）")
    result = subprocess.run(cmd, cwd=str(repo), check=False)
    if result.returncode != 0:
        print("构建失败，见上方 PyInstaller 输出", file=sys.stderr)
        return result.returncode
    print("构建完成: dist/deepddw/deepddw.exe")
    print("验证: dist/deepddw/deepddw.exe 启动后访问 http://127.0.0.1:8500/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
