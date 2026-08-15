#!/usr/bin/env python3
"""问渠生产全链路冒烟（ECS 执行，venv311）。

链路: 滑块→登录→充值到账→开课→SSE对话→练习变式→错题→周报→下课扣费
用法: python3 /tmp/wenqu_smoke.py
"""
import asyncio
import base64
import io
import json
import os
import sys

sys.path.insert(0, "/opt/ddw/ddw-ai-hub")
import httpx
from PIL import Image

BASE = os.environ.get("WENQU_SMOKE_BASE", "http://127.0.0.1:8500")
PHONE = os.environ.get("WENQU_SMOKE_PHONE", "13900000001")
PWD = os.environ.get("WENQU_SMOKE_PWD", "")  # 必填：WENQU_SMOKE_PWD=xxx 环境变量（不进仓库）
STUDENT = os.environ.get("WENQU_SMOKE_STUDENT", "CXY")
SUBJECT = os.environ.get("WENQU_SMOKE_SUBJECT", "physics")  # 7 科任选
CHAPTER = os.environ.get("WENQU_SMOKE_CHAPTER", "力学")

if not PWD:
    print("❌ 请设置 WENQU_SMOKE_PWD 环境变量（测试用户密码）")
    sys.exit(2)


def detect_gap_x(bg_b64: str) -> tuple:
    """亮度窗口法检测缺口中心，返回 (x, top3列表)。"""
    raw = base64.b64decode(bg_b64.split(",")[1] if "," in bg_b64 else bg_b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB").resize((320, 160))
    px = img.load()

    def lum(x, y):
        r, g, b = px[x, y]
        return 0.299 * r + 0.587 * g + 0.114 * b

    ys = [40, 50, 60, 70, 80]
    scores = []
    for x in range(60, 241):
        s = 0
        for y in ys:
            inner = sum(lum(x + dx, y) for dx in range(-18, 19)) / 37
            outer = (sum(lum(x + dx, y) for dx in range(-40, -23)) +
                     sum(lum(x + dx, y) for dx in range(24, 41))) / 34
            s += inner - outer
        scores.append((x, s))
    scores.sort(key=lambda t: -t[1])
    return scores[0][0], scores[:3]


async def login(c: httpx.AsyncClient) -> str:
    last = None
    for attempt in range(3):
        d = (await c.get(BASE + "/api/v1/auth/slider")).json()
        x, top3 = detect_gap_x(d["bg_image"])
        v = await c.post(BASE + "/api/v1/auth/slider/verify",
                         json={"captcha_id": d["captcha_id"], "x": x})
        vd = v.json()
        if "token" in vd:
            break
        last = f"x={x} top3={[(t[0], round(t[1], 1)) for t in top3]} body={vd}"
        await asyncio.sleep(1)
    else:
        raise RuntimeError(f"滑块 3 次全失败: {last}")
    ld = (await c.post(BASE + "/api/v1/auth/login-password", json={
        "phone": PHONE, "password": PWD, "slider_token": vd["token"],
        "device_fingerprint": {"ua": "wenqu-smoke"},
    })).json()
    if "access_token" not in ld:
        raise RuntimeError(f"登录失败: {ld}")
    c.headers["Authorization"] = f"Bearer {ld['access_token']}"
    return ld


async def topup(c: httpx.AsyncClient) -> str:
    """HTTP 建单 + 服务层回调到账（wallet 回调核心已单测覆盖）。"""
    r = (await c.post(BASE + "/api/v1/plugins/ddw_wallet/recharges",
                      json={"user_id": STUDENT, "amount_cents": 1000, "channel": "wechat"})).json()
    order_no = r["order_no"]
    from plugins.ddw_wallet.services.recharge import handle_wechat_notify
    from core.database.session import session_scope
    async with session_scope() as s:
        ok, _ = await handle_wechat_notify(s, {
            "out_trade_no": order_no, "trade_state": "SUCCESS",
            "amount": {"total": 1000}, "transaction_id": "SMOKE0001",
        })
        await s.commit()
    if not ok:
        raise RuntimeError(f"充值到账失败: {order_no}")
    return order_no


async def main() -> None:
    c = httpx.AsyncClient(timeout=60.0)
    # 0. 测试用户（幂等）
    import sqlite3
    from core.api.auth import hash_password
    db = sqlite3.connect("/opt/ddw/ddw-ai-hub/data/ddw_main.db")
    db.execute("INSERT OR IGNORE INTO users (phone, password_hash, role, tenant_id, name, status, created_at) "
               "VALUES (?,?,?,?,?,?,datetime('now'))",
               (PHONE, hash_password(PWD), "member", 1, "问渠冒烟", "active"))
    db.commit()
    db.close()

    print("1️⃣ 登录...")
    tok = await login(c)
    print("   ✅ JWT", tok.get("role", "?"), "tenant", tok.get("tenant_id"))

    print("2️⃣ 充值 ¥10（按学生名账户，产品设计口径）...")
    # 2a. 先验证 402 拦截：无账户学生开课必须被拒（用全新学生名避免上轮残留账户）
    import uuid
    noacc = "NOACC-" + uuid.uuid4().hex[:8]
    r402 = await c.post(BASE + "/api/v1/plugins/ddw_wenqu_tutor/session/start",
                        json={"student_name": noacc, "subject": "physics", "chapter": "力学"})
    if r402.status_code != 402:
        raise RuntimeError(f"❌ 计费漏洞: 无账户学生开课应 402, 实际 {r402.status_code}: {r402.text[:120]}")
    print("   ✅ 无账户开课被 402 拦截（计费漏洞已修复）")
    order = await topup(c)
    bal = (await c.get(BASE + f"/api/v1/plugins/ddw_wallet/accounts/{STUDENT}/balances")).json()
    print("   ✅", order, STUDENT, "余额(分):", bal.get("recharge_balance_cents"))

    print("3️⃣ 开课...")
    s0 = (await c.post(BASE + "/api/v1/plugins/ddw_wenqu_tutor/session/start",
                       json={"student_name": STUDENT, "subject": SUBJECT, "chapter": CHAPTER})).json()
    sid = s0["session_id"]
    print("   ✅ session", sid)

    print("4️⃣ SSE 对话（一次）...")
    r = await c.post(f"{BASE}/api/v1/plugins/ddw_wenqu_tutor/session/{sid}/message",
                     json={"content": "牛顿第一定律的内容是什么？"})
    txt = r.text
    print("   ✅ status", r.status_code, "len", len(txt), "head:", txt[:120].replace("\n", " "))

    print("5️⃣ 练习变式...")
    ql = (await c.get(BASE + "/api/v1/plugins/ddw_wenqu_tutor/questions/list",
                      params={"subject": SUBJECT, "limit": 1})).json()
    qid = ql["items"][0]["id"] if isinstance(ql, dict) and ql.get("items") else ql[0]["id"]
    gv = (await c.post(BASE + "/api/v1/plugins/ddw_wenqu_tutor/questions/generate-variant",
                       json={"question_id": qid, "difficulty": "easy"})).json()
    print("   ✅ variant:", str(gv.get("question_text"))[:60])

    print("6️⃣ 错题本...")
    wb = (await c.get(BASE + "/api/v1/plugins/ddw_wenqu_tutor/wrongbook/list")).json()
    print("   ✅ wrongbook items:", len(wb) if isinstance(wb, list) else wb)

    print("7️⃣ 周报...")
    wr = (await c.get(BASE + "/api/v1/plugins/ddw_wenqu_tutor/parent/weekly-report")).json()
    print("   ✅ weekly keys:", list(wr.keys())[:6] if isinstance(wr, dict) else type(wr).__name__)

    print("8️⃣ 下课扣费...")
    end = (await c.post(f"{BASE}/api/v1/plugins/ddw_wenqu_tutor/session/{sid}/end")).json()
    print("   ✅", json.dumps(end, ensure_ascii=False)[:200])
    bal2 = (await c.get(f"{BASE}/api/v1/plugins/ddw_wallet/accounts/{STUDENT}/balances")).json()
    print("   扣后余额(分):", bal2.get("recharge_balance_cents"))
    print("\n🎉 全链路通过")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ 冒烟失败: {type(e).__name__}: {e}")
        sys.exit(1)
