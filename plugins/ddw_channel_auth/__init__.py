"""DDW 渠道授权与结算插件 v1.0.0。

渠道合作伙伴报备、合同锁定、电子签、支付对账、注册码换码广播、试用期管理、POC 报告生成。
"""

PLUGIN_NAME = "ddw-channel-auth"
VERSION = "1.0.0"

TOOL_ANNOTATIONS: dict[str, dict] = {
    "health": {"readOnly": True},
    "accounts_me": {"readOnly": True},
    "banner_seen": {"readOnly": False},
    "banner_check": {"readOnly": True},
    "create_claim": {"readOnly": False},
    "list_claims": {"readOnly": True},
    "get_claim": {"readOnly": True},
    "upload_contract": {"readOnly": False},
    "sign_auth_contract": {"readOnly": False},
    "pay_claim": {"readOnly": False},
    "release_claim": {"readOnly": False},
    "claim_history": {"readOnly": True},
    "flag_difficult_customer": {"readOnly": False},
    "signature_providers": {"readOnly": True},
    "dispatch_signature": {"readOnly": False},
    "get_signature": {"readOnly": True},
    "signature_callback": {"readOnly": False},
    "manual_upload_signature": {"readOnly": False},
    "auto_verify_payment": {"readOnly": False},
    "pending_reconcile": {"readOnly": True},
    "reconcile_payment": {"readOnly": False},
    "issue_license_code": {"readOnly": False},
    "activate_license_code": {"readOnly": False},
    "swap_license_code": {"readOnly": False},
    "revoke_list": {"readOnly": True},
    "re_activate_license_code": {"readOnly": False},
    "broadcast_log": {"readOnly": True},
    "trials_available": {"readOnly": True},
    "start_trial": {"readOnly": False},
    "trials_me": {"readOnly": True},
    "cancel_trial": {"readOnly": False},
    "generate_poc_report": {"readOnly": False},
    "trial_metrics": {"readOnly": True},
    "portal_banner": {"readOnly": True},
    "portal_dashboard": {"readOnly": True},
}

__all__ = ["PLUGIN_NAME", "VERSION", "TOOL_ANNOTATIONS"]
