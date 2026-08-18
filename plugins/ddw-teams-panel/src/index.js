// deepDDW 多用户设置（服务端入口——仅日志，实际逻辑在网关 API）
export function apply(ctx) {
  const gw = ctx.config?.gatewayUrl || 'http://127.0.0.1:8500'
  ctx.on('ready', () => ctx.logger?.info?.('[ddw-multiuser] gateway=' + gw))
}
