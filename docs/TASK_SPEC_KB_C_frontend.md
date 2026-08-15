# TASK_SPEC: KB-C 知识库前端开发

> **日期**：2026-08-11
> **目标**：将 saas-admin.html 中的知识库占位替换为真实可用的前端

---

## 1. 现状

saas-admin.html 中 renderKnowledge() 函数返回"建设中"占位。

## 2. 后端 API（已就绪）

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| GET | /api/v1/plugins/ddw-knowledge-hierarchy/kb | 知识库列表 |
| POST | /api/v1/plugins/ddw-knowledge-hierarchy/kb | 创建知识库 |
| GET | /api/v1/plugins/ddw-knowledge-hierarchy/kb/{id} | 知识库详情 |
| DELETE | /api/v1/plugins/ddw-knowledge-hierarchy/kb/{id} | 删除 |
| POST | /api/v1/plugins/ddw-knowledge-hierarchy/documents/upload | 上传文档 |
| GET | /api/v1/plugins/ddw-knowledge-hierarchy/documents | 文档列表 |
| POST | /api/v1/plugins/ddw-knowledge-hierarchy/search/flat | 平铺搜索 |

## 3. 前端实现

### 3.1 替换 renderKnowledge()

将 saas-admin.html 中第 1031-1050 行的 renderKnowledge() 替换为：

```javascript
async function renderKnowledge() {
  let kbs = [];
  try {
    const r = await api('/api/v1/plugins/ddw-knowledge-hierarchy/kb');
    kbs = r.items || r || [];
  } catch (e) { /* ignore */ }
  
  return `
    <div class="card">
      <div class="card-head">
        <div class="card-title">知识库管理</div>
        <div class="card-extra">
          <button class="btn primary" onclick="showCreateKB()">+ 新建知识库</button>
        </div>
      </div>
      <div class="card-body" style="display:flex;gap:16px;min-height:500px">
        <div style="width:240px;border-right:1px solid var(--border);padding-right:16px;flex-shrink:0">
          <div style="font-size:13px;color:var(--text-muted);margin-bottom:8px">知识库目录</div>
          ${renderKBTree(kbs)}
        </div>
        <div style="flex:1">
          <div style="display:flex;gap:8px;margin-bottom:12px">
            <input id="kbSearch" placeholder="搜索知识库内容..." style="flex:1;height:32px;padding:4px 12px;border:1px solid var(--border-input);border-radius:var(--radius-sm);font-size:13px">
            <button class="btn" onclick="searchKB()">搜索</button>
            <button class="btn" onclick="uploadDoc()">上传文档</button>
          </div>
          <div id="kbDocList"><div class="empty">选择左侧知识库查看文档</div></div>
        </div>
      </div>
    </div>
  `;
}
```

### 3.2 新增辅助函数（在 renderKnowledge 之后）

```javascript
function renderKBTree(kbs) {
  if (!kbs || !kbs.length) return '<div class="empty" style="font-size:12px">暂无知识库</div>';
  const groups = { company: [], department: [], personal: [] };
  kbs.forEach(kb => { const s = kb.scope || 'company'; if (groups[s]) groups[s].push(kb); });
  const names = { company: '📁 企业知识库', department: '📂 部门知识库', personal: '📝 个人知识库' };
  let html = '';
  for (const [scope, items] of Object.entries(groups)) {
    if (!items.length) continue;
    html += '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:4px">' + names[scope] + ' (' + items.length + ')</div>';
    items.forEach(kb => {
      html += '<div class="kb-tree-item" onclick="selectKB(' + kb.id + ',this)" style="padding:6px 12px;font-size:13px;color:var(--text-secondary);cursor:pointer;border-radius:var(--radius-sm);margin:2px 0">' + (kb.name || '未命名') + '</div>';
    });
    html += '</div>';
  }
  return html;
}

let currentKBId = null;
async function selectKB(id, el) {
  currentKBId = id;
  document.querySelectorAll('.kb-tree-item').forEach(e => e.style.background = '');
  if (el) el.style.background = 'var(--bg-hover)';
  try {
    const r = await api('/api/v1/plugins/ddw-knowledge-hierarchy/documents?kb_id=' + id);
    const docs = r.items || r || [];
    const list = document.getElementById('kbDocList');
    if (!docs.length) { list.innerHTML = '<div class="empty">该知识库暂无文档</div>'; return; }
    list.innerHTML = '<table class="table"><thead><tr><th>文档名</th><th>大小</th><th>操作</th></tr></thead><tbody>' +
      docs.map(d => '<tr><td>' + (d.file_name || d.title || '未命名') + '</td><td>' + formatSize(d.file_size || 0) + '</td><td><button class="btn sm" onclick="deleteDoc(' + d.id + ')">删除</button></td></tr>').join('') +
      '</tbody></table>';
  } catch (e) {
    document.getElementById('kbDocList').innerHTML = '<div class="empty">加载失败：' + e.message + '</div>';
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

async function searchKB() {
  const q = document.getElementById('kbSearch').value.trim();
  if (!q) return;
  try {
    const r = await api('/api/v1/plugins/ddw-knowledge-hierarchy/search/flat', { method: 'POST', body: JSON.stringify({ query: q, kb_id: currentKBId }) });
    const results = r.results || r || [];
    const list = document.getElementById('kbDocList');
    if (!results.length) { list.innerHTML = '<div class="empty">未找到相关内容</div>'; return; }
    list.innerHTML = results.map(r => '<div style="padding:10px;border-bottom:1px solid var(--border-light)"><b>' + (r.title || '文档') + '</b><div style="font-size:12px;color:var(--text-muted);margin-top:4px">' + (r.content || r.text || '').slice(0, 200) + '</div></div>').join('');
  } catch (e) {
    document.getElementById('kbDocList').innerHTML = '<div class="empty">搜索失败：' + e.message + '</div>';
  }
}

function showCreateKB() { showToast('创建知识库功能开发中'); }
function uploadDoc() { if (!currentKBId) { showToast('请先选择知识库'); return; } showToast('文档上传功能开发中'); }
async function deleteDoc(docId) {
  if (!confirm('确定删除该文档？')) return;
  try { await api('/api/v1/plugins/ddw-knowledge-hierarchy/documents/' + docId, { method: 'DELETE' }); selectKB(currentKBId); showToast('已删除'); } catch (e) { showToast('删除失败：' + e.message); }
}
```

## 4. 验收标准
- [ ] renderKnowledge() 不再显示"建设中"
- [ ] 调用 /kb API 显示知识库列表
- [ ] 三层树形导航可点击
- [ ] 文档列表可加载
- [ ] 搜索框可用
- [ ] CSS 变量 0 硬编码色值

## 5. 禁止事项
- 禁止修改其他渲染函数
- 禁止修改 api() 函数
- 禁止修改侧栏导航
