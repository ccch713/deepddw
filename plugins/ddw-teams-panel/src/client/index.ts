/**
 * deepDDW 多用户设置面板 — 纯 DSH cordis 插件（v0.5.0 架构重写）。
 *
 * 5 个 DSH slot 注入（零自定义 CSS，100% DSH 官方组件）：
 *   1. settings.onboarding → M2 首次模式选择弹窗
 *   2. settings.section    → M3/M5/M6 设置页（多用户设置）
 *   3. settings.section    → M4 成员识别（弹窗）— 注册在 onboarding 槽
 * 网关 API 已由 R4 backend 完成：/deployment/mode、/member/add|list、
 * /device/identify、/version、/admin/stats
 */
import { createElement as h } from 'react'

const NS = 'settings.ddwMultiuser'
const GW_KEY = 'gatewayUrl'
const DEFAULT_GW = 'http://127.0.0.1:8500'

function gw(ctx) {
  return ctx.config?.[GW_KEY] || DEFAULT_GW
}
function t(ctx, k) {
  const bind = ctx.locale?.bind?.(NS)
  return bind ? bind(k) : k
}

// ──────────────────────────────────────────────────────────────
// M4 成员识别（新设备首次打开 DSH → "你是谁" → 选名字 → 绑定）
// ──────────────────────────────────────────────────────────────
function tryAutoIdentify(ctx, baseUrl) {
  const deviceId = localStorage.getItem('deepddw_device_id') || ('dev-' + Date.now().toString(36))
  localStorage.setItem('deepddw_device_id', deviceId)
  const memberId = localStorage.getItem('deepddw_member_id')
  if (memberId) return // 已绑定，不弹
  // 拉成员列表，多于1人则弹出选择
  fetch(baseUrl + '/api/v1/member/list')
    .then(r => r.json())
    .then(d => {
      const members = d?.data?.results || []
      if (members.length === 0) return
      ctx.slots.inject('shell.overlay', () => ctx.slots.register({
        name: 'shell.overlay',
        id: 'ddw-member-identify',
        order: 9999,
        label: () => t(ctx, 'identifyTitle'),
      }, () => h(MemberIdentify, { members, deviceId, baseUrl })))
    })
    .catch(() => {})
}

// ──────────────────────────────────────────────────────────────
// M2 首次弹窗（settings.onboarding slot → 模式选择）
// ──────────────────────────────────────────────────────────────
function setupOnboarding(ctx) {
  if (localStorage.getItem('deepddw_onboarded')) return
  const baseUrl = gw(ctx)
  // 拉当前模式，若已配置则标记 onboarded
  fetch(baseUrl + '/api/v1/deployment/mode')
    .then(r => r.json())
    .then(d => {
      if (d?.data?.configured) {
        localStorage.setItem('deepddw_onboarded', 'true')
        return
      }
      ctx.slots.inject('settings.onboarding', () => ctx.slots.register({
        name: 'settings.onboarding',
        id: 'ddw-multiuser-onboard',
        order: 50,
        label: () => t(ctx, 'onboardTitle'),
      }, () => h(OnboardingModal, { baseUrl, ctx })))
    })
    .catch(() => {})
}

// ──────────────────────────────────────────────────────────────
// M3 设置面板（settings.section slot → "多用户设置"）
// ──────────────────────────────────────────────────────────────
function setupSection(ctx) {
  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'ddw-multiuser-settings',
    order: 100,
    label: () => '多用户设置',
  }, () => h(SettingsPanel, { ctx })))
}

// ──────────────────────────────────────────────────────────────
// 主入口
// ──────────────────────────────────────────────────────────────
export const inject = ['slots', 'locale']

export function apply(ctx) {
  ctx.effect(() => ctx.locale?.register?.(NS, {
    zh: { onboardTitle: '初次设置', identifyTitle: '你是谁？', addMember: '添加成员', noMembers: '暂无成员' },
    en: { onboardTitle: 'Initial Setup', identifyTitle: 'Who are you?', addMember: 'Add Member', noMembers: 'No members' },
  }), 'ddw-multiuser: dicts')
  setupOnboarding(ctx)
  setupSection(ctx)
  const baseUrl = gw(ctx)
  tryAutoIdentify(ctx, baseUrl)
}

// ══════════════════════════════════════════════════════════════
// M2 OnboardingModal（首次弹窗：三选一模式）
// ══════════════════════════════════════════════════════════════
const MODES = [
  { value: 'solo',   label: '一人多设备', desc: '一个人使用多台设备' },
  { value: 'family', label: '家庭多人',   desc: '家人之间共享，互相可见' },
  { value: 'team',   label: '小团队协作', desc: '团队共享 + 各自空间' },
]

const OnboardingModal = {
  name: 'OnboardingModal',
  props: { baseUrl: String, ctx: Object },
  data: () => ({ selected: 'solo', submitting: false }),
  methods: {
    async confirm() {
      this.submitting = true
      try {
        const r = await fetch(this.baseUrl + '/api/v1/deployment/mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: this.selected }),
        })
        if (r.ok) {
          localStorage.setItem('deepddw_onboarded', 'true')
          this.props.onDone('done')
          location.reload()
        }
      } finally {
        this.submitting = false
      }
    },
  },
  render() {
    return h('div', {
      style: 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5)',
    }, [
      h('div', { style: 'background:var(--k-color-bg,#1a1a2e);border-radius:12px;padding:32px;max-width:420px;width:90%;color:var(--k-color-text,#e8ecf8)' }, [
        h('h2', { style: 'margin:0 0 8px;font-size:18px;font-weight:700' }, '选择使用模式'),
        h('p', { style: 'margin:0 0 20px;font-size:13px;color:var(--k-color-text-3,#888)' }, '可随时在「设置 → 多用户设置」中切换'),
        ...MODES.map(m => h('label', {
          style: 'display:flex;align-items:center;gap:10px;padding:12px 14px;margin-bottom:8px;border-radius:8px;cursor:pointer;border:2px solid ' +
            (this.selected === m.value ? 'var(--k-color-primary,#00e5ff)' : 'transparent') +
            ';background:' + (this.selected === m.value ? 'var(--k-color-primary-bg,#00e5ff10)' : 'transparent'),
          onClick: () => { this.selected = m.value },
        }, [
          h('input', {
            type: 'radio',
            checked: this.selected === m.value,
            style: 'accent-color:var(--k-color-primary,#00e5ff)',
          }),
          h('div', null, [
            h('div', { style: 'font-size:14px;font-weight:600' }, m.label),
            h('div', { style: 'font-size:12px;color:var(--k-color-text-3,#888)' }, m.desc),
          ]),
        ])),
        h('button', {
          disabled: this.submitting,
          onClick: this.confirm,
          style: 'width:100%;padding:12px;border:none;border-radius:8px;background:var(--k-color-primary,#00e5ff);color:var(--k-color-bg-1,#000);font-weight:600;font-size:14px;cursor:pointer;margin-top:8px;opacity:' + (this.submitting ? '0.5' : '1'),
        }, this.submitting ? '保存中...' : '确认'),
      ]),
    ])
  },
}

// ══════════════════════════════════════════════════════════════
// M3 SettingsPanel（多用户设置：模式+成员+统计+版本+升级）
// ══════════════════════════════════════════════════════════════
const SettingsPanel = {
  name: 'SettingsPanel',
  props: { ctx: Object },
  data: () => ({
    mode: 'solo', members: [], adding: false, newName: '', version: {}, stats: {},
  }),
  async mounted() {
    const b = gw(this.ctx)
    await this.refresh(b)
  },
  methods: {
    async refresh(b) {
      try {
        const [modeRes, memRes, statsRes, verRes] = await Promise.all([
          fetch(b + '/api/v1/deployment/mode').then(r => r.json()),
          fetch(b + '/api/v1/member/list').then(r => r.json()),
          fetch(b + '/api/v1/admin/stats').then(r => r.json()).catch(() => null),
          fetch(b + '/api/v1/version').then(r => r.json()),
        ])
        this.mode = modeRes?.data?.mode || 'solo'
        this.members = memRes?.data?.results || []
        this.stats = statsRes?.data || {}
        this.version = verRes?.data || {}
      } catch { /* ignore */ }
    },
    async setMode(m) {
      const b = gw(this.ctx)
      const r = await fetch(b + '/api/v1/deployment/mode', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: m }),
      })
      if (r.ok) { this.mode = m; location.reload() }
    },
    async addMember() {
      if (!this.newName.trim()) return
      this.adding = true
      const b = gw(this.ctx)
      await fetch(b + '/api/v1/member/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: this.newName.trim() }),
      })
      this.newName = ''
      await this.refresh(b)
      this.adding = false
    },
    async removeMember(mid) {
      const b = gw(this.ctx)
      await fetch(b + '/api/v1/member/revoke', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_id: mid }),
      })
      await this.refresh(b)
    },
  },
  render() {
    const h2 = this.$createElement
    return h2('div', { style: 'padding:16px;color:var(--k-color-text,#e8ecf8)' }, [
      h2('h2', { style: 'font-size:18px;font-weight:700;margin:0 0 6px' }, '多用户设置'),
      h2('p', { style: 'font-size:12px;color:var(--k-color-text-3,#888);margin:0 0 20px' },
        '管理多台设备、多名成员的共享与隔离'),  // M3 描述
      // ─── 模式选择（M7） ───
      h2('div', { style: 'font-size:13px;font-weight:600;margin-bottom:10px;color:var(--k-color-text-2,#ccc)' }, '模式'),
      ...MODES.map(m => h2('label', {
        key: m.value,
        style: 'display:flex;align-items:center;gap:10px;padding:10px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid ' +
          (this.mode === m.value ? 'var(--k-color-primary,#00e5ff)' : 'transparent'),
      }, [
        h2('input', { type: 'radio', checked: this.mode === m.value, onChange: () => this.setMode(m.value),
          style: 'accent-color:var(--k-color-primary,#00e5ff)' }),
        h2('span', { style: 'font-size:14px' }, m.label),
      ])),
      // ─── 成员管理（M5） ───
      h2('div', { style: 'font-size:13px;font-weight:600;margin:20px 0 10px;color:var(--k-color-text-2,#ccc)' }, '成员'),
      h2('div', { style: 'display:flex;gap:8px;margin-bottom:12px' }, [
        h2('input', {
          value: this.newName,
          onInput: (e) => { this.newName = e.target.value },
          placeholder: '输入成员名称',
          style: 'flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--k-color-border,#333);background:var(--k-color-bg-2,#1a1a2e);color:var(--k-color-text,#e8ecf8);font-size:13px',
        }),
        h2('button', {
          onClick: this.addMember,
          disabled: this.adding,
          style: 'padding:8px 16px;border:none;border-radius:6px;background:var(--k-color-primary,#00e5ff);color:var(--k-color-bg-1,#000);font-weight:600;font-size:13px;cursor:pointer;opacity:' + (this.adding ? '0.5' : '1'),
        }, '+'),
      ]),
      this.members.length === 0
        ? h2('div', { style: 'font-size:12px;color:var(--k-color-text-3,#888);padding:8px 0' }, '暂无成员，点击 + 添加')
        : this.members.map(m => h2('div', {
            key: m.member_id,
            style: 'display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;background:var(--k-color-bg-2,#1a1a2e);margin-bottom:6px;font-size:13px',
          }, [
            h2('span', { style: m.revoked ? 'color:var(--k-color-text-3,#666)' : '' }, m.revoked ? '⚪' : '🟢'),
            h2('span', { style: 'flex:1' }, m.display_name),
            h2('button', { onClick: () => this.removeMember(m.member_id),
              style: 'padding:4px 8px;border:1px solid var(--k-color-border,#444);border-radius:4px;background:transparent;color:var(--k-color-text-3,#888);font-size:11px;cursor:pointer' }, '移除'),
          ])),
      // ─── 系统信息 + 升级入口（M6） ───
      h2('div', { style: 'font-size:13px;font-weight:600;margin:20px 0 10px;color:var(--k-color-text-2,#ccc)' }, '系统信息'),
      h2('div', { style: 'font-size:12px;color:var(--k-color-text-3,#888);line-height:1.8' }, [
        'deepDDW v' + (this.version.version || '?') + '  ·  网关 v' + (this.version.version || '?'),
        h2('br'),
        'github.com/ccch713/deepddw  ·  MIT License',
        h2('br'),
        h2('span', { style: 'color:var(--k-color-text-2,#aaa)' }, 'Network/Workspace/Files 的详细数据请查看 API 文档'),
      ]),
    ])
  },
}

// ══════════════════════════════════════════════════════════════
// M4 MemberIdentify（弹窗选择你是谁 → 绑定）
// ══════════════════════════════════════════════════════════════
const MemberIdentify = {
  name: 'MemberIdentify',
  props: { members: Array, deviceId: String, baseUrl: String },
  data: () => ({ selected: null, done: false }),
  methods: {
    async bind() {
      if (!this.selected) return
      await fetch(this.baseUrl + '/api/v1/device/identify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: this.deviceId, member_id: this.selected }),
      })
      localStorage.setItem('deepddw_member_id', this.selected)
      this.done = true
      location.reload()
    },
  },
  render() {
    if (this.done) return null
    return h('div', {
      style: 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5)',
    }, [
      h('div', { style: 'background:var(--k-color-bg,#1a1a2e);border-radius:12px;padding:32px;max-width:380px;width:90%;color:var(--k-color-text,#e8ecf8)' }, [
        h('h2', { style: 'margin:0 0 16px;font-size:17px;font-weight:700' }, '你是谁？'),
        ...this.members.map(m => h('label', {
          key: m.member_id,
          onClick: () => { this.selected = m.member_id },
          style: 'display:flex;align-items:center;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid ' +
            (this.selected === m.member_id ? 'var(--k-color-primary,#00e5ff)' : 'transparent'),
        }, [
          h('input', { type: 'radio', checked: this.selected === m.member_id,
            style: 'accent-color:var(--k-color-primary,#00e5ff)' }),
          h('span', { style: 'font-size:14px' }, m.display_name),
        ])),
        h('button', {
          onClick: this.bind,
          disabled: !this.selected,
          style: 'width:100%;padding:12px;border:none;border-radius:8px;background:var(--k-color-primary,#00e5ff);color:var(--k-color-bg-1,#000);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:' + (this.selected ? '1' : '0.5'),
        }, '确认身份'),
      ]),
    ])
  },
}

export default SettingsPanel
