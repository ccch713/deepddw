#!/usr/bin/env python3
"""本地开发库演示数据（仅 32G 本地 ddw_main.db，不碰 ECS）。
生成：demo 用户 + 35 天 usage_logs + 6 月 wallet 充值 + 销售漏斗数据。"""
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.api.auth import hash_password  # noqa: E402 服务端一致：SHA256 预哈希 + bcrypt(12)

DB = "/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/data/ddw_main.db"
random.seed(42)

EVENTS = [
    ("ddw_wenqu_tutor", 0.22), ("ddw_clinic_cs", 0.18), ("ddw_wallet", 0.12),
    ("ddw_bid_writer", 0.10), ("ddw_esg_report", 0.08), ("ddw_chat", 0.12),
    ("ddw_kb_retrieval", 0.06), ("ddw_lead_claim", 0.05), ("ddw_saas_billing", 0.04),
    ("ddw_online_cs", 0.03),
]
PLUGIN_NAMES = [e[0] for e in EVENTS]
WEIGHTS = [e[1] for e in EVENTS]

c = sqlite3.connect(DB)
c.execute("PRAGMA foreign_keys=OFF")

# 0. 租户（幂等）
cur = c.execute("SELECT COUNT(*) FROM tenants WHERE id=1")
if cur.fetchone()[0] == 0:
    c.execute(
        "INSERT INTO tenants (id, name, plan, status, contact_phone, created_at, updated_at) "
        "VALUES (1,'演示租户','enterprise','active','13800000000',datetime('now'),datetime('now'))"
    )
    print("✅ 租户 1 已创建")
else:
    print("⏭️ 租户已存在")

# 1. 用户（幂等：已存在则修正哈希，不存在则插入）
pwd = hash_password("demo123")
cur = c.execute("SELECT COUNT(*) FROM users WHERE phone='13800000000'")
if cur.fetchone()[0] == 0:
    c.execute(
        "INSERT INTO users (phone, password_hash, role, tenant_id, name, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("13800000000", pwd, "member", 1, "演示用户", "active", datetime.now().isoformat()),
    )
    for i in range(2, 7):
        c.execute(
            "INSERT INTO users (phone, password_hash, role, tenant_id, name, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"1380000000{i}", pwd, "member", 1, f"演示用户{i}", "active", datetime.now().isoformat()),
        )
    print("✅ 用户 6 个（13800000000 / demo123）")
else:
    c.execute("UPDATE users SET password_hash=? WHERE phone='13800000000'", (pwd,))
    print("⏭️ 用户已存在，密码哈希已修正为服务端兼容格式")

# 2. usage_logs 近 35 天
c.execute("DELETE FROM usage_logs")
now = datetime.now()
cnt = 0
log_id = 1
for day in range(34, -1, -1):
    d = now - timedelta(days=day)
    n = random.randint(8, 20)
    for _ in range(n):
        et = random.choices(PLUGIN_NAMES, weights=WEIGHTS)[0]
        uid = random.randint(1, 6)
        tokens = random.randint(100, 5000)
        ts = d.replace(hour=random.randint(8, 22), minute=random.randint(0, 59), second=random.randint(0, 59))
        c.execute(
            "INSERT INTO usage_logs (id, tenant_id, user_id, event_type, tokens_used, created_at, updated_at) "
            "VALUES (?,1,?,?,?,?,?)",
            (log_id, uid, et, tokens, ts.strftime("%Y-%m-%d %H:%M:%S"), ts.strftime("%Y-%m-%d %H:%M:%S")),
        )
        log_id += 1
        cnt += 1
print(f"✅ usage_logs {cnt} 条（35 天 × 8-20 条/天）")

# 3. wallet 充值近 6 月（paid 为主 → MRR）
c.execute("DELETE FROM dw_wallet_recharge_orders")
cnt = 0
for m in range(5, -1, -1):
    month_start = (now - timedelta(days=30 * m)).replace(day=1, hour=10, minute=0, second=0)
    n = random.randint(2, 5)
    for i in range(n):
        amount = random.choice([9900, 19900, 29900, 49900, 99900, 149900])
        paid = random.random() > 0.2
        ts = month_start + timedelta(days=random.randint(0, 27), hours=random.randint(0, 10))
        c.execute(
            "INSERT INTO dw_wallet_recharge_orders "
            "(order_no, user_id, tenant_id, amount_cents, channel, status, paid_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                f"DEMO{m}{i}{random.randint(1000,9999)}", f"u{random.randint(1,6)}", "1",
                amount, random.choice(["wechat", "alipay"]),
                "paid" if paid else "pending",
                ts.strftime("%Y-%m-%d %H:%M:%S") if paid else None,
                ts.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        cnt += 1
print(f"✅ wallet 充值 {cnt} 笔（近 6 月）")

# 4. 漏斗数据（真实列名 + 补 crm_companies）
c.execute("DELETE FROM crm_lead_claims")
c.execute("DELETE FROM crm_opportunities")
c.execute("DELETE FROM crm_orders")
c.execute("DELETE FROM crm_companies")
now_iso = now.strftime("%Y-%m-%d %H:%M:%S")
for i in range(5):
    c.execute(
        "INSERT INTO crm_companies (id, name, industry, certification_status, status, tenant_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (i + 1, f"演示公司{i+1}", random.choice(["制造业", "医疗", "教育"]), "not_submitted", "active", 1, now_iso, now_iso),
    )
for i in range(10):
    c.execute(
        "INSERT INTO crm_lead_claims (partner_id, company_id, contact_person, opportunity_source, expected_amount, protection_days, status, tenant_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (1, random.randint(1, 5), f"联系人{i+1}", random.choice(["展会", "转介绍", "官网"]),
         random.randint(50000, 300000), 30, "claimed", 1, now_iso, now_iso),
    )
for i in range(6):
    c.execute(
        "INSERT INTO crm_opportunities (company_id, name, source, estimated_amount, stage, probability, status, tenant_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (random.randint(1, 5), f"演示商机{i+1}", "转介绍", random.randint(50000, 500000),
         random.choice(["qualify", "proposal", "negotiation"]), random.randint(30, 80), "open", 1, now_iso, now_iso),
    )
for i in range(4):
    c.execute(
        "INSERT INTO crm_orders (company_id, order_no, title, total_amount, status, tenant_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (random.randint(1, 5), f"ORD-DEMO-{i+1}", f"演示订单{i+1}", random.randint(30000, 300000), "paid", 1, now_iso, now_iso),
    )
print("✅ 漏斗：5 公司 / 10 线索 / 6 商机 / 4 订单")

c.commit()
c.close()
print("🎉 演示数据完成")
