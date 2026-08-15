# DDW Website 插件

官网作为 DDW 底座的一个插件能力，统一管理官网配置：

- **主题模版**：standard（标准商务）/ holiday（节日喜庆）/ mourning（素色简约）
  由 DDW 底座管理后台统一切换（`PUT /api/v1/plugins/ddw-website/theme`），
  前台页面只读（`GET .../theme`），无用户切换入口。
- **站点信息**：公司全称 / 双备案 / 联系方式 / 地址 / GitHub，集中管理。
- **页面清单**：官网各页面的规范化登记。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | /api/v1/plugins/ddw-website/theme | 当前主题（前台页面调用） |
| PUT  | /api/v1/plugins/ddw-website/theme | 切换主题（管理后台） |
| GET  | /api/v1/plugins/ddw-website/site | 站点基础信息 |
| PUT  | /api/v1/plugins/ddw-website/site | 更新站点信息（管理后台） |
| GET  | /api/v1/plugins/ddw-website/pages | 页面清单 |

## 主题切换流程

```
DDW 底座管理后台 ──PUT theme──▶ ddw-website 插件 ──持久化 site_config.json──▶
前台页面 ──GET theme──▶ 读取当前主题 ──▶ 加载 assets/css/themes/<theme>.css
```

## 官网页面

官网静态页面位于 `frontend/company/`（www.9cio.com），共享布局引擎
`assets/js/site-common.js`（导航/页脚/主题由引擎统一注入，改一处全站生效）。
