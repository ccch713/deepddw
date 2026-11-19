/**
 * deepDDW 团队管理面板 — DSH 客户端插件源码（v0.6.0）
 *
 * 构建：tsdown → lib/client.js（__ModuleLoader__ 格式）
 * 本文件是唯一权威源；不要直接手改 lib/client.js（构建会覆盖）。
 *
 * 关键机制（DSH 官方文档《添加设置卡片》）：
 * - `export const inject = ['slots']`：ctx 属性访问白名单（服务名）；
 *   未声明则访问 ctx.slots 抛 "cannot get property slots without inject"。
 * - 不能读 ctx.config（除非 inject 声明 'config'）；网关地址固定 8500。
 * - BASE 不能用 window.location.origin（那是 DSH web 3080，网关是独立 8500）。
 *
 * v0.6.0 左栏入口（契约依据 DSH 0.2.2-rc.5 类型定义）：
 * - `sidebar.panellist`（list/root，声明于 dsh-client-ui-sidebar）：左栏常驻图标位，
 *   root 作用域 = 不随会话生灭；owner props = { size, active }。
 * - `main`（keyed/root，声明于 dsh-client-ui-layout）："Central panel selected by
 *   sidebar entry id"，保留 key 是 conversation，其余 key 不绑会话。
 * - 两者必须成对（id 与 key 同值）：只有图标没有 main 占用者 = 死按钮。
 * - 注册必须包 ctx.slots.inject(slot, cb)：槽未声明时直接注册会抛
 *   slot "…" is not declared，且一次抛错会让整个插件 fiber failed
 *   （DSH 界面显示 Failed to load plugins）。参照 MisakaNet registerWhenDeclared。
 */
import * as React from 'react'

const h = React.createElement
// 网关地址固定 8500（deepDDW 独立服务，LAN_BYPASS 免密）
const BASE = 'http://127.0.0.1:8500'

// 轻量双语：DSH 跟随系统 locale；插件无 locale 注册面，按浏览器语言选择
const LANG = (typeof navigator !== 'undefined' && (navigator.language || 'zh').toLowerCase().startsWith('zh')) ? 'zh' : 'en'
const t = (zh: string, en: string): string => (LANG === 'zh' ? zh : en)

// 左栏入口 id：panellist 的 id 与 main 的 key 必须同值
const PANEL_ID = 'ddw-teams'

// v0.6.0：所有 API 调用带设备头——team 模式 admin 门按「设备→绑定成员角色」判定
// （服务端 core/api/teams.py require_admin 读 X-DDW-Device；未绑定设备无管理权限）
function api(path: string, opts: any = {}): Promise<any> {
  const dev = localStorage.getItem('deepddw_device_id') || ''
  opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers, { 'X-DDW-Device': dev })
  return fetch(BASE + path, opts)
}
const FORBIDDEN_MSG = '需要管理员角色（team 模式下须绑定管理员成员的设备）'

export const inject = ['slots']

const MODES = [
  { value: 'solo',   label: '一人多设备', spec: '推荐 8GB 内存（服务器 + OS）' },
  { value: 'family', label: '家庭多人',   spec: '推荐 16GB 内存（5 人以下）' },
  { value: 'team',   label: '小团队协作',  spec: '推荐 32GB+ 内存（20 人以内）' },
]

// ══════ 成员识别（手动输入；v0.6.0 team 模式需绑定码防冒名）══════
function MemberIdentify(props: any) {
  const [st, setSt] = React.useState({ name: '', code: '', error: '', submitting: false })
  function submit() {
    const n = (st.name || '').trim()
    if (!n) { setSt({ name: n, code: st.code, error: '请输入成员名称', submitting: false }); return }
    setSt({ name: n, code: st.code, error: '', submitting: true })
    fetch(BASE + '/api/v1/member/list').then((r: any) => r.json()).then((d: any) => {
      const mlist = ((d && d.data && d.data.results) || []).filter((m: any) => !m.revoked && !m.deleted)
      const match = mlist.find((m: any) => m.display_name === n)
      if (!match) { setSt({ name: n, code: st.code, error: '未找到成员："' + n + '"（请检查拼写）', submitting: false }); return }
      return api('/api/v1/device/identify', {
        method: 'POST',
        body: JSON.stringify({ device_id: props.deviceId, member_id: match.member_id, invite_code: (st.code || '').trim() }),
      }).then(async (r: any) => {
        if (r.ok) {
          localStorage.setItem('deepddw_member_id', match.member_id)
          localStorage.setItem('deepddw_workspace', 'member:' + match.member_id)
          location.reload()
        } else {
          // 403/绑定码错误：取 detail（HTTPException）或 data.note（业务返回）
          let note = '绑定失败，请重试'
          try {
            const j: any = await r.json()
            note = (j && (j.detail || j.message || (j.data && j.data.note))) || note
          } catch (e) { /* body 非JSON，保留默认提示 */ }
          setSt({ name: n, code: st.code, error: note, submitting: false })
        }
      })
    }).catch((e: any) => { setSt({ name: n, code: st.code, error: '网络错误：' + e.message, submitting: false }) })
  }
  return h('div', { style: { position: 'fixed', inset: 0, zIndex: 99999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,.6)' } },
    h('div', { style: { background: 'var(--dsw-alias-bg-base)', border: '1px solid var(--dsw-alias-border-l2)', borderRadius: '12px', padding: '32px', maxWidth: '400px', width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,.5)' } },
      h('h2', { style: { margin: '0 0 8px', fontSize: '17px', fontWeight: 700, color: 'var(--dsw-alias-label-primary)' } }, '请输入你的身份'),
      h('p', { style: { margin: '0 0 16px', fontSize: '12px', color: 'var(--dsw-alias-text-disabled)' } }, '输入你的成员名称，本设备将绑定到该成员。不同成员的记忆体和知识库是隔离的。'),
      h('input', { value: st.name, onChange: (e: any) => { setSt({ name: e.target.value, code: st.code, error: '', submitting: false }) }, onKeyDown: (e: any) => { if (e.key === 'Enter') submit() }, placeholder: '例如：张三', autoFocus: true, style: { width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-layer-2)', color: 'var(--dsw-alias-label-primary)', fontSize: '15px', outline: 'none' } }),
      h('input', { value: st.code, onChange: (e: any) => { setSt({ name: st.name, code: e.target.value, error: '', submitting: false }) }, onKeyDown: (e: any) => { if (e.key === 'Enter') submit() }, placeholder: '绑定码（team 模式必填，向管理员索取；家庭模式可留空）', style: { width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-layer-2)', color: 'var(--dsw-alias-label-primary)', fontSize: '13px', outline: 'none', marginTop: '10px' } }),
      st.error ? h('p', { style: { color: '#e74c3c', fontSize: '12px', marginTop: '8px' } }, st.error) : null,
      h('button', { onClick: submit, disabled: st.submitting, style: { width: '100%', padding: '12px', border: 'none', borderRadius: '8px', background: 'var(--dsw-alias-brand-primary)', color: 'var(--dsw-alias-bg-base)', fontWeight: 600, fontSize: '14px', cursor: 'pointer', marginTop: '16px', opacity: st.submitting ? 0.5 : 1 } }, st.submitting ? '绑定中...' : '确认身份'),
    ),
  )
}

// ══════ 设置面板（三页签 + 三列成员 + 在线状态 + sticky底部）══════
function SettingsPanel() {
  const [data, setData] = React.useState({ mode: 'solo', members: [], stats: {}, devices: [], onlineIds: new Set(), loading: true, error: '' })
  const [tab, setTab] = React.useState('active')
  const [newName, setName] = React.useState('')
  const [sel, setSel] = React.useState(new Set())

  let refreshAttempt = 0
  function refresh() {
    // 保留旧数据仅置 loading，避免切回面板时成员列表闪烁空白
    setData((prev: any) => Object.assign({}, prev, { loading: true, error: '' }))
    // 每个请求独立容错：单个端点失败不拖垮整个面板
    //（间歇性 "Load failed" 常见于 keep-alive 连接复用失败，服务端已拉长 timeout-keep-alive）
    const ok = { mode: false, members: false }
    Promise.all([
      fetch(BASE + '/api/v1/deployment/mode').then((r: any) => r.json()).then((d: any) => { ok.mode = true; return d }).catch(() => ({})),
      fetch(BASE + '/api/v1/member/list').then((r: any) => r.json()).then((d: any) => { ok.members = true; return d }).catch(() => ({})),
      fetch(BASE + '/api/v1/admin/stats').then((r: any) => r.json()).catch(() => ({})),
      fetch(BASE + '/api/v1/status').then((r: any) => r.json()).catch(() => ({})),
    ]).then((rs: any[]) => {
      // 关键请求失败（mode/member）→ 自动重试最多 3 次，间隔递增
      if ((!ok.mode || !ok.members) && refreshAttempt < 3) {
        refreshAttempt++
        setTimeout(refresh, 1000 * refreshAttempt)
        return
      }
      refreshAttempt = 0
      // 构建在线设备集合（last_seen 在 60s 内）
      const devices = (rs[3] && rs[3].data && rs[3].data.devices) || []
      const onlineSet = new Set()
      devices.forEach((d: any) => { if (d.online) onlineSet.add(d.device_id) })
      // 将 device_ids 转为 member_id 映射
      const memberOnline: any = {}
      ;(rs[1] && rs[1].data && rs[1].data.results || []).forEach((m: any) => {
        try { const ids = JSON.parse(m.device_ids || '[]'); ids.forEach((id: string) => { if (onlineSet.has(id)) memberOnline[m.member_id] = true }) } catch (e) { /* ignore */ }
      })
      setData({
        mode: (rs[0] && rs[0].data && rs[0].data.mode) || 'solo',
        members: (rs[1] && rs[1].data && rs[1].data.results) || [],
        stats: (rs[2] && rs[2].data) || {},
        devices: devices,
        onlineIds: memberOnline,
        loading: false, error: '',
      })
    }).catch((e: any) => { setData({ mode: 'solo', members: [], stats: {}, devices: [], onlineIds: {}, loading: false, error: e.message }) })
  }
  React.useEffect(refresh, [])

  function setMode(m: string) {
    if (!confirm('切换为 "' + (MODES.find((x) => x.value === m)!.label) + '" 模式后需重启服务，确认？')) return
    api('/api/v1/deployment/mode', { method: 'POST', body: JSON.stringify({ mode: m }) }).then((r: any) => {
      if (r.status === 403) { alert(FORBIDDEN_MSG); return }
      if (r.ok) refresh()
    })
  }
  function addMember() {
    if (!newName.trim()) return
    api('/api/v1/member/add', { method: 'POST', body: JSON.stringify({ display_name: newName.trim() }) }).then((r: any) => {
      if (r.status === 403) { alert(FORBIDDEN_MSG); return }
      setName(''); refresh()
    })
  }
  function removeMember(mid: string) {
    if (!confirm('定要移除此成员？该成员的记忆体和知识库将保留但无法再访问。')) return
    api('/api/v1/member/revoke', { method: 'POST', body: JSON.stringify({ member_id: mid }) }).then((r: any) => {
      if (r.status === 403) { alert(FORBIDDEN_MSG); return }
      refresh()
    })
  }
  function extractMembers() {
    if (sel.size === 0) return alert('请先选择成员')
    if (!confirm('将选中成员的记忆体和知识库提取到团队共享空间，并删除成员？')) return
    api('/api/v1/member/extract', { method: 'POST', body: JSON.stringify({ member_ids: Array.from(sel) }) })
      .then(async (r: any) => {
        if (r.status === 403) { alert(FORBIDDEN_MSG); return null }
        return r.json()
      })
      .then((d: any) => {
        if (!d) return
        alert('已提取 ' + ((d.data && d.data.extracted) || 0) + ' 条记忆到团队共享空间，已删除 ' + ((d.data && d.data.deleted) || 0) + ' 个成员。'); setSel(new Set()); refresh()
      })
      .catch((e: any) => { alert('提取失败：' + e.message) })
  }
  function toggleSel(id: string) { const n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); setSel(n) }

  const active = (data.members || []).filter((m: any) => !m.revoked && !m.deleted)
  const revoked = (data.members || []).filter((m: any) => m.revoked === 1 || m.revoked === 2)
  const deleted = (data.members || []).filter((m: any) => m.deleted === 1)
  const curMode = MODES.find((m) => m.value === data.mode)

  if (data.error) return h('div', { style: { padding: '16px', color: '#e74c3c' } }, 'API 请求失败：' + data.error)

  function renderMemberCard(m: any, showOnline: boolean) {
    const isOnline = showOnline && (data.onlineIds as any)[m.member_id]
    return h('div', { key: m.member_id, style: { flex: '1 1 calc(33.33% - 8px)', minWidth: '100px', maxWidth: '160px', padding: '8px 10px', borderRadius: '8px', background: 'var(--dsw-alias-bg-base)', border: '1px solid var(--dsw-alias-border-l2)', fontSize: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
      h('div', { style: { flex: 1 } },
        h('div', { style: { fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '4px' } },
          isOnline ? h('span', { style: { color: '#2ecc71', fontSize: '8px' } }, '●') : h('span', { style: { color: '#888', fontSize: '8px' } }, '●'),
          h('span', null, m.display_name || '(未命名)'),
        ),
      ),
      h('button', { onClick: () => { removeMember(m.member_id) }, style: { border: 'none', background: 'none', color: 'var(--dsw-alias-text-disabled)', fontSize: '14px', cursor: 'pointer', padding: '2px 4px' } }, '×'),
    )
  }

  const currentMemberName = (() => {
    const mid = localStorage.getItem('deepddw_member_id') || ''
    if (!mid) return '匿名'
    const found = active.find((m: any) => m.member_id === mid)
    return found ? String(found.display_name || '匿名') : '匿名'
  })()

  return h('div', { style: { padding: '16px', display: 'flex', flexDirection: 'column', minHeight: '100%' } },
    h('div', { style: { flex: 1 } },
      h('div', { style: { marginBottom: '16px' } },
        h('div', { style: { fontSize: '13px', color: 'var(--dsw-alias-text-disabled)', marginBottom: '4px' } }, '当前成员： ' + String(currentMemberName)),
        h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
          h('h2', { style: { fontSize: '18px', fontWeight: 700, margin: 0, color: 'var(--dsw-alias-label-primary)' } }, '多用户设置'),
          h('span', { style: { fontSize: '12px', padding: '4px 10px', borderRadius: '10px', background: 'var(--dsw-alias-bg-layer-2)', color: 'var(--dsw-alias-text-disabled)' } }, curMode ? curMode.label : data.mode),
        ),
      ),
      // 模式下拉
      h('div', { style: { background: 'var(--dsw-alias-bg-layer-2)', borderRadius: '10px', padding: '14px', marginBottom: '12px' } },
        h('div', { style: { fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: 'var(--dsw-alias-label-primary)' } }, '部署模式'),
        h('select', { value: data.mode, onChange: (e: any) => { setMode(e.target.value) }, style: { width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-base)', color: 'var(--dsw-alias-label-primary)', fontSize: '14px', cursor: 'pointer' } },
          MODES.map((m) => h('option', { key: m.value, value: m.value }, m.label + ' — ' + m.spec)),
        ),
        h('p', { style: { fontSize: '11px', color: 'var(--dsw-alias-text-disabled)', marginTop: '6px' } }, '切换后需重启服务生效。'),
      ),
      // 页签栏
      h('div', { style: { display: 'flex', borderBottom: '1px solid var(--dsw-alias-border-l2)', marginBottom: '12px', gap: '4px' } },
        ['active', 'revoked', 'deleted'].map((t) => {
          const count = t === 'active' ? active.length : t === 'revoked' ? revoked.length : deleted.length
          const label = t === 'active' ? '活跃成员' : t === 'revoked' ? '已吊销' : '已删除'
          return h('button', { key: t, onClick: () => { setTab(t); setSel(new Set()) },
            style: { padding: '8px 12px', border: 'none', borderBottom: '2px solid ' + (tab === t ? 'var(--dsw-alias-brand-primary)' : 'transparent'), background: 'none', color: tab === t ? 'var(--dsw-alias-brand-primary)' : 'var(--dsw-alias-text-disabled)', fontSize: '13px', fontWeight: tab === t ? 600 : 400, cursor: 'pointer' } },
            label + ' (' + count + ')',
          )
        }),
      ),
      // 页签内容
      tab === 'active' && h('div', null,
        h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' } },
          active.length === 0 ? h('div', { style: { fontSize: '12px', color: 'var(--dsw-alias-text-disabled)', padding: '8px 0' } }, '暂无活跃成员')
            : active.map((m: any) => renderMemberCard(m, true)),
        ),
        h('div', { style: { display: 'flex', gap: '6px' } },
          h('input', { value: newName, onChange: (e: any) => { setName(e.target.value) }, onKeyDown: (e: any) => { if (e.key === 'Enter') addMember() }, placeholder: '输入成员名称后回车', style: { flex: 1, padding: '8px 10px', borderRadius: '6px', border: '1px solid var(--dsw-alias-border-l2)', background: 'var(--dsw-alias-bg-base)', color: 'var(--dsw-alias-label-primary)', fontSize: '13px' } }),
          h('button', { onClick: addMember, style: { padding: '8px 14px', border: 'none', borderRadius: '6px', background: 'var(--dsw-alias-brand-primary)', color: 'var(--dsw-alias-bg-base)', fontWeight: 600, fontSize: '13px', cursor: 'pointer' } }, '添加'),
        ),
      ),
      tab === 'revoked' && h('div', null,
        revoked.length === 0 ? h('div', { style: { fontSize: '12px', color: 'var(--dsw-alias-text-disabled)', padding: '8px 0' } }, '无已吊销成员')
          : h('div', null,
            h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' } },
              revoked.map((m: any) => {
                return h('label', { key: m.member_id, style: { flex: '1 1 calc(33.33% - 8px)', minWidth: '100px', maxWidth: '160px', padding: '8px 10px', borderRadius: '8px', background: sel.has(m.member_id) ? 'var(--dsw-alias-brand-primary-bg)' : 'var(--dsw-alias-bg-base)', border: '1px solid ' + (sel.has(m.member_id) ? 'var(--dsw-alias-brand-primary)' : 'var(--dsw-alias-border-l2)'), fontSize: '12px', cursor: 'pointer' } },
                  h('input', { type: 'checkbox', checked: sel.has(m.member_id), onChange: () => { toggleSel(m.member_id) }, style: { marginRight: '6px', verticalAlign: 'middle' } }),
                  h('span', null, m.display_name || '(未命名)'),
                )
              }),
            ),
            h('button', { onClick: extractMembers, disabled: sel.size === 0, style: { padding: '8px 16px', border: 'none', borderRadius: '6px', background: sel.size > 0 ? 'var(--dsw-alias-brand-primary)' : 'var(--dsw-alias-border-l2)', color: sel.size > 0 ? 'var(--dsw-alias-bg-base)' : 'var(--dsw-alias-text-disabled)', fontWeight: 600, fontSize: '13px', cursor: sel.size > 0 ? 'pointer' : 'not-allowed' } }, '提取选中成员记忆到团队共享空间并删除'),
          ),
      ),
      tab === 'deleted' && h('div', null,
        deleted.length === 0 ? h('div', { style: { fontSize: '12px', color: 'var(--dsw-alias-text-disabled)', padding: '8px 0' } }, '无已删除成员')
          : h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '8px' } },
            deleted.map((m: any) => renderMemberCard(m, false)),
          ),
      ),
      // 统计
      (data.stats && (data.stats as any).members) ? h('div', { style: { background: 'var(--dsw-alias-bg-layer-2)', borderRadius: '10px', padding: '10px 14px', marginTop: '12px', fontSize: '12px', color: 'var(--dsw-alias-text-disabled)', display: 'flex', gap: '12px', flexWrap: 'wrap' } },
        h('span', null, '活跃: ' + active.length),
        h('span', null, '已吊销: ' + revoked.length),
        h('span', null, '已删除: ' + deleted.length),
        h('span', null, '共享记忆: ' + (((data.stats as any).shared_memory || {}).logs_3d || 0) + '条'),
      ) : null,
    ),
    // 底部固定
    h('div', { style: { borderTop: '1px solid var(--dsw-alias-border-l2)', paddingTop: '10px', marginTop: '16px', flexShrink: 0 } },
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--dsw-alias-text-disabled)' } },
        h('span', null, 'deepDDW v0.5.1 · MIT · ', h('a', { href: 'https://github.com/ccch713/deepddw', target: '_blank', style: { color: 'var(--dsw-alias-text-disabled)' } }, 'GitHub')),
        h('a', { href: 'https://ddw.ai-hub.com', target: '_blank', style: { color: 'var(--dsw-alias-brand-primary)', fontWeight: 500, fontSize: '12px' } }, '中大型团队？→ 商业版'),
      ),
    ),
  )
}

// ══════ 首次弹窗 ══════
function OnboardingModal() {
  const [st, setSt] = React.useState({ selected: 'solo', submitting: false })
  function confirm() {
    setSt({ selected: st.selected, submitting: true })
    fetch(BASE + '/api/v1/deployment/mode', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: st.selected }) })
      .then((r: any) => { if (r.ok) { localStorage.setItem('deepddw_onboarded', '1'); location.reload() } else { setSt({ selected: st.selected, submitting: false }) } })
      .catch(() => { setSt({ selected: st.selected, submitting: false }) })
  }
  return h('div', { style: { position: 'fixed', inset: 0, zIndex: 99999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,.6)' } },
    h('div', { style: { background: 'var(--dsw-alias-bg-base)', border: '1px solid var(--dsw-alias-border-l2)', borderRadius: '12px', padding: '32px', maxWidth: '420px', width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,.5)' } },
      h('h2', { style: { margin: '0 0 16px', fontSize: '18px', fontWeight: 700, color: 'var(--dsw-alias-label-primary)' } }, '选择使用模式'),
      h('p', { style: { margin: '0 0 20px', fontSize: '12px', color: 'var(--dsw-alias-text-disabled)' } }, '可随时在「设置 → 多用户设置」中切换'),
      MODES.map((m) => h('label', { key: m.value, style: { display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px 12px', marginBottom: '4px', borderRadius: '8px', cursor: 'pointer', border: '2px solid ' + (st.selected === m.value ? 'var(--dsw-alias-brand-primary)' : 'transparent') }, onClick: () => { setSt({ selected: m.value, submitting: false }) } },
        h('input', { type: 'radio', checked: st.selected === m.value, readOnly: true, style: { marginTop: '2px' } }),
        h('div', null, h('div', { style: { fontSize: '14px', fontWeight: 600 } }, m.label), h('div', { style: { fontSize: '12px', color: 'var(--dsw-alias-text-disabled)', marginTop: '2px' } }, m.spec)),
      )),
      h('button', { onClick: confirm, disabled: st.submitting, style: { width: '100%', padding: '12px', border: 'none', borderRadius: '8px', background: 'var(--dsw-alias-brand-primary)', color: 'var(--dsw-alias-bg-base)', fontWeight: 600, fontSize: '14px', cursor: 'pointer', marginTop: '12px', opacity: st.submitting ? 0.5 : 1 } }, st.submitting ? '保存中...' : '确认'),
    ),
  )
}

// ══════ 左栏入口（v0.6.0）══════

/**
 * 左栏图标位（sidebar.panellist 的占用者）。owner 传 { size, active }：
 * size 是请求的方形边长，active 表示该面板当前在主区选中。图标用
 * currentColor 描边，深浅主题自动跟随。
 */
function TeamIcon(props: any) {
  const size = (props && props.size) || 22
  const active = !!(props && props.active)
  return h('span', { style: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: size, height: size, opacity: active ? 1 : 0.75 } },
    h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true' },
      h('path', { d: 'M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20' }),
      h('circle', { cx: 9.5, cy: 7, r: 3 }),
      h('path', { d: 'M17 11a3 3 0 1 0-2.5-4.2M21 20v-1.5a4 4 0 0 0-3-3.8' }),
    ),
  )
}

/**
 * 左栏图标打开的主面板（main keyed 槽，key = PANEL_ID）。main 的非保留 key
 * 不绑会话 = 浏览器级视图；内容即全局管理台（成员/设备/模式/共享空间），
 * 与 设置 → 团队管理 共用同一组件：左栏是「入口」，设置页是「配置」，并存。
 */
function TeamMain(_props: any) {
  return h('div', { style: { height: '100%', overflowY: 'auto' } }, h(SettingsPanel))
}

/**
 * 右栏页签（v0.6.0，裁定方案 C 的会话伴随面）：当前身份 / 在线设备 / 共享空间。
 * 形态参照 dsh-context：sidebarRightTabs 服务注册页签类型，sidebar.right.pane.tab
 * （keyed / session 作用域）出页签体——无会话时页签不存在，属预期行为。
 * 注：「本会话写入的记忆」需按会话过滤的记忆查询 API，留待后端补（v0.7）。
 */
function TeamSideTab(_props: any) {
  const [st, setSt] = React.useState({ member: '', role: '', online: 0, total: 0, shared: 0, mode: '' })
  React.useEffect(() => {
    const mid = localStorage.getItem('deepddw_member_id') || ''
    fetch(BASE + '/api/v1/deployment/mode').then((r: any) => r.json()).then((d: any) => {
      setSt((s: any) => ({ ...s, mode: (d.data && d.data.mode) || '' }))
    }).catch(() => { /* 网关不可达时保持空态 */ })
    fetch(BASE + '/api/v1/status').then((r: any) => r.json()).then((d: any) => {
      const devs = (d.data && d.data.devices) || []
      setSt((s: any) => ({ ...s, online: devs.filter((x: any) => x.online).length, total: devs.length }))
    }).catch(() => { /* ignore */ })
    fetch(BASE + '/api/v1/member/list').then((r: any) => r.json()).then((d: any) => {
      const list = (d.data && d.data.results) || []
      const me = list.find((m: any) => m.member_id === mid)
      if (me) setSt((s: any) => ({ ...s, member: me.display_name || '', role: me.role || '' }))
    }).catch(() => { /* ignore */ })
    fetch(BASE + '/api/v1/admin/stats').then((r: any) => r.json()).then((d: any) => {
      setSt((s: any) => ({ ...s, shared: (d.data && d.data.shared_memory && d.data.shared_memory.logs_3d) || 0 }))
    }).catch(() => { /* ignore */ })
  }, [])
  const row = (k: string, v: any) => h('div', { key: k, style: { display: 'flex', justifyContent: 'space-between', padding: '6px 8px', borderRadius: '6px', background: 'var(--dsw-alias-bg-layer-2)' } },
    h('span', { style: { color: 'var(--dsw-alias-label-secondary)' } }, k),
    h('b', { style: { fontWeight: 600 } }, String(v)),
  )
  return h('div', { style: { padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px' } },
    row(t('当前身份', 'Identity'), st.member || t('未绑定', 'Unbound')),
    row(t('角色', 'Role'), st.role || '-'),
    row(t('在线设备', 'Devices online'), st.online + ' / ' + st.total),
    row(t('共享记忆（3 日）', 'Shared (3d)'), st.shared),
    row(t('部署模式', 'Mode'), st.mode || '-'),
    h('p', { style: { margin: '4px 2px 0', fontSize: '11px', color: 'var(--dsw-alias-text-disabled)' } },
      t('管理台见左栏「团队管理」。', 'Manage in the left-rail Team Admin entry.')),
  )
}

/**
 * 注册守卫：把「等槽声明再注册」包成一个 effect。槽已声明则立即执行，
 * 未声明则在其声明调用内执行——两种顺序都正确；直接注册会抛
 * slot "…" is not declared 并让整个插件 fiber failed。单个入口失败只记
 * 日志不向上抛：UI 插件可以丢一个入口，不能丢整个页面。
 */
function registerWhenDeclared(ctx: any, slot: string, options: any, component: any, label: string): void {
  try {
    ctx.effect(() => ctx.slots.inject(slot, () => ctx.slots.register(options, component)), 'ddw: ' + label)
  } catch (e) {
    console.error('[ddw] register ' + label + ' failed', e)
  }
}

// ══════ 主入口 ══════
export function apply(ctx: any) {
  try {
    // 注意：ctx.config 未在 inject 中声明，DSH 客户端代理会抛 "cannot get property config without inject"，
    // 故不能直接读取 ctx.config；网关地址固定 8500（与服务端 deepDDW 一致，LAN_BYPASS 免密）。
    if (!localStorage.getItem('deepddw_onboarded')) {
      fetch(BASE + '/api/v1/deployment/mode').then((r: any) => r.json()).then((d: any) => {
        if (d && d.data && d.data.configured) { localStorage.setItem('deepddw_onboarded', '1') }
        else { ctx.slots.inject('settings.onboarding', () => ctx.slots.register({ name: 'settings.onboarding', id: 'ddw-multiuser-onboard', order: 50, label: () => '初次设置' }, OnboardingModal)) }
      }).catch(() => { /* ignore */ })
    }
    ctx.slots.inject('settings.section', () => ctx.slots.register({ name: 'settings.section', id: 'ddw-multiuser-settings', order: 100, label: () => t('团队管理', 'Team Admin') }, SettingsPanel))
    // 左栏入口（v0.6.0）：panellist 画图标、main 承接点击——两个 root 槽成对注册，
    // id 与 key 同值（PANEL_ID）；设置 → 团队管理 保留为配置页，两处并存。
    registerWhenDeclared(ctx, 'sidebar.panellist',
      { name: 'sidebar.panellist', id: PANEL_ID, order: 30, label: () => t('团队管理', 'Team Admin') },
      TeamIcon, 'left rail icon')
    registerWhenDeclared(ctx, 'main',
      { name: 'main', key: PANEL_ID },
      TeamMain, 'main panel')
    // 右栏页签（裁定方案 C 会话伴随面）：sidebarRightTabs 服务 + keyed 槽成对注册；
    // 服务未到达时静默放弃右栏页签，不影响左栏与设置页（UI 可丢入口不能丢页面）。
    try {
      ctx.inject(['sidebarRightTabs'], (raw: any) => {
        const tabs = raw && raw.sidebarRightTabs
        if (!tabs || typeof tabs.register !== 'function') return undefined
        const disposers: Array<() => void> = []
        try {
          disposers.push(tabs.register({
            id: 'ddw-team-tab',
            kind: 'ddw-team-tab',
            title: () => t('团队', 'Team'),
            guide: [{
              id: 'ddw-team-tab',
              order: 30,
              title: () => t('团队', 'Team'),
              description: () => t('当前身份、在线设备与共享空间', 'Identity, devices online and shared space'),
              icon: TeamIcon,
            }],
          }))
          disposers.push(ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register(
            { name: 'sidebar.right.pane.tab', key: 'ddw-team-tab' },
            TeamSideTab,
          )))
          disposers.push(ctx.slots.inject('sidebar.right.pane.tab.title', () => ctx.slots.register(
            { name: 'sidebar.right.pane.tab.title', key: 'ddw-team-tab' },
            () => h('span', { style: { fontSize: '12px' } }, t('团队', 'Team')),
          )))
        } catch (e) {
          for (const d of disposers) d()
          console.error('[ddw] right tab register failed', e)
          return undefined
        }
        return () => { for (const d of disposers) d() }
      })
    } catch (e) {
      console.error('[ddw] right tab service wait failed', e)
    }
    const deviceId = localStorage.getItem('deepddw_device_id') || ('dev-' + Date.now().toString(36))
    localStorage.setItem('deepddw_device_id', deviceId)
    // 设备心跳：deepDDW 在线判定窗口 60s（last_seen < 60s），必须持续上报才保持在线。
    // 仅页面加载注册一次会导致 60s 后设备离线 → 成员列表显示灰色。
    function heartbeat() {
      fetch(BASE + '/api/v1/device/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId, device_name: 'web-client', workspace: localStorage.getItem('deepddw_workspace') || 'shared' }) }).catch(() => { /* ignore */ })
    }
    heartbeat()
    setInterval(heartbeat, 30000) // 每 30s 心跳（窗口 60s 的一半）
    const currentMemberId = localStorage.getItem('deepddw_member_id') || ''
    // 仅在已绑定成员时 identify（member_id 为空时调用会把空串写入历史数据，污染 device_ids）
    if (currentMemberId) {
      fetch(BASE + '/api/v1/device/identify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId, member_id: currentMemberId }) }).catch(() => { /* ignore */ })
    }

    if (!localStorage.getItem('deepddw_member_id')) {
      fetch(BASE + '/api/v1/member/list').then((r: any) => r.json()).then((d: any) => {
        const active = ((d && d.data && d.data.results) || []).filter((m: any) => !m.revoked && !m.deleted)
        if (active.length > 0) {
          ctx.slots.inject('shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'ddw-member-identify', order: 9999, label: () => '成员识别' }, () => h(MemberIdentify, { members: active, deviceId: deviceId })))
        }
      }).catch(() => { /* ignore */ })
    }
    console.log('[ddw] all slots registered (v0.6.0: settings.section + sidebar.panellist + main + sidebar.right.pane.tab)')
  } catch (e) { console.error('[ddw]', e) }
}
