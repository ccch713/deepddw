// deepDDW 多用户设置（服务端入口）
export const name = "ddw-multiuser"
export function apply(ctx) {
  const gw = process.env.DDW_GATEWAY_URL || "http://127.0.0.1:8600"
  ctx.on("ready", () => ctx.logger?.info?.("[ddw-multiuser] gateway=" + gw))
}
