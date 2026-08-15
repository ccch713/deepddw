/**
 * DDW 设备指纹采集模块
 * 采集 screen_resolution / canvas_hash / webgl_hash / user_agent / timezone
 * 组合后计算 SHA-256 → window.DDW_FINGERPRINT
 */
(function () {
  'use strict';

  async function sha256(str) {
    const buf = new TextEncoder().encode(str);
    const hash = await crypto.subtle.digest('SHA-256', buf);
    return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function getCanvasHash() {
    try {
      const c = document.createElement('canvas');
      c.width = 200; c.height = 50;
      const ctx = c.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 200, 50);
      ctx.fillStyle = '#069';
      ctx.fillText('DDW-device-fingerprint', 2, 15);
      ctx.fillStyle = 'rgba(102,204,0,0.7)';
      ctx.fillText('canvas-hash', 4, 30);
      return c.toDataURL();
    } catch (e) {
      return 'canvas-unsupported';
    }
  }

  function getWebGLHash() {
    try {
      const c = document.createElement('canvas');
      const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
      if (!gl) return 'webgl-unsupported';
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      const vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
      const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      return vendor + '|' + renderer;
    } catch (e) {
      return 'webgl-error';
    }
  }

  async function collect() {
    const screenResolution = screen.width + 'x' + screen.height;
    const canvasData = getCanvasHash();
    const webglData = getWebGLHash();
    const userAgent = navigator.userAgent;
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';

    const canvasHash = await sha256(canvasData);
    const webglHash = await sha256(webglData);
    const combined = [screenResolution, canvasHash, webglHash, userAgent, timezone].join('|');
    const fingerprintHash = await sha256(combined);

    window.DDW_FINGERPRINT = {
      serial_number: null,
      screen_resolution: screenResolution,
      canvas_hash: canvasHash,
      webgl_hash: webglHash,
      user_agent: userAgent,
      timezone: timezone,
      fingerprint_hash: fingerprintHash,
    };

    return window.DDW_FINGERPRINT;
  }

  // 页面加载后自动采集
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { collect(); });
  } else {
    collect();
  }

  window.DDW = window.DDW || {};
  window.DDW.collectFingerprint = collect;
})();
