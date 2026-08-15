# TASK_SPEC：DDW 文档库 URL 保护 + ddw_searxng 插件

> 执行人：MiMo Code。工作目录：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub`（活跃工作树，勿碰 local-llm/ 与 cloud-llm/ 历史副本）。
> 完成标准：两个任务全部实现 + pytest 通过 + 自检命令输出正常。

## 项目背景（必须阅读）

- FastAPI 应用入口：`core/main.py`（`app = FastAPI(...)`，`load_plugins(app)` 自动扫描 `plugins/*/plugin.py` 注册插件）
- 插件模板（完整模式）：**`plugins/ddw_support_ticket/`**（目录下划线；`__init__.py` 导出 `PLUGIN_NAME`+`VERSION`；`plugin.py` 定义 `class Plugin(PluginBase)`：name/version/router_prefix=`f"/api/v1/plugins/{PLUGIN_NAME}"`，`setup()` 里 `self._router = build_router(); self.app.include_router(self._router)`；router.py 用 `build_router()` 工厂）
- auth 依赖：`core/auth/jwt.py` 提供 `current_user` / `current_admin`（`from core.auth.jwt import current_user, current_admin`，FastAPI `Depends` 直接用）
- 插件鉴权惯例：参考 `plugins/ddw_support_ticket/router.py` 如何给端点加 `Depends(current_user)`
- 数据库：本任务两个模块**均不需要**数据库（文档保护纯文件+签名；searxng 纯 HTTP 转发），不要引入 SQLAlchemy
- 测试惯例：仓库根 `tests/` 下（查看现有 tests/ 结构，pytest 用 async 需要 pytest-asyncio——查看现有测试怎么处理 async 的，照抄模式）
- 前端 auth：`frontend/js/auth.js` 提供 `DDW.auth`（token 存取方式在文件里，修改 admin.html 前先读它）

## 任务 A：文档库 URL 级保护（后端托管）

**背景**：`frontend/docs/` 是 DDW 文档中心静态目录（Caddy 直接服务）。其中 `frontend/docs/fde/*.html` 是 FDE 内部文档（unlimited-ocr-demo-sop.html、unlimited-ocr-deploy.html），当前无保护。目标：无凭证直接访问 `/docs/fde/*` → 401；管理员通过**短期签名 URL**（或 Bearer token）可访问。

### A1. 新建 `core/api/docs.py`

```python
# 结构参考 core/api/ 下现有模块（router = APIRouter()）
```
- `GET /docs/fde/{filename}`：
  - `filename` 白名单校验：`re.fullmatch(r"[a-zA-Z0-9_-]+\.html", filename)`，否则 400
  - 鉴权二选一：
    1. query 参数 `sig` + `exp`（签名 URL）：`exp` 为 unix 秒（> now 才有效，默认有效期 900s）；`sig = hmac.new(secret, f"{filename}:{exp}".encode(), hashlib.sha256).hexdigest()`，`hmac.compare_digest` 比对，失败/过期 → 401 JSON `{detail: "无效或过期的文档链接"}`
    2. `Authorization: Bearer <jwt>`（`current_admin` 依赖）——直接放行（供 API/前端 fetch 场景）
  - 文件路径：`frontend/docs/fde/{filename}`（相对仓库根；运行时用 `Path(__file__).resolve().parent.parent.parent / "frontend" / "docs" / "fde"` 定位），不存在 → 404
  - 成功 → `FileResponse(path, media_type="text/html")`
- `GET /api/v1/docs/sign`（`Depends(current_admin)`）：
  - query 参数 `path`（如 `fde/unlimited-ocr-demo-sop.html`），白名单 `^[a-zA-Z0-9_/-]+\.html$`（只允许 fde/ 前缀，其他前缀 403）
  - 生成 `exp = int(time.time()) + 900`，`sig` 同 A1 算法（secret 用同一变量）
  - 返回 `{"url": f"/docs/fde/{basename}?sig={sig}&exp={exp}"}`（path 取 basename）
- `secret`：`os.environ.get("DDW_DOCS_SIGN_SECRET")`，为空时用 `secrets.token_hex(32)` 并 `logger.warning("DDW_DOCS_SIGN_SECRET 未设置，使用随机密钥（重启后旧链接失效）")`

### A2. 挂载路由

读 `core/main.py` 现有 API router 挂载方式（core/api 下的模块如何 include），按同方式把 docs router 挂进 app。

### A3. Caddy 配置（写到本仓库 `caddy/` 或单独输出配置片段文件 `docs/caddy-docs-fde.conf`）

输出片段（**不要改 ECS 线上文件**，只产出片段供部署）：
```
    # FDE 内部文档走后端（签名 URL 保护）
    handle /docs/fde/* {
        reverse_proxy 172.19.0.1:8500
    }
```
注明：插入位置 = `ddw.9cio.com` 站点块内、`handle /api/*` 之后、`handle /assets/*` 之前。

### A4. `frontend/admin.html` 文档库链接改造

- 现有"📚 文档库"section 中两个 FDE 卡片是静态 `<a href="/docs/fde/xxx.html">`，改为 JS 动态：给卡片链接加 `onclick="return openFdeDoc(event, 'unlimited-ocr-demo-sop.html')"`（第二个同理 deploy）
- 在 admin.html 的 `<script>` 区新增函数：
```js
async function openFdeDoc(e, file) {
  e.preventDefault();
  const token = /* 从 auth.js 的 token 存取方式读取 */;
  try {
    const r = await fetch('/api/v1/docs/sign?path=fde/' + file, {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    if (!r.ok) { alert('无权限访问内部文档'); return false; }
    const d = await r.json();
    window.open(d.url, '_blank');
  } catch (err) { alert('获取文档链接失败'); }
  return false;
}
```
- 读 `frontend/js/auth.js` 确认 token 的存取变量/键名，用它（如果 auth.js 暴露 `DDW.auth.getToken()` 就用它）

### A5. 测试 `tests/test_docs_protection.py`

用例（用 FastAPI TestClient 或 AsyncClient，照现有测试模式）：
1. 无签名访问 `/docs/fde/unlimited-ocr-demo-sop.html` → 401
2. 错误 sig → 401；过期 exp → 401
3. 合法签名 → 200 且 content-type text/html
4. `../` 路径穿越 → 400/422
5. 文件名非法（`a.exe`）→ 400
6. `/api/v1/docs/sign` 无 token → 401
7. `/api/v1/docs/sign` 带 admin token → 200 且返回 url 含 sig
8. 签名 URL 访问真实文件（测试时若文件不存在，先创建临时文件在 frontend/docs/fde/ 下或 mock FileResponse 路径——若文件存在就直接用真实文件）

> admin token 怎么造：查看现有测试如何生成 JWT（core/auth/jwt.py 有生成函数或测试里 mock current_admin——参考现有 tests/ 里 admin 端点测试的做法）

## 任务 B：ddw_searxng 插件

**背景**：SearXNG（MIT 元搜索）在 16G（http://192.168.1.7:8888）运行，JSON API：`GET {url}/search?q=<词>&format=json`（返回 `{results:[{title,url,content,engine,score}], unresponsive_engines:[[name,msg]]}`）。插件把该 API 封装为 DDW 标准插件。PRD：`/Users/chenye/workspace/DDW插件/ddw-searxng/PRD_ddw-searxng_v1.0.md`（读它，按 P0 范围实现 F1/F2/F3）。

### B1. 目录 `plugins/ddw_searxng/`（参考 plugins/ddw_support_ticket/）

| 文件 | 要点 |
|:--|:--|
| `__init__.py` | `PLUGIN_NAME = "ddw-searxng"`（连字符，路由前缀用）；`VERSION = "0.1.0"` |
| `plugin.py` | `class Plugin(PluginBase)`：name=PLUGIN_NAME, version=VERSION, router_prefix=`/api/v1/plugins/{PLUGIN_NAME}`, setup() 注册 router（照 support_ticket 模板） |
| `router.py` | `build_router()`：`GET /search`（`Depends(current_user)`，参数 q 必填/limit 默认5 max20/engines 可选逗号分隔）、`GET /health`（`Depends(current_user)`） |
| `services.py` | `SearXNGClient`（httpx.AsyncClient 或模块函数）：`search(query, limit, engines)`、`health()`；`SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")`；超时 15s；不可达/超时抛 `SearXNGUnavailable` 自定义异常；`_normalize(results)` 把 SearXNG 结果归一为 `{title,url,content,engine,score}` |
| `schemas.py` | search 响应模型（`SearchResp{success, data[], total, elapsed_ms, unresponsive_engines}`）+ 请求参数校验（Query） |
| `manifest.yaml` | name: ddw-searxng / version: 0.1.0 / description / author: Ruiguo / license: MIT；**无 ai_provider**（不调 LLM）；resource 声明（轻量级） |
| `README.md` + `README_EN.md` | 简介 + 配置（SEARXNG_URL 环境变量）+ API 示例 |
| `tests/test_ddw_searxng.py` | 见 B2 |

**路由行为**：
- `GET /api/v1/plugins/ddw-searxng/search?q=测试&limit=5` → 成功 `200 {success:true, data:[{title,url,content,engine,score}], total, elapsed_ms, unresponsive_engines}`；SearXNG 不可达 → `500 {success:false, error:"SEARXNG_UNREACHABLE", detail}`
- `GET /api/v1/plugins/ddw-searxng/health` → `200 {ok:true, searxng_url, engines:{}}`（engines 可空对象；SearXNG 不可达 → `{ok:false, searxng_url, detail}` 仍 200）
- 参数：q 缺失 → 422（FastAPI Query 必填）；limit 超 20 → 422（Query ge=1 le=20）

### B2. 测试 `plugins/ddw_searxng/tests/test_ddw_searxng.py`

（参考 support_ticket 的 tests 结构；**不连真实 SearXNG**，用 monkeypatch/httpx MockTransport）
1. search 成功（mock 返回含 results 的 JSON）→ 200、data 归一化正确、total=len
2. search 时 SearXNG 超时/ConnectionError → 500 + error=SEARXNG_UNREACHABLE
3. search 缺 q → 422；limit=50 → 422
4. health 成功/失败两态
5. 无 token → 401（如果测试环境 current_user 需要 token——照 support_ticket 测试的鉴权处理方式）

## 质量门禁（写一个验一个）

1. 每个 .py 写完：`python3 -m py_compile <file>`
2. 有 ruff 则 `ruff check <file>`（仓库根找 ruff 配置：pyproject.toml / ruff.toml / setup.cfg；没有就跳过）
3. 最后跑：
   ```bash
   cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
   python3 -m pytest tests/test_docs_protection.py -q --tb=short
   python3 -m pytest plugins/ddw_searxng/tests/ -q --tb=short
   python3 -c "from core.main import app; print('APP OK', len(app.routes))"
   ```
4. 全部通过后输出：改动文件清单 + pytest 结果 + 自检输出

## 交付物清单

- [ ] core/api/docs.py（新增）
- [ ] core/main.py（挂载 docs router）
- [ ] docs/caddy-docs-fde.conf（Caddy 配置片段，含插入位置注释）
- [ ] frontend/admin.html（文档库链接改签名 URL 动态生成）
- [ ] tests/test_docs_protection.py
- [ ] plugins/ddw_searxng/{__init__.py,plugin.py,router.py,services.py,schemas.py,manifest.yaml,README.md,README_EN.md}
- [ ] plugins/ddw_searxng/tests/test_ddw_searxng.py
- [ ] 全部 pytest 通过 + 自检输出

## 红线

- 不改 local-llm/ 与 cloud-llm/ 历史副本（除非确认它们是活跃副本，默认不碰）
- 不引入新第三方依赖（httpx/fastapi 已有）
- 不写死任何 IP 到代码（SEARXNG_URL 只走环境变量，默认 127.0.0.1 注释说明）
- manifest.yaml 不声明 ai_provider / 不存 API Key
- Caddy 片段只产出文件，不 ssh 改 ECS
