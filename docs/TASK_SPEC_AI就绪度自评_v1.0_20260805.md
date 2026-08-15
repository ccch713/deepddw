# TASK_SPEC · ddw_ai_readiness 插件（企业 AI 就绪度自评）v1.0

> 开发 Agent 唯一依据。严格按第十二节开发顺序执行：写一个文件 → py_compile+ruff → 写测试 → pytest 通过 → 再写下一个。每完成一个模块 git commit 一次。全部完成后跑全量 pytest 和 ruff 并汇报结果。

## 一、项目背景

DDW AI HUB 获客工具链：客户自助完成"企业 AI 就绪度自评问卷"（前端 HTML 已交付，见 `商务物料/DDW-就绪度自评/ddw-ai-readiness.html`），本插件负责**接收问卷答案 → 服务端评分（防篡改）→ 商机分级（A/B/C）→ SQLite 入库 → 销售端查询/统计**。

- 定位：私有商业插件（**禁止推 GitHub，只进 Gitea/ddw-ai-hub 主仓**）
- 插件名：`ddw_ai_readiness`（下划线目录，必须）
- 参照模板：`plugins/ddw_searxng/`（最近上线成功范例，结构与鉴权模式照抄）

## 二、目录结构（必须完整）

```
plugins/ddw_ai_readiness/
├── __init__.py          # PLUGIN_NAME + VERSION
├── plugin.py            # class Plugin(PluginBase)，照抄 searxng 模板
├── router.py            # build_router() 工厂函数
├── schemas.py           # Pydantic 请求/响应模型
├── services.py          # 评分逻辑 + SQLite 存储
├── manifest.yaml        # 插件元数据
├── README.md            # 中文说明
├── README_EN.md         # 英文说明（GitHub 备用，虽然私有）
└── tests/
    ├── __init__.py
    └── test_readiness.py   # 10 条 pytest 用例（见第十节）
```

## 三、__init__.py

```python
PLUGIN_NAME = "ddw_ai_readiness"
VERSION = "0.1.0"
```

## 四、plugin.py（照抄 searxng 模式）

```python
"""DDW AI Readiness 插件 Plugin 类。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """企业 AI 就绪度自评插件。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("%s plugin %s initialized", PLUGIN_NAME, VERSION)


__all__ = ["Plugin"]
```

> ⚠️ 若 PluginBase 的 `__init__` 需要 manifest 参数：`class Plugin(PluginBase):` 不带自定义 `__init__`（参照 searxng），由基类处理。严禁自定义签名导致 init failed。

## 五、schemas.py（Pydantic 模型）

```python
"""ddw_ai_readiness Pydantic 模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DataCat(BaseModel):
    """单个数据类别的三个回答（0-2 分）。"""
    a: Optional[int] = Field(None, ge=0, le=2)  # 有数据
    b: Optional[int] = Field(None, ge=0, le=2)  # 耗人工
    c: Optional[int] = Field(None, ge=0, le=2)  # 丢不起


class SubmissionIn(BaseModel):
    """测评提交请求。company/name/phone 选填（匿名也可提交）。"""
    company: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    q1: Optional[int] = Field(None, ge=0, le=3)
    q2: Optional[int] = Field(None, ge=0, le=3)
    q3: Optional[int] = Field(None, ge=0, le=2)
    q4: Optional[int] = Field(None, ge=0, le=3)
    q5: Optional[int] = Field(None, ge=0, le=3)
    q6: list[str] = Field(default_factory=list)
    q7: Optional[int] = Field(None, ge=0, le=3)
    d: dict[str, DataCat] = Field(default_factory=dict)
    scenes: list[str] = Field(default_factory=list)


class SubmissionOut(BaseModel):
    """提交响应：id + 服务端评分结果。"""
    id: int
    score1: int
    grade1: str        # A / B / C（就绪度）
    veto: bool         # 一票否决是否触发
    score2: int
    grade_points: int  # 3-9 商机总分
    grade: str         # A级 / B级 / C级（商机分级）
    created_at: str


class SubmissionDetail(SubmissionOut):
    """详情：含全部原始答案。"""
    company: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    q1: Optional[int] = None
    q2: Optional[int] = None
    q3: Optional[int] = None
    q4: Optional[int] = None
    q5: Optional[int] = None
    q6: list[str] = []
    q7: Optional[int] = None
    d: dict = {}
    scenes: list[str] = []


class StatsOut(BaseModel):
    total: int
    grade_a: int
    grade_b: int
    grade_c: int
    grade1_a: int
    grade1_b: int
    grade1_c: int
```

## 六、services.py（核心逻辑，直接使用）

```python
"""ddw_ai_readiness 评分与存储逻辑。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "readiness.db"
_lock = threading.Lock()

GRADE1_A = 12   # 就绪度 A 阈值（含）
GRADE1_B = 7    # 就绪度 B 阈值（含）

VALID_SCENES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
VALID_CATS = {"D1", "D2", "D3", "D4"}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT, name TEXT, phone TEXT,
            q1 INTEGER, q2 INTEGER, q3 INTEGER, q4 INTEGER, q5 INTEGER,
            q6 TEXT, q7 INTEGER,
            d TEXT, scenes TEXT,
            score1 INTEGER, grade1 TEXT, veto INTEGER,
            score2 INTEGER, grade_points INTEGER, grade TEXT,
            created_at TEXT
        )"""
    )
    return conn


def score_submission(data: dict) -> dict:
    """服务端评分（前端算分仅作即时反馈，入库以本函数为准）。"""
    def _int(v, lo, hi):
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if lo <= v <= hi else None

    q1 = _int(data.get("q1"), 0, 3)
    q2 = _int(data.get("q2"), 0, 3)
    q3 = _int(data.get("q3"), 0, 2)
    q4 = _int(data.get("q4"), 0, 3)
    q5 = _int(data.get("q5"), 0, 3)
    q7 = _int(data.get("q7"), 0, 3)
    missing = [x for x in (q1, q2, q3, q4, q5, q7) if x is None]
    if missing:
        raise ValueError("q1-q5/q7 必须为有效整数")

    # 第1段：就绪度
    score1 = q1 + q2 + q3 + q4 + q5 + q7
    veto = (q1 == 0 and q3 == 0)
    grade1 = "C" if veto else ("A" if score1 >= GRADE1_A else ("B" if score1 >= GRADE1_B else "C"))

    # 第2段：数据自评（缺失项按 0 处理）
    d = data.get("d") or {}
    score2 = 0
    for cat in VALID_CATS:
        c = d.get(cat) or {}
        for key in ("a", "b", "c"):
            v = _int(c.get(key), 0, 2)
            score2 += v if v is not None else 0

    # 商机分级：就绪度(1-3) + 痛点(1-3) + 预算决策(1-3)
    gp1 = {"A": 3, "B": 2, "C": 1}[grade1]
    gp2 = 3 if q4 >= 3 else (2 if q4 >= 2 else 1)
    gp3 = 3 if q7 >= 2 else (2 if q7 >= 1 else 1)
    grade_points = gp1 + gp2 + gp3
    grade = "A级" if grade_points >= 7 else ("B级" if grade_points >= 5 else "C级")

    return {
        "score1": score1, "grade1": grade1, "veto": veto,
        "score2": score2, "grade_points": grade_points, "grade": grade,
    }


def save_submission(payload: dict, scores: dict) -> int:
    scenes = [s for s in (payload.get("scenes") or []) if s in VALID_SCENES][:3]
    q6 = [s for s in (payload.get("q6") or [])][:10]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        conn = _conn()
        cur = conn.execute(
            """INSERT INTO submissions
               (company,name,phone,q1,q2,q3,q4,q5,q6,q7,d,scenes,
                score1,grade1,veto,score2,grade_points,grade,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (payload.get("company") or "")[:100],
                (payload.get("name") or "")[:50],
                (payload.get("phone") or "")[:50],
                payload.get("q1"), payload.get("q2"), payload.get("q3"),
                payload.get("q4"), payload.get("q5"),
                json.dumps(q6, ensure_ascii=False),
                payload.get("q7"),
                json.dumps(payload.get("d") or {}, ensure_ascii=False),
                json.dumps(scenes, ensure_ascii=False),
                scores["score1"], scores["grade1"], int(scores["veto"]),
                scores["score2"], scores["grade_points"], scores["grade"],
                now,
            ),
        )
        conn.commit()
        sid = cur.lastrowid
        conn.close()
    return sid


def get_submission(sid: int) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def list_submissions(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM submissions ORDER BY id DESC LIMIT ? OFFSET ?",
        (max(1, min(limit, 200)), max(0, offset)),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_stats() -> dict:
    conn = _conn()
    row = conn.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN grade='A级' THEN 1 ELSE 0 END) ga,
                  SUM(CASE WHEN grade='B级' THEN 1 ELSE 0 END) gb,
                  SUM(CASE WHEN grade='C级' THEN 1 ELSE 0 END) gc,
                  SUM(CASE WHEN grade1='A' THEN 1 ELSE 0 END) g1a,
                  SUM(CASE WHEN grade1='B' THEN 1 ELSE 0 END) g1b,
                  SUM(CASE WHEN grade1='C' THEN 1 ELSE 0 END) g1c
           FROM submissions"""
    ).fetchone()
    conn.close()
    return {
        "total": row["total"] or 0,
        "grade_a": row["ga"] or 0,
        "grade_b": row["gb"] or 0,
        "grade_c": row["gc"] or 0,
        "grade1_a": row["g1a"] or 0,
        "grade1_b": row["g1b"] or 0,
        "grade1_c": row["g1c"] or 0,
    }


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("q6", "d", "scenes"):
        try:
            d[k] = json.loads(d[k] or "[]" if k != "d" else d[k] or "{}")
        except (json.JSONDecodeError, TypeError):
            d[k] = [] if k != "d" else {}
    return d
```

## 七、router.py（照抄 searxng 的 build_router 模式）

```python
"""ddw_ai_readiness API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .schemas import StatsOut, SubmissionDetail, SubmissionIn, SubmissionOut
from .services import (get_stats, get_submission, list_submissions,
                       save_submission, score_submission)

router = APIRouter(prefix="/api/v1/plugins/ddw_ai_readiness", tags=["ddw_ai_readiness"])


def build_router() -> APIRouter:
    @router.post("/submissions", response_model=SubmissionOut)
    async def submit(payload: SubmissionIn):
        """提交测评（匿名可提交，供客户自助入口调用）。"""
        try:
            scores = score_submission(payload.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        sid = save_submission(payload.model_dump(), scores)
        return SubmissionOut(id=sid, created_at="", **scores)

    @router.get("/submissions", response_model=list[SubmissionDetail])
    async def list_all(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        """销售端列表（内部使用，鉴权模式参照 ddw_searxng）。"""
        return list_submissions(limit, offset)

    @router.get("/submissions/{sid}", response_model=SubmissionDetail)
    async def detail(sid: int):
        row = get_submission(sid)
        if not row:
            raise HTTPException(status_code=404, detail="submission not found")
        return row

    @router.get("/stats", response_model=StatsOut)
    async def stats():
        return get_stats()

    @router.get("/health")
    async def health():
        return {"plugin": "ddw_ai_readiness", "version": "0.1.0", "status": "ok"}

    return router
```

> ⚠️ 鉴权：**参照 ddw_searxng 的现有实现**。若 ddw_searxng 对列表/详情接口用了 `current_user` 依赖，保持一致（内部查询接口需登录）；`POST /submissions` 和 `/health` 必须匿名可访问（客户自助入口）。若 ddw_searxng 全部接口都匿名，则本插件全部匿名并在 README 注明"生产部署时建议由 Caddy/网关层加访问控制"。

## 八、manifest.yaml

```yaml
name: ddw_ai_readiness
version: 0.1.0
description: 企业 AI 就绪度自评：问卷答案接收、服务端评分、商机分级（A/B/C）、销售端查询统计
author: DDW Team
license: proprietary
```

## 九、README.md / README_EN.md

简要说明：功能、API 端点表、部署方式（SQLite 自动建库，零配置）、前端入口（`商务物料/DDW-就绪度自评/ddw-ai-readiness.html` 的 API_BASE 配置）。

## 十、测试用例（tests/test_readiness.py，10 条）

> 测试用临时 SQLite（monkeypatch services.DB_PATH 到 tmp_path），不污染真实 data/。

1. **test_high_readiness_grade_a**：q1=3,q2=3,q3=2,q4=3,q5=2,q7=2，d 全 2 分，scenes=[S5,S1,S3] → score1=15, grade1="A", veto=False, grade="A级"
2. **test_veto_rule**：q1=0,q3=0，其余全 3 → veto=True, grade1="C"（即使 score1 高）
3. **test_low_score_grade_c**：全 0 分 → grade1="C", grade="C级"
4. **test_mid_score_grade_b**：q1=2,q2=1,q3=1,q4=1,q5=1,q7=1 → score1=7 → grade1="B"
5. **test_score2_computation**：D1 全 2、其余全 0 → score2=6
6. **test_missing_q_raises**：q4=None → score_submission 抛 ValueError → API 422
7. **test_submission_persist**：save_submission + get_submission 回读字段一致（q6/scenes JSON 反序列化正确）
8. **test_list_and_stats**：插入 3 条（A/B/C 各一）→ list 返回 3 条倒序、stats 计数正确
9. **test_invalid_scenes_filtered**：scenes 含非法值 ["S99"] → 入库后 scenes=[]（被过滤）
10. **test_api_endpoints**：用 FastAPI TestClient 调 POST /submissions 200 + GET /stats 200 + GET /health 200

## 十一、验收标准

| 项 | 标准 |
|:--|:--|
| pytest | tests/ 10 条全过（含 TestClient 集成） |
| ruff | `ruff check plugins/ddw_ai_readiness/` 0 errors |
| py_compile | 所有 .py 通过 |
| 加载 | `python -c "from plugins.ddw_ai_readiness.plugin import Plugin; print(Plugin)"` 无 ImportError |
| 数据 | data/readiness.db 自动创建，重启不丢 |

## 十二、开发顺序（严格按序，写一个验一个）

```
1. __init__.py → py_compile
2. schemas.py → py_compile + ruff
3. services.py → py_compile + ruff
4. router.py → py_compile + ruff
5. plugin.py → py_compile + ruff
6. manifest.yaml + README.md + README_EN.md
7. tests/test_readiness.py → pytest（每条用例逐条过）
8. 全量验证：pytest tests/test_readiness.py -v + ruff check + 加载测试
9. git add + commit（信息：feat(readiness): ddw_ai_readiness 插件 v0.1.0）
10. 汇报：文件清单 + pytest/ruff 结果
```

## 十三、禁止事项

1. **禁止推 GitHub**（私有商业插件，只进 ddw-ai-hub 主仓 Gitea）
2. 禁止改 ddw_searxng 及其他已有插件
3. 禁止引入新依赖（只用 fastapi/pydantic/sqlite3 标准库）
4. 禁止在代码中写死任何 API Key / 密钥
5. 禁止删除 plugins/ 下其他任何文件
6. 禁止给 Plugin 自定义 `__init__` 签名（参照 searxng，避免 init failed）
7. 禁止格式化或重构其他目录文件
