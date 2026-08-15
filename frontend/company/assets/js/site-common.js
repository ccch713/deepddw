/* ============================================================
   site-common.js — 锐果/DDW 官网共享布局引擎（新中式科技风）
   ------------------------------------------------------------
   · 全站页面共享导航/页脚/三色主题切换
   · 三色为纯前端切换，localStorage key = ddw-palette
   · 左下角浮动胶囊切换控件
   ============================================================ */

(function () {
  'use strict';

  var SITE_BASE = window.SITE_BASE || '';
  var PALETTE_KEY = 'ddw-palette';

  /* ---------- 三色主题配色 ---------- */
  var PALETTES = {
    a: { paper:'#FAF6EE', paper2:'#F4EEE1', ink:'#2B2A26', ink2:'#5D5A50', ink3:'#98917F', cin:'#C43D2C', cindeep:'#9E2F22', gold:'#C9A063', golddeep:'#A87F3F', blue:'#3E5C76', line:'#E4DCCB', linestrong:'#C9BFA8', band:'#262B33', band2:'#313A45', textOnInk:'#EDE7DA' },
    b: { paper:'#F3F6F8', paper2:'#E9EEF2', ink:'#22313C', ink2:'#4E606E', ink3:'#8A9AA6', cin:'#2E5F78', cindeep:'#234B60', gold:'#C9A063', golddeep:'#A87F3F', blue:'#3E5C76', line:'#DCE4EA', linestrong:'#B9C8D4', band:'#22313C', band2:'#2B3D4E', textOnInk:'#EDE7DA' },
    c: { paper:'#FDFBF7', paper2:'#F6F1E8', ink:'#33302A', ink2:'#63604F', ink3:'#A29A87', cin:'#B34700', cindeep:'#8F3A00', gold:'#C9A063', golddeep:'#A87F3F', blue:'#6B7B8D', line:'#EDE6D8', linestrong:'#D5CBB6', band:'#2E2A22', band2:'#3A342A', textOnInk:'#EDE7DA' }
  };
  var PAL_NAMES = { a: '宣纸朱砂', b: '墨青黛蓝', c: '纸白金砂' };

  /* ---------- 主题切换 ---------- */
  function setPal(p) {
    var v = PALETTES[p];
    if (!v) return;
    var r = document.documentElement.style;
    r.setProperty('--paper', v.paper); r.setProperty('--paper-2', v.paper2);
    r.setProperty('--ink', v.ink); r.setProperty('--ink-2', v.ink2); r.setProperty('--ink-3', v.ink3);
    r.setProperty('--cinnabar', v.cin); r.setProperty('--cinnabar-deep', v.cindeep);
    r.setProperty('--gold', v.gold); r.setProperty('--gold-deep', v.golddeep);
    r.setProperty('--daiblue', v.blue); r.setProperty('--line', v.line); r.setProperty('--line-strong', v.linestrong);
    r.setProperty('--ink-band', v.band); r.setProperty('--ink-band-2', v.band2);
    r.setProperty('--text-on-ink', v.textOnInk);
    /* 兼容旧变量映射 */
    r.setProperty('--bg-base', v.paper); r.setProperty('--bg-page', v.paper);
    r.setProperty('--bg-hero', v.paper); r.setProperty('--bg-card', v.paper2);
    r.setProperty('--bg-elevated', v.paper2); r.setProperty('--text-primary', v.ink);
    r.setProperty('--text-secondary', v.ink2); r.setProperty('--text-muted', v.ink3);
    r.setProperty('--brand', v.cin); r.setProperty('--brand-hover', v.cindeep);
    r.setProperty('--brand-glow', v.cin + '40'); r.setProperty('--accent', v.gold);
    r.setProperty('--accent-orange', v.golddeep); r.setProperty('--border', v.line);
    r.setProperty('--border-strong', v.linestrong); r.setProperty('--border-hover', v.cin);
    r.setProperty('--btn-primary-bg', v.cin); r.setProperty('--btn-primary-text', v.paper);
    r.setProperty('--shadow-lg', '0 12px 40px rgba(60,50,30,.10)');
    r.setProperty('--shadow-glow', '0 14px 40px ' + v.cin + '38');
    r.setProperty('--cta-bg', v.band); r.setProperty('--cta-text', v.textOnInk);
    r.setProperty('--cta-sub', 'rgba(237,231,218,.7)');
    r.setProperty('--footer-bg', v.band); r.setProperty('--footer-text', 'rgba(237,231,218,.75)');
    r.setProperty('--footer-heading', v.textOnInk); r.setProperty('--footer-muted', 'rgba(237,231,218,.45)');
    r.setProperty('--footer-line', 'rgba(237,231,218,.12)');
    r.setProperty('--accent-soft', v.cin + '10');
    r.setProperty('--bg-hover', v.cin + '0A');
    /* 更新切换按钮状态 */
    var btns = document.querySelectorAll('.demo-switch button');
    btns.forEach(function (b, i) { b.classList.toggle('active', i === ['a','b','c'].indexOf(p)); });
    try { localStorage.setItem(PALETTE_KEY, p); } catch (e) {}
  }
  window.setPal = setPal;

  /* 防闪烁：首屏前先应用本地缓存 */
  (function () {
    try {
      var cached = localStorage.getItem(PALETTE_KEY);
      if (cached && PALETTES[cached]) setPal(cached);
    } catch (e) {}
  })();

  /* ---------- 导航 ---------- */
  function navLink(href, text, active) {
    var current = window.location.pathname.split('/').pop() || 'index.html';
    var isActive = active || (href === current) || (href === 'index.html' && (current === '' || current === '/'));
    return '<a href="' + SITE_BASE + href + '"' + (isActive ? ' class="active"' : '') + '>' + text + '</a>';
  }

  // 已登录检测：跨域 cookie（登录时由 ddw.9cio.com 种 Domain=.9cio.com）
  function isLoggedIn() {
    try {
      return document.cookie.split(';').some(function (c) {
        return c.trim().indexOf('ddw_logged_in=1') === 0;
      });
    } catch (e) { return false; }
  }

  function renderHeader() {
    var el = document.getElementById('site-header');
    if (!el) return;
    var page = window.location.pathname.split('/').pop() || 'index.html';
    var ctaText = isLoggedIn() ? '进入 AI HUB' : '登录 AI HUB';
    var html =
      '<header class="site-header"><div class="header-inner">' +
      '<button class="nav-toggle" id="nav-toggle" aria-label="菜单" onclick="toggleNav()">&#9776;</button>' +
      '<a class="logo" href="' + SITE_BASE + 'index.html">' +
      '<img class="logo-seal" src="' + SITE_BASE + 'assets/logo/corp-seal.svg" alt="锐果互动">' +
      '<span><span class="logo-text" style="display:block;">锐果互动</span>' +
      '<span class="logo-sub" style="display:block;">RUIGUO INTERACTIVE</span></span></a>' +
      '<nav class="main-nav">' +
      navLink('index.html', '首页') +
      '<div class="nav-item">' +
      '<a href="' + SITE_BASE + 'products.html"' + (['products.html', 'platform.html', 'plugins.html'].indexOf(page) !== -1 ? ' class="active"' : '') + '>产品</a>' +
      '<div class="dd-menu">' +
      '<div class="dd-title">AI HUB 底座平台</div>' +
      '<a href="' + SITE_BASE + 'platform.html">AI HUB 底座平台</a>' +
      '<a href="' + SITE_BASE + 'plugins.html">AI 赋能插件市场</a>' +
      '</div></div>' +
      navLink('services.html', '服务') +
      navLink('industry.html', '行业方案') +
      '<a href="' + SITE_BASE + 'about.html"' + (page === 'about.html' ? ' class="active"' : '') + '>关于我们</a>' +
      '<a href="' + SITE_BASE + 'contact.html"' + (page === 'contact.html' ? ' class="active"' : '') + '>联系我们</a>' +
      '<a class="nav-cta" href="https://ddw.9cio.com/login" target="_blank" rel="noopener">' + ctaText + '</a>' +
      '</nav></div></header>';
    el.innerHTML = html;
  }

  /* ---------- 移动端菜单 ---------- */
  window.toggleNav = function () {
    var nav = document.querySelector('.main-nav');
    if (nav) nav.classList.toggle('open');
  };

  /* ---------- 页脚 ---------- */
  function renderFooter() {
    var el = document.getElementById('site-footer');
    if (!el) return;
    var html =
      '<footer class="site-footer"><div class="container">' +
      '<div class="footer-grid">' +
      '<div><div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">' +
      '<img src="' + SITE_BASE + 'assets/logo/corp-seal.svg" alt="锐果互动" style="width:36px;height:36px;border-radius:6px;">' +
      '<h4 style="margin:0;">武汉锐果互动信息技术有限公司</h4></div>' +
      '<p class="footer-desc" style="margin-bottom:0;">专注数字化与ESG融合的复合型咨询服务机构。</p></div>' +
      '<div><h4>快速导航</h4><ul>' +
      '<li><a href="' + SITE_BASE + 'index.html">首页</a></li>' +
      '<li><a href="' + SITE_BASE + 'products.html">产品</a></li>' +
      '<li><a href="' + SITE_BASE + 'platform.html">AI HUB 底座平台</a></li>' +
      '<li><a href="' + SITE_BASE + 'plugins.html">AI 赋能插件市场</a></li>' +
      '<li><a href="' + SITE_BASE + 'services.html">服务总览</a></li>' +
      '<li><a href="' + SITE_BASE + 'industry.html">行业方案</a></li>' +
      '<li><a href="' + SITE_BASE + 'about.html">关于我们</a></li>' +
      '<li><a href="' + SITE_BASE + 'contact.html">联系我们</a></li></ul></div>' +
      '<div><h4>平台入口</h4><ul>' +
      '<li><a href="https://ddw.9cio.com" target="_blank" rel="noopener">DDW AI Hub</a></li>' +
      '<li><a href="https://ddw.9cio.com/login" target="_blank" rel="noopener">' + (isLoggedIn() ? '进入 AI HUB' : '登录平台') + '</a></li>' +
      '<li><a href="' + SITE_BASE + 'plugins.html">插件总览</a></li></ul></div>' +
      '<div><h4>联系方式</h4><ul>' +
      '<li>电话：027-89578881</li>' +
      '<li>邮箱：1099340186@qq.com</li></ul></div>' +
      '</div>' +
      '<div class="footer-bottom">' +
      '<span>&copy; 2026 武汉锐果互动信息技术有限公司 版权所有</span>' +
      '<span><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">鄂ICP备2026024883号-1</a>' +
      '&nbsp;|&nbsp;<a href="https://www.beian.gov.cn/" target="_blank" rel="noopener">鄂公网安备42011102006255号</a></span>' +
      '</div></div></footer>';
    el.innerHTML = html;
  }

  /* ---------- 三色切换控件（左下角浮动胶囊） ---------- */
  function renderPaletteSwitch() {
    var el = document.createElement('div');
    el.className = 'demo-switch';
    el.innerHTML =
      '<span>色板</span>' +
      '<button onclick="setPal(\'a\')">A 宣纸朱砂</button>' +
      '<button onclick="setPal(\'b\')">B 墨青黛蓝</button>' +
      '<button onclick="setPal(\'c\')">C 纸白金砂</button>';
    document.body.appendChild(el);
    /* 恢复当前选中状态 */
    try {
      var cached = localStorage.getItem(PALETTE_KEY) || 'a';
      var btns = el.querySelectorAll('button');
      btns.forEach(function (b, i) { b.classList.toggle('active', i === ['a','b','c'].indexOf(cached)); });
    } catch (e) {}
  }

  /* ---------- 全站浮动在线客服 ---------- */
  var FCS_API = '/api/v1/plugins/ddw_online_cs/chat';
  var FCS_UPLOAD = '/api/v1/plugins/ddw_online_cs/upload';
  var FCS_FEEDBACK = '/api/v1/plugins/ddw_online_cs/feedback';
  var FCS_KEY = 'ddw_fcs_state';
  var FCS_FB_KEY = 'ddw_fcs_feedback';
  var FCS_MODE = window.location.hostname.indexOf('ddw.') === 0 ? 'postsales' : 'presales';

  /* ---------- 行业推断 ---------- */
  function detectIndustry() {
    var path = window.location.pathname.toLowerCase();
    if (path.indexOf('dental') !== -1 || path.indexOf('clinic') !== -1 || path.indexOf('oral') !== -1) return 'dental';
    if (path.indexOf('food') !== -1 || path.indexOf('quality') !== -1) return 'food';
    if (path.indexOf('esg') !== -1) return 'esg';
    if (path.indexOf('manufacturing') !== -1) return 'manufacturing';
    var params = new URLSearchParams(window.location.search);
    return params.get('industry') || 'general';
  }

  /* ---------- 反馈系统 ---------- */
  var _fbCache = null;
  function _loadFeedbackState() {
    if (_fbCache) return _fbCache;
    try { _fbCache = JSON.parse(sessionStorage.getItem(FCS_FB_KEY) || '{}'); } catch (e) { _fbCache = {}; }
    return _fbCache;
  }
  function _saveFeedback(msgId, type) {
    var s = _loadFeedbackState();
    s[msgId] = type;
    _fbCache = s;
    try { sessionStorage.setItem(FCS_FB_KEY, JSON.stringify(s)); } catch (e) {}
  }

  function _injectFeedbackStyles() {
    if (document.getElementById('fcs-fb-style')) return;
    var s = document.createElement('style');
    s.id = 'fcs-fb-style';
    s.textContent = [
      '.fcs-fb-bar{display:flex;gap:6px;margin-top:4px;justify-content:flex-end;opacity:.6;transition:opacity .2s}',
      '.fcs-msg.ai:hover .fcs-fb-bar{opacity:1}',
      '.fcs-fb-bar button{background:none;border:1px solid var(--border,#ddd);border-radius:4px;cursor:pointer;font-size:14px;padding:2px 6px;line-height:1;transition:all .15s}',
      '.fcs-fb-bar button:hover{background:var(--accent-soft,rgba(195,61,44,.08));border-color:var(--cinnabar,#C43D2C)}',
      '.fcs-fb-bar button.fcs-fb-done{opacity:.4;cursor:default;border-color:var(--border,#ddd)}',
      '.fcs-fb-bar button.fcs-fb-done:hover{background:none}',
      '.fcs-fb-corr{margin-top:6px;display:flex;gap:4px;align-items:center}',
      '.fcs-fb-corr input{flex:1;border:1px solid var(--border,#ddd);border-radius:4px;padding:4px 8px;font-size:12px;background:var(--paper,#FAF6EE);color:var(--ink,#2B2A26)}',
      '.fcs-fb-corr button{background:var(--cinnabar,#C43D2C);color:var(--paper,#FAF6EE);border:none;border-radius:4px;padding:4px 10px;font-size:12px;cursor:pointer}',
    ].join('\n');
    document.head.appendChild(s);
  }

  function _renderFeedbackBar(wrapEl, msgId) {
    var state = _loadFeedbackState();
    var bar = document.createElement('div');
    bar.className = 'fcs-fb-bar';

    var btnUp = document.createElement('button');
    btnUp.textContent = '👍';
    btnUp.title = '有帮助';
    var btnDown = document.createElement('button');
    btnDown.textContent = '👎';
    btnDown.title = '需要改进';

    if (state[msgId]) {
      btnUp.className = 'fcs-fb-done';
      btnDown.className = 'fcs-fb-done';
      btnUp.disabled = true;
      btnDown.disabled = true;
      if (state[msgId] === 'positive') btnUp.style.borderColor = 'var(--cinnabar,#C43D2C)';
      else btnDown.style.borderColor = 'var(--cinnabar,#C43D2C)';
    }

    btnUp.addEventListener('click', function () {
      if (state[msgId]) return;
      _saveFeedback(msgId, 'positive');
      _postFeedback(msgId, 'positive', '');
      btnUp.className = 'fcs-fb-done';
      btnDown.className = 'fcs-fb-done';
      btnUp.disabled = true;
      btnDown.disabled = true;
      btnUp.style.borderColor = 'var(--cinnabar,#C43D2C)';
    });

    btnDown.addEventListener('click', function () {
      if (state[msgId]) return;
      btnDown.style.borderColor = 'var(--cinnabar,#C43D2C)';
      // 显示纠错输入框
      var corrDiv = wrapEl.querySelector('.fcs-fb-corr');
      if (!corrDiv) {
        corrDiv = document.createElement('div');
        corrDiv.className = 'fcs-fb-corr';
        var inp = document.createElement('input');
        inp.type = 'text';
        inp.placeholder = '哪里不好？（可选）';
        var sendBtn = document.createElement('button');
        sendBtn.textContent = '提交';
        sendBtn.addEventListener('click', function () {
          _saveFeedback(msgId, 'negative');
          _postFeedback(msgId, 'negative', inp.value);
          btnUp.className = 'fcs-fb-done';
          btnDown.className = 'fcs-fb-done';
          btnUp.disabled = true;
          btnDown.disabled = true;
          corrDiv.remove();
        });
        inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') sendBtn.click(); });
        corrDiv.appendChild(inp);
        corrDiv.appendChild(sendBtn);
        wrapEl.appendChild(corrDiv);
      }
    });

    bar.appendChild(btnUp);
    bar.appendChild(btnDown);
    wrapEl.appendChild(bar);
  }

  function _postFeedback(msgId, type, correction) {
    try {
      fetch(FCS_FEEDBACK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: _fcsState ? _fcsState.session_id : '',
          message_id: msgId,
          type: type,
          correction: correction || '',
          mode: FCS_MODE,
        }),
      }).catch(function () {});
    } catch (e) {}
  }

  var _fcsState = null;

  function fcsRender() {
    if (document.getElementById('ddw-fcs')) return;
    _injectFeedbackStyles();
    var isDDW = FCS_MODE === 'postsales';
    var el = document.createElement('div');
    el.id = 'ddw-fcs';
    el.innerHTML =
      '<button class="fcs-btn" id="fcs-btn" aria-label="在线客服">' +
      '<span class="fcs-badge"></span>' +
      '<svg viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>' +
      '<span class="fcs-btn-text">在线客服</span></button>' +
      '<div class="fcs-tooltip" id="fcs-tooltip">' +
      (isDDW ? '使用中遇到问题？投诉建议也欢迎！<br>点击开启对话 →' : '欢迎！有什么可以帮您的吗？<br>吐槽、发泄、专业咨询，统统欢迎～') +
      '</div>' +
      '<div class="fcs-window">' +
      '<div class="fcs-head" id="fcs-head"><span class="fcs-dot"></span>' +
      '<h4>' + (isDDW ? '果果 · DDW 使用助手' : '果果 · 在线客服') + '</h4>' +
      '<span class="fcs-min" id="fcs-min">&minus;</span></div>' +
      '<div class="fcs-body" id="fcs-body"></div>' +
      '<div class="fcs-foot">' +
      '<input type="file" id="fcs-file" accept="image/*,.pdf,.eml,.txt,.md,.csv" style="display:none">' +
      '<button id="fcs-attach" class="fcs-attach" title="上传附件">📎</button>' +
      '<input id="fcs-input" type="text" placeholder="' + (isDDW ? '描述问题或上传截图...' : '输入问题或上传附件...') + '" autocomplete="off">' +
      '<button id="fcs-send">发送</button></div></div>';
    document.body.appendChild(el);

    var btn = document.getElementById('fcs-btn');
    var head = document.getElementById('fcs-head');
    var input = document.getElementById('fcs-input');
    var sendBtn = document.getElementById('fcs-send');
    var attachBtn = document.getElementById('fcs-attach');
    var fileInput = document.getElementById('fcs-file');
    var body = document.getElementById('fcs-body');
    var tooltip = document.getElementById('fcs-tooltip');
    var busy = false;
    var selectedFile = null;
    var state = { session_id: null, messages: [], draft: '' };
    _fcsState = state;

    setTimeout(function () { if (tooltip) tooltip.classList.add('fcs-tooltip-hide'); }, 4000);
    if (tooltip) tooltip.addEventListener('click', function () { open(); });

    function persist() { try { sessionStorage.setItem(FCS_KEY, JSON.stringify(state)); } catch (e) {} }
    function load() {
      try { var s = sessionStorage.getItem(FCS_KEY); if (s) { var d = JSON.parse(s); if (d && d.messages) state = d; } } catch (e) {}
    }

    var typewriterTimers = [];
    var _msgCounter = 0;
    function typewriteAddMsg(content) {
      _msgCounter++;
      var msgId = 'msg_' + Date.now() + '_' + _msgCounter;
      state.messages.push({ role: 'ai', content: content, id: msgId });
      var wrap = document.createElement('div');
      wrap.className = 'fcs-msg ai';
      wrap.setAttribute('data-msg-id', msgId);
      var b = document.createElement('div');
      b.className = 'b';
      wrap.appendChild(b);
      body.appendChild(wrap);
      persist();
      var i = 0;
      var id = 'tw_' + Date.now();
      wrap.setAttribute('data-tw-id', id);
      var done = false;
      var timer = setInterval(function () {
        if (i < content.length) { b.textContent += content.charAt(i); i++; body.scrollTop = body.scrollHeight; }
        else {
          clearInterval(timer);
          typewriterTimers = typewriterTimers.filter(function (t) { return t !== id; });
          if (!done) { done = true; _renderFeedbackBar(wrap, msgId); body.scrollTop = body.scrollHeight; }
        }
      }, 25);
      typewriterTimers.push(id);
      wrap.addEventListener('click', function () {
        typewriterTimers.forEach(function (tid) { clearInterval(tid); });
        typewriterTimers = [];
        b.textContent = content;
        if (!done) { done = true; _renderFeedbackBar(wrap, msgId); }
        body.scrollTop = body.scrollHeight;
      });
      return wrap;
    }

    function addMsg(role, content, skipTypewrite) {
      if (role === 'ai' && !skipTypewrite) { typewriteAddMsg(content); }
      else {
        _msgCounter++;
        var msgId = 'msg_' + Date.now() + '_' + _msgCounter;
        state.messages.push({ role: role, content: content, id: msgId });
        var wrap = document.createElement('div');
        wrap.className = 'fcs-msg ' + (role === 'user' ? 'user' : 'sys');
        var b = document.createElement('div');
        b.className = 'b';
        b.textContent = content;
        wrap.appendChild(b);
        body.appendChild(wrap);
      }
      body.scrollTop = body.scrollHeight;
      persist();
    }

    function showLoading() {
      var w = document.createElement('div');
      w.className = 'fcs-msg ai fcs-loading';
      w.id = 'fcs-loading';
      w.innerHTML = '<div class="b"><i></i><i></i><i></i><span class="fcs-loading-text">' +
        (isDDW ? '正在分析中...' : '思考中...') + '</span></div>';
      body.appendChild(w);
      body.scrollTop = body.scrollHeight;
    }
    function hideLoading() { var el = document.getElementById('fcs-loading'); if (el) el.remove(); }

    function renderHistory() {
      body.innerHTML = '';
      state.messages.forEach(function (m) {
        var wrap = document.createElement('div');
        wrap.className = 'fcs-msg ' + (m.role === 'user' ? 'user' : (m.role === 'ai' ? 'ai' : 'sys'));
        var b = document.createElement('div');
        b.className = 'b';
        b.textContent = m.content;
        wrap.appendChild(b);
        if (m.role === 'ai' && m.id) {
          wrap.setAttribute('data-msg-id', m.id);
          _renderFeedbackBar(wrap, m.id);
        }
        body.appendChild(wrap);
      });
      body.scrollTop = body.scrollHeight;
    }

    function open() {
      el.classList.add('fcs-open');
      try { sessionStorage.setItem('ddw_fcs_open', '1'); } catch (e) {}
      if (tooltip) tooltip.classList.add('fcs-tooltip-hide');
      renderHistory();
      input.value = state.draft || '';
      if (!state.messages.length) {
        addMsg('ai', isDDW
          ? '嗨～我是 DDW 使用助手「果果」😊 有什么操作上的问题直接问我，不满意也欢迎吐槽，您的反馈是我们改进的动力！'
          : '您好呀～我是锐果互动 AI 在线客服「果果」👋 关于 DDW 平台、ESG 服务、企业信息化与智能制造规划的问题都可以问我，也可以直接告诉我您所在的行业和关注点，我来为您介绍合适的方案。', true);
      }
      input.focus();
    }
    function close() {
      state.draft = input.value;
      persist();
      try { sessionStorage.removeItem('ddw_fcs_open'); } catch (e) {}
      el.classList.remove('fcs-open');
    }

    function createStreamBubble() {
      var wrap = document.createElement('div');
      wrap.className = 'fcs-msg ai';
      var b = document.createElement('div');
      b.className = 'b';
      wrap.appendChild(b);
      body.appendChild(wrap);
      body.scrollTop = body.scrollHeight;
      return { wrap: wrap, el: b, appendToken: function(t) { b.textContent += t; body.scrollTop = body.scrollHeight; } };
    }

    function send() {
      var text = input.value.trim();
      var hasFile = selectedFile !== null;
      if ((!text && !hasFile) || busy) return;
      busy = true; sendBtn.disabled = true;
      var userText = hasFile ? (text || '📎 ' + selectedFile.name) : text;
      addMsg('user', userText, true);
      input.value = ''; state.draft = '';
      showLoading();
      if (hasFile) {
        var fd = new FormData(); fd.append('file', selectedFile);
        fd.append('session_id', state.session_id || '');
        fd.append('mode', FCS_MODE);
        fd.append('industry', detectIndustry());
        var fileName = selectedFile.name;
        selectedFile = null; fileInput.value = '';
        fetch(FCS_UPLOAD, { method: 'POST', body: fd })
          .then(function (r) { return r.json(); }).then(function (d) {
            hideLoading();
            if (d && d.answer) {
              state.session_id = d.session_id || state.session_id;
              typewriteAddMsg('📄 **' + fileName + '**（' + (d.file_type || '') + '）\n\n' + d.answer);
              persist();
            } else { addMsg('sys', d && d.error ? d.error : '文件处理异常，请稍后再试。'); }
          }).catch(function () { hideLoading(); addMsg('sys', '文件上传失败，请检查网络后重试。'); })
          .finally(function () { busy = false; sendBtn.disabled = false; input.focus(); });
      } else {
        var SSE_URL = '/api/v1/plugins/ddw_online_cs/chat/stream';
        var FALLBACK_URL = FCS_API;
        var bubble = null;
        var fullAnswer = '';

        function onToken(token) {
          if (!bubble) { hideLoading(); bubble = createStreamBubble(); }
          fullAnswer += token;
          bubble.el.textContent = fullAnswer;
          body.scrollTop = body.scrollHeight;
        }
        function onDone() {
          if (bubble) {
            _msgCounter++;
            var msgId = 'msg_' + Date.now() + '_' + _msgCounter;
            state.messages.push({ role: 'ai', content: fullAnswer, id: msgId });
            bubble.wrap.setAttribute('data-msg-id', msgId);
            _renderFeedbackBar(bubble.wrap, msgId);
            persist();
          }
          busy = false; sendBtn.disabled = false; input.focus();
        }
        function onError(msg) {
          hideLoading(); addMsg('sys', msg || '网络异常，请稍后再试。');
          busy = false; sendBtn.disabled = false; input.focus();
        }

        function tryStream() {
          fetch(SSE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: state.session_id || undefined, mode: FCS_MODE, industry: detectIndustry() })
          }).then(function (resp) {
            if (!resp.ok || !resp.body) throw new Error('not streaming');
            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buf = '';
            function pump() {
              return reader.read().then(function (result) {
                if (result.done) { onDone(); return; }
                buf += decoder.decode(result.value, { stream: true });
                var lines = buf.split('\n');
                buf = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                  var line = lines[i].trim();
                  if (!line.startsWith('data: ')) continue;
                  try {
                    var d = JSON.parse(line.substring(6));
                    if (d.session_id) state.session_id = d.session_id;
                    if (d.token) onToken(d.token);
                    if (d.error) { onError(d.error); return; }
                    if (d.done) { onDone(); return; }
                  } catch (e) {}
                }
                return pump();
              }).catch(function () { fallbackSync(); });
            }
            return pump();
          }).catch(function () { fallbackSync(); });
        }

        function fallbackSync() {
          fetch(FALLBACK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: state.session_id || undefined, mode: FCS_MODE, industry: detectIndustry() })
          }).then(function (r) { return r.json(); }).then(function (d) {
            hideLoading();
            if (d && d.answer) { state.session_id = d.session_id || state.session_id; typewriteAddMsg(d.answer); persist(); }
            else { addMsg('sys', '客服暂时繁忙，请稍后再试。'); }
          }).catch(function () { onError('网络异常，请稍后再试。'); })
            .finally(function () { busy = false; sendBtn.disabled = false; input.focus(); });
        }
        tryStream();
      }
    }

    btn.addEventListener('click', function () { if (el.classList.contains('fcs-open')) close(); else open(); });
    head.addEventListener('click', function () { close(); });
    sendBtn.addEventListener('click', send);
    attachBtn.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
      if (fileInput.files && fileInput.files[0]) {
        selectedFile = fileInput.files[0];
        var sz = Math.round(selectedFile.size / 1024);
        addMsg('sys', '📎 已选择文件：' + selectedFile.name + '（' + sz + 'KB）\n点击发送按钮上传并分析。');
      }
    });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
    input.addEventListener('input', function () { state.draft = input.value; });
    load();
    if (sessionStorage.getItem('ddw_fcs_open') === '1') {
      el.classList.add('fcs-open');
      renderHistory();
      input.value = state.draft || '';
    }
  }

  /* ---------- 初始化 ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    renderHeader();
    renderFooter();
    renderPaletteSwitch();
    fcsRender();
    /* 滚动渐入 */
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: .12 });
    document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });
    /* 数字滚动 */
    var numIO = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target, target = +el.dataset.count, t0 = performance.now();
        var tick = function (t) {
          var p = Math.min((t - t0) / 1200, 1), ease = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * ease);
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        numIO.unobserve(el);
      });
    }, { threshold: .6 });
    document.querySelectorAll('[data-count]').forEach(function (el) { numIO.observe(el); });
  });
})();
