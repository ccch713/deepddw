# 补充项：品牌标识 + ICP 备案 + 遗漏功能
# 这些内容追加到主提示词的"前端设计规范"部分之后

---

## 补充 A：公司 Logo（所有页面必须包含）

公司主体：**武汉锐果互动信息技术有限公司**
Logo 图形：**"钜"字**（黑底白字创意字体，现代无衬线设计）

Logo 文件位置：`/Users/chenye/workspace/ddw-ai-hub/frontend/assets/logo-ju.png`

### 使用规则

1. **Header 左上角**：Logo 图片（32×32px）+ "DDW AI Hub" 文字
2. **登录/注册页面**：Logo 图片（64×64px）居中 + 公司全称
3. **Footer 版权区**：公司全称 + ICP 备案号 + 公安备案号
4. **浏览器标签页**：favicon 使用 Logo 图片

### HTML 示例（每个页面的 Header）

```html
<header class="app-header">
  <div class="header-logo">
    <img src="assets/logo-ju.png" alt="钜" width="32" height="32">
    <span class="header-title">DDW AI Hub</span>
  </div>
  <!-- 其他 header 内容 -->
</header>
```

### HTML 示例（每个页面的 Footer）

```html
<footer class="app-footer">
  <div class="footer-content">
    <span>&copy; 2026 武汉锐果互动信息技术有限公司</span>
    <span class="footer-sep">|</span>
    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">鄂ICP备2026024883号-1</a>
    <span class="footer-sep">|</span>
    <a href="https://beian.mps.gov.cn/#/query/webSearch?code=42011102006255" target="_blank" rel="noopener">鄂公网安备42011102006255号</a>
  </div>
</footer>
```

### Footer CSS

```css
.app-footer {
  text-align: center;
  padding: 16px 0;
  color: #999;
  font-size: 12px;
  border-top: 1px solid #E8E8E8;
  background: #FFF;
}
.app-footer a {
  color: #999;
  text-decoration: none;
}
.app-footer a:hover {
  color: #1890FF;
}
.footer-sep {
  margin: 0 8px;
  color: #D9D9D9;
}
```

---

## 补充 B：ICP 备案号（法律强制要求）

**所有对外可访问的 HTML 页面必须在 footer 显示以下信息**：

| 项目 | 内容 |
|:---|:---|
| 版权主体 | 武汉锐果互动信息技术有限公司 |
| ICP 备案号 | 鄂ICP备2026024883号-1 |
| ICP 查询链接 | https://beian.miit.gov.cn/ |
| 公安备案号 | 鄂公网安备42011102006255号 |
| 公安查询链接 | https://beian.mps.gov.cn/#/query/webSearch?code=42011102006255 |

**自检命令**：
```bash
grep -r "鄂ICP备" /Users/chenye/workspace/ddw-ai-hub/frontend/
# 所有 saas-*.html / ddw-*.html 都必须命中
```

---

## 补充 C：知识库多级权限后端 API

在模块 B 的管理后台 API 中补充以下端点：

```
GET    /api/v1/knowledge/bases            → 知识库列表（按权限过滤）
POST   /api/v1/knowledge/bases            → 创建知识库
GET    /api/v1/knowledge/bases/{id}/permissions → 权限矩阵
PUT    /api/v1/knowledge/bases/{id}/permissions → 更新权限矩阵
```

权限矩阵结构：
```json
{
  "base_id": 1,
  "permissions": {
    "all_users": ["read"],
    "dept_cs": ["read", "write"],
    "dept_finance": ["read"],
    "dept_rd": ["read", "write", "delete"],
    "role_admin": ["read", "write", "delete", "manage"]
  }
}
```

知识库分类（8 类）：
1. 企业公共知识库（全员可读）
2. 客服知识库 ×N（按业务线分）
3. 财务知识库（财务部门）
4. 研发知识库（研发部门）
5. 采购知识库（采购部门）
6. 高层决策知识库（管理层）
7. 岗位知识库（按岗位）
8. 设备知识库（设备操作手册）

---

## 补充 D：数字员工工作流编辑器（DAG 可视化）

在 ddw-agents.html 的数字员工详情页中，增加一个"工作流"标签页：

- 使用纯 CSS + JS 实现简易 DAG 可视化（不引入第三方库）
- 节点 = 工作步骤（圆形 + 名称）
- 连线 = 依赖关系（SVG 线条）
- 支持拖拽调整节点位置
- 只读模式（查看已有工作流），编辑模式后续迭代

**优先级**：P2（先做只读展示，不做编辑器）

---

## 补充 E：全局自检追加命令

在模块 H 的全局自检中追加：

```bash
# Logo 文件存在
ls -la /Users/chenye/workspace/ddw-ai-hub/frontend/assets/logo-ju.png

# ICP 备案号出现在所有 HTML 页面
python3 -c "
import os
fd = '/Users/chenye/workspace/ddw-ai-hub/frontend'
missing = []
for f in sorted(os.listdir(fd)):
    if f.endswith('.html'):
        c = open(os.path.join(fd,f)).read()
        if '鄂ICP备' not in c:
            missing.append(f)
if missing:
    print(f'❌ ICP missing in: {missing}')
else:
    print('✅ ICP 备案号出现在所有 HTML 页面')
"

# Logo 出现在所有 HTML 页面
python3 -c "
import os
fd = '/Users/chenye/workspace/ddw-ai-hub/frontend'
missing = []
for f in sorted(os.listdir(fd)):
    if f.endswith('.html'):
        c = open(os.path.join(fd,f)).read()
        if 'logo-ju.png' not in c and 'logo' not in c.lower():
            missing.append(f)
if missing:
    print(f'⚠️ Logo missing in: {missing}')
else:
    print('✅ Logo 出现在所有 HTML 页面')
"
```
