/**
 * deepDDW 团队版设置面板（服务端入口）。
 * 客户端注入由 dsh.bundle.patch + dsh.client.inject 声明；
 * 服务端仅做配置读取与日志。
 */
export function apply(ctx: any): void {
  const gateway = ctx.config?.gatewayUrl || 'http://127.0.0.1:8500'
  ctx.on('ready', () => {
    ctx.logger?.info?.(`[ddw-teams-panel] gateway=${gateway}`)
  })
}
