/*!
 * virtual-office.js — 虚拟办公室渲染核心（单文件 · 零依赖 · 原创程序化像素实现）
 * 规格：《虚拟员工可视化设计包》PRD §5/§6/§7（活动→动画状态机 / 重要性加权战报）
 * 版权：原创 clean-room 实现，不包含任何第三方代码或美术资产；角色/家具全部代码绘制。
 * 用法：new VirtualOffice(container, { roster, poll, demo, strings, theme })
 */
(function (global) {
  'use strict';

  var TILE = 16;            // 逻辑瓦片尺寸
  var GRID_W = 48, GRID_H = 30;   // 逻辑网格
  var ANIM_FPS = 8;         // 精灵动画帧率（像素感）
  var STATE_SET = { idle:1, walking:1, working:1, search:1, doc:1, celebrating:1, upset:1, sleeping:1, alert:1, away:1 };

  // ---------- 工具 ----------
  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function rr(ctx, x, y, w, h, r) { // 圆角矩形路径
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ---------- 默认主题（深色像素风，三产品共用；accent 可覆盖） ----------
  var DEFAULT_THEME = {
    bg: '#0b0f14', floorA: '#131a24', floorB: '#182030', wall: '#1a2330', wallTop: '#223041',
    furniture: '#26334a', furnitureEdge: '#324260', screen: '#3fb1ff', screenGlow: 'rgba(63,177,255,.25)',
    plant: '#2f9e63', coffee: '#8b5a2b',
    accent: '#3fb1ff', mint: '#7ee2b8', warn: '#ffd44d', bad: '#ff7b72', good: '#3fb950', dim: '#5c7086',
    textPanel: '#c9d4e0', panelBg: '#11161d', panelLine: '#1e2836', pageBg: '#0b0f14', headText: '#eaf2fb'
  };

  var DEFAULT_STRINGS = {
    demoBtn: '演示模式', demoOn: '演示中', stop: '退出演示', fullscreen: '全屏',
    rosterTitle: '在岗板', digestTitle: '今日战报', failTitle: '今日翻车',
    away: '暂离', idle: '摸鱼中', walking: '走向工位', working: '干活中',
    search: '查资料', doc: '写文档', celebrating: '交付 ✅', upset: '翻车了',
    sleeping: '睡着了', alert: '待处理！', away_note: '今日尚未开工',
    offline: '后端暂离，画面的全是幻影…恢复后自动重连', empty: '今天还没有动静',
    todayDone: '今日完成', todayFail: '今日翻车', viewCard: '查看名片'
  };

  // ---------- 主类 ----------
  function VirtualOffice(container, opts) {
    if (!container || !opts || !Array.isArray(opts.roster)) throw new Error('VirtualOffice: container 与 roster 必填');
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.opts = opts;
    this.theme = Object.assign({}, DEFAULT_THEME, opts.theme || {});
    this.S = Object.assign({}, DEFAULT_STRINGS, opts.strings || {});
    this.roster = opts.roster;
    this.states = {};        // id -> {state, note, since, today}
    this.pos = {};           // id -> {x, y} 当前渲染坐标（瓦片）
    this.target = {};        // id -> {x, y} 目标坐标
    this.digest = null; this.banner = null;
    this.demo = { on: false, idx: 0, t0: 0 };
    this.offline = false;
    this._raf = null; this._animAcc = 0; this._last = 0; this._frame = 0;
    this._pollTimer = null;
    this._buildDom();
    this._layoutDesks();
    this._startLoop();
    if (opts.poll && opts.poll.fn) this._startPoll();
    var self = this;
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { self._last = 0; self._startLoop(); }
    });
  }

  VirtualOffice.prototype._buildDom = function () {
    var T = this.theme;
    this.container.classList.add('vo-root');
    var css = document.createElement('style'); css.textContent = VirtualOffice.css(T);
    this.container.appendChild(css);

    this.header = el('div', 'vo-head');
    this.header.innerHTML =
      '<div class="vo-title"><span class="vo-logo"></span><div><h1></h1><p></p></div></div>' +
      '<div class="vo-btns"><button class="vo-btn" data-a="demo"></button>' +
      '<button class="vo-btn" data-a="fs">' + this.S.fullscreen + '</button></div>';
    this.header.querySelector('h1').textContent = this.opts.title || '虚拟办公室';
    this.header.querySelector('p').textContent = this.opts.subtitle || '';
    this.container.appendChild(this.header);

    this.main = el('div', 'vo-main');
    this.stageWrap = el('div', 'vo-stage-wrap');
    this.canvas = el('canvas', 'vo-canvas');
    this.canvas.width = GRID_W * TILE; this.canvas.height = GRID_H * TILE;
    this.stageWrap.appendChild(this.canvas);
    this.offlineMask = el('div', 'vo-offline', '<div class="vo-offline-ico"></div><div></div>');
    this.offlineMask.querySelector('div:last-child').textContent = this.S.offline;
    this.offlineMask.style.display = 'none';
    this.stageWrap.appendChild(this.offlineMask);
    this.main.appendChild(this.stageWrap);

    this.side = el('div', 'vo-side');
    this.rosterBox = el('div', 'vo-panel');
    this.rosterBox.innerHTML = '<div class="vo-phead">' + this.S.rosterTitle + '</div><div class="vo-roster"></div>';
    this.digestBox = el('div', 'vo-panel');
    this.digestBox.innerHTML = '<div class="vo-phead">' + this.S.digestTitle + '</div><div class="vo-digest"></div>';
    this.side.appendChild(this.rosterBox); this.side.appendChild(this.digestBox);
    this.main.appendChild(this.side);
    this.container.appendChild(this.main);

    this.bannerEl = el('div', 'vo-banner'); this.bannerEl.style.display = 'none';
    this.container.insertBefore(this.bannerEl, this.main);

    this.card = el('div', 'vo-card'); this.card.style.display = 'none';
    this.container.appendChild(this.card);

    var self = this;
    this.header.querySelector('[data-a=demo]').addEventListener('click', function () { self._toggleDemo(); });
    this.header.querySelector('[data-a=fs]').addEventListener('click', function () {
      if (document.fullscreenElement) document.exitFullscreen();
      else self.container.requestFullscreen && self.container.requestFullscreen();
    });
    this.canvas.addEventListener('click', function (ev) { self._onClick(ev); });
    this.card.addEventListener('click', function (ev) {
      if (ev.target === self.card || ev.target.classList.contains('vo-card-close')) self.card.style.display = 'none';
    });
    this._demoBtnSync();
  };

  VirtualOffice.css = function (T) {
    return ''
    + '.vo-root{background:' + T.pageBg + ';color:' + T.textPanel + ';font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;'
    + 'display:flex;flex-direction:column;border-radius:14px;overflow:hidden;position:relative}'
    + '.vo-root *{box-sizing:border-box}'
    + '.vo-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px 10px;gap:12px;flex-wrap:wrap}'
    + '.vo-title{display:flex;gap:12px;align-items:center}'
    + '.vo-logo{width:34px;height:34px;border-radius:9px;background:' + T.accent + ';position:relative;flex:none}'
    + '.vo-logo::after{content:"";position:absolute;left:7px;top:9px;width:20px;height:4px;background:rgba(255,255,255,.9);box-shadow:0 7px 0 rgba(255,255,255,.55),0 14px 0 rgba(255,255,255,.3)}'
    + '.vo-head h1{margin:0;font-size:17px;color:' + T.headText + ';letter-spacing:.5px}'
    + '.vo-head p{margin:1px 0 0;font-size:12px;color:' + T.dim + '}'
    + '.vo-btn{background:' + T.panelBg + ';border:1px solid ' + T.panelLine + ';color:' + T.textPanel + ';border-radius:8px;'
    + 'padding:6px 14px;font-size:12.5px;cursor:pointer}'
    + '.vo-btn:hover{border-color:' + T.accent + ';color:#fff}'
    + '.vo-btn.on{background:' + T.warn + ';border-color:' + T.warn + ';color:#20240c}'
    + '.vo-main{display:flex;gap:12px;padding:0 18px 16px;align-items:stretch}'
    + '.vo-stage-wrap{flex:1;min-width:0;position:relative;border:1px solid ' + T.panelLine + ';border-radius:12px;overflow:hidden;background:' + T.bg + '}'
    + '.vo-canvas{display:block;width:100%;height:auto;image-rendering:pixelated;image-rendering:crisp-edges;cursor:pointer}'
    + '.vo-offline{position:absolute;inset:0;background:rgba(8,11,15,.88);display:flex;flex-direction:column;gap:10px;'
    + 'align-items:center;justify-content:center;font-size:13px;color:' + T.dim + ';text-align:center;padding:20px}'
    + '.vo-offline-ico{width:44px;height:52px;position:relative;opacity:.6}'
    + '.vo-offline-ico::before{content:"";position:absolute;bottom:0;left:4px;width:36px;height:22px;border:3px solid ' + T.dim + ';border-radius:4px 4px 10px 10px}'
    + '.vo-offline-ico::after{content:"";position:absolute;top:12px;left:16px;width:14px;height:14px;border:3px solid ' + T.dim + ';border-radius:50% 50% 0 0;transform:rotate(-35deg)}'
    + '.vo-side{width:290px;flex:none;display:flex;flex-direction:column;gap:12px;min-height:0}'
    + '.vo-panel{background:' + T.panelBg + ';border:1px solid ' + T.panelLine + ';border-radius:12px;overflow:hidden}'
    + '.vo-phead{padding:9px 13px;font-size:12.5px;font-weight:700;color:' + T.headText + ';border-bottom:1px solid ' + T.panelLine + ';letter-spacing:1px}'
    + '.vo-roster{max-height:300px;overflow-y:auto}'
    + '.vo-rrow{display:flex;align-items:center;gap:9px;padding:7px 13px;border-bottom:1px dashed ' + T.panelLine + ';cursor:pointer}'
    + '.vo-rrow:hover{background:rgba(63,177,255,.06)}'
    + '.vo-rdot{width:9px;height:9px;border-radius:50%;flex:none}'
    + '.vo-rname{font-size:12.5px;color:' + T.headText + ';flex:none}'
    + '.vo-rrole{font-size:11px;color:' + T.dim + ';flex:none;width:58px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
    + '.vo-rnote{font-size:11px;color:' + T.textPanel + ';margin-left:auto;text-align:right;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
    + '.vo-digest{padding:6px 13px 10px;max-height:220px;overflow-y:auto}'
    + '.vo-ditem{display:flex;gap:8px;padding:5px 0;font-size:12px;border-bottom:1px dashed ' + T.panelLine + '}'
    + '.vo-ditem a{color:' + T.accent + ';text-decoration:none}'
    + '.vo-ditem a:hover{text-decoration:underline}'
    + '.vo-dfail{color:' + T.bad + '}'
    + '.vo-dempty{color:' + T.dim + ';font-size:12px;padding:8px 0}'
    + '.vo-banner{margin:0 18px 10px;padding:9px 14px;border-radius:10px;font-size:13px;display:flex;align-items:center;gap:10px;cursor:pointer}'
    + '.vo-banner.warn{background:rgba(255,212,77,.12);border:1px solid ' + T.warn + ';color:' + T.warn + '}'
    + '.vo-banner.bad{background:rgba(255,123,114,.1);border:1px solid ' + T.bad + ';color:' + T.bad + '}'
    + '.vo-banner b{font-size:15px}'
    + '.vo-card{position:absolute;inset:0;background:rgba(8,11,15,.72);display:flex;align-items:center;justify-content:center;z-index:5}'
    + '.vo-card-in{background:' + T.panelBg + ';border:1px solid ' + T.panelLine + ';border-radius:14px;padding:18px 22px;width:320px;position:relative}'
    + '.vo-card-close{position:absolute;right:12px;top:10px;color:' + T.dim + ';cursor:pointer;font-size:16px}'
    + '.vo-card-top{display:flex;gap:14px;align-items:center;margin-bottom:8px}'
    + '.vo-card canvas{image-rendering:pixelated;border-radius:10px;background:' + T.bg + ';border:1px solid ' + T.panelLine + '}'
    + '.vo-card h3{margin:0;font-size:15px;color:' + T.headText + '}'
    + '.vo-card .role{font-size:12px;color:' + T.accent + ';margin-top:2px}'
    + '.vo-card .bio{font-size:12px;color:' + T.dim + ';margin:6px 0 10px}'
    + '.vo-card .stats{display:flex;gap:16px;font-size:12px;color:' + T.textPanel + '}'
    + '.vo-card .stats b{display:block;font-size:17px;color:' + T.headText + '}'
    + '@media(max-width:860px){.vo-main{flex-direction:column}.vo-side{width:100%;flex-direction:row}.vo-side .vo-panel{flex:1;min-width:0}}'
    ;
  };

  // 布局：按 roster 顺序给每个居民分配工位（自动网格）
  VirtualOffice.prototype._layoutDesks = function () {
    var perRow = 4, x0 = 3, y0 = 5, dx = 5.5, dy = 5.2, i = 0;
    for (var r = 0; r < 4; r++) for (var c = 0; c < perRow && i < this.roster.length; c++, i++) {
      var m = this.roster[i];
      var d = m.desk && m.desk.x != null ? m.desk : { x: x0 + c * dx, y: y0 + r * dy };
      m._desk = { x: d.x, y: d.y };
      // 初始站位：工位旁
      this.pos[m.id] = { x: d.x + 1.5, y: d.y + 1.2 };
      this.target[m.id] = { x: d.x + 1.5, y: d.y + 1.2 };
      this.states[m.id] = { state: 'idle', note: '' };
    }
    // 前台/大门坐标（下方正中）
    this._door = { x: GRID_W / 2, y: GRID_H - 1.5 };
    this._front = { x: GRID_W / 2, y: GRID_H - 4.5 };
    this._coffee = { x: GRID_W - 6.5, y: GRID_H - 5.5 };
    this._meeting = { x: GRID_W - 11, y: 6 };
  };

  VirtualOffice.prototype._startLoop = function () {
    if (this._raf) return;
    var self = this;
    function step(ts) {
      if (!self._last) self._last = ts;
      var dt = Math.min(100, ts - self._last); self._last = ts;
      self._animAcc += dt;
      if (self._animAcc >= 1000 / ANIM_FPS) { self._frame++; self._animAcc = 0; }
      self._tick(dt);
      self._draw();
      self._raf = requestAnimationFrame(step);
    }
    this._raf = requestAnimationFrame(step);
  };

  // ---------- 数据轮询 ----------
  VirtualOffice.prototype._startPoll = function () {
    var self = this, iv = this.opts.poll.interval || 5000;
    async function pull() {
      if (self.demo.on) return;
      try {
        var st = await self.opts.poll.fn();
        self.offline = false;
        self.offlineMask.style.display = 'none';
        self.applyState(st || {});
      } catch (e) {
        self.offline = true;
        self.offlineMask.style.display = 'flex';
      }
    }
    pull();
    this._pollTimer = setInterval(pull, iv);
  };

  // 外部/轮询灌入状态：{residents:{id:{state,note,today:{done,failed}}}, digest, banner}
  VirtualOffice.prototype.applyState = function (st) {
    var rs = st.residents || {};
    for (var id in rs) {
      if (!this.states[id]) continue;
      var s = rs[id];
      this.states[id].prev = this.states[id].state;
      this.states[id].state = STATE_SET[s.state] ? s.state : 'idle';
      this.states[id].note = s.note || '';
      this.states[id].today = s.today || this.states[id].today;
    }
    this.digest = st.digest || null;
    this.banner = st.banner || null;
    this._renderSide();
  };

  // ---------- 演示模式 ----------
  VirtualOffice.prototype._toggleDemo = function () {
    if (this.demo.on) { this._stopDemo(); return; }
    if (!this.opts.demo || !this.opts.demo.script) return;
    this.demo.on = true; this.demo.idx = 0; this.demo.t0 = performance.now();
    this._demoBtnSync();
    this.banner = { level: 'warn', text: this.S.demoOn };
    this._renderSide();
  };
  VirtualOffice.prototype._stopDemo = function () {
    this.demo.on = false;
    this._demoBtnSync();
    this.banner = null;
    for (var id in this.states) { this.states[id].state = 'idle'; this.states[id].note = ''; }
    this._renderSide();
  };
  VirtualOffice.prototype._demoBtnSync = function () {
    var b = this.header.querySelector('[data-a=demo]');
    if (!b) return;
    b.textContent = this.demo.on ? this.S.stop : this.S.demoBtn;
    b.classList.toggle('on', this.demo.on);
  };
  VirtualOffice.prototype._demoTick = function () {
    var d = this.opts.demo, sc = d.script;
    var el2 = (performance.now() - this.demo.t0) / 1000 / (d.speed || 1);
    while (this.demo.idx < sc.length && sc[this.demo.idx].t <= el2) {
      var s = sc[this.demo.idx++];
      if (s.residents) this.applyState({ residents: s.residents, digest: s.digest, banner: s.banner });
      else if (s.set) this.applyState({ residents: s.set });
    }
    if (this.demo.idx >= sc.length && el2 > (d.holdAfter || 8) + (sc[sc.length - 1].t)) this._stopDemo();
  };

  // ---------- 每帧逻辑 ----------
  VirtualOffice.prototype._tick = function (dt) {
    if (this.demo.on) this._demoTick();
    var k = clamp(dt / 1000 * 6, 0, 1);   // 位移平滑系数
    for (var i = 0; i < this.roster.length; i++) {
      var m = this.roster[i], st = this.states[m.id];
      // 目标位：工作态回工位；行走态向前台；咖啡彩蛋
      var tgt = this.target[m.id];
      if (st.state === 'walking') tgt = { x: this._front.x, y: this._front.y };
      else if (st.state === 'sleeping' && (this._frame % 240) < 60) tgt = { x: this._coffee.x, y: this._coffee.y };
      else tgt = { x: m._desk.x + 1.5, y: m._desk.y + 1.2 };
      var p = this.pos[m.id];
      p.x = lerp(p.x, tgt.x, k); p.y = lerp(p.y, tgt.y, k);
      st._moving = Math.abs(p.x - tgt.x) + Math.abs(p.y - tgt.y) > 0.15;
      st._dir = tgt.x < p.x - 0.05 ? -1 : 1;
    }
  };

  // ---------- 绘制 ----------
  VirtualOffice.prototype._draw = function () {
    var ctx = this.canvas.getContext('2d');
    var W = this.canvas.width, H = this.canvas.height;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = this.theme.bg; ctx.fillRect(0, 0, W, H);

    this._drawFloor(ctx);
    this._drawWalls(ctx);
    this._drawMeeting(ctx);
    this._drawCoffee(ctx);
    this._drawDoor(ctx);
    // 工位（含桌名牌）
    for (var i = 0; i < this.roster.length; i++) this._drawDesk(ctx, this.roster[i]);
    // 人（按 y 排序保证遮挡关系）
    var list = this.roster.slice().sort(function (a, b) { return a._desk.y - b._desk.y; });
    for (var j = 0; j < list.length; j++) this._drawPerson(ctx, list[j]);
    // 顶部横幅由 DOM 承担，这里画个室内时钟
    this._drawClock(ctx);
  };

  VirtualOffice.prototype._drawFloor = function (ctx) {
    var T = this.theme;
    for (var y = 3; y < GRID_H; y++) for (var x = 0; x < GRID_W; x++) {
      ctx.fillStyle = ((x + y) & 1) ? T.floorA : T.floorB;
      ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
    }
    // 门口地毯（迎宾垫）
    ctx.fillStyle = 'rgba(63,177,255,.14)';
    ctx.fillRect((this._door.x - 2.4) * TILE, (GRID_H - 3.2) * TILE, TILE * 4.8, TILE * 2.2);
    ctx.strokeStyle = 'rgba(63,177,255,.35)'; ctx.lineWidth = 2;
    ctx.strokeRect((this._door.x - 2.4) * TILE, (GRID_H - 3.2) * TILE, TILE * 4.8, TILE * 2.2);
    // 左下 + 右上角大绿植（画在地板之后才不被覆盖）
    this._drawPlant(ctx, TILE * 1.2, TILE * (GRID_H - 6), 1.6);
    this._drawPlant(ctx, TILE * (GRID_W - 4.2), TILE * 3.4, 1.4);
  };

  VirtualOffice.prototype._drawWalls = function (ctx) {
    var T = this.theme;
    ctx.fillStyle = T.wall; ctx.fillRect(0, 0, GRID_W * TILE, TILE * 2.6);
    ctx.fillStyle = T.wallTop; ctx.fillRect(0, TILE * 2.6, GRID_W * TILE, 4);
    // 窗户
    for (var i = 0; i < 6; i++) {
      var wx = 3 + i * 7.6;
      ctx.fillStyle = '#0e1a26'; ctx.fillRect(wx * TILE, TILE * 0.5, TILE * 3.4, TILE * 1.5);
      ctx.fillStyle = 'rgba(122,162,255,.30)'; ctx.fillRect(wx * TILE + 2, TILE * 0.5 + 2, TILE * 3.4 - 4, TILE * 1.5 - 4);
      ctx.fillStyle = 'rgba(255,255,255,.10)'; ctx.fillRect(wx * TILE + 2, TILE * 0.5 + 2, TILE * 3.4 - 4, 3);
      ctx.strokeStyle = T.wallTop; ctx.lineWidth = 2;
      ctx.strokeRect(wx * TILE, TILE * 0.5, TILE * 3.4, TILE * 1.5);
    }
  };

  VirtualOffice.prototype._drawMeeting = function (ctx) {
    var T = this.theme, m = this._meeting;
    var x = m.x * TILE, y = m.y * TILE;
    // 白板
    ctx.fillStyle = '#0e1a26'; ctx.fillRect(x, TILE * 3.1, TILE * 6, TILE * 2.2);
    ctx.strokeStyle = T.furnitureEdge; ctx.lineWidth = 2; ctx.strokeRect(x, TILE * 3.1, TILE * 6, TILE * 2.2);
    ctx.fillStyle = 'rgba(63,177,255,.35)';
    ctx.fillRect(x + 6, TILE * 3.1 + 6, TILE * 2.4, 3);
    ctx.fillRect(x + 6, TILE * 3.1 + 13, TILE * 4.2, 3);
    ctx.fillRect(x + 6, TILE * 3.1 + 20, TILE * 1.6, 3);
    // 长桌
    ctx.fillStyle = T.furniture; ctx.fillRect(x + TILE * 0.4, y + TILE * 0.6, TILE * 5.2, TILE * 2.6);
    ctx.fillStyle = T.furnitureEdge; ctx.fillRect(x + TILE * 0.4, y + TILE * 0.6, TILE * 5.2, 4);
    // 桌面水杯 ×2
    ctx.fillStyle = '#cfe0ff';
    ctx.fillRect(x + TILE * 1.2, y + TILE * 1.7, 4, 5); ctx.fillRect(x + TILE * 3.6, y + TILE * 1.7, 4, 5);
    ctx.fillStyle = T.mint; ctx.fillRect(x + TILE * 1.2, y + TILE * 1.7, 4, 2); ctx.fillRect(x + TILE * 3.6, y + TILE * 1.7, 4, 2);
    // 椅子四个
    for (var i = 0; i < 3; i++) {
      ctx.fillStyle = '#161e2a';
      ctx.fillRect(x + TILE * (0.9 + i * 1.6), y + TILE * 0.1, TILE * 0.8, TILE * 0.5);
      ctx.fillRect(x + TILE * (0.9 + i * 1.6), y + TILE * 3.3, TILE * 0.8, TILE * 0.5);
    }
  };

  VirtualOffice.prototype._drawCoffee = function (ctx) {
    var T = this.theme, c = this._coffee;
    var x = c.x * TILE, y = c.y * TILE;
    ctx.fillStyle = T.furniture; ctx.fillRect(x, y, TILE * 2.4, TILE * 1.2);
    ctx.fillStyle = T.coffee; ctx.fillRect(x + 4, y + 4, TILE * 0.9, TILE * 0.9);
    ctx.fillStyle = T.warn; ctx.fillRect(x + TILE * 1.3, y + 6, 6, 6);
    // 吧台
    ctx.fillStyle = T.furniture; ctx.fillRect(x - TILE * 2.8, y + TILE * 1.6, TILE * 5.2, TILE * 0.8);
    // 绿植（咖啡机旁 + 吧台尾）
    this._drawPlant(ctx, x + TILE * 2.6, y - TILE * 0.4, 1.3);
    this._drawPlant(ctx, x - TILE * 3.4, y + TILE * 0.4, 1.1);
  };

  VirtualOffice.prototype._drawPlant = function (ctx, px, py, scale) {
    var T = this.theme, k = scale || 1;
    ctx.fillStyle = T.furniture; ctx.fillRect(px, py + 10 * k, 14 * k, 9 * k);
    ctx.fillStyle = T.plant;
    ctx.fillRect(px + 2 * k, py + 2 * k, 10 * k, 8 * k);
    ctx.fillRect(px - 1 * k, py - 4 * k, 5 * k, 7 * k); ctx.fillRect(px + 9 * k, py - 4 * k, 5 * k, 7 * k);
    ctx.fillRect(px + 4 * k, py - 8 * k, 5 * k, 8 * k);
    ctx.fillStyle = 'rgba(255,255,255,.14)'; ctx.fillRect(px + 3 * k, py + 3 * k, 3 * k, 3 * k);
  };

  VirtualOffice.prototype._drawDoor = function (ctx) {
    var T = this.theme, d = this._door;
    var x = (d.x - 1.2) * TILE, y = (GRID_H - 2.6) * TILE;
    ctx.fillStyle = '#0d1420'; ctx.fillRect(x, y, TILE * 2.4, TILE * 2.6);
    ctx.strokeStyle = T.accent; ctx.lineWidth = 2; ctx.strokeRect(x, y, TILE * 2.4, TILE * 2.6);
    // 门上"欢迎"指示灯
    var on = (this._frame % 16) < 8;
    ctx.fillStyle = on ? T.mint : T.furnitureEdge;
    ctx.fillRect(x + TILE * 1.05, y + 6, 6, 6);
  };

  VirtualOffice.prototype._drawDesk = function (ctx, m) {
    var T = this.theme, st = this.states[m.id];
    var x = m._desk.x * TILE, y = m._desk.y * TILE;
    var absent = st && st.state === 'away';
    ctx.globalAlpha = absent ? 0.45 : 1;
    // 桌
    ctx.fillStyle = T.furniture; ctx.fillRect(x, y + TILE * 0.7, TILE * 3, TILE * 1.5);
    ctx.fillStyle = T.furnitureEdge; ctx.fillRect(x, y + TILE * 0.7, TILE * 3, 3);
    // 显示器（工作中发光呼吸）
    var glow = 0;
    if (st && (st.state === 'working' || st.state === 'search' || st.state === 'doc')) {
      glow = 0.5 + 0.5 * Math.sin(this._frame / 4);
    }
    ctx.fillStyle = '#0d1420'; ctx.fillRect(x + TILE * 0.5, y - TILE * 0.5, TILE * 2, TILE * 1.1);
    if (glow > 0) {
      ctx.fillStyle = 'rgba(63,177,255,' + (0.10 + glow * 0.16) + ')';
      ctx.fillRect(x + TILE * 0.5 - 3, y - TILE * 0.5 - 3, TILE * 2 + 6, TILE * 1.1 + 6);
    }
    ctx.fillStyle = glow > 0 ? T.screen : '#1a2536';
    ctx.fillRect(x + TILE * 0.62, y - TILE * 0.38, TILE * 1.76, TILE * 0.86);
    // 支架
    ctx.fillStyle = T.furnitureEdge; ctx.fillRect(x + TILE * 1.4, y + TILE * 0.6, TILE * 0.2, TILE * 0.14);
    // 桌牌
    ctx.fillStyle = absent ? T.dim : 'rgba(234,242,251,.75)';
    ctx.font = '9px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(m.name, x + TILE * 1.5, y + TILE * 2.62);
    ctx.globalAlpha = 1;
  };

  // 程序化小人（约 10×16 逻辑像素，像素画风格）
  VirtualOffice.prototype._drawPerson = function (ctx, m) {
    var st = this.states[m.id]; if (!st) return;
    var p = this.pos[m.id];
    var px = Math.round(p.x * TILE), py = Math.round(p.y * TILE);
    var pal = m.palette || {};
    var hair = pal.hair || '#ffd44d', cloth = pal.clothes || '#3fb1ff', skin = pal.skin || '#f2c9a0';
    var f = this._frame, T = this.theme;
    var dir = st._dir || 1;
    ctx.save();
    ctx.translate(px, py);
    // 状态微动画
    var bob = 0, tilt = 0, armUp = 0, crouch = 0, typeArm = 0;
    if (st.state === 'idle' || st.state === 'walking') bob = ((f % 10) < 5) ? 0 : 1;
    if (st.state === 'sleeping') tilt = 0.07;
    if (st.state === 'celebrating') armUp = 1;
    if (st.state === 'upset') crouch = 3;
    if (st.state === 'working' || st.state === 'search' || st.state === 'doc') typeArm = ((f % 4) < 2) ? 0 : 1;
    if (st.state === 'away') { ctx.globalAlpha = 0.25; }

    ctx.scale(dir, 1); ctx.rotate(tilt);
    var y0 = bob + crouch;
    // 腿
    ctx.fillStyle = '#2a3342';
    if (st._moving) {
      var w = (f % 4);
      ctx.fillRect(-3, y0 + 11, 2, w === 1 || w === 3 ? 4 : 3);
      ctx.fillRect(1, y0 + 11, 2, w === 0 || w === 2 ? 4 : 3);
    } else {
      ctx.fillRect(-3, y0 + 11, 2, 4); ctx.fillRect(1, y0 + 11, 2, 4);
    }
    // 身
    ctx.fillStyle = cloth;
    ctx.fillRect(-4, y0 + 4, 8, 8);
    // 手臂
    ctx.fillStyle = skin;
    if (armUp) { ctx.fillRect(3, y0 - 2, 2, 7); ctx.fillRect(-5, y0 + 5, 2, 5); }
    else if (typeArm) { ctx.fillRect(-6, y0 + 6, 3, 2); ctx.fillRect(3, y0 + 6, 3, 2); }
    else { ctx.fillRect(-5, y0 + 5, 2, 5); ctx.fillRect(3, y0 + 5, 2, 5); }
    // 头
    ctx.fillStyle = skin; ctx.fillRect(-3, y0 - 3, 6, 6);
    ctx.fillStyle = hair; ctx.fillRect(-3, y0 - 4, 6, 3);
    if (dir < 0) { ctx.fillStyle = hair; ctx.fillRect(1, y0 - 3, 2, 2); }
    // 睡觉 zZz / 气泡
    ctx.restore();

    // 气泡（不随 dir 翻转）
    this._drawBubble(ctx, m, px, py - (18 + bob));
    ctx.globalAlpha = 1;
  };

  VirtualOffice.prototype._drawBubble = function (ctx, m, px, py) {
    var st = this.states[m.id];
    var kind = null;
    switch (st.state) {
      case 'working': kind = 'think'; break;
      case 'search': kind = 'magnifier'; break;
      case 'doc': kind = 'paper'; break;
      case 'celebrating': kind = 'check'; break;
      case 'upset': kind = 'cross'; break;
      case 'sleeping': kind = 'zzz'; break;
      case 'alert': kind = 'alertdot'; break;
      case 'walking': kind = 'brief'; break;
    }
    if (!kind) return;
    var T = this.theme, bx = px + 8, by = py - 6;
    // 云朵泡
    ctx.fillStyle = '#eaf2fb';
    rr(ctx, bx, by, 22, 16, 5); ctx.fill();
    ctx.fillStyle = '#eaf2fb';
    ctx.beginPath(); ctx.moveTo(bx + 4, by + 15); ctx.lineTo(bx + 8, by + 21); ctx.lineTo(bx + 11, by + 15); ctx.fill();
    // alert 用红底
    if (kind === 'alertdot') {
      ctx.fillStyle = T.bad; rr(ctx, bx, by, 22, 16, 5); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.font = 'bold 11px monospace'; ctx.textAlign = 'center';
      ctx.fillText('!', bx + 11, by + 12); return;
    }
    var c = '#0b0f14';
    if (kind === 'think') {
      ctx.fillStyle = 'rgba(139,150,165,.9)';
      ctx.beginPath(); ctx.arc(bx + 11, by + 8, 5, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(bx + 17, by + 6, 3, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(bx + 20, by + 11, 2, 0, 7); ctx.fill();
    } else if (kind === 'magnifier') {
      ctx.strokeStyle = c; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(bx + 10, by + 8, 4, 0, 7); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(bx + 13, by + 11); ctx.lineTo(bx + 17, by + 15); ctx.stroke();
    } else if (kind === 'paper') {
      ctx.fillStyle = c; ctx.fillRect(bx + 8, by + 3, 9, 11);
      ctx.fillStyle = '#eaf2fb';
      ctx.fillRect(bx + 10, by + 5, 5, 1); ctx.fillRect(bx + 10, by + 8, 5, 1); ctx.fillRect(bx + 10, by + 11, 3, 1);
    } else if (kind === 'check') {
      ctx.strokeStyle = T.good; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(bx + 7, by + 9); ctx.lineTo(bx + 10, by + 12); ctx.lineTo(bx + 16, by + 4); ctx.stroke();
    } else if (kind === 'cross') {
      ctx.strokeStyle = T.bad; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(bx + 7, by + 4); ctx.lineTo(bx + 15, by + 12);
      ctx.moveTo(bx + 15, by + 4); ctx.lineTo(bx + 7, by + 12); ctx.stroke();
    } else if (kind === 'zzz') {
      ctx.fillStyle = T.dim; ctx.font = 'bold 9px monospace'; ctx.textAlign = 'left';
      ctx.fillText('z', bx + 6, by + 12); ctx.fillText('Z', bx + 12, by + 7);
    } else if (kind === 'brief') {
      ctx.fillStyle = c; ctx.fillRect(bx + 7, by + 6, 11, 8);
      ctx.fillRect(bx + 10, by + 3, 5, 3);
    }
  };

  VirtualOffice.prototype._drawClock = function (ctx) {
    var T = this.theme;
    var d = new Date();
    var txt = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
    ctx.fillStyle = 'rgba(11,15,20,.75)';
    rr(ctx, GRID_W * TILE - 74, 8, 62, 24, 6); ctx.fill();
    ctx.fillStyle = T.mint; ctx.font = 'bold 13px monospace'; ctx.textAlign = 'center';
    ctx.fillText(txt, GRID_W * TILE - 43, 25);
    // 呼吸小点（表示"活着"）
    var on = (this._frame % 16) < 8;
    ctx.fillStyle = on ? T.mint : '#233';
    ctx.fillRect(GRID_W * TILE - 66, 15, 4, 4);
  };

  // ---------- 侧栏 / 横幅 / 名片 ----------
  VirtualOffice.prototype._stateLabel = function (s) {
    var M = {
      idle: this.S.idle, walking: this.S.walking, working: this.S.working, search: this.S.search,
      doc: this.S.doc, celebrating: this.S.celebrating, upset: this.S.upset,
      sleeping: this.S.sleeping, alert: this.S.alert, away: this.S.away
    };
    return M[s] || s;
  };
  VirtualOffice.prototype._stateColor = function (s) {
    var T = this.theme;
    var M = { working: T.accent, search: T.accent, doc: T.accent, celebrating: T.good, upset: T.bad, alert: T.bad, sleeping: T.dim, away: T.dim, idle: T.dim, walking: T.warn };
    return M[s] || T.dim;
  };

  VirtualOffice.prototype._renderSide = function () {
    var self = this;
    // 在岗板
    var box = this.rosterBox.querySelector('.vo-roster'); box.innerHTML = '';
    this.roster.forEach(function (m) {
      var st = self.states[m.id] || {};
      var row = el('div', 'vo-rrow');
      row.innerHTML = '<span class="vo-rdot" style="background:' + self._stateColor(st.state) + '"></span>' +
        '<span class="vo-rname">' + m.name + '</span><span class="vo-rrole">' + (m.role || '') + '</span>' +
        '<span class="vo-rnote">' + (st.note || self._stateLabel(st.state)) + '</span>';
      row.addEventListener('click', function () { self._openCard(m); });
      box.appendChild(row);
    });
    // 战报
    var dg = this.digestBox.querySelector('.vo-digest'); dg.innerHTML = '';
    if (!this.digest || (!this.digest.top && !this.digest.fails)) {
      dg.appendChild(el('div', 'vo-dempty', this.S.empty));
    } else {
      (this.digest.top || []).forEach(function (it) {
        var d2 = el('div', 'vo-ditem');
        var txt = '<span style="color:' + self.theme.mint + '">◆</span><span>' + (it.name ? it.name + ' ' : '') + (it.href ? '<a href="' + it.href + '" target="_blank">' + it.text + '</a>' : it.text) + '</span>';
        d2.innerHTML = txt; dg.appendChild(d2);
      });
      if (this.digest.fails && this.digest.fails.length) {
        dg.appendChild(el('div', 'vo-phead', this.S.failTitle));
        this.digest.fails.forEach(function (it) {
          var d3 = el('div', 'vo-ditem vo-dfail', '<span>◇</span><span>' + (it.name ? it.name + ' ' : '') + it.text + '</span>');
          dg.appendChild(d3);
        });
      }
    }
    // 横幅
    if (this.banner && this.banner.text) {
      this.bannerEl.style.display = 'flex';
      this.bannerEl.className = 'vo-banner ' + (this.banner.level || 'warn');
      this.bannerEl.innerHTML = '<b>' + (this.banner.count != null ? this.banner.count + ' ' : '') + '</b><span>' + this.banner.text + '</span>';
    } else this.bannerEl.style.display = 'none';
  };

  VirtualOffice.prototype._onClick = function (ev) {
    var rect = this.canvas.getBoundingClientRect();
    var sx = this.canvas.width / rect.width;
    var mx = (ev.clientX - rect.left) * sx, my = (ev.clientY - rect.top) * sx;
    var best = null, bd = 1e9;
    for (var i = 0; i < this.roster.length; i++) {
      var m = this.roster[i], p = this.pos[m.id];
      var d = Math.abs(p.x * TILE - mx) + Math.abs((p.y * TILE - 8) - my);
      if (d < bd) { bd = d; best = m; }
    }
    if (best && bd < 40) this._openCard(best);
  };

  VirtualOffice.prototype._openCard = function (m) {
    var st = this.states[m.id] || {}, self = this;
    this.card.style.display = 'flex';
    this.card.innerHTML = '';
    var inn = el('div', 'vo-card-in');
    inn.innerHTML = '<span class="vo-card-close">✕</span>' +
      '<div class="vo-card-top"><canvas width="64" height="64"></canvas>' +
      '<div><h3>' + m.name + '</h3><div class="role">' + (m.role || '') + '</div></div></div>' +
      '<div class="bio">' + (m.bio || '') + '</div>' +
      '<div class="stats"><div><b>' + ((st.today && st.today.done) || 0) + '</b>' + this.S.todayDone + '</div>' +
      '<div><b>' + ((st.today && st.today.failed) || 0) + '</b>' + this.S.todayFail + '</div>' +
      '<div><b>' + this._stateLabel(st.state) + '</b>当前状态</div></div>';
    this.card.appendChild(inn);
    // 画大头像（放大 4 倍的同款小人）
    var cv = inn.querySelector('canvas'), c2 = cv.getContext('2d');
    c2.imageSmoothingEnabled = false;
    var tmp = document.createElement('canvas'); tmp.width = 16; tmp.height = 20;
    var tc = tmp.getContext('2d');
    var pal = m.palette || {};
    tc.fillStyle = pal.skin || '#f2c9a0'; tc.fillRect(5, 2, 6, 6);
    tc.fillStyle = pal.hair || '#ffd44d'; tc.fillRect(5, 0, 6, 3);
    tc.fillStyle = pal.clothes || '#3fb1ff'; tc.fillRect(4, 8, 8, 8);
    tc.fillStyle = '#2a3342'; tc.fillRect(5, 16, 2, 4); tc.fillRect(9, 16, 2, 4);
    c2.drawImage(tmp, 0, 0, 16, 20, 0, 0, 64, 64);
    inn.querySelector('.vo-card-close').addEventListener('click', function () { self.card.style.display = 'none'; });
  };

  global.VirtualOffice = VirtualOffice;
})(window);
