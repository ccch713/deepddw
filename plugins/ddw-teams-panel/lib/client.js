window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: (require) => {
var module = { exports: {} };
var exports = module.exports;
Object.defineProperty(exports, "__esModule", { value: true });

// 工具
function gw() { return (typeof window !== "undefined" && window.location && window.location.origin) || "http://127.0.0.1:8600"; }
function api(path, opts) { return fetch(gw() + path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {})).then(function(r){ return r.json(); }); }

// Overlay 容器（无 Vue，纯 DOM）
function makeOverlay(id) {
  var el = document.createElement("div");
  el.id = id;
  el.style.cssText = "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)";
  var card = document.createElement("div");
  card.style.cssText = "background:var(--dsw-alias-bg-base,#1a1a2e);border:1px solid var(--dsw-alias-border-l2,#333);border-radius:12px;padding:32px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5);color:var(--dsw-alias-label-primary,#e8ecf8)";
  el.appendChild(card);
  return { el: el, card: card };
}

// M2 首次弹窗
var MODES = [
  { value: "solo", label: "\u4e00\u4eba\u591a\u8bbe\u5907", desc: "\u4e00\u4e2a\u4eba\u4f7f\u7528\u591a\u53f0\u8bbe\u5907" },
  { value: "family", label: "\u5bb6\u5ead\u591a\u4eba", desc: "\u5bb6\u4eba\u4e4b\u95f4\u5171\u4eab\uff0c\u4e92\u76f8\u53ef\u89c1" },
  { value: "team", label: "\u5c0f\u56e2\u961f\u534f\u4f5c", desc: "\u56e2\u961f\u5171\u4eab + \u5404\u81ea\u7a7a\u95f4" }
];
function showOnboarding() {
  var o = makeOverlay("ddw-onboard-overlay");
  var selected = "solo";
  var title = document.createElement("h2");
  title.style.cssText = "margin:0 0 16px;font-size:18px;font-weight:700";
  title.textContent = "\u9009\u62e9\u4f7f\u7528\u6a21\u5f0f";
  o.card.appendChild(title);
  var sub = document.createElement("p");
  sub.style.cssText = "margin:0 0 20px;font-size:13px;color:var(--dsw-alias-text-disabled)";
  sub.textContent = "\u53ef\u968f\u65f6\u5728\u300c\u8bbe\u7f6e \u2192 \u591a\u7528\u6237\u8bbe\u7f6e\u300d\u4e2d\u5207\u6362";
  o.card.appendChild(sub);
  MODES.forEach(function(m) {
    var lab = document.createElement("label");
    lab.style.cssText = "display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid transparent";
    var inp = document.createElement("input");
    inp.type = "radio"; inp.name = "ddw-mode"; inp.value = m.value;
    inp.style.cssText = "margin-top:2px;accent-color:var(--dsw-alias-brand-primary)";
    inp.onchange = function() { selected = m.value; lab.style.borderColor = "var(--dsw-alias-brand-primary)"; };
    lab.appendChild(inp);
    var txt = document.createElement("div");
    txt.innerHTML = "<div style='font-size:14px;font-weight:600'>" + m.label + "</div><div style='font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px'>" + m.desc + "</div>";
    lab.appendChild(txt);
    o.card.appendChild(lab);
  });
  var btn = document.createElement("button");
  btn.style.cssText = "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px";
  btn.textContent = "\u786e\u8ba4";
  btn.onclick = function() {
    btn.textContent = "\u4fdd\u5b58\u4e2d..."; btn.disabled = true;
    fetch(gw() + "/api/v1/deployment/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: selected }) })
      .then(function(r) { if (r.ok) { localStorage.setItem("deepddw_onboarded", "1"); o.el.remove(); location.reload(); } })
      .catch(function() { btn.textContent = "\u786e\u8ba4"; btn.disabled = false; });
  };
  o.card.appendChild(btn);
  document.body.appendChild(o.el);
}

// M3 设置面板（纯 DOM）
function renderSettingsPanel() {
  var o = makeOverlay("ddw-settings-panel");
  o.el.style.cssText = "position:relative;inset:auto;background:none;max-width:600px;width:100%;margin:0 auto;padding:24px";
  o.card.style.cssText = "background:var(--dsw-alias-bg-base,#1a1a2e);border:1px solid var(--dsw-alias-border-l2,#333);border-radius:12px;padding:24px;color:var(--dsw-alias-label-primary)";
  var title = document.createElement("h2");
  title.style.cssText = "margin:0 0 6px;font-size:18px;font-weight:700";
  title.textContent = "\u591a\u7528\u6237\u8bbe\u7f6e";
  o.card.appendChild(title);
  var desc = document.createElement("p");
  desc.style.cssText = "margin:0 0 20px;font-size:12px;color:var(--dsw-alias-text-disabled)";
  desc.textContent = "\u7ba1\u7406\u591a\u53f0\u8bbe\u5907\u3001\u591a\u540d\u6210\u5458\u7684\u5171\u4eab\u4e0e\u9694\u79bb";
  o.card.appendChild(desc);
  Promise.all([
    api("/api/v1/deployment/mode"),
    api("/api/v1/member/list"),
    api("/api/v1/admin/stats"),
    api("/api/v1/version")
  ]).then(function(r) {
    var mode = (r[0] && r[0].data && r[0].data.mode) || "solo";
    var members = (r[1] && r[1].data && r[1].data.results) || [];
    var stats = (r[2] && r[2].data) || {};
    var ver = (r[3] && r[3].data && r[3].data.version) || "?";
    // 模式
    var modeH = document.createElement("h3");
    modeH.style.cssText = "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)";
    modeH.textContent = "\u90e8\u7f72\u6a21\u5f0f";
    o.card.appendChild(modeH);
    var MODES2 = [{v:"solo",l:"\u4e00\u4eba\u591a\u8bbe\u5907",d:"\u4e00\u4e2a\u4eba\u4f7f\u7528\u591a\u53f0\u8bbe\u5907"},{v:"family",l:"\u5bb6\u5ead\u591a\u4eba",d:"\u5bb6\u4eba\u4e4b\u95f4\u5171\u4eab\uff0c\u4e92\u76f8\u53ef\u89c1"},{v:"team",l:"\u5c0f\u56e2\u961f\u534f\u4f5c",d:"\u56e2\u961f\u5171\u4eab + \u5404\u81ea\u7a7a\u95f4"}];
    MODES2.forEach(function(m) {
      var lab = document.createElement("label");
      lab.style.cssText = "display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;border:2px solid " + (mode===m.v?"var(--dsw-alias-brand-primary)":"transparent");
      lab.innerHTML = "<input type='radio' name='ddw-mode-s' " + (mode===m.v?"checked":"") + " style='margin-top:2px;accent-color:var(--dsw-alias-brand-primary)'><div><div style='font-size:14px;font-weight:600'>" + m.l + "</div><div style='font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px'>" + m.d + "</div></div>";
      lab.onclick = function() { fetch(gw()+"/api/v1/deployment/mode",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:m.v})}).then(function(r){if(r.ok){localStorage.setItem("deepddw_onboarded","1");location.reload();}}); };
      o.card.appendChild(lab);
    });
    // 成员
    var memH = document.createElement("h3");
    memH.style.cssText = "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)";
    memH.textContent = "\u6210\u5458";
    o.card.appendChild(memH);
    var inputRow = document.createElement("div");
    inputRow.style.cssText = "display:flex;gap:8px;margin-bottom:10px";
    var inp = document.createElement("input");
    inp.placeholder = "\u8f93\u5165\u6210\u5458\u540d\u79f0";
    inp.style.cssText = "flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);font-size:13px";
    var addBtn = document.createElement("button");
    addBtn.textContent = "+";
    addBtn.style.cssText = "padding:8px 16px;border:none;border-radius:6px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:13px;cursor:pointer";
    addBtn.onclick = function() {
      if (!inp.value.trim()) return;
      fetch(gw()+"/api/v1/member/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({display_name:inp.value.trim()})}).then(function(){inp.value="";o.el.remove();renderSettingsPanel();});
    };
    inp.onkeydown = function(e) { if(e.key==="Enter") addBtn.click(); };
    inputRow.appendChild(inp); inputRow.appendChild(addBtn);
    o.card.appendChild(inputRow);
    if (members.length === 0) {
      var empty = document.createElement("div");
      empty.style.cssText = "font-size:12px;color:var(--dsw-alias-text-disabled);padding:8px 0";
      empty.textContent = "\u6682\u65e0\u6210\u5458\uff0c\u70b9\u51fb + \u6dfb\u52a0";
      o.card.appendChild(empty);
    } else {
      members.forEach(function(m) {
        var row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;background:var(--dsw-alias-bg-layer-2);margin-bottom:4px;font-size:13px";
        row.innerHTML = "<span style='color:var(--dsw-alias-text-disabled)'>" + (m.revoked ? "\u26aa" : "\ud83d\udfe2") + "</span><span style='flex:1'>" + (m.display_name||"") + "</span>";
        var rmBtn = document.createElement("button");
        rmBtn.textContent = "\u79fb\u9664";
        rmBtn.style.cssText = "padding:4px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:4px;background:transparent;color:var(--dsw-alias-text-disabled);font-size:11px;cursor:pointer";
        rmBtn.onclick = function() { fetch(gw()+"/api/v1/member/revoke",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({member_id:m.member_id})}).then(function(){o.el.remove();renderSettingsPanel();}); };
        row.appendChild(rmBtn);
        o.card.appendChild(row);
      });
    }
    // 系统信息
    var sysH = document.createElement("h3");
    sysH.style.cssText = "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)";
    sysH.textContent = "\u7cfb\u7edf\u4fe1\u606f";
    o.card.appendChild(sysH);
    var sysBody = document.createElement("div");
    sysBody.style.cssText = "font-size:12px;color:var(--dsw-alias-text-disabled);line-height:1.8";
    sysBody.innerHTML = "deepDDW v" + ver + " &middot; github.com/ccch713/deepddw &middot; MIT License";
    o.card.appendChild(sysBody);
  }).catch(function(e) { o.card.innerHTML = "<p style='color:red'>\u52a0\u8f7d\u5931\u8d25: " + e.message + "</p>"; });
  return o.el;
}

// ══════ 主入口 ══════
exports.inject = ["slots", "locale"];
exports.apply = function(ctx) {
  // M2 首次弹窗
  if (!localStorage.getItem("deepddw_onboarded")) {
    api("/api/v1/deployment/mode").then(function(d) {
      if (d && d.data && d.data.configured) {
        localStorage.setItem("deepddw_onboarded", "1");
      } else {
        showOnboarding();
      }
    }).catch(function() {});
  }
  // M3 设置面板
  ctx.slots.inject("settings.section", function() {
    return ctx.slots.register({
      name: "settings.section",
      id: "ddw-multiuser-settings",
      order: 100,
      label: function() { return "\u591a\u7528\u6237\u8bbe\u7f6e"; }
    }, function() { return renderSettingsPanel(); });
  });
  // M4 成员识别
  var deviceId = localStorage.getItem("deepddw_device_id") || ("dev-" + Date.now().toString(36));
  localStorage.setItem("deepddw_device_id", deviceId);
  if (!localStorage.getItem("deepddw_member_id")) {
    api("/api/v1/member/list").then(function(d) {
      var mlist = (d && d.data && d.data.results) || [];
      if (mlist.length > 0) {
        var overlay = makeOverlay("ddw-identify-overlay");
        var title2 = document.createElement("h2");
        title2.style.cssText = "margin:0 0 16px;font-size:17px;font-weight:700";
        title2.textContent = "\u4f60\u662f\u8c01\uff1f";
        overlay.card.appendChild(title2);
        var selectedId = null;
        mlist.forEach(function(m) {
          var lab = document.createElement("label");
          lab.style.cssText = "display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid transparent";
          lab.innerHTML = "<input type='radio' name='ddw-who' style='margin-top:2px;accent-color:var(--dsw-alias-brand-primary)'><span style='font-size:14px'>" + (m.display_name||"") + "</span>";
          lab.onclick = function() { selectedId = m.member_id; lab.style.borderColor = "var(--dsw-alias-brand-primary)"; };
          overlay.card.appendChild(lab);
        });
        var btn2 = document.createElement("button");
        btn2.style.cssText = "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px";
        btn2.textContent = "\u786e\u8ba4\u8eab\u4efd";
        btn2.onclick = function() {
          if (!selectedId) return;
          fetch(gw()+"/api/v1/device/identify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:deviceId,member_id:selectedId})})
            .then(function(){localStorage.setItem("deepddw_member_id",selectedId);overlay.el.remove();location.reload();});
        };
        overlay.card.appendChild(btn2);
        document.body.appendChild(overlay.el);
      }
    }).catch(function() {});
  }
};

exports.default = exports;
    return module.exports;
  }
});
