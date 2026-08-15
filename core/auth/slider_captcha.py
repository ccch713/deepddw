"""AJ-Captcha 风格拼图滑块验证码（Pillow 实现，零新依赖）。

生成 320x160 背景图（随机渐变+几何图形）+ 50x50 拼图块（透明底）。
存储：Redis 优先（ddw:slider:{captcha_id} TTL 120s），不可用降级内存 dict。
校验：|x - x_target| <= 5px 即通过，通过后生成一次性 token（TTL 300s）。
限流：同 IP 3 次失败 → 滑块作废 + 60s 冷却。
"""

from __future__ import annotations

import base64
import io
import logging
import random
import time
import uuid
from typing import Optional, Tuple

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SLIDER_TTL = 120
SLIDER_TOKEN_TTL = 300
SLIDER_TOLERANCE = 5
MAX_FAILS = 3
FAIL_COOLDOWN = 60

BG_WIDTH = 320
BG_HEIGHT = 160
PUZZLE_SIZE = 50
X_RANGE = (60, 240)
Y_MIN = 30
Y_MAX = 90

# ---------------------------------------------------------------------------
# Redis 连接复用 auth.py 的 _get_redis
# ---------------------------------------------------------------------------
_redis_failed_logged = False


def _get_redis():
    global _redis_failed_logged
    try:
        from core.api.auth import _get_redis as _auth_get_redis
        return _auth_get_redis()
    except Exception:
        if not _redis_failed_logged:
            logger.warning("slider captcha redis unavailable, using in-memory store")
            _redis_failed_logged = True
        return None


# ---------------------------------------------------------------------------
# 内存降级存储
# ---------------------------------------------------------------------------
_SLIDER_STORE: dict[str, Tuple[int, float]] = {}
_SLIDER_TOKEN_STORE: dict[str, Tuple[str, float]] = {}
_SLIDER_FAIL_STORE: dict[str, Tuple[int, float]] = {}
_SLIDER_IP_COOLDOWN: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Redis 键
# ---------------------------------------------------------------------------

def _redis_slider_key(captcha_id: str) -> str:
    return f"ddw:slider:{captcha_id}"


def _redis_token_key(token: str) -> str:
    return f"ddw:slider_token:{token}"


def _redis_fail_key(ip: str) -> str:
    return f"ddw:slider_fail:{ip}"


def _redis_cooldown_key(ip: str) -> str:
    return f"ddw:slider_cooldown:{ip}"


# ---------------------------------------------------------------------------
# 图片生成（AJ-Captcha 风格）
# ---------------------------------------------------------------------------

def _random_color() -> Tuple[int, int, int]:
    """随机 RGB 颜色。"""
    return (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))


def _draw_gradient(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """绘制随机渐变背景。"""
    c1 = _random_color()
    c2 = _random_color()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
        g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
        b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _draw_random_shapes(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """绘制随机几何图形。"""
    for _ in range(random.randint(5, 12)):
        shape = random.choice(["circle", "rect", "line", "polygon"])
        color = _random_color()
        if shape == "circle":
            cx, cy = random.randint(0, width), random.randint(0, height)
            r = random.randint(10, 40)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        elif shape == "rect":
            x1, y1 = random.randint(0, width - 30), random.randint(0, height - 30)
            x2, y2 = x1 + random.randint(20, 60), y1 + random.randint(20, 60)
            draw.rectangle([x1, y1, x2, y2], fill=color)
        elif shape == "line":
            x1, y1 = random.randint(0, width), random.randint(0, height)
            x2, y2 = random.randint(0, width), random.randint(0, height)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=random.randint(1, 3))
        else:
            pts = [(random.randint(0, width), random.randint(0, height)) for _ in range(random.randint(3, 6))]
            if len(pts) >= 3:
                draw.polygon(pts, fill=color)


def _create_puzzle_mask(size: int) -> Image.Image:
    """创建拼图块形状蒙版。"""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = size // 2, size // 2
    r = size // 2 - 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    bump_r = size // 6
    bump_cx = cx + r - 2
    draw.ellipse(
        [bump_cx - bump_r, cy - bump_r, bump_cx + bump_r, cy + bump_r],
        fill=255,
    )
    return mask


def _image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """PIL Image 转 base64 data URL。"""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def generate_slider() -> Tuple[str, str, str, int, int]:
    """生成拼图滑块。

    Returns:
        (captcha_id, bg_base64, puzzle_base64, x_target, y_target) 元组
    """
    captcha_id = uuid.uuid4().hex
    x_target = random.randint(X_RANGE[0], X_RANGE[1])
    y_target = random.randint(Y_MIN, Y_MAX)

    # 1. 生成背景图
    bg = Image.new("RGB", (BG_WIDTH, BG_HEIGHT))
    bg_draw = ImageDraw.Draw(bg)
    _draw_gradient(bg_draw, BG_WIDTH, BG_HEIGHT)
    _draw_random_shapes(bg_draw, BG_WIDTH, BG_HEIGHT)

    # 2. 从背景挖出拼图块
    mask = _create_puzzle_mask(PUZZLE_SIZE)
    puzzle = Image.new("RGBA", (PUZZLE_SIZE, PUZZLE_SIZE), (0, 0, 0, 0))
    bg_crop = bg.crop((x_target, y_target, x_target + PUZZLE_SIZE, y_target + PUZZLE_SIZE))
    puzzle.paste(bg_crop, (0, 0), mask)

    # 2b. 拼图块加白色描边（AJ-Captcha 标准：拼图块必须可见）
    # 顺序关键：先深色外圈（阴影），后白色内圈（高亮边），否则白边被盖住
    outline = Image.new("RGBA", (PUZZLE_SIZE, PUZZLE_SIZE), (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline)
    outline_draw.ellipse(
        [2, 2, PUZZLE_SIZE - 2, PUZZLE_SIZE - 2],
        outline=(0, 0, 0, 110), width=6,
    )
    outline_draw.ellipse(
        [2, 2, PUZZLE_SIZE - 2, PUZZLE_SIZE - 2],
        outline=(255, 255, 255, 235), width=3,
    )
    outline = Image.composite(outline, Image.new("RGBA", (PUZZLE_SIZE, PUZZLE_SIZE), (0, 0, 0, 0)), mask)
    puzzle = Image.alpha_composite(puzzle, outline)

    # 3. 背景图缺口：阴影 + 灰白色填充
    shadow_layer = Image.new("RGBA", (BG_WIDTH, BG_HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    sx, sy = x_target + 2, y_target + 2
    shadow_draw.ellipse(
        [sx - PUZZLE_SIZE // 2 + 2, sy - PUZZLE_SIZE // 2 + 2,
         sx + PUZZLE_SIZE // 2 - 2, sy + PUZZLE_SIZE // 2 - 2],
        fill=(0, 0, 0, 80),
    )
    bg_rgba = bg.convert("RGBA")
    bg_rgba = Image.alpha_composite(bg_rgba, shadow_layer)

    gap_layer = Image.new("RGBA", (BG_WIDTH, BG_HEIGHT), (0, 0, 0, 0))
    gap_draw = ImageDraw.Draw(gap_layer)
    gx, gy = x_target, y_target
    gap_draw.ellipse(
        [gx - PUZZLE_SIZE // 2 + 2, gy - PUZZLE_SIZE // 2 + 2,
         gx + PUZZLE_SIZE // 2 - 2, gy + PUZZLE_SIZE // 2 - 2],
        fill=(220, 220, 220, 180),
    )
    bg_rgba = Image.alpha_composite(bg_rgba, gap_layer)
    bg_final = bg_rgba.convert("RGB")

    # 4. 存储
    _store_slider(captcha_id, x_target)

    return captcha_id, _image_to_base64(bg_final), _image_to_base64(puzzle), x_target, y_target


# ---------------------------------------------------------------------------
# 存储操作
# ---------------------------------------------------------------------------

def _store_slider(captcha_id: str, x_target: int) -> None:
    expire_at = time.time() + SLIDER_TTL
    _SLIDER_STORE[captcha_id] = (x_target, expire_at)
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_slider_key(captcha_id), SLIDER_TTL, str(x_target))
        except Exception as exc:
            logger.warning("slider redis setex failed: %s", exc)


def _get_x_target(captcha_id: str) -> Optional[int]:
    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(_redis_slider_key(captcha_id))
            if stored is not None:
                return int(stored.decode("utf-8"))
        except Exception as exc:
            logger.warning("slider redis get failed: %s", exc)
    rec = _SLIDER_STORE.get(captcha_id)
    if rec is None:
        return None
    x_target, expire_at = rec
    if time.time() > expire_at:
        _SLIDER_STORE.pop(captcha_id, None)
        return None
    return x_target


def _invalidate_slider(captcha_id: str) -> None:
    _SLIDER_STORE.pop(captcha_id, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_slider_key(captcha_id))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 失败计数 / IP 冷却
# ---------------------------------------------------------------------------

def _get_fail_count(ip: str) -> int:
    r = _get_redis()
    if r is not None:
        try:
            val = r.get(_redis_fail_key(ip))
            if val is not None:
                return int(val)
        except Exception:
            pass
    rec = _SLIDER_FAIL_STORE.get(ip)
    if rec is None:
        return 0
    count, expire_at = rec
    if time.time() > expire_at:
        _SLIDER_FAIL_STORE.pop(ip, None)
        return 0
    return count


def _increment_fail_count(ip: str) -> None:
    r = _get_redis()
    if r is not None:
        try:
            n = r.incr(_redis_fail_key(ip))
            if n == 1:
                r.expire(_redis_fail_key(ip), SLIDER_TTL)
            return
        except Exception:
            pass
    rec = _SLIDER_FAIL_STORE.get(ip)
    if rec is None:
        _SLIDER_FAIL_STORE[ip] = (1, time.time() + SLIDER_TTL)
    else:
        count, expire_at = rec
        _SLIDER_FAIL_STORE[ip] = (count + 1, expire_at)


def _clear_fail_count(ip: str) -> None:
    _SLIDER_FAIL_STORE.pop(ip, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_fail_key(ip))
        except Exception:
            pass


def _set_ip_cooldown(ip: str) -> None:
    expire_at = time.time() + FAIL_COOLDOWN
    _SLIDER_IP_COOLDOWN[ip] = expire_at
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_cooldown_key(ip), FAIL_COOLDOWN, "1")
        except Exception:
            pass


def _is_ip_cooldown(ip: str) -> bool:
    r = _get_redis()
    if r is not None:
        try:
            if r.exists(_redis_cooldown_key(ip)):
                return True
        except Exception:
            pass
    expire_at = _SLIDER_IP_COOLDOWN.get(ip)
    if expire_at is None:
        return False
    if time.time() > expire_at:
        _SLIDER_IP_COOLDOWN.pop(ip, None)
        return False
    return True


# ---------------------------------------------------------------------------
# 校验 / Token 操作
# ---------------------------------------------------------------------------

def verify_slider(captcha_id: str, x: int, ip: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """校验滑块位置。

    Returns:
        (ok, reason, token)
    """
    if ip and _is_ip_cooldown(ip):
        return False, "验证失败次数过多，请稍后再试", None

    x_target = _get_x_target(captcha_id)
    if x_target is None:
        return False, "验证失败，请重试", None

    if ip:
        fail_count = _get_fail_count(ip)
        if fail_count >= MAX_FAILS:
            _invalidate_slider(captcha_id)
            _set_ip_cooldown(ip)
            _clear_fail_count(ip)
            return False, "验证失败次数过多，请稍后再试", None

    if abs(x - x_target) > SLIDER_TOLERANCE:
        if ip:
            _increment_fail_count(ip)
        return False, "验证失败，请重试", None

    # 校验成功
    _invalidate_slider(captcha_id)
    if ip:
        _clear_fail_count(ip)
    token = uuid.uuid4().hex
    _store_slider_token(token, captcha_id)
    return True, "ok", token


def _store_slider_token(token: str, captcha_id: str) -> None:
    expire_at = time.time() + SLIDER_TOKEN_TTL
    _SLIDER_TOKEN_STORE[token] = (captcha_id, expire_at)
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_redis_token_key(token), SLIDER_TOKEN_TTL, captcha_id)
        except Exception as exc:
            logger.warning("slider token redis setex failed: %s", exc)


def consume_slider_token(token: str, ip: Optional[str] = None) -> bool:
    """校验 token 有效性（不消费，多租户 409 后可复用）。"""
    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(_redis_token_key(token))
            if stored is not None:
                return True
        except Exception as exc:
            logger.warning("slider token redis get failed: %s", exc)
    rec = _SLIDER_TOKEN_STORE.get(token)
    if rec is None:
        return False
    _cid, expire_at = rec
    if time.time() > expire_at:
        _SLIDER_TOKEN_STORE.pop(token, None)
        return False
    return True


def revoke_slider_token(token: str) -> None:
    """登录成功后消费 token（删除）。"""
    _SLIDER_TOKEN_STORE.pop(token, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_token_key(token))
        except Exception:
            pass


def get_x_range() -> Tuple[int, int]:
    return X_RANGE


__all__ = [
    "generate_slider",
    "verify_slider",
    "consume_slider_token",
    "revoke_slider_token",
    "get_x_range",
    "SLIDER_TTL",
    "SLIDER_TOKEN_TTL",
    "SLIDER_TOLERANCE",
    "MAX_FAILS",
    "X_RANGE",
]
