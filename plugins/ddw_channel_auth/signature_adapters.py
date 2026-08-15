"""DDW 渠道授权与结算插件电子签适配器。

5 家电子签供应商抽象 + V1 e签宝实装 + 其余 4 家 stub。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSignatureAdapter(ABC):
    """电子签 provider 统一抽象。"""

    name: str

    @abstractmethod
    async def create_request(
        self, document_name: str, signers: list, callback_url: str
    ) -> dict:
        """返回：{external_request_id, sign_url?, expires_at}"""

    @abstractmethod
    async def verify_callback(self, payload: dict, signature: str) -> bool:
        """校验第三方回调签名。"""

    @abstractmethod
    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        """下载已签 PDF。"""


class EsignAdapter(BaseSignatureAdapter):
    """e签宝适配器（V1 stub：仅返回 mock external_request_id）。"""

    name = "esign"

    async def create_request(
        self, document_name: str, signers: list, callback_url: str,
    ) -> dict:
        return {
            "external_request_id": f"ESIGN-MOCK-{document_name[:20]}",
            "sign_url": f"https://open.esign.cn/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload: dict, signature: str) -> bool:
        # V1 mock 校验：开发期直接通过；V2 实现 RSA 验签
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        return b"%PDF-1.4\n% mock esign signed PDF\n"


class FadadaAdapter(BaseSignatureAdapter):
    """法大大适配器（V1 stub）。"""

    name = "fadada"

    async def create_request(
        self, document_name: str, signers: list, callback_url: str,
    ) -> dict:
        return {
            "external_request_id": f"FDD-MOCK-{document_name[:20]}",
            "sign_url": f"https://www.fadada.com/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload: dict, signature: str) -> bool:
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        return b"%PDF-1.4\n% mock fadada signed PDF\n"


class TencentAdapter(BaseSignatureAdapter):
    """腾讯电子签适配器（V1 stub）。"""

    name = "tencent"

    async def create_request(
        self, document_name: str, signers: list, callback_url: str,
    ) -> dict:
        return {
            "external_request_id": f"TXESIGN-MOCK-{document_name[:20]}",
            "sign_url": f"https://essopen.tencent.cn/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload: dict, signature: str) -> bool:
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        return b"%PDF-1.4\n% mock tencent esign signed PDF\n"


class QiyuesuoAdapter(BaseSignatureAdapter):
    """契约锁适配器（V1 stub，私有化部署变体：内网 HTTP）。"""

    name = "qiyuesuo"

    async def create_request(
        self, document_name: str, signers: list, callback_url: str,
    ) -> dict:
        return {
            "external_request_id": f"QYS-MOCK-{document_name[:20]}",
            "sign_url": f"https://www.qiyuesuo.com/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload: dict, signature: str) -> bool:
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        return b"%PDF-1.4\n% mock qiyuesuo signed PDF\n"


class ShangshangqianAdapter(BaseSignatureAdapter):
    """上上签适配器（V1 stub）。"""

    name = "shangshangqian"

    async def create_request(
        self, document_name: str, signers: list, callback_url: str,
    ) -> dict:
        return {
            "external_request_id": f"SSQ-MOCK-{document_name[:20]}",
            "sign_url": f"https://www.bestsign.cn/sign/{document_name}",
            "expires_at": None,
        }

    async def verify_callback(self, payload: dict, signature: str) -> bool:
        return len(signature) > 0

    async def fetch_signed_pdf(self, external_request_id: str) -> bytes:
        return b"%PDF-1.4\n% mock shangshangqian signed PDF\n"


ADAPTERS: dict[str, BaseSignatureAdapter] = {
    cls.name: cls()
    for cls in [
        EsignAdapter,
        FadadaAdapter,
        TencentAdapter,
        QiyuesuoAdapter,
        ShangshangqianAdapter,
    ]
}
