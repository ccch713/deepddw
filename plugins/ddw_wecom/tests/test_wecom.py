"""DDW 企业微信插件测试用例（覆盖 OAuth + JIT 建号 + 部门同步 + external_identity + 消息占位）。"""

from __future__ import annotations

import pytest

from plugins.ddw_wecom.models import (
    MessageStatus,
    MessageType,
    OAuthCallback,
    WeComDepartment,
)
from plugins.ddw_wecom.service import WeComService


@pytest.fixture
def svc() -> WeComService:
    return WeComService(corp_secret="test_secret_for_testing")


# ===========================================================================
# 1. OAuth 授权 URL 生成
# ===========================================================================


def test_oauth_authorize_url(svc: WeComService):
    url = svc.get_authorize_url(state="csrf_token_123")
    assert "appid=test_corp_id" in url
    assert "agentid=test_agent_id" in url
    assert "state=csrf_token_123" in url
    assert url.startswith("https://open.work.weixin.qq.com/")


# ===========================================================================
# 2. OAuth 回调 → JIT 建号（新用户自动创建）
# ===========================================================================


def test_oauth_callback_jit_create(svc: WeComService):
    callback = OAuthCallback(
        code="valid_authcode",
        state="s1",
        user_info={
            "userid": "zhangsan",
            "name": "张三",
            "department": [101, 102],
            "avatar": "https://example.com/zs.png",
            "mobile": "13900001111",
            "email": "zhangsan@corp.com",
        },
    )
    user = svc.handle_oauth_callback(callback)
    assert user.wecom_userid == "zhangsan"
    assert user.ddw_user_id.startswith("ddw_")
    assert user.name == "张三"
    assert user.department_ids == [101, 102]
    assert user.corp_id == "test_corp_id"

    # 二次登录应返回同一用户，不再建号
    user2 = svc.handle_oauth_callback(callback)
    assert user2.ddw_user_id == user.ddw_user_id


# ===========================================================================
# 3. OAuth 无效 code 抛异常
# ===========================================================================


def test_oauth_invalid_code_raises(svc: WeComService):
    callback = OAuthCallback(code="bad_code", state="")
    with pytest.raises(ValueError, match="invalid oauth code"):
        svc.handle_oauth_callback(callback)


# ===========================================================================
# 4. 部门同步 — 新建 + DDW ID 映射
# ===========================================================================


def test_department_sync(svc: WeComService):
    departments = [
        WeComDepartment(wecom_dept_id=1, name="总公司", parent_id=None),
        WeComDepartment(wecom_dept_id=2, name="技术部", parent_id=1),
        WeComDepartment(wecom_dept_id=3, name="产品部", parent_id=1),
    ]
    synced = svc.sync_departments(departments)
    assert len(synced) == 3
    assert synced[0].ddw_department_id == "ddw_dept_1"
    assert synced[1].ddw_department_id == "ddw_dept_2"

    # 查询已同步的部门
    dept = svc.get_department(2)
    assert dept is not None
    assert dept.name == "技术部"
    assert dept.parent_id == 1


# ===========================================================================
# 5. 部门同步 — 幂等（重复同步保留映射）
# ===========================================================================


def test_department_sync_idempotent(svc: WeComService):
    dept = WeComDepartment(wecom_dept_id=10, name="财务部")
    svc.sync_departments([dept])

    # 手动修改映射后重新同步，应保留已有映射
    first_mapping = svc.get_department(10).ddw_department_id
    dept2 = WeComDepartment(wecom_dept_id=10, name="财务部v2")
    svc.sync_departments([dept2])
    assert svc.get_department(10).ddw_department_id == first_mapping


# ===========================================================================
# 6. External Identity — 绑定 + 反查
# ===========================================================================


def test_external_identity_bind_and_lookup(svc: WeComService):
    # 先通过 OAuth 建号
    callback = OAuthCallback(
        code="valid_ext",
        state="",
        user_info={"userid": "lisi", "name": "李四", "department": [1]},
    )
    user = svc.handle_oauth_callback(callback)

    # 绑定第三方身份
    updated = svc.bind_external_identity("lisi", "dingtalk", "dt_001")
    assert updated is not None
    assert updated.external_identity["dingtalk"] == "dt_001"

    # 反查
    found = svc.get_user_by_external_identity("dingtalk", "dt_001")
    assert found is not None
    assert found.wecom_userid == "lisi"

    # 不存在的绑定返回 None
    assert svc.get_user_by_external_identity("feishu", "xxx") is None


# ===========================================================================
# 7. External Identity — 绑定不存在的用户返回 None
# ===========================================================================


def test_external_identity_bind_nonexistent(svc: WeComService):
    result = svc.bind_external_identity("ghost", "dingtalk", "dt_ghost")
    assert result is None


# ===========================================================================
# 8. 消息发送（占位） — 模板记录 + 状态为 PENDING
# ===========================================================================


def test_message_send_placeholder(svc: WeComService):
    msg = svc.send_message("tpl_001", "你好，{name}", MessageType.TEXT)
    assert msg.template_id == "tpl_001"
    assert msg.content == "你好，{name}"
    assert msg.msg_type == MessageType.TEXT
    assert msg.status == MessageStatus.PENDING

    # 列表查询
    messages = svc.list_messages()
    assert len(messages) == 1
    assert messages[0].template_id == "tpl_001"


# ===========================================================================
# 9. 消息发送 — 支持多种类型
# ===========================================================================


def test_message_multiple_types(svc: WeComService):
    svc.send_message("tpl_text", "纯文本", MessageType.TEXT)
    svc.send_message("tpl_md", "**加粗**", MessageType.MARKDOWN)
    svc.send_message("tpl_img", "media_id_xxx", MessageType.IMAGE)

    messages = svc.list_messages()
    assert len(messages) == 3
    types = {m.msg_type for m in messages}
    assert types == {MessageType.TEXT, MessageType.MARKDOWN, MessageType.IMAGE}
