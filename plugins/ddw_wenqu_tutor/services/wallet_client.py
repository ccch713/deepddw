"""问渠→Wallet Hub HTTP 桥接客户端。

封装 3 个 wallet API：
1. get_balance - 查余额
2. check_balance - 余额检查
3. charge - 扣费（幂等）

使用 httpx.AsyncClient（FastAPI async 友好）。
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class WalletServiceError(Exception):
    """钱包服务调用失败（网络错误、500等）。"""
    pass


class InsufficientBalanceError(Exception):
    """余额不足。"""
    def __init__(self, balance_cents: int, required_cents: int):
        self.balance_cents = balance_cents
        self.required_cents = required_cents
        super().__init__(
            f"余额不足: 当前 {balance_cents} 分，需要 {required_cents} 分"
        )


class WenquWalletClient:
    """问渠→wallet hub HTTP 桥接客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8500"):
        self.base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_balance(self, user_id: str) -> dict:
        """GET /api/v1/plugins/ddw_wallet/accounts/{user_id}/balances

        Returns:
            {"recharge_balance_cents": int, "income_balance_cents": int, "skin_balance_cents": int}

        Raises:
            WalletServiceError: 网络错误或服务端错误
        """
        url = f"{self.base}/api/v1/plugins/ddw_wallet/accounts/{user_id}/balances"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"get_balance failed: {resp.status_code} {resp.text}")
                raise WalletServiceError(
                    f"wallet service returned {resp.status_code}"
                )
        except httpx.HTTPError as e:
            logger.error(f"get_balance HTTP error: {e}")
            raise WalletServiceError(f"wallet service unavailable: {e}")

    async def check_balance(self, user_id: str, min_cents: int = 100) -> bool:
        """余额是否 >= min_cents。

        Returns:
            True: 余额充足
            False: 余额不足
        """
        try:
            balance = await self.get_balance(user_id)
            total = (
                balance.get("recharge_balance_cents", 0)
                + balance.get("income_balance_cents", 0)
                + balance.get("skin_balance_cents", 0)
            )
            return total >= min_cents
        except WalletServiceError as e:
            if "404" in str(e):
                # 账户不存在 = 无余额，禁止开课（不允许免费上课）
                return False
            # 服务不可用时，允许开课（降级策略）
            logger.warning(f"wallet service unavailable, allowing session start for {user_id}")
            return True

    async def charge(
        self,
        user_id: str,
        charge_type: str,
        subject: str | None,
        ref_id: str,
        ref_type: str,
        amount_cents: int,
        balance_priority: str = "recharge,income,skin",
    ) -> dict:
        """POST /api/v1/plugins/ddw_wallet/charges/fallback

        Returns:
            {"txn_no": str, "amount_cents": int, "balance_after_cents": int}

        Raises:
            InsufficientBalanceError: 余额不足（402）
            WalletServiceError: 其他错误（503）
        """
        url = f"{self.base}/api/v1/plugins/ddw_wallet/charges/fallback"
        payload = {
            "user_id": user_id,
            "charge_type": charge_type,
            "subject": subject,
            "ref_id": ref_id,
            "ref_type": ref_type,
            "amount_cents": amount_cents,
            "balance_priority": balance_priority,
        }
        try:
            resp = await self._client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 402:
                detail = resp.json()
                balance_cents = detail.get("balance_cents", 0)
                raise InsufficientBalanceError(
                    balance_cents=balance_cents,
                    required_cents=amount_cents,
                )
            else:
                logger.error(f"charge failed: {resp.status_code} {resp.text}")
                raise WalletServiceError(
                    f"wallet service returned {resp.status_code}"
                )
        except httpx.HTTPError as e:
            logger.error(f"charge HTTP error: {e}")
            raise WalletServiceError(f"wallet service unavailable: {e}")

    async def create_recharge(self, user_id: str, amount_cents: int) -> dict:
        """POST /api/v1/plugins/ddw_wallet/recharges 创建充值单。

        Returns:
            {"order_no": str, "status": str, ...}
        """
        url = f"{self.base}/api/v1/plugins/ddw_wallet/recharges"
        try:
            resp = await self._client.post(
                url,
                json={
                    "amount_cents": amount_cents,
                    "channel": "wechat",
                    "user_id": user_id,
                },
            )
            if resp.status_code in (200, 201):
                return resp.json()
            logger.error(f"create_recharge failed: {resp.status_code} {resp.text}")
            raise WalletServiceError(
                f"wallet service returned {resp.status_code}"
            )
        except httpx.HTTPError as e:
            logger.error(f"create_recharge HTTP error: {e}")
            raise WalletServiceError(f"wallet service unavailable: {e}")

    async def get_recharge(self, order_no: str) -> dict:
        """GET /api/v1/plugins/ddw_wallet/recharges/{order_no} 查询充值单。"""
        url = f"{self.base}/api/v1/plugins/ddw_wallet/recharges/{order_no}"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"get_recharge failed: {resp.status_code} {resp.text}")
            raise WalletServiceError(
                f"wallet service returned {resp.status_code}"
            )
        except httpx.HTTPError as e:
            logger.error(f"get_recharge HTTP error: {e}")
            raise WalletServiceError(f"wallet service unavailable: {e}")

    async def close(self):
        """关闭 httpx client。"""
        await self._client.aclose()


__all__ = [
    "WenquWalletClient",
    "WalletServiceError",
    "InsufficientBalanceError",
]