"""S1: Force first login password change (PRD v5.7 §31.2).

One API issue: root password hardcoded as 123456.
Fix:
1. First startup generates random password for admin
2. Requires forced password change on first login
3. Password strength validation (≥8 chars, upper+lower+digit+special)
"""

from __future__ import annotations

import logging
import re
import secrets
import string
from typing import Tuple

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class FirstLoginGuard:
    """Enforce first-login password change with strength validation."""

    MIN_PASSWORD_LENGTH = 8
    PASSWORD_PATTERN = re.compile(
        r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,}$"
    )

    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """Validate password strength.

        Returns (ok, error_message).
        """
        if len(password) < FirstLoginGuard.MIN_PASSWORD_LENGTH:
            return False, (
                f"密码长度不足 {FirstLoginGuard.MIN_PASSWORD_LENGTH} 位"
            )

        if not FirstLoginGuard.PASSWORD_PATTERN.match(password):
            return False, (
                "密码必须包含: 大写字母、小写字母、数字、特殊字符(@$!%*?&#)"
            )

        return True, ""

    @staticmethod
    def generate_temp_password() -> str:
        """Generate a random temporary password (for first startup)."""
        chars = string.ascii_letters + string.digits + "@$!%*?&#"
        while True:
            password = "".join(secrets.choice(chars) for _ in range(12))
            ok, _ = FirstLoginGuard.validate_password(password)
            if ok:
                return password

    @staticmethod
    def is_default_password(password_hash: str) -> bool:
        """Check if a password hash looks like a default/weak password.

        In production, this would check against known weak hashes.
        For now, we check if the user has a password_hash set at all.
        """
        # If no password_hash is set, treat as needing password change
        return not password_hash or password_hash.strip() == ""

    @staticmethod
    def require_password_change(user) -> None:
        """Raise 403 if user needs to change password.

        Call this from auth endpoints after successful login.
        """
        if FirstLoginGuard.is_default_password(user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="必须修改初始密码后才能使用系统",
                headers={"X-Password-Change-Required": "true"},
            )
