/**
 * @deepddw/dsh-workbench — host side.
 *
 * deepDDW workbench plugin for DSH (official plugin mechanism; NO DSH source
 * changes). Host responsibilities:
 *   - resolve the deepDDW gateway base URL (env `DEEPDDW_BASE_URL` >
 *     plugin config `deepddw.baseUrl` > default http://127.0.0.1:8600);
 *   - serve a same-origin `/deepddw-meta` JSON route so the browser client
 *     can learn the gateway address without hard-coding a cross-origin URL.
 *
 * The browser half (`./client`) registers the actual UI: settings sections
 * (KB / memory / LLM config) and the collapsible docs rail.
 */

export const name = '@deepddw/dsh-workbench'

/** Services this plugin's root fiber requires. */
export const inject = []

/** Resolve the deepDDW gateway base URL (config > env > default). */
function resolveBaseUrl(config, ctx) {
  const cfg = config?.deepddw
  const candidates = [
    cfg && typeof cfg.baseUrl === 'string' ? cfg.baseUrl : undefined,
    typeof process !== 'undefined' && process.env && process.env.DEEPDDW_BASE_URL
      ? process.env.DEEPDDW_BASE_URL
      : undefined,
  ]
  const found = candidates.find((v) => v && v.trim().length > 0)
  return found ? String(found).replace(/\/+$/, '') : 'http://127.0.0.1:8600'
}

/**
 * Plugin entry: mount the meta route (tears down with the fiber).
 * @param ctx - cordis host context.
 * @param config - plugin config from the profile layer (cordis.yml / patch).
 * @returns disposer.
 */
export async function apply(ctx, config) {
  const baseUrl = resolveBaseUrl(config, ctx)

  // Optional Web route: only mounted when a webServer service exists.
  ctx.inject(['webServer'], (webCtx) => webCtx.effect(() => {
    const webServer = webCtx.webServer
    const disposeRoute = webServer.register({
      kind: 'exact',
      path: '/deepddw-meta',
      handler: (req, res) => {
        res.statusCode = 200
        res.setHeader('content-type', 'application/json; charset=utf-8')
        res.setHeader('cache-control', 'no-store')
        res.setHeader('x-content-type-options', 'nosniff')
        res.end(JSON.stringify({
          plugin: name,
          version: '0.2.0',
          baseUrl,
        }))
      },
    })
    return () => {
      disposeRoute()
    }
  }, 'deepddw-workbench: meta route'))

  ctx.logger.info(`deepddw-workbench mounted (baseUrl=${baseUrl})`)

  return async () => {
    // All contributions tear down via their own effect disposers.
  }
}
