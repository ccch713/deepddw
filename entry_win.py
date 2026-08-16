"""deepDDW Windows 打包入口（PyInstaller exe 的启动点）。

等价 docker CMD: python -m uvicorn core.main:app --host 0.0.0.0 --port 8500
PyInstaller 冻结环境必须走本入口（uvicorn main 字符串引用的模块需显式导入）。
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def _bootstrap() -> None:
    """PyInstaller one-dir 下把 _internal 加入 sys.path（保证 core 可导入）。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        internal = os.path.join(base, "_internal")
        if os.path.isdir(internal) and internal not in sys.path:
            sys.path.insert(0, internal)
        if base not in sys.path:
            sys.path.insert(0, base)


def main() -> None:
    _bootstrap()
    import uvicorn

    from core.config import get_tls_config

    host = os.environ.get("DDW_HOST", "0.0.0.0")
    port = int(os.environ.get("DDW_PORT", "8500"))
    kwargs: dict = {"reload": False}
    # P1-2（multidevice）：可选 TLS——deployment.yaml security.tls.* / env 启用
    tls = get_tls_config()
    if tls.get("enabled") and tls.get("cert_file") and tls.get("key_file"):
        kwargs["ssl_certfile"] = tls["cert_file"]
        kwargs["ssl_keyfile"] = tls["key_file"]
        if tls.get("port"):
            port = int(tls["port"])
        print(f"TLS enabled on port {port} ({tls['cert_file']})")
    uvicorn.run("core.main:app", host=host, port=port, **kwargs)


if __name__ == "__main__":
    # PyInstaller 多进程安全（uvicorn/内部 worker 场景）
    multiprocessing.freeze_support()
    main()
