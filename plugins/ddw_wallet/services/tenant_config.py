"""子商户号路由服务（G10）— 按租户选择支付配置。"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wallet.models import TenantPaymentConfig

logger = logging.getLogger(__name__)


async def get_tenant_config(
    session: AsyncSession,
    tenant_id: str,
) -> Optional[TenantPaymentConfig]:
    """获取租户支付配置。"""
    stmt = select(TenantPaymentConfig).where(
        TenantPaymentConfig.tenant_id == tenant_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_or_update_tenant_config(
    session: AsyncSession,
    tenant_id: str,
    wechat_mch_id: Optional[str] = None,
    wechat_app_id: Optional[str] = None,
    alipay_app_id: Optional[str] = None,
    wechat_cert_path: Optional[str] = None,
    wechat_key_path: Optional[str] = None,
) -> TenantPaymentConfig:
    """创建或更新租户支付配置。"""
    config = await get_tenant_config(session, tenant_id)
    if config:
        if wechat_mch_id:
            config.wechat_mch_id = wechat_mch_id
        if wechat_app_id:
            config.wechat_app_id = wechat_app_id
        if alipay_app_id:
            config.alipay_app_id = alipay_app_id
        if wechat_cert_path:
            config.wechat_cert_path = wechat_cert_path
        if wechat_key_path:
            config.wechat_key_path = wechat_key_path
    else:
        config = TenantPaymentConfig(
            tenant_id=tenant_id,
            wechat_mch_id=wechat_mch_id,
            wechat_app_id=wechat_app_id,
            alipay_app_id=alipay_app_id,
            wechat_cert_path=wechat_cert_path,
            wechat_key_path=wechat_key_path,
        )
        session.add(config)
    await session.flush()
    return config
