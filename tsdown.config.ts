import { defineConfig } from 'tsdown'

const PLUGIN_ID = '@deepddw/ddw-teams-panel'

/**
 * DSH 客户端 loader 在浏览器中提供的 require 函数能解析的模块。
 * 这些模块在 bundle 中必须标记为外部，运行时由 DSH loader 通过 require() 注入。
 */
const DSH_CLIENT_EXTERNALS = [
  'react',
  'react/jsx-runtime',
  'react-dom',
  'react-dom/client',
  '@deepseek-ai/cordis',
  '@deepseek-ai/dsh-client-modules',
  '@deepseek-ai/dsh-client-runtime',
  '@deepseek-ai/dsh-client-runtime/client',
  '@deepseek-ai/dsh-client-connection',
  '@deepseek-ai/dsh-client-locale',
  '@deepseek-ai/dsh-client-ui-slots',
  '@deepseek-ai/dsh-client-ui-primitives',
  '@deepseek-ai/dsh-client-ui-attachment',
  '@deepseek-ai/dsh-client-schema-form',
]

// banner 包裹 __ModuleLoader__ 开头 + CJS 兼容变量
const BANNER = `window.__ModuleLoader__.load({
	id: ${JSON.stringify(PLUGIN_ID)},
	factory: (require) => {
	var module = { exports: {} };
	var exports = module.exports;`

const FOOTER = `
	return module.exports;
	}
});`

export default defineConfig([
  {
    entry: {
      client: 'plugins/ddw-teams-panel/src/client/index.ts',
    },
    outDir: 'plugins/ddw-teams-panel/lib',
    format: 'cjs',
    platform: 'browser',
    target: 'es2020',
    clean: true,
    sourcemap: true,

    deps: {
      neverBundle: DSH_CLIENT_EXTERNALS,
    },

    banner: { js: BANNER },
    footer: { js: FOOTER },

    dts: false,
    treeshake: false,

    outExtensions: () => ({ js: '.js' }),
  },
])
