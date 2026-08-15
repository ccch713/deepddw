"""DDW 数字错误 ID 体系（技术规范 §7.3）

数字 ID 不进日志文字，仅进 telemetry error_id 字段。
"""
from __future__ import annotations

# 错误码分区：
# 1xx - Plugin 加载/运行
# 2xx - LLM 调用
# 3xx - 路径/文件/IAM
# 4xx - 认证
# 5xx - 业务逻辑
# 9xx - 系统/未知

E_PLUGIN_LOAD_FAILED = 101
E_PLUGIN_COMPAT_CHECK_FAILED = 102
E_PLUGIN_HOOK_BLOCKED = 103
E_PLUGIN_STATE_INVALID = 104

E_LLM_RATE_LIMITED = 201
E_LLM_PROVIDER_DOWN = 202
E_LLM_INVALID_RESPONSE = 203
E_LLM_TOKEN_EXCEEDED = 204
E_LLM_CASCADE_FAILED = 205

E_PATH_TRAVERSAL = 301
E_PATH_TOO_LONG = 302
E_PATH_INVALID_CHAR = 303
E_BINARY_FILE_DETECTED = 304
E_READ_BEFORE_WRITE = 305

E_AUTH_INVALID_TOKEN = 401
E_AUTH_EXPIRED = 402
E_AUTH_NO_PERMISSION = 403
E_AUTH_WHITELIST_REJECTED = 404

E_BUSINESS_VALIDATION = 501
E_BUSINESS_NOT_FOUND = 502
E_BUSINESS_CONFLICT = 503

E_SYSTEM_UNKNOWN = 901
E_SYSTEM_TIMEOUT = 902
E_SYSTEM_OOM = 903


# 错误码 → 人类可读描述的映射（仅 telemetry 用，不进业务日志）
ERROR_DESCRIPTIONS: dict[int, str] = {
    E_PLUGIN_LOAD_FAILED: "Plugin 加载失败",
    E_PLUGIN_COMPAT_CHECK_FAILED: "Plugin 兼容性检查失败",
    E_PLUGIN_HOOK_BLOCKED: "Plugin Hook 阻断加载",
    E_PLUGIN_STATE_INVALID: "Plugin 状态非法",
    E_LLM_RATE_LIMITED: "LLM 限流",
    E_LLM_PROVIDER_DOWN: "LLM Provider 不可用",
    E_LLM_INVALID_RESPONSE: "LLM 响应格式非法",
    E_LLM_TOKEN_EXCEEDED: "Token 超限",
    E_LLM_CASCADE_FAILED: "Fallback 全部失败",
    E_PATH_TRAVERSAL: "路径遍历攻击",
    E_PATH_TOO_LONG: "路径超长",
    E_PATH_INVALID_CHAR: "路径包含非法字符",
    E_BINARY_FILE_DETECTED: "检测到二进制文件",
    E_READ_BEFORE_WRITE: "Read-Before-Write 检查失败",
    E_AUTH_INVALID_TOKEN: "Token 无效",
    E_AUTH_EXPIRED: "Token 过期",
    E_AUTH_NO_PERMISSION: "无权限",
    E_AUTH_WHITELIST_REJECTED: "白名单拒绝",
    E_BUSINESS_VALIDATION: "业务校验失败",
    E_BUSINESS_NOT_FOUND: "资源不存在",
    E_BUSINESS_CONFLICT: "业务冲突",
    E_SYSTEM_UNKNOWN: "未知系统错误",
    E_SYSTEM_TIMEOUT: "系统超时",
    E_SYSTEM_OOM: "内存不足",
}


def get_error_description(code: int) -> str:
    """获取错误码的描述（用于 telemetry，不进用户日志）。"""
    return ERROR_DESCRIPTIONS.get(code, f"未知错误 {code}")
