#!/usr/bin/env python3
"""gen-q1-demos.py — 生成 Q1 业务域布局 4 个 demo（A 分组折叠 / B 侧栏导航 / C Tab 切换 / D 索引速查）
数据与官网规范共享：base.css + site-common.js + 主题系统；未来加业务域只需在 DATA_JS 追加。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEMOS_DIR = os.path.join(HERE, "..", "frontend", "company", "demos")
os.makedirs(DEMOS_DIR, exist_ok=True)

DATA_JS = """
var DOMAINS = [
  { id:'sales', name:'销售 CRM', icon:'销', desc:'线索、商机到回款的全流程销售管理', count:'21 个插件', tiers:[
    {tier:'最小', n:'3 个', combo:'线索认领 + 商机管理 + 销售看板', scene:'销售团队刚起步，先把线索和商机管起来，业绩一目了然'},
    {tier:'中等', n:'12 个', combo:'最小组合 + 销售助手 + 销售笔记 + 报价 + 合同 + 电子签章 + 订单 + 产品目录 + 客户档案', scene:'销售流程完整跑通：从跟进话术、语音记笔记到报价签约、下单交付'},
    {tier:'全量', n:'26 个', combo:'中等组合 + 发票 + 回款 + 对账 + 应收账款 + 经销商体系 + 续费 + 投标 + KPI 考核等', scene:'销售、渠道、财务全流程数字化，管理层实时掌握经营全貌'}]},
  { id:'quality', name:'质量管理', icon:'质', desc:'质量文档、CAPA、SPC 与法规合规管理', count:'5 个插件', tiers:[
    {tier:'最小', n:'2 个', combo:'质量助手 + 质量知识库', scene:'先让 AI 帮质量工程师写报告、查法规：输入问题描述，自动生成 8D/CAPA/偏差说明初稿，从"从零写"变成"审稿改稿"'},
    {tier:'中等', n:'4 个', combo:'最小组合 + CAPA 工作流 + SPC 统计', scene:'异常从发现到关闭全流程留痕，检测数据自动算 Cp/Cpk、控制图判异，法规和客户审核时有据可查'},
    {tier:'全量', n:'5 个 + 知识库', combo:'中等组合 + 法规证据链 + 企业知识库（法规/模板/案例蒸馏入库）', scene:'多辖区法规证据链管理，历史案例结构化沉淀，越用越准——把质量知识变成企业 AI 资产'}]},
  { id:'training', name:'培训人才', icon:'训', desc:'培训、考核、资质档案一体化', count:'5 个插件', tiers:[
    {tier:'最小', n:'2 个', combo:'培训管理 + 员工花名册', scene:'课程发布、学习、考核、证书全流程，员工档案建档'},
    {tier:'中等', n:'3 个', combo:'最小组合 + 岗位资质', scene:'关键岗位持证上岗校验，培训记录与资质档案联动'},
    {tier:'全量', n:'5 个', combo:'中等组合 + 语音转写 + 录音采集', scene:'面授/线上课程自动转写为知识文档，沉淀企业内部培训资产'}]},
  { id:'finance', name:'财务运营', icon:'财', desc:'经营数据汇总与成本测算', count:'3 个插件', tiers:[
    {tier:'最小', n:'1 个', combo:'财务看板', scene:'应收应付、现金流一目了然'},
    {tier:'中等', n:'2 个', combo:'财务看板 + 运营报告', scene:'经营数据自动汇总，月度报告不再手写'},
    {tier:'全量', n:'3 个', combo:'中等组合 + 成本知识', scene:'报价与成本测算参考，支撑销售端快速出价'}]},
  { id:'service', name:'客服协作', icon:'客', desc:'工单流转与智能应答', count:'1 个插件', tiers:[
    {tier:'最小', n:'1 个', combo:'工单系统', scene:'客户问题统一入口，支持流转与跟踪'},
    {tier:'中等', n:'1 个 + 知识库', combo:'工单系统 + 知识库检索', scene:'客服在钉钉/飞书/企微里直接检索答案，快速响应'},
    {tier:'全量', n:'定制', combo:'工单系统 + 智能客服自动应答 + 人工转接', scene:'常见问题 AI 自动答，复杂问题转人工，7×24 小时在线'}]},
  { id:'esg', name:'ESG 合规', icon:'ES', desc:'出口企业 ESG 预评估与持续合规', count:'4 个插件', tiers:[
    {tier:'最小', n:'1 个', combo:'ESG 预评估（单次自评）', scene:'先做一次 AI 预评估，快速定位与目标评级之间的差距'},
    {tier:'中等', n:'2 个', combo:'ESG 预评估 + 标准对标', scene:'对照 EcoVadis/ISO/GRI/CSRD 持续跟踪合规状态'},
    {tier:'全量', n:'4 个', combo:'预评估 + 对标 + 报告生成 + 持续监控', scene:'出口企业 ESG 全流程管理：从差距分析到合规报告到评级提升'}]}
];

var INDUSTRY_DOMAINS = [
  { id:'food', name:'食品质量', icon:'食', desc:'应对多法规体系叠加、客户审厂与监管检查', combo:'质量管理插件群 + 食品法规知识库（食品安全法/GB/HACCP/ISO 22000/EU Novel Food/FDA）', scene:'把质量文档、CAPA、追溯、供应商合规集中管起来'},
  { id:'clinic', name:'口腔诊所', icon:'口', desc:'预约、病历到收费一个 App 搞定', combo:'病历管理 + 预约 + 收费', scene:'钉钉消息驱动，从预约到病历到收费一站式'},
  { id:'knowledge', name:'知识管理', icon:'知', desc:'历史文档蒸馏入库，AI 复用生成', combo:'企业知识库 + 层级检索 + 文档生成', scene:'历史文档（PDF/Word/Excel）蒸馏入库，AI 生成后续文档，多方案、多标书复用'}
];
"""

LAYOUT_NAMES = {"A": "分组折叠", "B": "侧栏导航", "C": "Tab 切换", "D": "索引速查"}

def hero_open(active_letter, desc):
    links_parts = []
    for l in "ABCD":
        cls = ' class="active"' if l == active_letter else ""
        links_parts.append('<a href="q1-layout-' + l.lower() + '.html"' + cls + '>' + l + '. ' + LAYOUT_NAMES[l] + '</a>')
    return ('<div class="layout-hero">\n  <div class="container">\n'
            '    <div class="tag">布局方案 ' + active_letter + ' · ' + LAYOUT_NAMES[active_letter] + '</div>\n'
            '    <h1>业务AI能力插件群</h1>\n'
            '    <p>' + desc + '</p>\n'
            '    <div class="layout-switcher">' + "".join(links_parts) + '</div>\n  </div>\n</div>')

def build_demo(title, hero_html, body_html, extra_js, label):
    head = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<meta name="description" content="DDW 业务AI能力插件 — 业务域布局方案 __LABEL__。最小/中等/全量三档组合，丰俭由人。">
<link rel="icon" href="../assets/logo/logo-favicon.png">
<link rel="stylesheet" href="../assets/css/base.css">
<script>window.SITE_BASE = '../';</script>
<script src="../assets/js/site-common.js"></script>
<style>
  .layout-hero { padding: 52px 0 38px; }
  .layout-hero h1 { font-size: 32px; margin: 10px 0 12px; }
  .layout-hero p { max-width: 760px; color: var(--text-secondary); }
  .layout-switcher { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 20px; }
  .layout-switcher a { padding: 8px 16px; border: 1px solid var(--border); border-radius: 6px; font-size: 13.5px; color: var(--text-secondary); text-decoration: none; }
  .layout-switcher a.active { background: var(--brand); border-color: var(--brand); color: #fff; }
  .note-bar { margin: 24px 0 0; padding: 12px 16px; background: var(--bg-elevated); border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0; font-size: 13.5px; color: var(--text-secondary); }
  .tier-tag { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }
  .tier-min { background: rgba(0,179,164,.12); color: var(--accent); }
  .tier-mid { background: rgba(26,107,255,.10); color: var(--brand); }
  .tier-full { background: rgba(249,115,22,.12); color: var(--accent-orange); }
</style>
</head>
<body>
<div id="site-header"></div>
__HERO__
__BODY__
<div id="site-footer"></div>
<script>
__DATA__
__EXTRA_JS__
</script>
</body>
</html>"""
    html = head.replace("__TITLE__", title).replace("__LABEL__", label)
    html = html.replace("__HERO__", hero_html).replace("__BODY__", body_html)
    html = html.replace("__DATA__", DATA_JS).replace("__EXTRA_JS__", extra_js)
    return html


# ============ 布局 A：分组折叠 ============
heroA = hero_open("A", "每个业务板块一张卡片：默认收起，点击展开三档参考组合。业务域再多也不怕——首屏永远只有卡片清单，未来 50+ 业务域依然清爽。")
bodyA = """
<section class="section" style="padding-top:8px;">
  <div class="container">
    <div class="section-head" style="align-items:flex-start;">
      <div>
        <div class="tag">PLUGIN GROUPS</div>
        <h2 style="margin:8px 0 10px;">按业务板块，选你的插件组合</h2>
        <p>插件装多装少，完全由贵司的实际业务场景决定：业务场景覆盖范围广，插件群规模就大；业务场景单一，或先以最小业务范围做 AI 落地测试，选最小插件群即可。插件授权费用也随之有多有少——不用的不装，不为用不上的功能付费。</p>
      </div>
      <button class="btn btn-outline" onclick="toggleAll()" id="toggle-all" style="white-space:nowrap;">全部展开</button>
    </div>
    <div id="domain-list"></div>
    <div class="note-bar">当前已上线 <b>6 大业务域 · 41 个插件</b>。新增业务域只需在数据文件追加一条记录，页面自动出现，无需改代码。</div>
  </div>
</section>"""
jsA = """
(function () {
  function tierHtml(t) {
    var cls = t.tier === '最小' ? 'tier-min' : (t.tier === '中等' ? 'tier-mid' : 'tier-full');
    return '<div class="tier-row" style="border-bottom:1px solid var(--border);padding:14px 0;">' +
      '<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">' +
      '<span class="tier-tag ' + cls + '">' + t.tier + ' · ' + t.n + '</span>' +
      '<span style="font-weight:600;">' + t.combo + '</span></div>' +
      '<div style="color:var(--text-secondary);font-size:14px;margin-top:6px;">' + t.scene + '</div></div>';
  }
  function card(d) {
    return '<div class="card" style="margin-bottom:16px;overflow:hidden;">' +
      '<div class="domain-head" onclick="toggleCard(this)" style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;cursor:pointer;">' +
      '<div style="display:flex;align-items:center;gap:14px;">' +
      '<span style="width:40px;height:40px;border-radius:10px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;">' + d.icon + '</span>' +
      '<div><div style="font-size:17px;font-weight:700;">' + d.name + '<span style="color:var(--text-muted);font-weight:400;font-size:13px;margin-left:10px;">' + d.count + '</span></div>' +
      '<div style="font-size:13.5px;color:var(--text-secondary);margin-top:2px;">' + d.desc + '</div></div></div>' +
      '<span class="expand-arrow" style="color:var(--text-muted);font-size:18px;transition:transform .25s;">&#9662;</span></div>' +
      '<div class="tier-body" style="display:none;padding:0 22px 18px;">' +
      d.tiers.map(tierHtml).join('') +
      '<div style="font-size:13px;color:var(--text-muted);margin-top:10px;">可跨板块自由搭配，也可按需定制。</div></div></div>';
  }
  document.getElementById('domain-list').innerHTML = DOMAINS.map(card).join('') +
    '<h3 style="margin:28px 0 14px;">行业垂直方案</h3>' + INDUSTRY_DOMAINS.map(function(d){
    return '<div class="card" style="margin-bottom:12px;padding:16px 22px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;">' +
      '<div style="flex:1;min-width:220px;"><div style="font-weight:700;">' + d.name + '</div><div style="font-size:13.5px;color:var(--text-secondary);margin-top:2px;">' + d.desc + '</div></div>' +
      '<div style="flex:2;min-width:240px;font-size:13.5px;color:var(--text-secondary);">' + d.combo + '</div>' +
      '<span class="tier-tag tier-full" style="white-space:nowrap;">查看方案 &#8594;</span></div>';
  }).join('');
  window.toggleCard = function (el) {
    var body = el.nextElementSibling;
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    el.querySelector('.expand-arrow').style.transform = open ? '' : 'rotate(180deg)';
  };
  window.toggleAll = function () {
    var all = document.querySelectorAll('.tier-body');
    var first = all[0].style.display !== 'block';
    for (var i = 0; i < all.length; i++) all[i].style.display = first ? 'block' : 'none';
    var arrows = document.querySelectorAll('.expand-arrow');
    for (var j = 0; j < arrows.length; j++) arrows[j].style.transform = first ? 'rotate(180deg)' : '';
    document.getElementById('toggle-all').textContent = first ? '全部收起' : '全部展开';
  };
})();
"""

# ============ 布局 B：侧栏导航 + 右侧详情 ============
heroB = hero_open("B", "左侧业务域目录，右侧展示选中域的三档组合。目录区固定，业务域再多也只是一列清单，适合客户快速逐个浏览。")
bodyB = """
<section class="section" style="padding-top:8px;">
  <div class="container">
    <div class="tag">PLUGIN GROUPS</div>
    <h2 style="margin:8px 0 16px;">按业务板块，选你的插件组合</h2>
    <div style="display:grid;grid-template-columns:260px 1fr;gap:24px;align-items:start;" class="q1-b-grid">
      <aside class="card" style="padding:14px;position:sticky;top:84px;" id="domain-nav"></aside>
      <div class="card" style="padding:24px;" id="domain-detail"></div>
    </div>
    <div class="note-bar">左侧目录固定，未来 50+ 业务域时目录自动增长、可滚动，详情区始终只显示当前选中域。</div>
  </div>
</section>"""
jsB = """
(function () {
  var ALL = DOMAINS.concat(INDUSTRY_DOMAINS.map(function (d) {
    return { id: d.id, name: d.name, icon: d.icon, desc: d.desc, count: '行业方案', tiers: [
      { tier: '组合', n: '1 套', combo: d.combo, scene: d.scene } ] };
  }));
  var nav = document.getElementById('domain-nav');
  var detail = document.getElementById('domain-detail');
  function renderNav() {
    var html = '<div style="font-size:12px;color:var(--text-muted);padding:6px 10px 10px;">业务域目录</div>';
    ALL.forEach(function (d, i) {
      html += '<div class="q1-nav-item" data-id="' + d.id + '" onclick="showDomain(' + i + ')" style="padding:10px 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:10px;font-size:14px;">' +
        '<span style="width:28px;height:28px;border-radius:7px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;">' + d.icon + '</span>' +
        d.name + '</div>';
    });
    nav.innerHTML = html;
  }
  function renderDetail(idx) {
    var d = ALL[idx];
    var clsMap = { '最小': 'tier-min', '中等': 'tier-mid', '全量': 'tier-full', '组合': 'tier-full' };
    var rows = d.tiers.map(function (t) {
      return '<div style="padding:16px 0;border-bottom:1px solid var(--border);">' +
        '<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">' +
        '<span class="tier-tag ' + (clsMap[t.tier] || 'tier-mid') + '">' + t.tier + ' · ' + t.n + '</span>' +
        '<span style="font-weight:600;">' + t.combo + '</span></div>' +
        '<div style="color:var(--text-secondary);font-size:14px;margin-top:6px;">' + t.scene + '</div></div>';
    }).join('');
    detail.innerHTML = '<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">' +
      '<span style="width:44px;height:44px;border-radius:11px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;">' + d.icon + '</span>' +
      '<div><div style="font-size:20px;font-weight:700;">' + d.name + ' <span style="font-size:13px;color:var(--text-muted);font-weight:400;">' + d.count + '</span></div>' +
      '<div style="font-size:13.5px;color:var(--text-secondary);">' + d.desc + '</div></div></div>' +
      rows +
      '<div style="font-size:13px;color:var(--text-muted);margin-top:12px;">可跨板块自由搭配，也可按需定制。</div>';
    var items = nav.querySelectorAll('.q1-nav-item');
    for (var i = 0; i < items.length; i++) {
      items[i].style.background = (i === idx) ? 'var(--bg-elevated)' : '';
      items[i].style.color = (i === idx) ? 'var(--brand)' : '';
      items[i].style.fontWeight = (i === idx) ? '700' : '';
    }
  }
  window.showDomain = function (i) { renderDetail(i); };
  renderNav();
  renderDetail(0);
})();
"""

# ============ 布局 C：Tab 切换 ============
heroC = hero_open("C", "顶部 Tab 一个业务域一页内容。适合业务域数量适中（10 个以内）时使用，点击 Tab 切换域的三档组合。")
bodyC = """
<section class="section" style="padding-top:8px;">
  <div class="container">
    <div class="tag">PLUGIN GROUPS</div>
    <h2 style="margin:8px 0 16px;">按业务板块，选你的插件组合</h2>
    <div id="tab-bar" style="display:flex;gap:6px;flex-wrap:wrap;border-bottom:2px solid var(--border);margin-bottom:20px;"></div>
    <div class="card" style="padding:24px;" id="tab-detail"></div>
    <div class="note-bar">Tab 自动换行，业务域增加时 Tab 行变长；超过一屏后 Tab 行可横向滚动（移动端优先推荐此方案）。</div>
  </div>
</section>"""
jsC = """
(function () {
  var ALL = DOMAINS.concat(INDUSTRY_DOMAINS.map(function (d) {
    return { id: d.id, name: d.name, icon: d.icon, desc: d.desc, count: '行业方案', tiers: [
      { tier: '组合', n: '1 套', combo: d.combo, scene: d.scene } ] };
  }));
  var bar = document.getElementById('tab-bar');
  var detail = document.getElementById('tab-detail');
  function renderTabs() {
    bar.innerHTML = ALL.map(function (d, i) {
      return '<button onclick="showTab(' + i + ')" data-i="' + i + '" style="padding:10px 18px;border:none;background:transparent;cursor:pointer;font-size:14.5px;color:var(--text-secondary);border-bottom:2px solid transparent;margin-bottom:-2px;">' + d.name + '</button>';
    }).join('');
  }
  function renderDetail(idx) {
    var d = ALL[idx];
    var clsMap = { '最小': 'tier-min', '中等': 'tier-mid', '全量': 'tier-full', '组合': 'tier-full' };
    var rows = d.tiers.map(function (t) {
      return '<div style="padding:16px 0;border-bottom:1px solid var(--border);">' +
        '<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">' +
        '<span class="tier-tag ' + (clsMap[t.tier] || 'tier-mid') + '">' + t.tier + ' · ' + t.n + '</span>' +
        '<span style="font-weight:600;">' + t.combo + '</span></div>' +
        '<div style="color:var(--text-secondary);font-size:14px;margin-top:6px;">' + t.scene + '</div></div>';
    }).join('');
    detail.innerHTML = '<div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">' +
      '<span style="width:44px;height:44px;border-radius:11px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;">' + d.icon + '</span>' +
      '<div><div style="font-size:20px;font-weight:700;">' + d.name + ' <span style="font-size:13px;color:var(--text-muted);font-weight:400;">' + d.count + '</span></div>' +
      '<div style="font-size:13.5px;color:var(--text-secondary);">' + d.desc + '</div></div></div>' +
      rows +
      '<div style="font-size:13px;color:var(--text-muted);margin-top:12px;">可跨板块自由搭配，也可按需定制。</div>';
    var tabs = bar.querySelectorAll('button');
    for (var i = 0; i < tabs.length; i++) {
      var active = (i === idx);
      tabs[i].style.color = active ? 'var(--brand)' : 'var(--text-secondary)';
      tabs[i].style.borderBottom = active ? '2px solid var(--brand)' : '2px solid transparent';
      tabs[i].style.fontWeight = active ? '700' : '';
    }
  }
  window.showTab = function (i) { renderDetail(i); };
  renderTabs();
  renderDetail(0);
})();
"""

# ============ 布局 D：索引速查 ============
heroD = hero_open("D", "首屏一张业务域速查索引墙，全部业务域一眼可见、按分类编号，点击直达下方对应详情。业务域再多也只是索引墙变长，客户找得准。")
bodyD = """
<section class="section" style="padding-top:8px;">
  <div class="container">
    <div class="tag">PLUGIN GROUPS</div>
    <h2 style="margin:8px 0 6px;">业务域速查</h2>
    <p style="color:var(--text-secondary);font-size:15px;margin-bottom:22px;">6 大业务板块 + 行业垂直方案，点击任意卡片直达对应组合详情。</p>
    <div id="index-wall" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;"></div>
    <div id="detail-sections" style="margin-top:36px;"></div>
    <div class="note-bar">索引墙自动按数据渲染，未来 50+ 业务域时按分类编号排列，客户一屏浏览全部域。</div>
  </div>
</section>"""
jsD = """
(function () {
  var ALL = DOMAINS.concat(INDUSTRY_DOMAINS.map(function (d) {
    return { id: d.id, name: d.name, icon: d.icon, desc: d.desc, count: '行业方案', tiers: [
      { tier: '组合', n: '1 套', combo: d.combo, scene: d.scene } ] };
  }));
  var wall = document.getElementById('index-wall');
  var sections = document.getElementById('detail-sections');
  function renderWall() {
    wall.innerHTML = ALL.map(function (d, i) {
      return '<a href="#q1-dom-' + i + '" style="text-decoration:none;">' +
        '<div class="card" style="padding:16px;height:100%;">' +
        '<div style="display:flex;align-items:center;gap:10px;">' +
        '<span style="width:34px;height:34px;border-radius:8px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;">' + d.icon + '</span>' +
        '<div><div style="font-weight:700;font-size:15px;">' + d.name + '</div>' +
        '<div style="font-size:12px;color:var(--text-muted);">' + d.count + '</div></div></div>' +
        '<div style="font-size:13px;color:var(--text-secondary);margin-top:10px;line-height:1.6;">' + d.desc + '</div></div></a>';
    }).join('');
  }
  function renderSections() {
    var clsMap = { '最小': 'tier-min', '中等': 'tier-mid', '全量': 'tier-full', '组合': 'tier-full' };
    sections.innerHTML = ALL.map(function (d, i) {
      var rows = d.tiers.map(function (t) {
        return '<div style="padding:14px 0;border-bottom:1px solid var(--border);">' +
          '<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">' +
          '<span class="tier-tag ' + (clsMap[t.tier] || 'tier-mid') + '">' + t.tier + ' · ' + t.n + '</span>' +
          '<span style="font-weight:600;">' + t.combo + '</span></div>' +
          '<div style="color:var(--text-secondary);font-size:14px;margin-top:6px;">' + t.scene + '</div></div>';
      }).join('');
      return '<div class="card" style="padding:24px;margin-bottom:20px;" id="q1-dom-' + i + '">' +
        '<div style="display:flex;align-items:center;gap:14px;margin-bottom:6px;">' +
        '<span style="width:44px;height:44px;border-radius:11px;background:var(--bg-elevated);color:var(--brand);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;">' + d.icon + '</span>' +
        '<div><div style="font-size:20px;font-weight:700;">' + d.name + ' <span style="font-size:13px;color:var(--text-muted);font-weight:400;">' + d.count + '</span></div>' +
        '<div style="font-size:13.5px;color:var(--text-secondary);">' + d.desc + '</div></div></div>' +
        rows + '</div>';
    }).join('');
  }
  renderWall();
  renderSections();
})();
"""

demos = {
    "q1-layout-a.html": ("布局方案 A · 分组折叠 — 业务AI能力插件（Demo）", heroA, bodyA, jsA, "A"),
    "q1-layout-b.html": ("布局方案 B · 侧栏导航 — 业务AI能力插件（Demo）", heroB, bodyB, jsB, "B"),
    "q1-layout-c.html": ("布局方案 C · Tab 切换 — 业务AI能力插件（Demo）", heroC, bodyC, jsC, "C"),
    "q1-layout-d.html": ("布局方案 D · 索引速查 — 业务AI能力插件（Demo）", heroD, bodyD, jsD, "D"),
}
for fname, (title, hero, body, js, label) in demos.items():
    html = build_demo(title, hero, body, js, label)
    with open(os.path.join(DEMOS_DIR, fname), "w", encoding="utf-8") as f:
        f.write(html)
    print("生成:", fname, len(html), "字符")
print("全部 demo 生成完毕 →", DEMOS_DIR)
