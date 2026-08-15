"""泛微OA统一认证中心 SSO 客户端（DDW AI Hub v5.5）。

支持两种协议接入泛微OA统一认证中心：
- CAS 3.0 协议（简单、快速集成）
- OAuth2.0 授权码流程（安全、推荐生产环境）

使用方式：
    1. 在泛微OA「认证应用管理」中注册DDW应用，获取 appid / client_id / client_secret
    2. 在 DDW deployment.yaml 中配置 weaver_sso 段
    3. 用户访问 DDW 时自动跳转 OA 登录页，认证后回调 DDW 创建本地 JWT

泛微OA认证地址格式（基于官方文档）：
- CAS登录：  {oa_url}/sso/login?appid={appid}&service={callback_url}
- CAS验证：  {oa_url}/sso/serviceValidate?ticket={ticket}&service={callback_url}
- CAS退出：  {oa_url}/sso/logout?service={callback_url}
- OAuth2授权：{oa_url}/sso/oauth2.0/authorize
- OAuth2 Token：{oa_url}/sso/oauth2.0/accessToken
- OAuth2用户信息：{oa_url}/sso/oauth2.0/profile
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, Optional
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


class WeaverSSOError(Exception):
    """泛微OA SSO 错误基类。"""


class WeaverCASClient:
    """泛微OA CAS 3.0 客户端。

    CAS认证流程：
    1. 用户访问DDW → DDW返回302重定向到OA CAS登录页
    2. 用户在OA登录 → OA重定向回DDW回调URL，带ticket参数
    3. DDW后端用ticket向OA CAS服务端验证 → 获取用户信息
    4. DDW创建本地JWT → 返回给前端

    参考文档：
    - 泛微CAS接口文档: https://www.e-cology.com.cn/sp/doc/docDetail/100500240014460469
    """

    def __init__(
        self,
        oa_url: str,
        appid: str,
        callback_url: str,
        timeout: int = 10,
    ):
        """
        Args:
            oa_url: 泛微OA访问地址，如 http://192.168.1.100:8080
            appid: 在OA「认证应用管理」中注册的应用标识
            callback_url: DDW的SSO回调地址，如 https://ddw.example.com/api/v1/sso/cas/callback
            timeout: HTTP请求超时秒数
        """
        self.oa_url = oa_url.rstrip("/")
        self.appid = appid
        self.callback_url = callback_url
        self.timeout = timeout

    @property
    def cas_base(self) -> str:
        return f"{self.oa_url}/sso"

    def get_login_url(self, state: Optional[str] = None) -> str:
        """生成CAS登录重定向URL。

        用户访问DDW后，DDW返回302重定向到此URL。
        用户在OA登录成功后，OA会重定向回 callback_url 并带 ticket 参数。
        """
        params = {
            "appid": self.appid,
            "service": self.callback_url,
        }
        if state:
            params["state"] = state
        return f"{self.cas_base}/login?{urllib.parse.urlencode(params)}"

    def get_logout_url(self, redirect_url: Optional[str] = None) -> str:
        """生成CAS退出URL。

        OA认证会话注销后，会回调跳转到 redirect_url。
        """
        params = {}
        if redirect_url:
            params["service"] = redirect_url
        qs = f"?{urllib.parse.urlencode(params)}" if params else ""
        return f"{self.cas_base}/logout{qs}"

    async def validate_ticket(self, ticket: str) -> Dict[str, Any]:
        """向OA CAS服务端验证ticket，获取用户信息。

        Args:
            ticket: OA登录成功后回调带的ticket参数

        Returns:
            用户信息字典，包含 loginid（OA登录名）等

        Raises:
            WeaverSSOError: ticket验证失败
        """
        validate_url = (
            f"{self.cas_base}/serviceValidate"
            f"?ticket={urllib.parse.quote(ticket)}"
            f"&service={urllib.parse.quote(self.callback_url)}"
        )

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            try:
                resp = await client.get(validate_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise WeaverSSOError(f"CAS ticket验证HTTP错误: {e}")

        return self._parse_cas_response(resp.text)

    def _parse_cas_response(self, xml_text: str) -> Dict[str, Any]:
        """解析CAS 3.0 XML响应。

        成功响应格式：
        <cas:serviceResponse>
            <cas:authenticationSuccess>
                <cas:user>loginid</cas:user>
                <cas:attributes>
                    <cas:loginid>zhangsan</cas:loginid>
                    <cas:lastname>张三</cas:lastname>
                    <cas:email>zhangsan@example.com</cas:email>
                    ...
                </cas:attributes>
            </cas:authenticationSuccess>
        </cas:serviceResponse>
        """
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            raise WeaverSSOError(f"CAS响应XML解析失败: {e}")

        # 处理命名空间
        ns = {"cas": "http://www.yale.edu/tp/cas"}

        # 尝试带命名空间查找
        success = root.find(".//cas:authenticationSuccess", ns)
        if success is None:
            # 尝试不带命名空间
            success = root.find(".//authenticationSuccess")
        if success is None:
            failure = root.find(".//cas:authenticationFailure", ns)
            if failure is None:
                failure = root.find(".//authenticationFailure")
            code = failure.get("code", "UNKNOWN") if failure is not None else "UNKNOWN"
            msg = failure.text.strip() if failure is not None and failure.text else "未知错误"
            raise WeaverSSOError(f"CAS认证失败 [{code}]: {msg}")

        # 提取用户名（从根查找更可靠；fallback到attributes中的loginid）
        user_elem = root.find(".//cas:user", ns) or root.find(".//user")
        username = user_elem.text.strip() if user_elem is not None and user_elem.text else ""

        # 提取属性
        user_info: Dict[str, Any] = {"username": username, "source": "weaver_cas"}

        attrs = root.find(".//cas:attributes", ns) or root.find(".//attributes")
        if attrs is not None:
            for child in attrs:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child.text:
                    user_info[tag] = child.text.strip()

        # fallback: username 为空时从 attributes 的 loginid 补充
        if not user_info.get("username") and user_info.get("loginid"):
            user_info["username"] = user_info["loginid"]

        return user_info


class WeaverOAuth2Client:
    """泛微OA OAuth2.0 客户端。

    OAuth2授权码流程：
    1. 用户访问DDW → DDW返回302重定向到OA OAuth2授权页
    2. 用户在OA授权 → OA重定向回DDW回调URL，带code参数
    3. DDW后端用code换取access_token
    4. DDW用access_token获取用户信息
    5. DDW创建本地JWT → 返回给前端

    参考文档：
    - 泛微OAuth2接口文档: https://www.e-cology.com.cn/sp/doc/docDetail/100500240014460453
    """

    def __init__(
        self,
        oa_url: str,
        client_id: str,
        client_secret: str,
        callback_url: str,
        timeout: int = 10,
    ):
        """
        Args:
            oa_url: 泛微OA访问地址
            client_id: 在OA「认证应用管理」中注册的应用标识
            client_secret: 在OA「认证应用管理」中注册的应用密钥
            callback_url: DDW的OAuth2回调地址
            timeout: HTTP请求超时秒数
        """
        self.oa_url = oa_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_url = callback_url
        self.timeout = timeout

    @property
    def oauth_base(self) -> str:
        return f"{self.oa_url}/sso/oauth2.0"

    def get_authorize_url(self, state: Optional[str] = None, scope: str = "read") -> str:
        """生成OAuth2授权重定向URL。

        用户访问DDW后，DDW返回302重定向到此URL。
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "response_type": "code",
            "scope": scope,
        }
        if state:
            params["state"] = state
        return f"{self.oauth_base}/authorize?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """用授权码换取access_token。

        Args:
            code: OA授权后回调带的code参数

        Returns:
            包含 access_token, token_type, expires_in 等的字典

        Raises:
            WeaverSSOError: token获取失败
        """
        token_url = f"{self.oauth_base}/accessToken"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.callback_url,
        }

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            try:
                resp = await client.post(token_url, data=data)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise WeaverSSOError(f"OAuth2 token获取HTTP错误: {e}")

        try:
            result = resp.json()
        except Exception:
            raise WeaverSSOError(f"OAuth2 token响应解析失败: {resp.text[:200]}")

        if "error" in result:
            raise WeaverSSOError(
                f"OAuth2 token获取失败: {result.get('error')} - {result.get('error_description', '')}"
            )

        return result

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """用access_token获取用户信息。

        Args:
            access_token: OAuth2 access_token

        Returns:
            用户信息字典

        Raises:
            WeaverSSOError: 用户信息获取失败
        """
        profile_url = f"{self.oauth_base}/profile"
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            try:
                resp = await client.get(profile_url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise WeaverSSOError(f"OAuth2用户信息获取HTTP错误: {e}")

        try:
            user_info = resp.json()
        except Exception:
            raise WeaverSSOError(f"OAuth2用户信息响应解析失败: {resp.text[:200]}")

        user_info["source"] = "weaver_oauth2"
        return user_info

    def get_logout_url(self, redirect_url: Optional[str] = None) -> str:
        """生成退出URL。"""
        params = {}
        if redirect_url:
            params["service"] = redirect_url
        qs = f"?{urllib.parse.urlencode(params)}" if params else ""
        return f"{self.oa_url}/sso/logout{qs}"


def create_cas_client(config: Dict[str, Any]) -> WeaverCASClient:
    """从配置字典创建CAS客户端。"""
    return WeaverCASClient(
        oa_url=config["oa_url"],
        appid=config["appid"],
        callback_url=config["callback_url"],
        timeout=config.get("timeout", 10),
    )


def create_oauth2_client(config: Dict[str, Any]) -> WeaverOAuth2Client:
    """从配置字典创建OAuth2客户端。"""
    return WeaverOAuth2Client(
        oa_url=config["oa_url"],
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        callback_url=config["callback_url"],
        timeout=config.get("timeout", 10),
    )
