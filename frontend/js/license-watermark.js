/**
 * DDW AI Hub - License Watermark（P1 客户水印 + P3 换码广播提示）
 *
 * 在管理后台页面底部固定显示授权信息，盗版流传后一眼溯源：
 *   "授权给：<公司名> · 有效期至 YYYY-MM-DD"
 *   - 到期前 30 天：黄色警告条（--c-warn）
 *   - 宽限期内（过期 ≤30 天）：红色警告条（--c-danger）
 *   - 授权码被替换（supersede）：宽限内黄色"授权即将更新"，超期红色
 *     "授权已更新，请联系经销商获取新授权码"（P3）
 *
 * 依赖：frontend/js/api.js（DDW.api）先加载；数据源 GET /api/v1/license/info。
 * 色值全部取自 :root CSS 变量（frontend/css/theme.css），禁止硬编码色值。
 */
(function () {
  'use strict';

  var STYLE_TEXT = [
    '#ddw-license-watermark{position:fixed;left:0;right:0;bottom:0;z-index:9999;',
    'background:var(--c-bg-dark);color:var(--c-text-inv);',
    'text-align:center;padding:7px 12px;font-size:13px;letter-spacing:.5px;',
    'box-shadow:0 -2px 8px rgba(0,0,0,.25);}',
    '#ddw-license-watermark.soon{background:var(--c-warn);color:var(--c-bg-dark);font-weight:600;}',
    '#ddw-license-watermark.grace{background:var(--c-danger);color:var(--c-text-inv);font-weight:700;}',
  ].join('');

  function daysText(daysLeft) {
    if (daysLeft === null || daysLeft === undefined) return '?';
    return String(daysLeft);
  }

  function init() {
    if (!window.DDW || !DDW.api) return;
    DDW.api.get('/license/info').then(function (res) {
      if (!res.ok || !res.data) return;
      var d = res.data;
      var bar = document.createElement('div');
      bar.id = 'ddw-license-watermark';
      bar.className = 'ddw-license-watermark';

      // P3 换码广播提示优先（superseded 超期时 licensed=false，仍需显示）
      var ss = d.supersede;
      if (ss && ss.superseded) {
        var text = '授权已更新：当前授权码已被 ' + (ss.superseded_by || '新码') + ' 替换';
        if (ss.grace_expired) {
          text += ' · 请联系经销商获取新授权码';
          bar.classList.add('grace');
        } else {
          text += ' · 宽限期内（授权即将更新）';
          bar.classList.add('soon');
        }
        bar.textContent = text;
      } else if (!d.licensed) {
        return; // 未授权/未登录不显示
      } else {
        var text2 = '授权给：' + (d.customer || '未知客户');
        if (d.valid_to) text2 += ' · 有效期至 ' + d.valid_to;
        if (d.in_grace_period) {
          text2 += ' · 宽限期内（已过期 ' + daysText(-d.days_left) + ' 天），请尽快联系续费';
          bar.classList.add('grace');
        } else if (d.warning_level === 'soon') {
          text2 += ' · 即将到期（剩余 ' + daysText(d.days_left) + ' 天），请及时续费';
          bar.classList.add('soon');
        }
        bar.textContent = text2;
      }

      var style = document.createElement('style');
      style.textContent = STYLE_TEXT;
      document.head.appendChild(style);
      document.body.appendChild(bar);
    }).catch(function () {
      /* 水印非关键路径，静默失败 */
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
