"""Promotion and commission logic for ESG payment plugin.

Translated from TypeScript source.
"""
from __future__ import annotations

import random
import string
from typing import Optional

from .models import (
    Promotion,
)

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

PLANS = {
    "free": {
        "name": "免费体验",
        "price_cents": 0,
        "description": "1次基础评估（单框架）",
    },
    "single": {
        "name": "单次评估",
        "price_cents": 990,
        "description": "1次完整评估（单框架+PDF）",
    },
    "all-single": {
        "name": "单次多模",
        "price_cents": 14900,
        "description": "1次多框架评估（5框架+跨框架对比）",
    },
    "yearly": {
        "name": "企业定制",
        "price_cents": 199900,
        "description": "全框架+定制报告+顾问服务",
    },
}

# ---------------------------------------------------------------------------
# Promotion config
# ---------------------------------------------------------------------------

PROMO_CONFIG = {
    "max_promoters_soft": 20,
    "max_promoters_hard": 50,
    "commission_tiers": [
        {"min_amount_cents": 990, "rate": 0.30},
        {"min_amount_cents": 14900, "rate": 0.30},
        {"min_amount_cents": 199900, "rate": 0.35},
    ],
    "cold_start_bonus_rate": 0.05,
    "cold_start_count": 5,
    "attribution_days": 30,
    "withdrawal_min_cents": 10000,       # ¥100
    "withdrawal_max_cents": 500000,      # ¥5000
    "withdrawal_daily_max_cents": 1000000,  # ¥10000
    "withdrawal_monthly_limit": 3,
    "coupon_amounts": {
        "welcome": 1000,
        "first_single": 3000,
        "first_all": 5000,
        "first_yearly": 20000,
    },
    "coupon_validity_days": 30,
    "prefixes": ["HY", "QZ", "XS", "VIP"],
}


# ---------------------------------------------------------------------------
# Promo code generation
# ---------------------------------------------------------------------------

def generate_promo_code(prefix: str = "HY") -> str:
    """Generate a 9-char promo code: 2-char prefix + 6 random + 1 check digit."""
    body = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    raw = prefix + body
    check = sum(ord(c) for c in raw) % 10
    return raw + str(check)


# ---------------------------------------------------------------------------
# Commission calculation
# ---------------------------------------------------------------------------

def calculate_commission(amount_cents: int, promoter_pay_count: int) -> tuple[int, float]:
    """Returns (commission_cents, rate)."""
    rate = 0.30  # default
    for tier in PROMO_CONFIG["commission_tiers"]:
        if amount_cents >= tier["min_amount_cents"]:
            rate = tier["rate"]
    # Cold start bonus
    if promoter_pay_count < PROMO_CONFIG["cold_start_count"]:
        rate += PROMO_CONFIG["cold_start_bonus_rate"]
    commission = int(amount_cents * rate)
    return commission, rate


# ---------------------------------------------------------------------------
# Coupon helper
# ---------------------------------------------------------------------------

def coupon_amount_for_plan(plan_id: str) -> int:
    """Return coupon amount (cents) for a plan's first-time coupon, or 0."""
    mapping = {
        "single": PROMO_CONFIG["coupon_amounts"]["first_single"],
        "all-single": PROMO_CONFIG["coupon_amounts"]["first_all"],
        "yearly": PROMO_CONFIG["coupon_amounts"]["first_yearly"],
    }
    return mapping.get(plan_id, 0)


# ---------------------------------------------------------------------------
# Order final-price calculation
# ---------------------------------------------------------------------------

def compute_order_amounts(
    plan_id: str,
    promo_code: Optional[Promotion] = None,
    coupon_amount: int = 0,
) -> dict:
    """Compute original, discount, coupon, and final amounts for an order."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")
    original = plan["price_cents"]
    discount = 0
    if promo_code:
        discount = int(original * promo_code.commission_rate) if promo_code.commission_rate else 0
    final = max(0, original - discount - coupon_amount)
    return {
        "original_amount": original,
        "discount_amount": discount,
        "coupon_amount": coupon_amount,
        "final_amount": final,
    }
