# deepDDW Windows 打包评估（2026-08-17）

> 背景：朋友提醒"nodejs 应用本身支持一键打包 exe"。评估该路线合理性，
> 以**便于后续维护升级**的方式开展 Windows 版本打包处理。

## 一、先澄清一个关键事实

**deepDDW 的主体不是 Node.js 应用**——它是 **Python (FastAPI) 网关**。
本仓库里的 Node.js 部分只有：
- `dsh`（DeepSeek Harness，官方 MIT，npm 包）——用户侧工作台，**我们不改它**
- 启动器/前端静态页（`frontend/`，纯静态 HTML，无构建链）

因此"nodejs 一键打包 exe"（如 electron-builder / pkg / nexe）**只适用于 dsh 工作台**，
不适用于 deepDDW 核心。deepDDW 核心的 Windows 化要走 **Python 打包** 路线。

## 二、两条可行路线对比

| 路线 | 工具 | 产出 | 优点 | 缺点 |
|---|---|---|---|---|
| **A. Python 原生打包（推荐）** | PyInstaller（one-dir + 自定义入口） | deepddw.exe + 依赖目录（绿色版） | 官方 Python 生态、无 Electron 重依赖、内网单文件替换即升级 | exe 启动略慢（解包）；首次打包需在 Windows 上做（跨平台打包不可靠） |
| **B. 容器化（WSL2/Docker Desktop）** | compose 文件已交付 | 与 Linux/macOS 完全一致 | 零平台差异、升级=重新 compose up | 用户需装 Docker Desktop（Windows 家庭版门槛）、非"一键 exe"体验 |
| C. Electron 外壳（不推荐） | electron-builder | deepddw-setup.exe（含浏览器壳） | 安装器体验好 | 重（~200MB）、把 FastAPI 网关也塞进去复杂度剧增、维护成本高 |

**结论：路线 A（PyInstaller one-dir）最贴合"便于维护升级"**——
升级时只需替换 `_internal` 里的 `core/` 与 `.pyc` 对应文件，或重新跑一次打包脚本。

## 三、推荐实施方式（维护升级友好）

### 1. 打包脚本（仓库内新增 `scripts/build_windows.py`，跨平台可写、Windows 上执行）

```python
# scripts/build_windows.py — 用法: python scripts/build_windows.py
# 在 Windows 主机（或 Windows CI runner）上执行：
#   pip install -r requirements.txt pyinstaller
#   python scripts/build_windows.py
# 产出: dist/deepddw/ （deepddw.exe + _internal/）
import subprocess, sys

def main():
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "deepddw",
        "--onedir",                      # one-dir：升级可局部替换，优于 onefile
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "mcp.server.fastmcp",
        "--collect-submodules", "core",
        "--collect-submodules", "plugins",
        "--add-data", "frontend;frontend",   # Windows 用 ; 分隔
        "--add-data", "config;config",
        "entry_win.py",                    # 见下
    ]
    subprocess.run(cmd, check=True)
    print("构建完成: dist/deepddw/deepddw.exe")

if __name__ == "__main__":
    main()
```

### 2. 入口文件 `entry_win.py`（1 个文件，把 uvicorn 启动包成 exe 入口）

```python
# entry_win.py — Windows 打包入口（等价 docker CMD: uvicorn core.main:app）
import multiprocessing
import uvicorn

if __name__ == "__main__":
    multiprocessing.freeze_support()  # PyInstaller 多进程安全
    uvicorn.run("core.main:app", host="0.0.0.0", port=8500)
```

### 3. CI 支持（可选，推荐 GitHub Actions windows-latest）

```yaml
# .github/workflows/windows-build.yml（简略）
# runs-on: windows-latest → pip install -r requirements.txt pyinstaller
# → python scripts/build_windows.py → upload-artifact dist/deepddw/
# 优点：不需要本地 Windows 机器；每次发布自动出 exe
```

### 4. 升级策略（维护友好的核心）

- **one-dir 布局**：`deepddw.exe` 只是薄壳，业务代码全在 `_internal/`。
  小版本升级 = 覆盖 `_internal/core/` + 重启，**不用重新打包**。
- **数据目录独立**：数据落在 `%USERPROFILE%\.deepddw\`（`DDW_DATA_DIR` 环境变量），
  exe 升级不碰用户数据。
- **配置沿用**：`.env` 同机制；Windows 路径用 `os.getenv` 兼容（现有代码已是 Path 抽象）。

## 四、风险与对策

| 风险 | 对策 |
|---|---|
| PyInstaller 在 Linux/macOS 上不能交叉打包 Windows | 用 GitHub Actions windows-latest 自动出包（不依赖本地） |
| lancedb/pydantic 等带 C 扩展的包 | PyInstaller `--collect-all lancedb`（hook 已较成熟）；若体积/兼容问题，Windows 默认降级纯关键词（设计已保证不阻塞） |
| uvicorn reload 在 exe 内不可用 | 生产模式本身不用 reload；本地开发仍走源码 |
| 杀毒软件误报（PyInstaller 通病） | one-dir + 官方数字签名（后续可选） |

## 五、结论

- **合理，但要用 Python 路线而非 Node 路线**：Electron/nexe 那条路是给 dsh 工作台用的，
  deepDDW 核心的 Windows 化 = **PyInstaller one-dir + GitHub Actions windows-latest CI**。
- 投入约 **0.5-1 天**（写脚本 + 试跑 + CI 排错），收益是"真正的绿色 exe + 可维护升级"。
- **建议执行顺序**（等你确认后再动工）：
  1. `scripts/build_windows.py` + `entry_win.py` 入库（跨平台无害，CI 里 Python 语法检查可过）
  2. 加 `.github/workflows/windows-build.yml`（windows-latest 自动出包）
  3. 首次构建产物验证（启动 exe → health → Token 门禁 → MCP 工具列表）
  4. README 增补 Windows 安装小节

> 本评估不涉及任何"把 dsh 改掉/注入"的内容——v2.1 定案（纯官方 MCP 接入）不变，
> Windows 打包只作用于 deepDDW 网关本体；dsh 工作台继续用官方 npm 安装。
