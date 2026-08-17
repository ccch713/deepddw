/**
 * deepDDW 团队版设置面板客户端（DSH for Teams）。
 *
 * 注册方式：settings.section slot（与「皮肤中心/Web UI 插件/宠物」同级，
 * 出现在侧边栏「社区插件」下方）。内部页签：记忆体/知识库/网络/用户/设备/文件库。
 * UI 硬约束：全部使用 DSH 官方设置页组件与 CSS 变量，禁止自设色号/字体。
 */
import { h } from 'vue'
import { inject } from '@koishijs/client'

export const inject = ['slots', 'locale', 'http']

const NS = 'settings.ddwTeamsPanel'

// deepDDW 网关地址（launcher 同源；可在插件配置 gatewayUrl 覆盖）
function gatewayUrl(ctx: any): string {
  return ctx.app?.config?.gatewayUrl || 'http://127.0.0.1:8500'
}

/** 页签定义（solo 模式无「用户」页签——由后端 mode 决定，前端统一渲染后由面板隐藏） */
const TABS = [
  { id: 'memory', label: '记忆体', api: '/api/v1/memory/context?budget=200' },
  { id: 'kb', label: '知识库', api: '/api/v1/knowledge/bases' },
  { id: 'network', label: '网络', api: '/api/v1/version' },
  { id: 'users', label: '用户', api: '/api/v1/member/list', soloHidden: true },
  { id: 'devices', label: '设备', api: '/api/v1/status' },
  { id: 'files', label: '文件库', api: '/api/v1/files/list' },
]

export function apply(ctx: any): void {
  ctx.effect(() => ctx.locale?.register?.(NS, {
    zh: { nav: 'DDW团队版' },
    en: { nav: 'DDW Teams' },
  }), 'ddw-teams-panel: dicts')

  const t = (key: string) => ctx.locale?.bind?.(NS)?.(key) ?? key

  ctx.slots.inject('settings.section', () => ctx.slots.register({
    name: 'settings.section',
    id: 'ddw-teams-panel',
    order: 100, // 社区插件区域：官方分区之后
    label: () => t('nav'),
    locale: NS,
  }, () => h(TeamsPanel, {
    ctx,
    gateway: gatewayUrl(ctx),
    t,
  })))
}

/** 页签内容区：拉取对应 API 并渲染为 DSH 设置页列表样式 */
const TeamsPanel = {
  name: 'TeamsPanel',
  props: {
    ctx: { type: Object, required: true },
    gateway: { type: String, required: true },
    t: { type: Function, required: true },
  },
  data() {
    return {
      active: 'memory',
      soloMode: false,
      loading: false,
      payload: null as any,
      token: '',
    }
  },
  async mounted() {
    // 探测部署模式（solo 隐藏「用户」页签）
    try {
      const r = await fetch(`${this.gateway}/api/v1/deployment/mode`)
      const d = await r.json()
      this.soloMode = d?.data?.mode === 'solo'
    } catch { /* 网关不可达时按默认渲染 */ }
  },
  computed: {
    visibleTabs() {
      return TABS.filter((tb) => !(this.soloMode && (tb as any).soloHidden))
    },
  },
  methods: {
    async switchTab(id: string) {
      this.active = id
      const tab = TABS.find((x) => x.id === id)
      if (!tab) return
      this.loading = true
      this.payload = null
      try {
        const r = await fetch(`${this.gateway}${tab.api}`)
        this.payload = await r.json()
      } catch (e: any) {
        this.payload = { error: String(e?.message || e) }
      } finally {
        this.loading = false
      }
    },
    fmt(v: any): string {
      try { return JSON.stringify(v, null, 2) } catch { return String(v) }
    },
  },
  render() {
    // 全部使用 DSH CSS 变量（--k-color-* / --k-bg-*），不引入自定义色号
    const tabs = this.visibleTabs.map((tb: any) => h('button', {
      class: 'ddw-tab',
      style: this.active === tb.id
        ? 'border-bottom:2px solid var(--k-color-primary,#00e5ff);font-weight:600'
        : '',
      onClick: () => this.switchTab(tb.id),
    }, tb.label))

    const content = this.loading
      ? h('div', { class: 'ddw-pane' }, '加载中…')
      : h('pre', {
          class: 'ddw-pane',
          style: 'white-space:pre-wrap;font-size:12px;color:var(--k-color-text,#e8ecf8)',
        }, this.fmt(this.payload))

    return h('div', { class: 'ddw-teams-panel' }, [
      h('div', { class: 'ddw-tabs', style: 'display:flex;gap:14px;border-bottom:1px solid var(--k-color-border,#233052);margin-bottom:12px' }, tabs),
      content,
    ])
  },
}

export default TeamsPanel
