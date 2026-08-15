/**
 * DDW AI Hub - 插件市场交互逻辑
 * 三个视图：插件目录(catalog)、插件详情(detail)、已安装管理(managed)
 * 通过 hash 路由: #catalog | #detail/{name} | #managed
 */
(function (global) {
  'use strict';

  const DDW = global.DDW = global.DDW || {};
  const BASE = '/api/v1';

  /* ------------------------------------------------------------------ */
  /*  Helpers                                                           */
  /* ------------------------------------------------------------------ */

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
    );
  }

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return (ctx || document).querySelectorAll(sel); }

  async function apiGet(path) {
    try {
      const r = await DDW.api.get(path);
      return r.ok ? r.data : null;
    } catch { return null; }
  }

  async function apiPost(path, body) {
    try {
      const r = await DDW.api.post(path, body);
      return r;
    } catch (e) {
      return { ok: false, message: e.message || '请求失败' };
    }
  }

  function showLoading(host) {
    host.innerHTML = '<div class="pm-loading"><div class="pm-spinner"></div><p style="margin-top:12px;">加载中...</p></div>';
  }

  function showEmpty(host, icon, text) {
    host.innerHTML = `<div class="pm-empty"><div class="pm-empty-icon">${icon}</div><p>${text}</p></div>`;
  }

  function showModal(title, body, actions) {
    const overlay = document.createElement('div');
    overlay.className = 'pm-modal-overlay';
    overlay.innerHTML = `
      <div class="pm-modal">
        <h3>${title}</h3>
        <p>${body}</p>
        <div class="pm-modal-actions" id="pm-modal-actions"></div>
      </div>`;
    document.body.appendChild(overlay);
    const actHost = overlay.querySelector('#pm-modal-actions');
    actions.forEach(a => {
      const btn = document.createElement('button');
      btn.className = a.cls || 'pm-btn pm-btn-outline';
      btn.textContent = a.label;
      btn.onclick = () => { overlay.remove(); if (a.fn) a.fn(); };
      actHost.appendChild(btn);
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  }

  /* ------------------------------------------------------------------ */
  /*  State                                                             */
  /* ------------------------------------------------------------------ */

  let state = {
    view: 'catalog',
    plugins: [],          // 全量市场列表
    installedMap: {},      // name → {enabled, version}
    stats: null,
    search: '',
    category: 'all',
    sort: 'rating',
  };

  /* ------------------------------------------------------------------ */
  /*  Navigation                                                        */
  /* ------------------------------------------------------------------ */

  function navigate(view, param) {
    if (view === 'detail') {
      location.hash = `detail/${param}`;
    } else if (view === 'managed') {
      location.hash = 'managed';
    } else {
      location.hash = 'catalog';
    }
  }

  function parseHash() {
    const h = location.hash.replace(/^#\/?/, '');
    if (h.startsWith('detail/')) {
      return { view: 'detail', param: decodeURIComponent(h.slice(7)) };
    }
    if (h === 'managed') {
      return { view: 'managed' };
    }
    return { view: 'catalog' };
  }

  /* ------------------------------------------------------------------ */
  /*  Data loading                                                      */
  /* ------------------------------------------------------------------ */

  async function loadAllData() {
    const [listResp, installedResp, statsResp] = await Promise.all([
      apiGet('/plugins'),
      apiGet('/plugins/installed'),
      apiGet('/plugins/stats'),
    ]);

    state.plugins = listResp?.items || [];
    state.stats = statsResp || null;

    state.installedMap = {};
    (installedResp?.items || []).forEach(inst => {
      state.installedMap[inst.name] = inst;
    });
  }

  /* ------------------------------------------------------------------ */
  /*  Render: Catalog (list view)                                       */
  /* ------------------------------------------------------------------ */

  function renderCatalog() {
    state.view = 'catalog';
    const container = $('#pm-content');
    showLoading(container);

    let list = state.plugins.slice();

    // Filter by category
    if (state.category !== 'all') {
      list = list.filter(p => {
        const cat = typeof p.category === 'object' ? p.category.value || p.category : p.category;
        return cat === state.category;
      });
    }

    // Filter by search
    if (state.search) {
      const q = state.search.toLowerCase();
      list = list.filter(p =>
        (p.name || '').toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q) ||
        (p.author || '').toLowerCase().includes(q) ||
        (p.tags || []).some(t => t.toLowerCase().includes(q))
      );
    }

    // Sort
    if (state.sort === 'rating') list.sort((a, b) => (b.rating || 0) - (a.rating || 0));
    else if (state.sort === 'downloads') list.sort((a, b) => (b.downloads || 0) - (a.downloads || 0));
    else if (state.sort === 'name') list.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

    const cats = [...new Set(state.plugins.map(p => {
      const c = typeof p.category === 'object' ? p.category.value || p.category : p.category;
      return c;
    }).filter(Boolean))];
    const catLabels = {
      'infrastructure': '基础设施', 'data': '数据分析', 'ai': 'AI 工具',
      'business': '业务插件', 'devops': 'DevOps', 'marketing': '营销',
    };

    const installedCount = Object.keys(state.installedMap).length;
    const totalCount = state.plugins.length;

    container.innerHTML = `
      <!-- View tabs -->
      <div class="pm-view-tabs">
        <button class="pm-view-tab active" data-view="catalog">🏪 插件市场</button>
        <button class="pm-view-tab" data-view="managed">📦 已安装 (${installedCount})</button>
      </div>

      <!-- Toolbar -->
      <div class="pm-toolbar">
        <input type="search" class="pm-search" id="pm-search" placeholder="搜索插件名称、标签、描述..."
               value="${esc(state.search)}">
        <select class="pm-sort" id="pm-sort">
          <option value="rating" ${state.sort === 'rating' ? 'selected' : ''}>⭐ 按评分</option>
          <option value="downloads" ${state.sort === 'downloads' ? 'selected' : ''}>📥 按下载量</option>
          <option value="name" ${state.sort === 'name' ? 'selected' : ''}>🔤 按名称</option>
        </select>
      </div>

      <!-- Category chips -->
      <div class="pm-chips" id="pm-chips">
        <button class="pm-chip ${state.category === 'all' ? 'active' : ''}" data-cat="all">全部</button>
        ${cats.map(c => `
          <button class="pm-chip ${state.category === c ? 'active' : ''}" data-cat="${esc(c)}">
            ${esc(catLabels[c] || c)}
          </button>
        `).join('')}
      </div>

      <!-- Result count -->
      <div class="pm-result-count" style="margin-top:20px;">
        找到 <strong>${list.length}</strong> 个插件（共 ${totalCount} 个可用）
      </div>

      <!-- Grid -->
      <div class="pm-grid" id="pm-grid"></div>
    `;

    const grid = $('#pm-grid');
    if (list.length === 0) {
      showEmpty(grid, '🔍', '没有匹配的插件，试试其他关键词');
    } else {
      grid.innerHTML = list.map(p => renderCard(p)).join('');
      grid.querySelectorAll('.pm-card').forEach(card => {
        card.addEventListener('click', () => navigate('detail', card.dataset.name));
      });
    }

    // Bind events
    $('#pm-search').addEventListener('input', e => {
      state.search = e.target.value;
      renderCatalog();
      // Restore focus
      const el = $('#pm-search');
      if (el) { el.focus(); el.selectionStart = el.selectionEnd = el.value.length; }
    });
    $('#pm-sort').addEventListener('change', e => {
      state.sort = e.target.value;
      renderCatalog();
    });
    $$('.pm-chip').forEach(ch => {
      ch.addEventListener('click', e => {
        e.stopPropagation();
        state.category = ch.dataset.cat;
        renderCatalog();
      });
    });
    $$('.pm-view-tab').forEach(tab => {
      tab.addEventListener('click', () => navigate(tab.dataset.view));
    });
  }

  function renderCard(p) {
    const isInstalled = !!state.installedMap[p.name];
    const cat = typeof p.category === 'object' ? p.category.value || p.category : p.category;
    const catLabels = {
      'infrastructure': '基础设施', 'data': '数据分析', 'ai': 'AI 工具',
      'business': '业务插件', 'devops': 'DevOps', 'marketing': '营销',
    };
    const iconMap = {
      'infrastructure': '🏗️', 'data': '📊', 'ai': '🤖',
      'business': '💼', 'devops': '⚙️', 'marketing': '📣',
    };

    return `
      <div class="pm-card" data-name="${esc(p.name)}">
        <div class="pm-card-head">
          <span class="pm-cat-badge">${esc(catLabels[cat] || cat || '其他')}</span>
          ${isInstalled ? '<span class="pm-installed-badge">✓ 已安装</span>' : ''}
          <span>${iconMap[cat] || '🧩'}</span>
        </div>
        <div class="pm-card-body">
          <h3>${esc(p.name)}</h3>
          <p class="pm-desc">${esc(p.description)}</p>
          <div class="pm-card-tags">
            ${(p.tags || []).slice(0, 3).map(t => `<span class="pm-tag">${esc(t)}</span>`).join('')}
          </div>
          <div class="pm-card-meta">
            <span class="pm-rating">★ ${p.rating != null ? p.rating.toFixed(1) : '—'}</span>
            <span class="pm-author">${esc(p.author || '未知')}</span>
            <span>${p.downloads || 0} 下载</span>
          </div>
          <div class="pm-card-actions" onclick="event.stopPropagation()">
            <button class="pm-btn pm-btn-outline pm-btn-sm" onclick="event.stopPropagation(); navigate('detail','${esc(p.name)}')">详情</button>
            ${!isInstalled
              ? `<button class="pm-btn pm-btn-primary pm-btn-sm" onclick="event.stopPropagation(); PM.install('${esc(p.name)}', this)">安装</button>`
              : `<button class="pm-btn pm-btn-blue pm-btn-sm" disabled>已安装</button>`
            }
          </div>
        </div>
      </div>`;
  }

  /* ------------------------------------------------------------------ */
  /*  Render: Detail view                                               */
  /* ------------------------------------------------------------------ */

  async function renderDetail(pluginName) {
    state.view = 'detail';
    const container = $('#pm-content');
    showLoading(container);

    const detail = await apiGet(`/plugins/${encodeURIComponent(pluginName)}`);
    if (!detail) {
      showEmpty(container, '❌', `插件 "${pluginName}" 不存在或已下架`);
      return;
    }

    const isInstalled = !!state.installedMap[pluginName];
    const isEnabled = state.installedMap[pluginName]?.enabled;

    const catLabels = {
      'infrastructure': '基础设施', 'data': '数据分析', 'ai': 'AI 工具',
      'business': '业务插件', 'devops': 'DevOps', 'marketing': '营销',
    };
    const cat = typeof detail.category === 'object' ? detail.category.value || detail.category : detail.category;

    const actionBtns = isInstalled
      ? `
        <button class="pm-btn pm-btn-blue" onclick="PM.toggleEnabled('${esc(pluginName)}', ${isEnabled})">
          ${isEnabled ? '⏸ 禁用' : '▶ 启用'}
        </button>
        <button class="pm-btn pm-btn-danger" onclick="PM.confirmUninstall('${esc(pluginName)}')">
          🗑 卸载
        </button>`
      : `
        <button class="pm-btn pm-btn-primary" id="pm-install-btn" onclick="PM.installDetail('${esc(pluginName)}')">
          ⚡ 安装插件
        </button>`;

    container.innerHTML = `
      <!-- Hero -->
      <div class="pm-detail-hero">
        <div class="container">
          <a href="#catalog" style="color:rgba(255,255,255,.7);font-size:13px;text-decoration:none;">← 返回插件市场</a>
          <div class="pm-detail-top" style="margin-top:16px;">
            <div class="pm-detail-icon">🧩</div>
            <div class="pm-detail-info">
              <h1>${esc(detail.name)}</h1>
              <p class="pm-sub">${esc(detail.description)}</p>
              <div class="pm-detail-meta">
                <span>★ ${detail.rating != null ? detail.rating.toFixed(1) : '—'}</span>
                <span>📥 ${detail.downloads || 0} 下载</span>
                <span>📁 ${esc(catLabels[cat] || cat || '其他')}</span>
                <span>📦 v${esc(detail.version)}</span>
                <span>👨‍💻 ${esc(detail.author || '未知')}</span>
                ${isInstalled ? `<span style="color:#86EFAC;">✓ 已安装${isEnabled ? ' (已启用)' : ' (已禁用)'}</span>` : ''}
              </div>
            </div>
            <div class="pm-detail-actions">
              ${actionBtns}
            </div>
          </div>
        </div>
      </div>

      <!-- Body -->
      <div class="pm-detail-body">
        <div class="container">
          <div class="pm-detail-grid">
            <div>
              <!-- README / Description -->
              <div class="pm-section">
                <h3>📖 插件说明</h3>
                <div style="font-size:14px;color:#374151;line-height:1.8;">${esc(detail.description)}</div>
                ${detail.tags && detail.tags.length ? `
                  <div style="margin-top:14px;display:flex;gap:6px;flex-wrap:wrap;">
                    ${detail.tags.map(t => `<span class="pm-tag">${esc(t)}</span>`).join('')}
                  </div>
                ` : ''}
              </div>

              <!-- Permissions -->
              ${detail.permissions && detail.permissions.length ? `
                <div class="pm-section">
                  <h3>🔐 权限请求</h3>
                  <div style="display:flex;flex-wrap:wrap;gap:8px;">
                    ${detail.permissions.map(p => `<span class="pm-tag" style="background:#FEF3C7;color:#92400E;">${esc(p)}</span>`).join('')}
                  </div>
                </div>
              ` : ''}

              <!-- Dependencies -->
              ${detail.dependencies && Object.keys(detail.dependencies).length ? `
                <div class="pm-section">
                  <h3>🔗 依赖</h3>
                  <div style="font-size:14px;color:#374151;">
                    ${Object.entries(detail.dependencies).map(([k, v]) => `<div style="padding:4px 0;border-bottom:1px solid var(--pm-gray-light);"><code>${esc(k)}</code>: ${esc(v)}</div>`).join('')}
                  </div>
                </div>
              ` : ''}

              <!-- Config schema -->
              ${detail.config_schema ? `
                <div class="pm-section">
                  <h3>⚙️ 配置项</h3>
                  <div style="font-family:monospace;font-size:13px;background:#1E293B;color:#E2E8F0;padding:14px;border-radius:8px;overflow-x:auto;">
                    <pre style="margin:0;white-space:pre-wrap;">${esc(typeof detail.config_schema === 'string' ? detail.config_schema : JSON.stringify(detail.config_schema, null, 2))}</pre>
                  </div>
                </div>
              ` : ''}

              <!-- Version history -->
              ${detail.versions && detail.versions.length ? `
                <div class="pm-section">
                  <h3>📜 版本历史</h3>
                  ${detail.versions.map(v => `
                    <div class="pm-version">
                      <span><strong>v${esc(v.version)}</strong></span>
                      <span style="color:var(--pm-gray);font-size:13px;">${v.released_at ? new Date(v.released_at).toLocaleDateString('zh-CN') : '—'}</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}

              <!-- Reviews -->
              <div class="pm-section">
                <h3>⭐ 用户评价 (${(detail.reviews || []).length})</h3>
                <div id="pm-reviews">
                  ${(detail.reviews || []).length === 0
                    ? '<p style="color:var(--pm-gray);font-size:14px;margin:0;">暂无评价</p>'
                    : detail.reviews.map(r => `
                      <div class="pm-review">
                        <div class="pm-review-header">
                          <span class="pm-review-user">用户 ${esc(r.user_id || '匿名')}</span>
                          <span class="pm-review-date">${r.created_at ? new Date(r.created_at).toLocaleDateString('zh-CN') : ''}</span>
                        </div>
                        <div class="pm-review-stars">${'★'.repeat(r.rating || 0)}${'☆'.repeat(5 - (r.rating || 0))}</div>
                        ${r.comment ? `<div class="pm-review-text">${esc(r.comment)}</div>` : ''}
                      </div>
                    `).join('')
                  }
                </div>
                <!-- Write review -->
                ${isInstalled ? `
                  <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--pm-border);">
                    <h4 style="font-size:14px;margin:0 0 8px;">写评价</h4>
                    <div style="display:flex;gap:4px;margin-bottom:8px;" id="pm-review-stars">
                      ${[1,2,3,4,5].map(n => `<span style="font-size:22px;cursor:pointer;color:#D1D5DB;" data-star="${n}">★</span>`).join('')}
                    </div>
                    <textarea id="pm-review-text" placeholder="分享你的使用体验..." style="width:100%;padding:10px;border:1.5px solid var(--pm-border);border-radius:8px;font-size:13px;resize:vertical;min-height:60px;"></textarea>
                    <button class="pm-btn pm-btn-primary pm-btn-sm" style="margin-top:8px;" onclick="PM.submitReview('${esc(pluginName)}')">提交评价</button>
                  </div>
                ` : ''}
              </div>
            </div>

            <!-- Sidebar -->
            <aside>
              <div class="pm-sidebar-card">
                <div class="pm-price-box">
                  <div class="pm-price-label">许可证</div>
                  <div class="pm-price-val" style="font-size:18px;">${esc(detail.license || 'MIT')}</div>
                </div>
                <div class="pm-info-row"><span>📦 版本</span><span>v${esc(detail.version)}</span></div>
                <div class="pm-info-row"><span>⭐ 评分</span><span>${detail.rating != null ? detail.rating.toFixed(1) : '—'}</span></div>
                <div class="pm-info-row"><span>📥 下载量</span><span>${detail.downloads || 0}</span></div>
                <div class="pm-info-row"><span>👨‍💻 作者</span><span>${esc(detail.author || '未知')}</span></div>
                <div class="pm-info-row"><span>📁 分类</span><span>${esc(catLabels[cat] || cat || '其他')}</span></div>
                <div style="margin-top:16px;">
                  <button class="pm-btn pm-btn-outline" style="width:100%;margin-bottom:8px;" onclick="location.hash='catalog'">← 返回市场</button>
                  ${isInstalled
                    ? `<button class="pm-btn pm-btn-blue" style="width:100%;" onclick="navigate('managed')">管理已安装插件</button>`
                    : ''
                  }
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>`;

    // Review star selection
    if (isInstalled) {
      let selectedStars = 0;
      const starsHost = $('#pm-review-stars');
      if (starsHost) {
        starsHost.querySelectorAll('[data-star]').forEach(s => {
          s.addEventListener('click', () => {
            selectedStars = parseInt(s.dataset.star);
            starsHost.querySelectorAll('[data-star]').forEach(st => {
              st.style.color = parseInt(st.dataset.star) <= selectedStars ? '#F59E0B' : '#D1D5DB';
            });
          });
          s.addEventListener('mouseenter', () => {
            const val = parseInt(s.dataset.star);
            starsHost.querySelectorAll('[data-star]').forEach(st => {
              st.style.color = parseInt(st.dataset.star) <= val ? '#F59E0B' : '#D1D5DB';
            });
          });
        });
        starsHost.addEventListener('mouseleave', () => {
          starsHost.querySelectorAll('[data-star]').forEach(st => {
            st.style.color = parseInt(st.dataset.star) <= selectedStars ? '#F59E0B' : '#D1D5DB';
          });
        });
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /*  Render: Installed management                                      */
  /* ------------------------------------------------------------------ */

  async function renderManaged() {
    state.view = 'managed';
    const container = $('#pm-content');
    showLoading(container);

    const resp = await apiGet('/plugins/installed');
    const items = resp?.items || [];

    container.innerHTML = `
      <div class="pm-view-tabs">
        <button class="pm-view-tab" data-view="catalog">🏪 插件市场</button>
        <button class="pm-view-tab active" data-view="managed">📦 已安装 (${items.length})</button>
      </div>

      <div class="pm-section" style="margin-bottom:20px;">
        <h3>📦 已安装插件管理</h3>
        <p style="font-size:14px;color:var(--pm-gray);margin:0 0 16px;">
          管理已安装插件的启用/禁用状态、配置和卸载操作。
        </p>
      </div>

      ${items.length === 0
        ? `<div class="pm-empty" style="background:#fff;border-radius:12px;box-shadow:var(--pm-card-shadow);">
             <div class="pm-empty-icon">📭</div>
             <p>还没有安装任何插件</p>
             <button class="pm-btn pm-btn-primary" style="margin-top:16px;" onclick="navigate('catalog')">浏览插件市场</button>
           </div>`
        : `
          <table class="pm-mgmt-table">
            <thead>
              <tr>
                <th>插件名称</th>
                <th>版本</th>
                <th>状态</th>
                <th>启用/禁用</th>
                <th>安装时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${items.map(inst => {
                const detail = state.plugins.find(p => p.name === inst.name) || {};
                return `
                  <tr>
                    <td>
                      <div style="font-weight:600;color:#111827;">${esc(inst.name)}</div>
                      <div style="font-size:12px;color:var(--pm-gray);margin-top:2px;">
                        ${esc(detail.description || '').slice(0, 60)}${(detail.description || '').length > 60 ? '...' : ''}
                      </div>
                    </td>
                    <td><code style="font-size:13px;background:var(--pm-gray-light);padding:2px 8px;border-radius:4px;">v${esc(inst.version)}</code></td>
                    <td>
                      <span style="display:inline-flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:${inst.enabled ? 'var(--pm-green)' : 'var(--pm-gray)'};">
                        <span style="width:8px;height:8px;border-radius:50%;background:${inst.enabled ? 'var(--pm-green)' : '#D1D5DB'};display:inline-block;"></span>
                        ${inst.enabled ? '已启用' : '已禁用'}
                      </span>
                    </td>
                    <td>
                      <label class="pm-toggle">
                        <input type="checkbox" ${inst.enabled ? 'checked' : ''}
                               onchange="PM.toggleEnabled('${esc(inst.name)}', ${!inst.enabled})">
                        <span class="pm-slider"></span>
                      </label>
                    </td>
                    <td style="font-size:13px;color:var(--pm-gray);">
                      ${inst.installed_at ? new Date(inst.installed_at).toLocaleDateString('zh-CN') : '—'}
                    </td>
                    <td>
                      <div style="display:flex;gap:6px;">
                        <button class="pm-btn pm-btn-outline pm-btn-sm" onclick="navigate('detail','${esc(inst.name)}')">详情</button>
                        <button class="pm-btn pm-btn-danger pm-btn-sm" onclick="PM.confirmUninstall('${esc(inst.name)}')">卸载</button>
                        <button class="pm-btn pm-btn-outline pm-btn-sm" onclick="PM.openConfig('${esc(inst.name)}')">配置</button>
                      </div>
                    </td>
                  </tr>`;
              }).join('')}
            </tbody>
          </table>
        `}
    `;

    $$('.pm-view-tab').forEach(tab => {
      tab.addEventListener('click', () => navigate(tab.dataset.view));
    });
  }

  /* ------------------------------------------------------------------ */
  /*  Actions                                                           */
  /* ------------------------------------------------------------------ */

  const PM = {
    async install(name, btn) {
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="pm-spinner" style="width:14px;height:14px;border-width:2px;"></span>';
      }
      const r = await apiPost(`/plugins/${encodeURIComponent(name)}/install`);
      if (r?.ok || r?.data?.success) {
        DDW.toast(`✅ ${name} 安装成功`, 'success');
        // Refresh installed map
        const resp = await apiGet('/plugins/installed');
        (resp?.items || []).forEach(inst => { state.installedMap[inst.name] = inst; });
        // Re-render current view
        PM.refresh();
      } else {
        DDW.toast(`❌ 安装失败: ${r?.message || '未知错误'}`, 'error');
        if (btn) { btn.disabled = false; btn.textContent = '安装'; }
      }
    },

    async installDetail(name) {
      const btn = $('#pm-install-btn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="pm-spinner" style="width:14px;height:14px;border-width:2px;"></span> 安装中...';
      }
      const r = await apiPost(`/plugins/${encodeURIComponent(name)}/install`);
      if (r?.ok || r?.data?.success) {
        DDW.toast(`✅ ${name} 安装成功`, 'success');
        const resp = await apiGet('/plugins/installed');
        (resp?.items || []).forEach(inst => { state.installedMap[inst.name] = inst; });
        renderDetail(name);
      } else {
        DDW.toast(`❌ 安装失败: ${r?.message || '未知错误'}`, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '⚡ 安装插件'; }
      }
    },

    async toggleEnabled(name, shouldEnable) {
      const action = shouldEnable ? 'enable' : 'disable';
      const r = await apiPost(`/plugins/${encodeURIComponent(name)}/${action}`);
      if (r?.ok || r?.data?.success) {
        DDW.toast(`✅ ${name} 已${shouldEnable ? '启用' : '禁用'}`, 'success');
        state.installedMap[name] = { ...state.installedMap[name], enabled: shouldEnable };
        PM.refresh();
      } else {
        DDW.toast(`❌ 操作失败: ${r?.message || '未知错误'}`, 'error');
      }
    },

    confirmUninstall(name) {
      showModal(
        '确认卸载',
        `确定要卸载插件 <strong>${esc(name)}</strong> 吗？卸载后需要重新安装才能使用。`,
        [
          { label: '取消', cls: 'pm-btn pm-btn-outline' },
          {
            label: '确认卸载',
            cls: 'pm-btn pm-btn-danger',
            fn: () => PM.uninstall(name),
          },
        ]
      );
    },

    async uninstall(name) {
      const r = await apiPost(`/plugins/${encodeURIComponent(name)}/uninstall`);
      if (r?.ok || r?.data?.success) {
        DDW.toast(`✅ ${name} 已卸载`, 'success');
        delete state.installedMap[name];
        PM.refresh();
      } else {
        DDW.toast(`❌ 卸载失败: ${r?.message || '未知错误'}`, 'error');
      }
    },

    async submitReview(name) {
      const textEl = $('#pm-review-text');
      const text = textEl ? textEl.value.trim() : '';
      if (!text) {
        DDW.toast('请输入评价内容', 'info');
        return;
      }
      const starsHost = $('#pm-review-stars');
      let rating = 0;
      if (starsHost) {
        starsHost.querySelectorAll('[data-star]').forEach(s => {
          if (s.style.color === 'rgb(245, 158, 11)') rating = Math.max(rating, parseInt(s.dataset.star));
        });
      }
      if (!rating) rating = 5;

      const r = await apiPost(`/plugins/${encodeURIComponent(name)}/reviews`, {
        rating,
        comment: text,
        user_id: 'frontend-user',
      });
      if (r?.ok || r?.data?.success) {
        DDW.toast('✅ 评价提交成功', 'success');
        renderDetail(name);
      } else {
        DDW.toast(`❌ 提交失败: ${r?.message || '未知错误'}`, 'error');
      }
    },

    async openConfig(name) {
      const detail = state.plugins.find(p => p.name === name);
      const schema = detail?.config_schema;
      const configStr = schema
        ? (typeof schema === 'string' ? schema : JSON.stringify(schema, null, 2))
        : '{\n  \n}';

      showModal(
        `配置 - ${name}`,
        '',
        [
          { label: '取消', cls: 'pm-btn pm-btn-outline' },
          { label: '保存配置', cls: 'pm-btn pm-btn-primary', fn: () => {
            DDW.toast('✅ 配置已保存（演示模式）', 'success');
          }},
        ]
      );
      // Add config editor to modal
      const modal = document.querySelector('.pm-modal');
      if (modal) {
        const editor = document.createElement('textarea');
        editor.className = 'pm-config-editor';
        editor.value = configStr;
        editor.style.marginBottom = '16px';
        const pEl = modal.querySelector('p');
        if (pEl) pEl.replaceWith(editor);
      }
    },

    refresh() {
      const p = parseHash();
      if (p.view === 'detail' && p.param) renderDetail(p.param);
      else if (p.view === 'managed') renderManaged();
      else renderCatalog();
    },
  };

  /* ------------------------------------------------------------------ */
  /*  Init                                                              */
  /* ------------------------------------------------------------------ */

  async function init() {
    await loadAllData();

    // Hash routing
    window.addEventListener('hashchange', () => {
      const p = parseHash();
      if (p.view === 'detail' && p.param) renderDetail(p.param);
      else if (p.view === 'managed') renderManaged();
      else renderCatalog();
    });

    // Initial render
    const p = parseHash();
    if (p.view === 'detail' && p.param) renderDetail(p.param);
    else if (p.view === 'managed') renderManaged();
    else renderCatalog();
  }

  // Expose globals
  DDW.PM = PM;
  DDW.navigate = navigate;
  global.PM = PM;
  global.navigate = navigate;

  // Boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})(window);
