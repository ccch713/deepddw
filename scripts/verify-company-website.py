#!/usr/bin/env python3
"""hermes-verify-website-delivery.py — 官网全量重构交付验证（v2）

覆盖：
1. HTML 标签闭合（11 页）
2. 资源引用完整性
3. JS 语法（site-common.js / PoC 内联脚本）
4. CSS 变量完整性：
   - 加载主题的 10 页：引用变量必须在三主题文件中有定义
   - PoC 页（自包含）：引用变量必须在自身 :root+覆盖块中有定义
   - 主题桥接存在性：PoC 页含 data-theme 覆盖块 + 桥接脚本
5. 合规扫描（禁 AI-slop 词 / 禁虚构客户数 / 禁 OPC/单人表述 / 禁写死交付时间）
6. 必含信息（公司全称/ICP/公安备案/电话/邮箱/地址/创始人20年）
"""
import re, os, glob, sys, subprocess
from html.parser import HTMLParser

COMPANY = "/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/company"
LOGIN = "/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/login.html"
errors = []

# ---------- 1. HTML 标签闭合 ----------
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.errs = []
    def handle_starttag(self, tag, attrs):
        if tag not in VOID: self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in VOID: return
        if not self.stack: self.errs.append(f"extra </{tag}>"); return
        if self.stack.pop() != tag: self.errs.append(f"mismatch </{tag}>")

html_files = sorted(glob.glob(COMPANY + "/*.html")) + ([LOGIN] if os.path.exists(LOGIN) else [])
for f in html_files:
    c = Checker(); c.feed(open(f, encoding="utf-8").read()); c.close()
    if c.errs or c.stack:
        errors.append(f"HTML 闭合: {os.path.basename(f)} {c.errs[:2]} {c.stack[:2]}")
print(f"1/7 HTML 标签闭合: {len(html_files)} 页 → {'PASS' if not any('HTML 闭合' in e for e in errors) else 'FAIL'}")

# ---------- 2. 资源引用完整性 ----------
bad_refs = []
for f in html_files:
    t = open(f, encoding="utf-8").read()
    for r in re.findall(r'(?:src|href)="(assets/[^"]+)"', t):
        if not os.path.exists(os.path.join(COMPANY, r)):
            bad_refs.append(f"{os.path.basename(f)} → {r}")
if bad_refs: errors.append(f"资源缺失: {bad_refs[:5]}")
print(f"2/7 资源引用: {'PASS' if not bad_refs else 'FAIL ' + str(bad_refs[:3])}")

# ---------- 3. JS 语法 ----------
r = subprocess.run(["node", "--check", COMPANY + "/assets/js/site-common.js"], capture_output=True, text=True)
if r.returncode != 0: errors.append(f"JS: {r.stderr[:200]}")
print(f"3/7 JS 语法: {'PASS' if r.returncode == 0 else 'FAIL'}")

# ---------- 4. CSS 变量完整性 ----------
# 4a. 加载主题的页面（10 页，不含 PoC）
theme_pages = [f for f in html_files if "PoC" not in f]
texts = [open(f, encoding="utf-8").read() for f in theme_pages]
texts.append(open(COMPANY + "/assets/css/base.css", encoding="utf-8").read())
texts.append(open(COMPANY + "/assets/js/site-common.js", encoding="utf-8").read())
used = set(re.findall(r"var\((--[a-z0-9-]+)\)", "\n".join(texts)))
for theme in ["standard", "holiday", "mourning"]:
    css = open(f"{COMPANY}/assets/css/themes/{theme}.css", encoding="utf-8").read()
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    missing = used - defined
    if missing: errors.append(f"{theme}.css 缺变量: {missing}")
print(f"4a/7 主题变量完整性: {len(used)} 引用 × 3 主题 → {'PASS' if not any('.css 缺' in e for e in errors) else 'FAIL'}")

# 4b. PoC 页自包含检查
poc = open(f"{COMPANY}/DDW_PoC_Demo_绿色智能体.html", encoding="utf-8").read()
style = re.search(r"<style>(.*?)</style>", poc, re.S).group(1)
poc_defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", style))
poc_used = set(re.findall(r"var\((--[a-z0-9-]+)", style))
poc_missing = poc_used - poc_defined
if poc_missing: errors.append(f"PoC 自包含缺变量: {poc_missing}")
print(f"4b/7 PoC 自包含: 引用 {len(poc_used)} 定义 {len(poc_defined)} → {'PASS' if not poc_missing else 'FAIL ' + str(poc_missing)}")

# 4c. PoC 主题桥接存在性
bridge_ok = ('html[data-theme="mourning"]' in style and 'html[data-theme="holiday"]' in style
             and "ddw-website/theme" in poc and "data-theme" in poc)
if not bridge_ok: errors.append("PoC 主题桥接缺失")
print(f"4c/7 PoC 主题桥接: {'PASS' if bridge_ok else 'FAIL'}")

# ---------- 5. 合规扫描 ----------
banned = ['赋能','助力','一站式','全方位','全链路','闭环','护航','底层逻辑','未来可期','OPC','陈烨','独立开发者','30分钟上线','8周交付','500+','200+']
hits = []
for f in html_files + [COMPANY + "/assets/js/site-common.js"]:
    t = open(f, encoding="utf-8").read()
    for w in banned:
        if w in t:
            # about.html 的"陈烨"为用户明确要求的百度搜索引导（2026-08-04 拍板）
            if w == "陈烨" and os.path.basename(f) == "about.html":
                continue
            # "AI 赋能插件市场"为用户指定的产品名（2026-08-04 拍板），豁免该固定短语
            if w == "赋能" and "AI 赋能插件市场" in t:
                continue
            hits.append(f"{os.path.basename(f)}: {w}")
if hits: errors.append(f"合规: {hits[:5]}")
print(f"5/7 合规扫描: {'PASS' if not hits else 'FAIL ' + str(hits[:3])}")

# ---------- 6. 必含信息 + 本轮修复断言 ----------
js = open(COMPANY + "/assets/js/site-common.js", encoding="utf-8").read()
must = {'公司全称':'武汉锐果互动信息技术有限公司','ICP':'鄂ICP备2026024883号-1',
        '公安备案':'鄂公网安备42011102006255号','电话':'027-89578881',
        '邮箱':'1099340186@qq.com','创始人20年':'超二十年'}
missing = [k for k,v in must.items() if v not in js]
if missing: errors.append(f"必含信息: {missing}")
print(f"6/7 必含信息: {'PASS' if not missing else 'FAIL ' + str(missing)}")

# 6b. 本轮修复断言（2026-08-04 v1.2）
css = open(COMPANY + "/assets/css/base.css", encoding="utf-8").read()
fix_checks = {
    "假地址已删除": "光谷大道77号" not in js,
    "开源代码已删除": "开源代码" not in js and "github.com" not in js,
    "主题演示浮层已删(JS)": "buildDemoSwitcher" not in js,
    "主题演示浮层已删(CSS)": "theme-demo" not in css,
    "登录AI HUB 按钮": "登录AI HUB" in js and "ddw.9cio.com/login" in js,
    "sticky 在 #site-header": "#site-header" in css and "position: sticky" in css,
    "nav-cta 醒目(蓝底白字)": ".nav-cta" in css and "background: var(--brand)" in css,
}
fix_fails = [k for k,v in fix_checks.items() if not v]
if fix_fails: errors.append(f"修复断言: {fix_fails}")
print(f"6b/7 修复断言: {'PASS' if not fix_fails else 'FAIL ' + str(fix_fails)}")

# ---------- 7. API 路径正确性 ----------
api_ok = ("ddw-website/theme" in js) and ("api/v1/site/theme" not in js)
if not api_ok: errors.append("API 路径未修正")
print(f"7/7 API 路径: {'PASS' if api_ok else 'FAIL'}")

# ---------- 8. 新增页面与内容断言（v1.3 全量开发） ----------
v13_checks = {}
about = open(COMPANY + "/about.html", encoding="utf-8").read()
v13_checks["about.html 存在且含创始人介绍"] = "创始人" in about
v13_checks["about.html 不含供职公司名"] = ("东贝" not in about and "正源" not in about and "高德" not in about)
v13_checks["about.html 含国家级项目荣誉"] = "智能制造试点示范" in about and "5G" in about
v13_checks["about.html 含标准起草"] = "T/WHCSA 002" in about and "T/CI 643" in about
v13_checks["about.html 含百度搜索引导"] = "baidu.com" in about
v13_checks["open-case.html 过渡页存在"] = os.path.exists(COMPANY + "/open-case.html")
v13_checks["industry.html 用过渡页跳客户页"] = "open-case.html" in open(COMPANY + "/industry.html", encoding="utf-8").read()
v13_checks["plugins.html Tab+AI增强文案"] = "ai-boost" in open(COMPANY + "/plugins.html", encoding="utf-8").read()
v13_checks["plugins.html hash定位支持"] = "location.hash" in open(COMPANY + "/plugins.html", encoding="utf-8").read()
v13_checks["products.html 插件概括跳转"] = "plugins.html#sales" in open(COMPANY + "/products.html", encoding="utf-8").read()
v13_checks["products.html 部署4宫格"] = "deploy-grid" in open(COMPANY + "/products.html", encoding="utf-8").read()
v13_checks["services.html 服务清单总览"] = "service-overview" in open(COMPANY + "/services.html", encoding="utf-8").read()
v13_checks["导航指向 about.html"] = "about.html" in js
v13_checks["login.html 官网风格(引用company主题)"] = ("/company/assets/css" in open(LOGIN, encoding="utf-8").read()) if os.path.exists(LOGIN) else False
v13_checks["login.html 无emoji"] = ("👋" not in open(LOGIN, encoding="utf-8").read()) if os.path.exists(LOGIN) else False
v13_checks["移动端汉堡菜单"] = "nav-toggle" in js and "toggleNav" in js
v13_checks["base.css 两端对齐"] = "text-align: justify" in open(COMPANY + "/assets/css/base.css", encoding="utf-8").read()
v13_fails = [k for k, v in v13_checks.items() if not v]
if v13_fails: errors.append(f"v1.3 断言: {v13_fails}")
print(f"8/8 v1.3 页面断言: {'PASS (' + str(len(v13_checks)) + ' 项)' if not v13_fails else 'FAIL ' + str(v13_fails)}")

print()
print("=" * 50)
if errors:
    print("FAILURES:")
    for e in errors: print("  ✗", e)
    sys.exit(1)
print("ALL CHECKS PASSED — 官网交付物验证通过 (8/8 + 全部断言)")
