/**
 * DDW AI Hub - Auth helpers
 * 负责登录态检查 / 跳转守卫 / 用户信息缓存
 */
(function (global) {
  'use strict';
  const DDW = global.DDW = global.DDW || {};

  /**
   * 校验当前 token 有效性（调用 /auth/me）
   * @returns {Promise<{valid: boolean, claims?: object}>}
   */
  async function verifyToken() {
    if (!DDW.api.getToken()) return { valid: false };
    const resp = await DDW.api.get('/auth/me');
    if (resp.ok && resp.data) {
      return { valid: true, claims: resp.data };
    }
    DDW.api.clearToken();
    return { valid: false };
  }

  /**
   * 页面守卫：未登录跳转到 /login.html
   */
  async function requireLogin(loginPath) {
    const target = loginPath || '/login.html';
    const v = await verifyToken();
    if (!v.valid) {
      window.location.href = target;
      return null;
    }
    return v.claims;
  }

  /**
   * 检查管理员权限（消费后端 /auth/me 的 can_access_admin）
   */
  async function requireAdmin(loginPath) {
    const claims = await requireLogin(loginPath);
    if (!claims) return null;
    if (!claims.can_access_admin) {
      DDW.toast('需要管理员权限', 'error');
      setTimeout(() => { window.location.href = claims.redirect_target || '/index.html'; }, 800);
      return null;
    }
    return claims;
  }

  function logout() {
    DDW.api.clearToken();
    // 清除跨域登录态 cookie（官网按钮恢复为"登录 AI HUB"）
    try {
      document.cookie = 'ddw_logged_in=; Domain=.9cio.com; Path=/; Max-Age=0';
    } catch (e) { /* ignore */ }
    try { localStorage.removeItem('ddw_user'); localStorage.removeItem('ddw_tenant'); } catch (e) { /* ignore */ }
    // 退出后必须强制跳转首页（2026-08-11 用户定案：禁止停留在带守卫的页面形成弹窗死循环）
    window.location.href = '/index.html';
  }

  /**
   * 检测 URL 中的 demo_token 参数并兑换为正式会话
   * 流程：?demo_token=xxx → POST /auth/demo-login → 存 JWT → 跳转干净 URL
   */
  async function handleDemoToken() {
    var params = new URLSearchParams(window.location.search);
    var demoToken = params.get('demo_token');
    if (!demoToken) return false;

    // 调用 demo-login 兑换
    var resp = await fetch('/api/v1/auth/demo-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ demo_token: demoToken }),
    });
    if (!resp.ok) {
      var err = await resp.json().catch(function () { return {}; });
      alert('Demo 登录失败: ' + (err.detail || 'token 无效或已过期'));
      // 移除 demo_token 参数，避免重复尝试
      params.delete('demo_token');
      var clean = params.toString() ? window.location.pathname + '?' + params.toString() : window.location.pathname;
      window.history.replaceState(null, '', clean);
      return false;
    }
    var data = await resp.json();
    // 存储 JWT
    DDW.api.setToken(data.access_token);
    // 移除 demo_token 参数
    params.delete('demo_token');
    var cleanUrl = params.toString() ? window.location.pathname + '?' + params.toString() : window.location.pathname;
    window.history.replaceState(null, '', cleanUrl);
    return true;
  }

  DDW.auth = { verifyToken, requireLogin, requireAdmin, logout, handleDemoToken };
})(window);