/**
 * @deepddw/dsh-workbench — browser client half (full workbench).
 *
 * deepDDW capabilities injected into the STOCK DSH UI via official slots:
 *   1. `settings.section` ×2 — 知识库 / 记忆（模型配置走 dsh 原版） (settings-page left nav);
 *   2. `conversation.session.header.utilities` — docs-rail toggle button
 *      (top-right utility seat) opening a collapsible 320px right rail.
 *
 * Auth (deepDDW 鉴权开发说明):
 *   - `headers()` helper: attach X-DDW-Token only when a token exists
 *     (LAN no-token requests are fine; external requests need it);
 *   - 401 → visible hint "未授权：外网访问需通过启动页填写 Token" + link back
 *     to the launcher — never silent;
 *   - token comes from sessionStorage["deepddw_token"] or the
 *     `deepddw-token` postMessage (launcher iframe); never written to
 *     URL / iframe src / logs.
 *
 * Bundle format: DSH client module system (`window.__ModuleLoader__.load`).
 */

window.__ModuleLoader__.load({
  id: '@deepddw/dsh-workbench',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    var react = require('react')
    var jsxRuntime = require('react/jsx-runtime')

    // ------------------------------------------------------------------ //
    // deepDDW gateway helpers
    // ------------------------------------------------------------------ //

    var _baseUrl = null
    var _token = null

    /** Read a token posted by the launcher iframe (cross-origin). */
    function bindTokenChannel() {
      window.addEventListener('message', function (ev) {
        if (ev.data && ev.data.type === 'deepddw-token' && ev.data.token) {
          _token = ev.data.token
          try { sessionStorage.setItem('deepddw_token', _token) } catch (e) {}
        }
      })
      try {
        _token = sessionStorage.getItem('deepddw_token') || null
      } catch (e) { _token = null }
    }

    /** Resolve the deepDDW gateway base URL via the same-origin meta route. */
    function getBaseUrl() {
      if (_baseUrl) return Promise.resolve(_baseUrl)
      return fetch('/deepddw-meta')
        .then(function (r) { return r.json() })
        .then(function (d) {
          _baseUrl = d.baseUrl || 'http://127.0.0.1:8600'
          return _baseUrl
        })
        .catch(function () {
          _baseUrl = 'http://127.0.0.1:8600'
          return _baseUrl
        })
    }

    /** Unified auth headers: attach token when present, else send bare. */
    function headers() {
      var h = { 'Content-Type': 'application/json' }
      if (_token) h['X-DDW-Token'] = _token
      return h
    }

    /**
     * 401 handling: visible hint + link back to the launcher. Never silent.
     * @param resp - fetch Response (or null when the request itself failed).
     */
    function handle401() {
      getBaseUrl().then(function (base) {
        var msg = '未授权：外网访问需通过启动页填写 Token'
        window.alert(msg)
        var launcher = base + '/ui/deepddw-launcher.html'
        window.open(launcher, '_blank')
      })
    }

    /** Call a deepDDW API endpoint with the auth helper. */
    function api(path, opts) {
      var options = opts || {}
      return getBaseUrl().then(function (base) {
        return fetch(base + path, {
          method: options.method || 'GET',
          headers: headers(),
          body: options.body ? JSON.stringify(options.body) : undefined,
        }).then(function (resp) {
          if (resp.status === 401) {
            handle401()
            var err = new Error('unauthorized')
            err.status = 401
            throw err
          }
          return resp
        })
      })
    }

    /** Minimal JSON reader with deepDDW envelope tolerance. */
    function readData(json) {
      return json && typeof json.data !== 'undefined' ? json.data : json
    }

    // ------------------------------------------------------------------ //
    // Shared styles (reuse DSH CSS variables — stock look & feel)
    // ------------------------------------------------------------------ //

    var S = {
      card: { background: 'var(--dsw-alias-bg-layer-2)', border: '1px solid var(--dsw-alias-border-subtle, #333)', borderRadius: '12px', padding: '14px', marginBottom: '12px' },
      h3: { margin: '0 0 10px', fontSize: '15px', fontWeight: 600, color: 'var(--dsw-alias-label-primary)' },
      label: { display: 'block', fontSize: '12px', margin: '10px 0 4px', color: 'var(--dsw-alias-label-secondary, #aaa)' },
      input: { width: '100%', boxSizing: 'border-box', padding: '8px 10px', fontSize: '13px', color: 'var(--dsw-alias-label-primary)', background: 'var(--dsw-alias-bg-input, #1e1e1e)', border: '1px solid var(--dsw-alias-border-subtle, #333)', borderRadius: '8px', outline: 'none' },
      btn: { padding: '8px 14px', marginTop: '10px', fontSize: '13px', fontWeight: 600, color: '#04121f', background: 'linear-gradient(135deg,#00e5ff,#0099ff)', border: 'none', borderRadius: '8px', cursor: 'pointer' },
      item: { padding: '10px 12px', marginTop: '8px', fontSize: '12.5px', lineHeight: 1.6, color: 'var(--dsw-alias-label-primary)', background: 'var(--dsw-alias-bg-layer-3, #16204a)', border: '1px solid var(--dsw-alias-border-subtle, #333)', borderRadius: '8px' },
      msg: { minHeight: '16px', marginTop: '8px', fontSize: '12px', color: 'var(--dsw-alias-label-secondary, #aaa)' },
      hint: { fontSize: '12px', color: 'var(--dsw-alias-label-secondary, #888)', lineHeight: 1.6 },
    }

    // ------------------------------------------------------------------ //
    // 知识库 section
    // ------------------------------------------------------------------ //

    function KbSection() {
      var q, setQ = react.useState('')[1]
      var items, setItems = react.useState([])[1]
      var busy, setBusy = react.useState(false)[1]
      var title, setTitle = react.useState('')[1]
      var content, setContent = react.useState('')[1]
      var msg, setMsg = react.useState('')[1]

      function doSearch() {
        if (!q) return
        setBusy(true)
        api('/api/v1/knowledge/search?q=' + encodeURIComponent(q) + '&top_k=5')
          .then(function (r) { return r.json() })
          .then(function (d) { setItems((readData(d) && readData(d).results) || []) })
          .catch(function () { setItems([]) })
          .finally(function () { setBusy(false) })
      }
      function doAdd() {
        if (!title || !content) { setMsg('标题与正文必填'); return }
        api('/api/v1/knowledge/documents', { method: 'POST', body: { title: title, content: content } })
          .then(function (r) { return r.json() })
          .then(function (d) { setMsg('入库成功 id=' + (readData(d) && readData(d).id)); setContent('') })
          .catch(function (e) { setMsg('失败：' + e.message) })
      }

      return jsxRuntime.jsx('div', { children: [
        jsxRuntime.jsx('div', { style: S.card, children: [
          jsxRuntime.jsx('h3', { style: S.h3, children: '📚 知识库检索' }),
          jsxRuntime.jsx('input', { style: S.input, placeholder: '检索词，如：部署', value: q, onInput: function (e) { q = e.target.value; setQ(q) }, onKeyDown: function (e) { if (e.key === 'Enter') doSearch() } }),
          jsxRuntime.jsx('button', { style: S.btn, disabled: busy, onClick: doSearch, children: busy ? '检索中…' : '检索' }),
          (items || []).map(function (it, i) {
            return jsxRuntime.jsx('div', { style: S.item, children: [
              jsxRuntime.jsx('b', { children: it.title }),
              jsxRuntime.jsx('div', { children: it.excerpt }),
            ] }, 'kb-' + i)
          }),
        ] }),
        jsxRuntime.jsx('div', { style: S.card, children: [
          jsxRuntime.jsx('h3', { style: S.h3, children: '➕ 新增文档' }),
          jsxRuntime.jsx('input', { style: S.input, placeholder: '标题', value: title, onInput: function (e) { title = e.target.value; setTitle(title) } }),
          jsxRuntime.jsx('textarea', { style: Object.assign({}, S.input, { minHeight: '64px', marginTop: '8px' }), placeholder: '正文内容', value: content, onInput: function (e) { content = e.target.value; setContent(content) } }),
          jsxRuntime.jsx('button', { style: S.btn, onClick: doAdd, children: '入库' }),
          jsxRuntime.jsx('div', { style: S.msg, children: msg }),
        ] }),
      ] })
    }

    // ------------------------------------------------------------------ //
    // 记忆 section
    // ------------------------------------------------------------------ //

    function MemorySection() {
      var key, setKey = react.useState('')[1]
      var value, setValue = react.useState('')[1]
      var q, setQ = react.useState('')[1]
      var items, setItems = react.useState([])[1]
      var msg, setMsg = react.useState('')[1]

      function doPut() {
        if (!key || !value) { setMsg('key 与内容必填'); return }
        api('/api/v1/memory/put', { method: 'POST', body: { key: key, value: value, tags: [] } })
          .then(function (r) { return r.json() })
          .then(function (d) { setMsg('已保存（id=' + (readData(d) && readData(d).id) + '）'); setValue('') })
          .catch(function (e) { setMsg('失败：' + e.message) })
      }
      function doSearch() {
        if (!q) return
        api('/api/v1/memory/search?q=' + encodeURIComponent(q) + '&top_k=5')
          .then(function (r) { return r.json() })
          .then(function (d) { setItems((readData(d) && readData(d).results) || []) })
          .catch(function () { setItems([]) })
      }

      return jsxRuntime.jsx('div', { children: [
        jsxRuntime.jsx('div', { style: S.card, children: [
          jsxRuntime.jsx('h3', { style: S.h3, children: '🧠 记忆写入' }),
          jsxRuntime.jsx('input', { style: S.input, placeholder: 'key，如：preference', value: key, onInput: function (e) { key = e.target.value; setKey(key) } }),
          jsxRuntime.jsx('textarea', { style: Object.assign({}, S.input, { minHeight: '64px', marginTop: '8px' }), placeholder: '记忆内容', value: value, onInput: function (e) { value = e.target.value; setValue(value) } }),
          jsxRuntime.jsx('button', { style: S.btn, onClick: doPut, children: '保存' }),
          jsxRuntime.jsx('div', { style: S.msg, children: msg }),
        ] }),
        jsxRuntime.jsx('div', { style: S.card, children: [
          jsxRuntime.jsx('h3', { style: S.h3, children: '🔍 记忆检索' }),
          jsxRuntime.jsx('input', { style: S.input, placeholder: '检索词', value: q, onInput: function (e) { q = e.target.value; setQ(q) }, onKeyDown: function (e) { if (e.key === 'Enter') doSearch() } }),
          jsxRuntime.jsx('button', { style: S.btn, onClick: doSearch, children: '检索' }),
          (items || []).map(function (it, i) {
            return jsxRuntime.jsx('div', { style: S.item, children: [
              jsxRuntime.jsx('b', { children: '[' + it.key + ']' }),
              jsxRuntime.jsx('span', { children: ' ' + it.value }),
            ] }, 'mem-' + i)
          }),
        ] }),
      ] })
    }

    // ------------------------------------------------------------------ //
    // 右上角文档栏（可隐藏；当前对话/知识库文档列表 + 预览）
    // ------------------------------------------------------------------ //

    function DocsRailSection() {
      var open, setOpen = react.useState(false)[1]
      var docs, setDocs = react.useState([])[1]
      var preview, setPreview = react.useState(null)[1]
      var busy, setBusy = react.useState(false)[1]

      function loadDocs() {
        setBusy(true)
        Promise.all([
          api('/api/v1/knowledge/bases').then(function (r) { return r.json() }).catch(function () { return {} }),
        ]).then(function (results) {
          var list = (readData(results[0]) || []).map(function (d) {
            return { id: d.id, title: d.title, kind: 'kb', url: null }
          })
          // 并入文档栏目（docs_portal）已发布文档
          return api('/api/v1/plugins/ddw-docs-portal/docs?page=1&page_size=50')
            .then(function (r) { return r.json() })
            .then(function (d2) {
              var portal = (d2.items || []).map(function (x) {
                return { id: x.id, title: x.title, kind: 'portal', url: '/api/v1/plugins/ddw-docs-portal/docs/' + x.id }
              })
              return list.concat(portal)
            })
            .catch(function () { return list })
        }).then(function (merged) {
          setDocs(merged)
          setBusy(false)
        })
      }

      function openPreview(item) {
        if (item.kind === 'kb') {
          // 知识库文档：excerpt 即内容摘要（预览元数据）
          setPreview({ title: item.title, content: item.excerpt || '(知识库条目，正文在检索结果中查看)' })
          return
        }
        api(item.url)
          .then(function (r) { return r.json() })
          .then(function (d) { setPreview({ title: item.title, content: (d.content || d.detail || JSON.stringify(d)).slice(0, 6000) }) })
          .catch(function () { setPreview({ title: item.title, content: '(预览失败)' }) })
      }

      // 切换时加载一次
      react.useEffect(function () {
        if (open && docs.length === 0) loadDocs()
      }, [open])

      var railStyle = {
        position: 'fixed', top: 0, right: open ? 0 : '-340px',
        width: '320px', height: '100vh', zIndex: 999,
        background: 'var(--dsw-alias-bg-layer-2)', borderLeft: '1px solid var(--dsw-alias-border-subtle, #333)',
        boxShadow: 'var(--dsw-shadow-lv3, 0 14px 40px rgba(0,0,0,.35))',
        display: 'flex', flexDirection: 'column', transition: 'right .25s ease',
        fontFamily: 'inherit',
      }

      return jsxRuntime.jsx(react.Fragment, { children: [
        // 右上角按钮（header.utilities 座位，dsh 风格）
        jsxRuntime.jsx('button', {
          title: open ? '隐藏文档栏' : '文档栏',
          'aria-label': open ? '隐藏文档栏' : '文档栏',
          onClick: function () {
            var next = !open
            setOpen(next)
            if (next) loadDocs()
          },
          style: {
            width: '28px', height: '28px', margin: '0 2px', padding: 0,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: open ? 'var(--dsw-specific-sidebar-nav-item-active, #1c3a5f)' : 'transparent',
            border: 'none', borderRadius: '8px', cursor: 'pointer',
            color: 'var(--dsw-alias-label-primary)', fontSize: '15px',
          },
          children: '📄',
        }),
        // 右侧滑出文档栏
        jsxRuntime.jsx('div', { style: railStyle, children: [
          jsxRuntime.jsx('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', borderBottom: '1px solid var(--dsw-alias-border-subtle, #333)' }, children: [
            jsxRuntime.jsx('b', { children: '文档栏' }),
            jsxRuntime.jsx('button', {
              onClick: function () { setOpen(false) },
              style: { background: 'none', border: 'none', color: 'var(--dsw-alias-label-secondary, #aaa)', fontSize: '16px', cursor: 'pointer' },
              children: '✕',
            }),
          ] }),
          jsxRuntime.jsx('div', { style: { flex: 1, overflowY: 'auto', padding: '12px' }, children: [
            busy && jsxRuntime.jsx('div', { style: S.hint, children: '加载中…' }),
            !busy && docs.length === 0 && jsxRuntime.jsx('div', { style: S.hint, children: '暂无文档（知识库为空）' }),
            docs.map(function (it, i) {
              return jsxRuntime.jsx('div', {
                style: Object.assign({}, S.item, { cursor: 'pointer' }),
                onClick: function () { openPreview(it) },
                children: [
                  jsxRuntime.jsx('b', { children: it.title }),
                  jsxRuntime.jsx('div', { style: { color: 'var(--dsw-alias-label-secondary, #888)', fontSize: '11px', marginTop: '2px' }, children: it.kind === 'kb' ? '知识库' : '文档栏目' }),
                ],
              }, 'doc-' + i)
            }),
            preview && jsxRuntime.jsx('div', { style: Object.assign({}, S.card, { marginTop: '14px' }), children: [
              jsxRuntime.jsx('b', { children: preview.title }),
              jsxRuntime.jsx('pre', { style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '12px', lineHeight: 1.6, color: 'var(--dsw-alias-label-primary)', marginTop: '8px' }, children: preview.content }),
            ] }),
          ] }),
        ] }),
      ] })
    }

    // ------------------------------------------------------------------ //
    // inject: 声明 apply 需要从宿主拿的能力（缺此声明 ctx.slots 为 undefined，
    // 报 "cannot get property 'slots' without inject"——官方插件同样模式）
    // ------------------------------------------------------------------ //

    const inject = ["slots"]

    // ------------------------------------------------------------------ //
    // apply: register slots (settings sections + header utilities)
    // ------------------------------------------------------------------ //

    function apply(ctx) {
      bindTokenChannel()

      ctx.slots.inject('settings.section', () => ctx.slots.register({
        name: 'settings.section',
        id: 'deepddw-kb',
        order: 100,
        label: () => '知识库',
      }, KbSection))

      ctx.slots.inject('settings.section', () => ctx.slots.register({
        name: 'settings.section',
        id: 'deepddw-memory',
        order: 110,
        label: () => '记忆',
      }, MemorySection))

      ctx.slots.inject('conversation.session.header.utilities', () => ctx.slots.register({
        name: 'conversation.session.header.utilities',
        id: 'deepddw-docs-rail',
        order: 10,
      }, DocsRailSection))
    }

    exports.apply = apply
    exports.inject = inject
    return exports
  },
})
