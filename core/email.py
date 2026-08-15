"""邮件发送模块（DDW AI Hub 邮箱绑定 + 找回密码）。

配置（环境变量）：
  DDW_SMTP_HOST     默认 smtp.qiye.aliyun.com
  DDW_SMTP_PORT     默认 465
  DDW_SMTP_USER     账号（如 noreply@9cio.com）
  DDW_SMTP_PASSWORD SMTP 授权码
  DDW_SMTP_SENDER   发件人（如 DDW AI HUB <noreply@9cio.com>）

行为：
  - production 未配置 SMTP → raise RuntimeError（调用方返回 503）
  - 非 production 未配置 → 日志打印验证码（mock 模式）
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SMTP 配置
# ---------------------------------------------------------------------------
_SMTP_HOST = os.environ.get("DDW_SMTP_HOST", "smtp.qiye.aliyun.com")
_SMTP_PORT = int(os.environ.get("DDW_SMTP_PORT", "465"))
_SMTP_USER = os.environ.get("DDW_SMTP_USER", "")
_SMTP_PASSWORD = os.environ.get("DDW_SMTP_PASSWORD", "")
_SMTP_SENDER = os.environ.get("DDW_SMTP_SENDER", "")


def is_smtp_configured() -> bool:
    """SMTP 是否已完整配置。"""
    return bool(_SMTP_USER and _SMTP_PASSWORD)


def _send_mail_sync(to: str, subject: str, html: str) -> bool:
    """同步 SMTP_SSL 发送（在线程中调用）。"""
    msg = MIMEMultipart("alternative")
    msg["From"] = _SMTP_SENDER or _SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.login(_SMTP_USER, _SMTP_PASSWORD)
            server.sendmail(_SMTP_SENDER or _SMTP_USER, [to], msg.as_string())
        return True
    except Exception as exc:
        logger.error("SMTP send failed to=%s: %s", to, exc)
        return False


async def send_mail(to: str, subject: str, html: str) -> bool:
    """异步发送邮件（smtplib + asyncio.to_thread）。"""
    return await asyncio.to_thread(_send_mail_sync, to, subject, html)


# ---------------------------------------------------------------------------
# 验证码邮件模板
# ---------------------------------------------------------------------------

_VERIFY_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;">
<div style="max-width:480px;margin:40px auto;background:#fff;border-radius:8px;padding:32px;font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="text-align:center;margin-bottom:24px;">
    <h2 style="margin:0;color:#333;font-size:20px;">{title}</h2>
    <p style="margin:6px 0 0;color:#999;font-size:13px;">DDW AI HUB · 武汉锐果互动信息技术有限公司</p>
  </div>
  <div style="text-align:center;padding:20px 0;">
    <p style="color:#666;font-size:14px;margin-bottom:16px;">您的验证码为：</p>
    <div style="font-size:36px;font-weight:bold;color:#1890FF;letter-spacing:6px;padding:16px;background:#f0f7ff;border-radius:6px;">{code}</div>
    <p style="color:#999;font-size:13px;margin-top:16px;">验证码 5 分钟内有效，请勿泄露给他人。</p>
  </div>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="color:#bbb;font-size:12px;text-align:center;">此邮件由系统自动发送，请勿回复。</p>
</div>
</body>
</html>"""

_PURPOSE_TITLES = {
    "verify_email": "邮箱验证码 — 邮箱绑定",
    "reset_password": "验证码 — 找回密码",
}


async def send_verify_code(email: str, code: str, purpose: str) -> bool:
    """发送验证码邮件。

    Args:
        email: 收件人邮箱
        code: 6 位验证码
        purpose: verify_email / reset_password
    """
    title = _PURPOSE_TITLES.get(purpose, "验证码")
    html = _VERIFY_HTML_TEMPLATE.format(title=title, code=code)
    subject = f"{title} — DDW AI HUB"

    env = os.environ.get("DDW_ENV", "development")
    if not is_smtp_configured():
        if env == "production":
            raise RuntimeError("SMTP not configured in production")
        # 非 production：mock 模式，日志打印验证码
        logger.info("[MOCK EMAIL] to=%s purpose=%s code=%s", email, purpose, code)
        return True

    return await send_mail(email, subject, html)
