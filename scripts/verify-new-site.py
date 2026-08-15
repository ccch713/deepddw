#!/usr/bin/env python3
"""官网新中式改版验收脚本（mimo 开发完成后运行）"""
import re, sys, glob, os

BASE = "/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend"
ok = True

def check(name, cond, detail=""):
    global ok
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond: ok = False

# 1. 禁词扫描（company 站点 + 共享 js/css）
BAD = [r'开源', r'open.?source', r'\bRAG\b', r'Embedding', r'向量', r'LLM', r'大模型',
       r'FastAPI', r'Python', r'MySQL', r'SQLite', r'哀悼', r'一站式', r'未来可期',
       r'DeepSeek', r'MiMo', r'通义千问', r'ddw-[a-z]+-[a-z]+']
files = glob.glob(f"{BASE}/company/*.html") + glob.glob(f"{BASE}/company/assets/js/*.js") + glob.glob(f"{BASE}/company/assets/css/*.css")
hits = []
for f in files:
    try:
        t = open(f, encoding="utf-8").read()
    except Exception:
        continue
    for pat in BAD:
        for m in re.finditer(pat, t, re.I):
            line = t[:m.start()].count("\n") + 1
            hits.append(f"{os.path.basename(f)}:{line} {pat}")
# 豁免：AI 赋能插件市场（用户指定名）
hits = [h for h in hits if not ("plugins" in h and "AI 赋能插件市场" in open(files[0], encoding="utf-8").read())]
check("禁词扫描 = 0", len(hits) == 0, "; ".join(hits[:5]))

# 2. logo/favicon 应用
html_all = ""
for f in glob.glob(f"{BASE}/company/*.html"):
    html_all += open(f, encoding="utf-8").read()
js_all = open(f"{BASE}/company/assets/js/site-common.js", encoding="utf-8").read()
check("企业章 logo 出现", (js_all.count("corp-seal") >= 2), "导航+页脚应在 site-common.js 各 1 处")
check("favicon 引用", html_all.count("favicon-64") >= 1)
check("三色切换控件 (ddw-palette)", "ddw-palette" in js_all)

# 3. HTML 闭合校验
from html.parser import HTMLParser
VOID = {"meta","link","img","br","hr","input","source","area","base","col","embed","track","wbr","path","circle","rect","line","ellipse","polygon","stop","use"}
class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack = []; self.errs = []
    def handle_starttag(self, tag, attrs):
        if tag not in VOID: self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in VOID: return
        if self.stack and self.stack[-1] == tag: self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag: self.errs.append(f"未闭合 <{self.stack.pop()}>")
            if self.stack: self.stack.pop()
        else: self.errs.append(f"多余 </{tag}>")
for f in sorted(glob.glob(f"{BASE}/company/*.html")):
    p = P()
    try:
        p.feed(open(f, encoding="utf-8").read())
    except Exception as e:
        check(f"HTML 解析 {os.path.basename(f)}", False, str(e)); continue
    errs = p.errs + [f"未闭合 <{t}>" for t in p.stack]
    check(f"HTML 闭合 {os.path.basename(f)}", not errs, "; ".join(errs[:3]))

# 4. 失效页删除
for dead in ["ddw-plugin-marketplace.html", "marketplace.html", "plugin-market.html", "plugin-detail.html", "ddw_homepage.html"]:
    check(f"失效页已删 {dead}", not os.path.exists(f"{BASE}/{dead}"))

# 5. 首页/插件页关键内容
idx = open(f"{BASE}/company/index.html", encoding="utf-8").read()
check("首页新文案", "别让企业为用不上的 AI 买单" in idx)
check("首页数字 67", "67" in idx)
plg = open(f"{BASE}/company/plugins.html", encoding="utf-8").read()
check("插件页数据驱动", "DOMAINS" in plg or "PLUGIN_DATA" in plg)

print("\n" + ("🎉 全部通过" if ok else "⚠️ 有失败项"))
sys.exit(0 if ok else 1)
