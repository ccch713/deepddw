/**
 * deepDDW 多用户设置面板 — React 组件
 * v0.5.0-patch8: 成员3页签(活跃/已吊销/已删除)+在线状态+三列网格+sticky底部+商业版链接+准确内存推荐
 */
window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: function(require) {
    var module = { exports: {} };
    var exports = module.exports;
    var React = require("react");
    var h = React.createElement;
    var BASE = window.location.origin;
    exports.inject = ["slots"];

    var MODES = [
      { value: "solo",   label: "\u4e00\u4eba\u591a\u8bbe\u5907", spec: "\u63a8\u8350 8GB \u5185\u5b58\uff08\u670d\u52a1\u5668 + OS\uff09" },
      { value: "family", label: "\u5bb6\u5ead\u591a\u4eba",   spec: "\u63a8\u8350 16GB \u5185\u5b58\uff085 \u4eba\u4ee5\u4e0b\uff09" },
      { value: "team",   label: "\u5c0f\u56e2\u961f\u534f\u4f5c",  spec: "\u63a8\u8350 32GB+ \u5185\u5b58\uff0820 \u4eba\u4ee5\u5185\uff09" }
    ];

    // ══════ 成员识别（手动输入）══════
    function MemberIdentify(props) {
      var s = React.useState({ name: "", error: "", submitting: false });
      var st = s[0]; var setSt = s[1];
      function submit() {
        var n = (st.name || "").trim();
        if (!n) { setSt({ name: n, error: "\u8bf7\u8f93\u5165\u6210\u5458\u540d\u79f0", submitting: false }); return; }
        setSt({ name: n, error: "", submitting: true });
        fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}).then(function(d) {
          var mlist = ((d && d.data && d.data.results) || []).filter(function(m) { return !m.revoked && !m.deleted; });
          var match = mlist.find(function(m) { return m.display_name === n; });
          if (!match) { setSt({ name: n, error: "\u672a\u627e\u5230\u6210\u5458\uff1a\"" + n + "\"\uff08\u8bf7\u68c0\u67e5\u62fc\u5199\uff09", submitting: false }); return; }
          return fetch(BASE + "/api/v1/device/identify", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: props.deviceId, member_id: match.member_id })
          }).then(function(r) { if (r.ok) { localStorage.setItem("deepddw_member_id", match.member_id); localStorage.setItem("deepddw_workspace", "member:" + match.member_id); location.reload(); } else { setSt({ name: n, error: "\u7ed1\u5b9a\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5", submitting: false }); } });
        }).catch(function(e) { setSt({ name: n, error: "\u7f51\u7edc\u9519\u8bef\uff1a" + e.message, submitting: false }); });
      }
      return h("div", { style: { position: "fixed", inset: 0, zIndex: 99999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.6)" } },
        h("div", { style: { background: "var(--dsw-alias-bg-base)", border: "1px solid var(--dsw-alias-border-l2)", borderRadius: "12px", padding: "32px", maxWidth: "400px", width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,.5)" } },
          h("h2", { style: { margin: "0 0 8px", fontSize: "17px", fontWeight: 700, color: "var(--dsw-alias-label-primary)" } }, "\u8bf7\u8f93\u5165\u4f60\u7684\u8eab\u4efd"),
          h("p", { style: { margin: "0 0 16px", fontSize: "12px", color: "var(--dsw-alias-text-disabled)" } }, "\u8f93\u5165\u4f60\u7684\u6210\u5458\u540d\u79f0\uff0c\u672c\u8bbe\u5907\u5c06\u7ed1\u5b9a\u5230\u8be5\u6210\u5458\u3002\u4e0d\u540c\u6210\u5458\u7684\u8bb0\u5fc6\u4f53\u548c\u77e5\u8bc6\u5e93\u662f\u9694\u79bb\u7684\u3002"),
          h("input", { value: st.name, onChange: function(e) { setSt({ name: e.target.value, error: "", submitting: false }); }, onKeyDown: function(e) { if (e.key === "Enter") submit(); }, placeholder: "\u4f8b\u5982\uff1a\u5f20\u4e09", autoFocus: true, style: { width: "100%", padding: "12px", borderRadius: "8px", border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-layer-2)", color: "var(--dsw-alias-label-primary)", fontSize: "15px", outline: "none" } }),
          st.error ? h("p", { style: { color: "#e74c3c", fontSize: "12px", marginTop: "8px" } }, st.error) : null,
          h("button", { onClick: submit, disabled: st.submitting, style: { width: "100%", padding: "12px", border: "none", borderRadius: "8px", background: "var(--dsw-alias-brand-primary)", color: "var(--dsw-alias-bg-base)", fontWeight: 600, fontSize: "14px", cursor: "pointer", marginTop: "16px", opacity: st.submitting ? 0.5 : 1 } }, st.submitting ? "\u7ed1\u5b9a\u4e2d..." : "\u786e\u8ba4\u8eab\u4efd")
        )
      );
    }

    // ══════ 设置面板（三页签 + 三列成员 + 在线状态 + sticky底部）══════
    function SettingsPanel() {
      var s = React.useState({ mode: "solo", members: [], stats: {}, devices: [], onlineIds: new Set(), loading: true, error: "" });
      var data = s[0]; var setData = s[1];
      var tabS = React.useState("active"); var tab = tabS[0]; var setTab = tabS[1];
      var nameS = React.useState(""); var newName = nameS[0]; var setName = nameS[1];
      var selS = React.useState(new Set()); var sel = selS[0]; var setSel = selS[1];

      function refresh() {
        setData({ mode: "solo", members: [], stats: {}, devices: [], onlineIds: new Set(), loading: true, error: "" });
        Promise.all([
          fetch(BASE + "/api/v1/deployment/mode").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/admin/stats").then(function(r){return r.json();}).catch(function(){return {};}),
          fetch(BASE + "/api/v1/status").then(function(r){return r.json();}).catch(function(){return {};}),
        ]).then(function(rs) {
          // 构建在线设备集合（last_seen 在 60s 内）
          var devices = (rs[3] && rs[3].data && rs[3].data.devices) || [];
          var now = Date.now();
          var onlineSet = new Set();
          devices.forEach(function(d) {
            if (d.online) onlineSet.add(d.device_id);
          });
          // 将 device_ids 转为 member_id 映射
          var memberOnline = {};
          (rs[1] && rs[1].data && rs[1].data.results || []).forEach(function(m) {
            try { var ids = JSON.parse(m.device_ids || "[]"); ids.forEach(function(id) { if (onlineSet.has(id)) memberOnline[m.member_id] = true; }); } catch(e){}
          });
          setData({
            mode: (rs[0]&&rs[0].data&&rs[0].data.mode) || "solo",
            members: (rs[1]&&rs[1].data&&rs[1].data.results) || [],
            stats: (rs[2]&&rs[2].data) || {},
            devices: devices,
            onlineIds: memberOnline,
            loading: false, error: ""
          });
        }).catch(function(e) { setData({ mode: "solo", members: [], stats: {}, devices: [], onlineIds: {}, loading: false, error: e.message }); });
      }
      React.useEffect(refresh, []);

      function setMode(m) {
        if (!confirm("\u5207\u6362\u4e3a \"" + (MODES.find(function(x){return x.value===m;}).label) + "\" \u6a21\u5f0f\u540e\u9700\u91cd\u542f\u670d\u52a1\uff0c\u786e\u8ba4\uff1f")) return;
        fetch(BASE + "/api/v1/deployment/mode", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ mode: m }) }).then(function(r){ if(r.ok) refresh(); });
      }
      function addMember() {
        if (!newName.trim()) return;
        fetch(BASE + "/api/v1/member/add", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ display_name: newName.trim() }) }).then(function(){ setName(""); refresh(); });
      }
      function removeMember(mid) {
        if (!confirm("\u786e\u5b9a\u79fb\u9664\u6b64\u6210\u5458\uff1f\u8be5\u6210\u5458\u7684\u8bb0\u5fc6\u4f53\u548c\u77e5\u8bc6\u5e93\u5c06\u4fdd\u7559\u4f46\u65e0\u6cd5\u518d\u8bbf\u95ee\u3002")) return;
        fetch(BASE + "/api/v1/member/revoke", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ member_id: mid }) }).then(function(){ refresh(); });
      }
      function extractMembers() {
        if (sel.size === 0) return alert("\u8bf7\u5148\u9009\u62e9\u6210\u5458");
        if (!confirm("\u5c06\u9009\u4e2d\u6210\u5458\u7684\u8bb0\u5fc6\u4f53\u548c\u77e5\u8bc6\u5e93\u63d0\u53d6\u5230\u56e2\u961f\u5171\u4eab\u7a7a\u95f4\uff0c\u5e76\u5220\u9664\u6210\u5458\uff1f")) return;
        fetch(BASE + "/api/v1/member/extract", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ member_ids: Array.from(sel) }) })
          .then(function(r){ return r.json(); })
          .then(function(d) { alert("\u5df2\u63d0\u53d6 " + (d.data&&d.data.extracted||0) + " \u6761\u8bb0\u5fc6\u5230\u56e2\u961f\u5171\u4eab\u7a7a\u95f4\uff0c\u5df2\u5220\u9664 " + (d.data&&d.data.deleted||0) + " \u4e2a\u6210\u5458\u3002"); setSel(new Set()); refresh(); })
          .catch(function(e) { alert("\u63d0\u53d6\u5931\u8d25\uff1a" + e.message); });
      }
      function toggleSel(id) { var n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); setSel(n); }

      var active = (data.members||[]).filter(function(m){return !m.revoked && !m.deleted;});
      var revoked = (data.members||[]).filter(function(m){return m.revoked === 1 || m.revoked === 2;});
      var deleted = (data.members||[]).filter(function(m){return m.deleted === 1;});
      var curMode = MODES.find(function(m){return m.value===data.mode;});

      if (data.error) return h("div", { style: { padding: "16px", color: "#e74c3c" } }, "API \u8bf7\u6c42\u5931\u8d25\uff1a" + data.error);

      function renderMemberCard(m, showOnline) {
        var isOnline = showOnline && data.onlineIds[m.member_id];
        return h("div", { key: m.member_id, style: { flex: "1 1 calc(33.33% - 8px)", minWidth: "100px", maxWidth: "160px", padding: "8px 10px", borderRadius: "8px", background: "var(--dsw-alias-bg-base)", border: "1px solid var(--dsw-alias-border-l2)", fontSize: "12px", display: "flex", justifyContent: "space-between", alignItems: "center" } },
          h("div", { style: { flex: 1 } },
            h("div", { style: { fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: "4px" } },
              isOnline ? h("span", { style: { color: "#2ecc71", fontSize: "8px" } }, "\u25cf") : h("span", { style: { color: "#888", fontSize: "8px" } }, "\u25cf"),
              h("span", null, m.display_name || "(\u672a\u547d\u540d)")
            )
          ),
          h("button", { onClick: function(){ removeMember(m.member_id); }, style: { border: "none", background: "none", color: "var(--dsw-alias-text-disabled)", fontSize: "14px", cursor: "pointer", padding: "2px 4px" } }, "\u00d7")
        );
      }

      return h("div", { style: { padding: "16px", display: "flex", flexDirection: "column", minHeight: "100%" } },
        h("div", { style: { flex: 1 } },
          // 标题
          h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" } },
            h("h2", { style: { fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--dsw-alias-label-primary)" } }, "\u591a\u7528\u6237\u8bbe\u7f6e"),
            h("span", { style: { fontSize: "12px", padding: "4px 10px", borderRadius: "10px", background: "var(--dsw-alias-bg-layer-2)", color: "var(--dsw-alias-text-disabled)" } }, curMode ? curMode.label : data.mode)
          ),
          // 模式下拉
          h("div", { style: { background: "var(--dsw-alias-bg-layer-2)", borderRadius: "10px", padding: "14px", marginBottom: "12px" } },
            h("div", { style: { fontSize: "13px", fontWeight: 600, marginBottom: "6px", color: "var(--dsw-alias-label-primary)" } }, "\u90e8\u7f72\u6a21\u5f0f"),
            h("select", { value: data.mode, onChange: function(e) { setMode(e.target.value); }, style: { width: "100%", padding: "10px", borderRadius: "8px", border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-base)", color: "var(--dsw-alias-label-primary)", fontSize: "14px", cursor: "pointer" } },
              MODES.map(function(m) { return h("option", { key: m.value, value: m.value }, m.label + " \u2014 " + m.spec); })
            ),
            h("p", { style: { fontSize: "11px", color: "var(--dsw-alias-text-disabled)", marginTop: "6px" } }, "\u5207\u6362\u540e\u9700\u91cd\u542f\u670d\u52a1\u751f\u6548\u3002")
          ),
          // 页签栏
          h("div", { style: { display: "flex", borderBottom: "1px solid var(--dsw-alias-border-l2)", marginBottom: "12px", gap: "4px" } },
            ["active", "revoked", "deleted"].map(function(t) {
              var count = t === "active" ? active.length : t === "revoked" ? revoked.length : deleted.length;
              var label = t === "active" ? "\u6d3b\u8dc3\u6210\u5458" : t === "revoked" ? "\u5df2\u540a\u9500" : "\u5df2\u5220\u9664";
              return h("button", { key: t, onClick: function() { setTab(t); setSel(new Set()); },
                style: { padding: "8px 12px", border: "none", borderBottom: "2px solid " + (tab === t ? "var(--dsw-alias-brand-primary)" : "transparent"), background: "none", color: tab === t ? "var(--dsw-alias-brand-primary)" : "var(--dsw-alias-text-disabled)", fontSize: "13px", fontWeight: tab === t ? 600 : 400, cursor: "pointer" } },
                label + " (" + count + ")"
              );
            })
          ),
          // 页签内容
          tab === "active" && h("div", null,
            h("div", { style: { display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "12px" } },
              active.length === 0 ? h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", padding: "8px 0" } }, "\u6682\u65e0\u6d3b\u8dc3\u6210\u5458")
              : active.map(function(m) { return renderMemberCard(m, true); })
            ),
            // 添加成员（放在最下方）
            h("div", { style: { display: "flex", gap: "6px" } },
              h("input", { value: newName, onChange: function(e) { setName(e.target.value); }, onKeyDown: function(e) { if (e.key === "Enter") addMember(); }, placeholder: "\u8f93\u5165\u6210\u5458\u540d\u79f0\u540e\u56de\u8f66", style: { flex: 1, padding: "8px 10px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-base)", color: "var(--dsw-alias-label-primary)", fontSize: "13px" } }),
              h("button", { onClick: addMember, style: { padding: "8px 14px", border: "none", borderRadius: "6px", background: "var(--dsw-alias-brand-primary)", color: "var(--dsw-alias-bg-base)", fontWeight: 600, fontSize: "13px", cursor: "pointer" } }, "\u6dfb\u52a0")
            )
          ),
          tab === "revoked" && h("div", null,
            revoked.length === 0 ? h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", padding: "8px 0" } }, "\u65e0\u5df2\u540a\u9500\u6210\u5458")
            : h("div", null,
              h("div", { style: { display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "12px" } },
                revoked.map(function(m) {
                  return h("label", { key: m.member_id, style: { flex: "1 1 calc(33.33% - 8px)", minWidth: "100px", maxWidth: "160px", padding: "8px 10px", borderRadius: "8px", background: sel.has(m.member_id) ? "var(--dsw-alias-brand-primary-bg)" : "var(--dsw-alias-bg-base)", border: "1px solid " + (sel.has(m.member_id) ? "var(--dsw-alias-brand-primary)" : "var(--dsw-alias-border-l2)"), fontSize: "12px", cursor: "pointer" } },
                    h("input", { type: "checkbox", checked: sel.has(m.member_id), onChange: function() { toggleSel(m.member_id); }, style: { marginRight: "6px", verticalAlign: "middle" } }),
                    h("span", null, m.display_name || "(\u672a\u547d\u540d)")
                  );
                })
              ),
              h("button", { onClick: extractMembers, disabled: sel.size === 0, style: { padding: "8px 16px", border: "none", borderRadius: "6px", background: sel.size > 0 ? "var(--dsw-alias-brand-primary)" : "var(--dsw-alias-border-l2)", color: sel.size > 0 ? "var(--dsw-alias-bg-base)" : "var(--dsw-alias-text-disabled)", fontWeight: 600, fontSize: "13px", cursor: sel.size > 0 ? "pointer" : "not-allowed" } }, "\u63d0\u53d6\u9009\u4e2d\u6210\u5458\u8bb0\u5fc6\u5230\u56e2\u961f\u5171\u4eab\u7a7a\u95f4\u5e76\u5220\u9664")
            )
          ),
          tab === "deleted" && h("div", null,
            deleted.length === 0 ? h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", padding: "8px 0" } }, "\u65e0\u5df2\u5220\u9664\u6210\u5458")
            : h("div", { style: { display: "flex", flexWrap: "wrap", gap: "8px" } },
                deleted.map(function(m) { return renderMemberCard(m, false); })
            )
          ),
          // 统计
          (data.stats && data.stats.members) ? h("div", { style: { background: "var(--dsw-alias-bg-layer-2)", borderRadius: "10px", padding: "10px 14px", marginTop: "12px", fontSize: "12px", color: "var(--dsw-alias-text-disabled)", display: "flex", gap: "12px", flexWrap: "wrap" } },
            h("span", null, "\u6d3b\u8dc3: " + active.length),
            h("span", null, "\u5df2\u540a\u9500: " + revoked.length),
            h("span", null, "\u5df2\u5220\u9664: " + deleted.length),
            h("span", null, "\u5171\u4eab\u8bb0\u5fc6: " + ((data.stats.shared_memory||{}).logs_3d||0) + "\u6761")
          ) : null
        ),
        // 底部固定
        h("div", { style: { borderTop: "1px solid var(--dsw-alias-border-l2)", paddingTop: "10px", marginTop: "16px", flexShrink: 0 } },
          h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "var(--dsw-alias-text-disabled)" } },
            h("span", null, "deepDDW v0.5.0 \u00b7 MIT \u00b7 ", h("a", { href: "https://github.com/ccch713/deepddw", target: "_blank", style: { color: "var(--dsw-alias-text-disabled)" } }, "GitHub")),
            h("a", { href: "https://ddw.ai-hub.com", target: "_blank", style: { color: "var(--dsw-alias-brand-primary)", fontWeight: 500, fontSize: "12px" } }, "\u4e2d\u5927\u578b\u56e2\u961f\uff1f\u2192 \u5546\u4e1a\u7248")
          )
        )
      );
    }

    // ══════ 首次弹窗 ══════
    function OnboardingModal() {
      var s = React.useState({selected:"solo",submitting:false});var st=s[0];var setSt=s[1];
      function confirm(){
        setSt({selected:st.selected,submitting:true});
        fetch(BASE+"/api/v1/deployment/mode",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:st.selected})}).then(function(r){if(r.ok){localStorage.setItem("deepddw_onboarded","1");location.reload();}else{setSt({selected:st.selected,submitting:false});}}).catch(function(){setSt({selected:st.selected,submitting:false});});
      }
      return h("div",{style:{position:"fixed",inset:0,zIndex:99999,display:"flex",alignItems:"center",justifyContent:"center",background:"rgba(0,0,0,.6)"}},
        h("div",{style:{background:"var(--dsw-alias-bg-base)",border:"1px solid var(--dsw-alias-border-l2)",borderRadius:"12px",padding:"32px",maxWidth:"420px",width:"90%",boxShadow:"0 20px 60px rgba(0,0,0,.5)"}},
          h("h2",{style:{margin:"0 0 16px",fontSize:"18px",fontWeight:700,color:"var(--dsw-alias-label-primary)"}},"\u9009\u62e9\u4f7f\u7528\u6a21\u5f0f"),
          h("p",{style:{margin:"0 0 20px",fontSize:"12px",color:"var(--dsw-alias-text-disabled)"}},"\u53ef\u968f\u65f6\u5728\u300c\u8bbe\u7f6e \u2192 \u591a\u7528\u6237\u8bbe\u7f6e\u300d\u4e2d\u5207\u6362"),
          MODES.map(function(m){return h("label",{key:m.value,style:{display:"flex",alignItems:"flex-start",gap:"10px",padding:"10px 12px",marginBottom:"4px",borderRadius:"8px",cursor:"pointer",border:"2px solid "+(st.selected===m.value?"var(--dsw-alias-brand-primary)":"transparent")},onClick:function(){setSt({selected:m.value,submitting:false});}},
            h("input",{type:"radio",checked:st.selected===m.value,readOnly:true,style:{marginTop:"2px"}}),
            h("div",null,h("div",{style:{fontSize:"14px",fontWeight:600}},m.label),h("div",{style:{fontSize:"12px",color:"var(--dsw-alias-text-disabled)",marginTop:"2px"}},m.spec))
          );}),
          h("button",{onClick:confirm,disabled:st.submitting,style:{width:"100%",padding:"12px",border:"none",borderRadius:"8px",background:"var(--dsw-alias-brand-primary)",color:"var(--dsw-alias-bg-base)",fontWeight:600,fontSize:"14px",cursor:"pointer",marginTop:"12px",opacity:st.submitting?0.5:1}},st.submitting?"\u4fdd\u5b58\u4e2d...":"\u786e\u8ba4")
        )
      );
    }

    exports.apply = function(ctx) {
      try {
        if (!localStorage.getItem("deepddw_onboarded")) {
          fetch(BASE+"/api/v1/deployment/mode").then(function(r){return r.json();}).then(function(d){
            if(d&&d.data&&d.data.configured){localStorage.setItem("deepddw_onboarded","1");}
            else{ctx.slots.inject("settings.onboarding",function(){return ctx.slots.register({name:"settings.onboarding",id:"ddw-multiuser-onboard",order:50,label:function(){return "\u521d\u6b21\u8bbe\u7f6e";}},OnboardingModal);});}
          }).catch(function(){});
        }
        ctx.slots.inject("settings.section",function(){return ctx.slots.register({name:"settings.section",id:"ddw-multiuser-settings",order:100,label:function(){return "\u591a\u7528\u6237\u8bbe\u7f6e";}},SettingsPanel);});
        var deviceId=localStorage.getItem("deepddw_device_id")||("dev-"+Date.now().toString(36));localStorage.setItem("deepddw_device_id",deviceId);
        if(!localStorage.getItem("deepddw_member_id")){
          fetch(BASE+"/api/v1/member/list").then(function(r){return r.json();}).then(function(d){
            var active=((d&&d.data&&d.data.results)||[]).filter(function(m){return !m.revoked&&!m.deleted;});
            if(active.length>0){ctx.slots.inject("shell.overlay",function(){return ctx.slots.register({name:"shell.overlay",id:"ddw-member-identify",order:9999,label:function(){return "\u6210\u5458\u8bc6\u522b";}},function(){return h(MemberIdentify,{members:active,deviceId:deviceId});});});}
          }).catch(function(){});
        }
        console.log("[ddw] all slots registered (patch8)");
      }catch(e){console.error("[ddw]",e);}
    };
    return module.exports;
  }
});
