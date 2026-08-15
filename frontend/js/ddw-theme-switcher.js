/**
 * DDW Theme Engine v2
 * 
 * 功能：
 * 1. 从 localStorage 读取用户主题偏好
 * 2. 在 <html> 上设置 data-theme 属性
 * 3. 自动在导航栏注入主题切换按钮
 * 4. 不同员工各自独立（localStorage per origin）
 * 5. CSS变量 + !important 覆盖双管齐下，确保切换生效
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'ddw-theme';
  var THEMES = { light: 'light', dark: 'dark' };
  var LABELS = { light: '\u2600 \u6D45\u8272', dark: '\u263E \u6DF1\u8272' }; // ☀ 浅色 / ☾ 深色

  function getStoredTheme() {
    try {
      var t = localStorage.getItem(STORAGE_KEY);
      if (t === THEMES.light || t === THEMES.dark) return t;
    } catch (e) {}
    return THEMES.light;
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head.appendChild(meta);
    }
    meta.content = theme === THEMES.dark ? '#050816' : '#152c6b';
  }

  function saveTheme(theme) {
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
  }

  function toggleTheme() {
    var current = getStoredTheme();
    var next = current === THEMES.light ? THEMES.dark : THEMES.light;
    saveTheme(next);
    applyTheme(next);
    updateToggleButtons(next);
  }

  function updateToggleButtons(theme) {
    var btns = document.querySelectorAll('.ddw-theme-toggle');
    for (var i = 0; i < btns.length; i++) {
      btns[i].innerHTML = LABELS[theme];
      btns[i].title = theme === THEMES.light ? '\u5207\u6362\u5230\u6DF1\u8272\u4E3B\u9898' : '\u5207\u6362\u5230\u6D45\u8272\u4E3B\u9898';
    }
  }

  function createToggleButton(theme) {
    var btn = document.createElement('button');
    btn.className = 'ddw-theme-toggle';
    btn.innerHTML = LABELS[theme];
    btn.title = theme === THEMES.light ? '\u5207\u6362\u5230\u6DF1\u8272\u4E3B\u9898' : '\u5207\u6362\u5230\u6D45\u8272\u4E3B\u9898';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleTheme();
    });
    return btn;
  }

  function injectToggle(theme) {
    // Try common DDW nav patterns
    var targets = [
      '.topbar-right',
      '.nav-right',
      '.header-meta',
      '.nav-links',
      'header .right',
      'nav .right',
      '.topbar',
      'header',
      'nav'
    ];

    var injected = false;
    for (var i = 0; i < targets.length; i++) {
      var el = document.querySelector(targets[i]);
      if (el) {
        var btn = createToggleButton(theme);
        // For topbar/header/nav, append to the right side
        if (targets[i] === '.topbar' || targets[i] === 'header' || targets[i] === 'nav') {
          btn.style.cssText = 'margin-left:auto;';
          // Find or create a right-side container
          var right = el.querySelector('.topbar-right, .nav-right, .header-meta');
          if (right) {
            right.appendChild(btn);
          } else {
            el.appendChild(btn);
          }
        } else {
          el.appendChild(btn);
        }
        injected = true;
        break;
      }
    }

    // Fallback: fixed position
    if (!injected) {
      var btn = createToggleButton(theme);
      btn.style.cssText = 'position:fixed;top:12px;right:12px;z-index:9999;';
      document.body.appendChild(btn);
    }
  }

  function init() {
    var theme = getStoredTheme();
    applyTheme(theme);
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { injectToggle(theme); });
    } else {
      injectToggle(theme);
    }
  }

  init();
})();
