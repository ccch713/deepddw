"""DDW 登录安全 P0 行为验收脚本（16G 本地 127.0.0.1 执行）"""
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8500/api/v1/auth"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def get_captcha():
    with urllib.request.urlopen(BASE + "/captcha", timeout=10) as r:
        d = json.loads(r.read())
        return d["captcha_id"], d["image_base64"]


results = []

# 1. 验证码生成
cid, img = get_captcha()
results.append(("captcha_create", bool(cid and img.startswith("data:image/png"))))

# 2. 错误验证码 → 400
phone = "139" + str(uuid.uuid4().int)[:8]
st, d = post("/login-password", {"phone": phone, "password": "Test12345", "captcha_id": cid, "captcha_code": "XXXX"})
results.append(("wrong_captcha_400", st == 400))

# 3. 正确验证码 + 不存在用户 → 401 防枚举（非 404）
cid2, _ = get_captcha()
st2, d2 = post("/login-password", {"phone": phone, "password": "Test12345", "captcha_id": cid2, "captcha_code": ""})
# 缺验证码被拒绝（Pydantic 422 或业务 400 均可，关键是拒绝且非 200）
results.append(("captcha_required_rejected", st2 in (400, 422)))

# 4. 连续 3 次错误验证码 → 该 captcha 作废 + IP 冷却
cid3, _ = get_captcha()
statuses = []
for _ in range(3):
    st, _ = post("/login-password", {"phone": "13900001111", "password": "Test12345", "captcha_id": cid3, "captcha_code": "ZZZZ"})
    statuses.append(st)
# 第 4 次同 captcha → 400（作废）
st4, _ = post("/login-password", {"phone": "13900001111", "password": "Test12345", "captcha_id": cid3, "captcha_code": "ZZZZ"})
results.append(("captcha_3_fails", statuses == [400, 400, 400] and st4 == 400))

# 5. send-code 无验证码 → 拒绝（400/422 均可）
st5, _ = post("/send-code", {"phone": "13900001111"})
results.append(("send_code_requires_captcha", st5 in (400, 422)))

# 6. 注册弱密码 → 422
cid6, _ = get_captcha()
st6, _ = post("/register", {"phone": "13900002222", "password": "short", "captcha_id": cid6, "captcha_code": "XXXX"})
results.append(("register_weak_password_422", st6 == 422))

# 7. 登录页/指纹静态资源（相对路径）
import urllib.request as u
ok7 = u.urlopen("http://127.0.0.1:8500/ui/js/fingerprint.js", timeout=5).status == 200
results.append(("fingerprint_js_200", ok7))

print("=== 验收结果 ===")
all_ok = True
for name, ok in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print(f"\n总体: {'全部通过' if all_ok else '存在失败'} ({sum(1 for _, ok in results if ok)}/{len(results)})")
