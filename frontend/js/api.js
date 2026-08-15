/**
 * DDW AI Hub - API Client
 * 统一封装 fetch 调用，处理 JWT 注入 / 错误解析 / 响应信封拆封
 */
(function (global) {
  'use strict';

  const BASE = '/api/v1';
  const TOKEN_KEY = 'ddw_token';

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
  }
  function setToken(t) {
    try { localStorage.setItem(TOKEN_KEY, t || ''); } catch (e) {}
  }
  function clearToken() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
  }

  /**
   * 核心请求方法
   * @param {string} path 形如 '/auth/login' 或完整 URL
   * @param {object} options { method, body, headers, raw }
   * @returns {Promise<{ok: boolean, code: number, message: string, data: any}>}
   */
  async function request(path, options = {}) {
    const url = path.startsWith('http') ? path : (BASE + path);
    const headers = Object.assign(
      { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      options.headers || {}
    );
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;

    const fetchOpts = {
      method: options.method || 'GET',
      headers: headers,
    };
    if (options.body !== undefined && options.body !== null) {
      fetchOpts.body = typeof options.body === 'string'
        ? options.body
        : JSON.stringify(options.body);
    }

    let resp;
    try {
      resp = await fetch(url, fetchOpts);
    } catch (e) {
      return { ok: false, code: -1, message: '网络错误: ' + (e.message || e), data: null };
    }

    let payload;
    try {
      payload = await resp.json();
    } catch (e) {
      // 非 JSON 响应
      return {
        ok: resp.ok,
        code: resp.status,
        message: resp.statusText || ('HTTP ' + resp.status),
        data: null,
      };
    }

    // 标准信封 {code, message, data, timestamp}
    if (payload && typeof payload === 'object' && 'code' in payload && 'message' in payload) {
      return {
        ok: resp.ok && payload.code === 0,
        code: payload.code ?? resp.status,
        message: payload.message || '',
        data: payload.data,
      };
    }
    // 兜底：裸 JSON
    return { ok: resp.ok, code: resp.status, message: '', data: payload };
  }

  // 快捷方法
  const api = {
    get: (path) => request(path, { method: 'GET' }),
    post: (path, body) => request(path, { method: 'POST', body }),
    put: (path, body) => request(path, { method: 'PUT', body }),
    del: (path) => request(path, { method: 'DELETE' }),
    request: request,
    getToken, setToken, clearToken,
  };

  // 全局 toast
  function ensureToastHost() {
    let host = document.getElementById('toast-host');
    if (!host) {
      host = document.createElement('div');
      host.id = 'toast-host';
      host.className = 'toast-host';
      document.body.appendChild(host);
    }
    return host;
  }
  function toast(message, type = 'info', timeout = 3000) {
    const host = ensureToastHost();
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity .25s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 280);
    }, timeout);
  }

  // 暴露
  global.DDW = global.DDW || {};
  global.DDW.api = api;
  global.DDW.toast = toast;
})(window);