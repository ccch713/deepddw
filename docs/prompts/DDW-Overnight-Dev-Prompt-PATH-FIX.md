# ⚠️ 路径修正 + 补充项
# 追加到主提示词最前面

---

## ⚠️ 关键修正：16G 项目路径映射

**主提示词中所有 `/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/` 开头的路径，在 16G 上实际是 `/Users/chenye/workspace/ddw-ai-hub/`（根目录）。**

正确的路径对照表：

| 提示词写的路径 | 16G 实际路径 |
|:---|:---|
| `cloud-llm/ddw-ai-hub/core/main.py` | `core/main.py` |
| `cloud-llm/ddw-ai-hub/core/database/models.py` | `core/database/models.py` |
| `cloud-llm/ddw-ai-hub/core/middleware/tenant.py` | `core/middleware/tenant.py` |
| `cloud-llm/ddw-ai-hub/core/auth/jwt.py` | `core/auth/jwt.py` |
| `cloud-llm/ddw-ai-hub/core/config.py` | `core/config.py` |
| `cloud-llm/ddw-ai-hub/core/api/admin.py` | `core/api/admin.py` |
| `cloud-llm/ddw-ai-hub/core/api/auth.py` | `core/api/auth.py` |
| `plugins/ddw-token-manager/models.py` | `plugins/ddw-token-manager/models.py`（同） |
| `frontend/saas-register.html` | `frontend/saas-register.html`（同） |

**所有新建文件都放在项目根目录下，不要创建 `cloud-llm/` 目录。**

---

## ⚠️ 技术栈修正

| 项 | 提示词写的 | 16G 实际情况 |
|:---|:---|:---|
| 数据库 | PostgreSQL | **SQLite**（16G 没有 Docker/PG） |
| JWT | RSA256 + PyJWT | **HS256**（复用现有 JWT 实现） |
| 依赖 | PyJWT + uvicorn | 检查 `requirements.txt`，缺什么装什么 |

**原则：复用 16G 已有的实现，不要重写。**

---

## ⚠️ Logo 使用方式

Logo 文件不在 16G 上。**不要用 image_synthesize 生成 logo**。改用 CSS 文字 Logo：

```html
<!-- Header Logo（每个页面） -->
<div class="header-logo">
  <span class="logo-char">钜</span>
  <span class="header-title">DDW AI Hub</span>
</div>
```

```css
.logo-char {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: #000;
  color: #FFF;
  font-size: 20px;
  font-weight: bold;
  font-family: "PingFang SC", "Microsoft YaHei", serif;
  border-radius: 2px;
  margin-right: 8px;
}
```

32G 设备验收时会用真实 Logo PNG 替换这个 CSS 版本。

---

## ⚠️ ICP 备案号（所有页面 footer 必须包含）

```html
<footer class="app-footer">
  <span>&copy; 2026 武汉锐果互动信息技术有限公司</span>
  <span class="footer-sep">|</span>
  <a href="https://beian.miit.gov.cn/" target="_blank">鄂ICP备2026024883号-1</a>
  <span class="footer-sep">|</span>
  <a href="https://beian.mps.gov.cn/#/query/webSearch?code=42011102006255" target="_blank">鄂公网安备42011102006255号</a>
</footer>
```

---

## ⚠️ 自检命令修正

所有自检命令中的路径按上面的映射表替换。例如：

```bash
# 原来（32G 路径，错误）
# python -c "from core.database.tenant_filter import ..."

# 修正为（16G 路径）
cd /Users/chenye/workspace/ddw-ai-hub
python -c "from core.database.tenant_filter import set_tenant_context; print('OK')"
```

---

## 项目结构参考（16G 当前已有）

```
/Users/chenye/workspace/ddw-ai-hub/
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── database/
│   │   ├── models.py         ← 已有
│   │   ├── tenant_filter.py  ← 已创建
│   │   └── session.py
│   ├── middleware/
│   │   └── __init__.py
│   ├── auth/
│   │   └── __init__.py
│   ├── api/
│   │   └── __init__.py
│   ├── events/
│   │   └── __init__.py
│   ├── services/
│   │   ├── tenant_service.py ← 已创建
│   │   └── __init__.py
│   ├── hris_adapters/        ← 已创建
│   └── mcp/                  ← 已创建
├── cli/
│   ├── server_cmd.py
│   └── ...
├── sdk/
│   ├── plugin_base.py
│   └── ...
├── embedded_llm/
├── plugins/
│   ├── customer-service/
│   └── _template/
├── config/
│   └── deployment.yaml
├── frontend/                 ← 需要创建
│   ├── assets/
│   │   └── logo-ju.png       ← 32G 验收时替换
│   ├── saas-register.html
│   ├── saas-pricing.html
│   ├── saas-admin.html
│   ├── ddw-training.html
│   ├── ddw-skills.html
│   ├── ddw-agents.html
│   └── ddw-hris.html
└── scripts/
```
