window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: function(require) {
    var module = { exports: {} };
    var exports = module.exports;
    var React = require("react");
    var h = React.createElement;
    var BASE = window.location.origin;

    exports.inject = ["slots"];

    // ─── 完整设置面板 ───
    function SettingsPanel() {
      var s = React.useState({ mode: "solo", members: [], stats: {}, version: "?", loading: true, error: "" });
      var data = s[0];
      var setData = s[1];
      var nameS = React.useState("");
      var newName = nameS[0];
      var setName = nameS[1];

      function refresh() {
        setData({ mode: "solo", members: [], stats: {}, version: "?", loading: true, error: "" });
        Promise.all([
          fetch(BASE + "/api/v1/deployment/mode").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/admin/stats").then(function(r){return r.json();}).catch(function(){return {};})
        ]).then(function(rs) {
          setData({
            mode: (rs[0] && rs[0].data && rs[0].data.mode) || "solo",
            members: (rs[1] && rs[1].data && rs[1].data.results) || [],
            stats: (rs[2] && rs[2].data) || {},
            version: "?",
            loading: false,
            error: ""
          });
        }).catch(function(e) {
          setData({ mode: "solo", members: [], stats: {}, version: "?", loading: false, error: e.message });
        });
      }

      React.useEffect(refresh, []);

      function setMode(m) {
        fetch(BASE + "/api/v1/deployment/mode", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ mode: m }) })
          .then(function(r){ if (r.ok) { refresh(); } });
      }

      function addMember() {
        if (!newName.trim()) return;
        fetch(BASE + "/api/v1/member/add", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ display_name: newName.trim() }) })
          .then(function(){ setName(""); refresh(); });
      }

      function removeMember(mid) {
        fetch(BASE + "/api/v1/member/revoke", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ member_id: mid }) })
          .then(function(){ refresh(); });
      }

      var MODES = [
        { value: "solo", label: "一人多设备", desc: "一个人使用多台设备" },
        { value: "family", label: "家庭多人", desc: "家人之间共享，互相可见" },
        { value: "team", label: "小团队协作", desc: "团队共享 + 各自空间" }
      ];

      if (data.error) {
        return h("div", { style: { padding: "16px", color: "#e74c3c" } }, "API 请求失败: " + data.error);
      }

      return h("div", { style: { padding: "16px", maxWidth: "600px" } },
        h("h2", { style: { fontSize: "18px", fontWeight: 700, marginBottom: "6px", color: "var(--dsw-alias-label-primary)" } },
          "多用户设置"),
        h("p", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", marginBottom: "20px" } },
          "管理多台设备、多名成员的共享与隔离"),

        // 部署模式
        h("h3", { style: { fontSize: "13px", fontWeight: 600, marginBottom: "8px", color: "var(--dsw-alias-label-primary)" } },
          "部署模式"),
        MODES.map(function(m) {
          return h("label", { key: m.value, style: { display: "flex", alignItems: "flex-start", gap: "10px", padding: "10px 14px", marginBottom: "4px", borderRadius: "8px", cursor: "pointer", border: "2px solid " + (data.mode === m.value ? "var(--dsw-alias-brand-primary)" : "transparent") }, onClick: function(){ setMode(m.value); } },
            h("input", { type: "radio", checked: data.mode === m.value, readOnly: true, style: { marginTop: "2px" } }),
            h("div", null,
              h("div", { style: { fontSize: "14px", fontWeight: 600 } }, m.label),
              h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", marginTop: "2px" } }, m.desc)
            )
          );
        }),

        // 成员管理
        h("h3", { style: { fontSize: "13px", fontWeight: 600, margin: "20px 0 8px", color: "var(--dsw-alias-label-primary)" } },
          "成员"),
        h("div", { style: { display: "flex", gap: "8px", marginBottom: "10px" } },
          h("input", { value: newName, onChange: function(e){ setName(e.target.value); }, placeholder: "输入成员名称", onKeyDown: function(e){ if(e.key === "Enter") addMember(); }, style: { flex: 1, padding: "8px 12px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2)", background: "var(--dsw-alias-bg-layer-2)", color: "var(--dsw-alias-label-primary)", fontSize: "13px" } }),
          h("button", { onClick: addMember, style: { padding: "8px 16px", border: "none", borderRadius: "6px", background: "var(--dsw-alias-brand-primary)", color: "var(--dsw-alias-bg-base)", fontWeight: 600, fontSize: "13px", cursor: "pointer" } }, "+")
        ),
        (data.members || []).filter(function(m) { return !m.revoked; }).length === 0
          ? h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", padding: "8px 0" } }, "暂无成员，点击 + 添加")
          : (data.members || []).filter(function(m) { return !m.revoked; }).map(function(m) {
              return h("div", { key: m.member_id, style: { display: "flex", alignItems: "center", gap: "10px", padding: "8px 12px", borderRadius: "6px", background: "var(--dsw-alias-bg-layer-2)", marginBottom: "4px", fontSize: "13px" } },
                h("span", { style: { color: "var(--dsw-alias-text-disabled)" } }, "⚪"),
                h("span", { style: { flex: 1, color: "var(--dsw-alias-label-primary)" } }, m.display_name || "(未命名)"),
                h("span", { style: { fontSize: "11px", color: "var(--dsw-alias-text-disabled)" } }, "离线"),
                h("button", { onClick: function(){ removeMember(m.member_id); }, style: { padding: "4px 8px", border: "1px solid var(--dsw-alias-border-l2)", borderRadius: "4px", background: "transparent", color: "var(--dsw-alias-text-disabled)", fontSize: "11px", cursor: "pointer" } }, "移除")
              );
            }),

        // 统计
        (data.stats && data.stats.members) ?
          h("div", { style: { marginTop: "16px", padding: "12px", borderRadius: "8px", background: "var(--dsw-alias-bg-layer-2)", fontSize: "12px", color: "var(--dsw-alias-text-disabled)", lineHeight: 1.8 } },
            "活跃成员: " + (data.stats.members.active || 0) + " 人" +
            ((data.stats.members.revoked || 0) > 0 ? "（已吊销 " + data.stats.members.revoked + "）" : "") +
            " | 共享记忆: " + ((data.stats.shared_memory || {}).logs_3d || 0) + " 条")
          : null,

        // 系统信息
        h("h3", { style: { fontSize: "13px", fontWeight: 600, margin: "20px 0 8px", color: "var(--dsw-alias-label-primary)" } },
          "系统信息"),
        h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", lineHeight: 1.8 } },
          "deepDDW v" + (data.version || "0.5.0"),
          h("br"),
          "github.com/ccch713/deepddw · MIT License",
          h("br"),
          h("a", { href: "https://github.com/ccch713/deepddw/releases", target: "_blank", style: { color: "var(--dsw-alias-brand-primary)" } }, "检查更新 →")
        )
      );
    }

    // ─── 首次弹窗（onboarding）───
    function OnboardingModal() {
      var s = React.useState({ selected: "solo", submitting: false });
      var st = s[0];
      var setSt = s[1];
      var MODES = [
        { value: "solo", label: "一人多设备", desc: "一个人使用多台设备" },
        { value: "family", label: "家庭多人", desc: "家人之间共享，互相可见" },
        { value: "team", label: "小团队协作", desc: "团队共享 + 各自空间" }
      ];
      function confirm() {
        setSt({ selected: st.selected, submitting: true });
        fetch(BASE + "/api/v1/deployment/mode", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ mode: st.selected }) })
          .then(function(r) {
            if (r.ok) {
              localStorage.setItem("deepddw_onboarded", "1");
              location.reload();
            } else { setSt({ selected: st.selected, submitting: false }); }
          })
          .catch(function(){ setSt({ selected: st.selected, submitting: false }); });
      }
      return h("div", { style: { position: "fixed", inset: 0, zIndex: 99999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.6)" } },
        h("div", { style: { background: "var(--dsw-alias-bg-base)", border: "1px solid var(--dsw-alias-border-l2)", borderRadius: "12px", padding: "32px", maxWidth: "420px", width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,.5)" } },
          h("h2", { style: { margin: "0 0 16px", fontSize: "18px", fontWeight: 700, color: "var(--dsw-alias-label-primary)" } }, "选择使用模式"),
          h("p", { style: { margin: "0 0 20px", fontSize: "13px", color: "var(--dsw-alias-text-disabled)" } }, "可随时在「设置 → 多用户设置」中切换"),
          MODES.map(function(m) {
            return h("label", { key: m.value, style: { display: "flex", alignItems: "flex-start", gap: "10px", padding: "12px 14px", marginBottom: "6px", borderRadius: "8px", cursor: "pointer", border: "2px solid " + (st.selected === m.value ? "var(--dsw-alias-brand-primary)" : "transparent") }, onClick: function(){ setSt({ selected: m.value, submitting: st.submitting }); } },
              h("input", { type: "radio", checked: st.selected === m.value, readOnly: true, style: { marginTop: "2px" } }),
              h("div", null,
                h("div", { style: { fontSize: "14px", fontWeight: 600 } }, m.label),
                h("div", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", marginTop: "2px" } }, m.desc)
              )
            );
          }),
          h("button", { onClick: confirm, disabled: st.submitting, style: { width: "100%", padding: "12px", border: "none", borderRadius: "8px", background: "var(--dsw-alias-brand-primary)", color: "var(--dsw-alias-bg-base)", fontWeight: 600, fontSize: "14px", cursor: "pointer", marginTop: "12px", opacity: st.submitting ? 0.5 : 1 } }, st.submitting ? "保存中..." : "确认")
        )
      );
    }


    // ─── 成员识别（"你是谁？"弹窗）───
    function MemberIdentify(props) {
      var s = React.useState({ selected: null, submitting: false });
      var st = s[0];
      var setSt = s[1];
      var members = props.members || [];

      function bind() {
        if (!st.selected) return;
        setSt({ selected: st.selected, submitting: true });
        fetch(BASE + "/api/v1/device/identify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: props.deviceId, member_id: st.selected })
        }).then(function(r) {
          if (r.ok) {
            localStorage.setItem("deepddw_member_id", st.selected);
            // 设置工作区为成员个人空间，实现记忆/知识库隔离
            localStorage.setItem("deepddw_workspace", "member:" + st.selected);
            location.reload();
          } else { setSt({ selected: st.selected, submitting: false }); }
        }).catch(function(){ setSt({ selected: st.selected, submitting: false }); });
      }

      return h("div", { style: { position: "fixed", inset: 0, zIndex: 99999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.6)" } },
        h("div", { style: { background: "var(--dsw-alias-bg-base)", border: "1px solid var(--dsw-alias-border-l2)", borderRadius: "12px", padding: "32px", maxWidth: "380px", width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,.5)" } },
          h("h2", { style: { margin: "0 0 16px", fontSize: "17px", fontWeight: 700, color: "var(--dsw-alias-label-primary)" } }, "你是谁？"),
          h("p", { style: { margin: "0 0 16px", fontSize: "12px", color: "var(--dsw-alias-text-disabled)" } }, "选择你的身份，本设备将绑定到该成员（记忆/知识库按成员隔离）"),
          members.map(function(m) {
            return h("label", { key: m.member_id, style: { display: "flex", alignItems: "flex-start", gap: "10px", padding: "12px 14px", marginBottom: "6px", borderRadius: "8px", cursor: "pointer", border: "2px solid " + (st.selected === m.member_id ? "var(--dsw-alias-brand-primary)" : "transparent") }, onClick: function(){ setSt({ selected: m.member_id, submitting: false }); } },
              h("input", { type: "radio", checked: st.selected === m.member_id, readOnly: true, style: { marginTop: "2px" } }),
              h("span", { style: { fontSize: "14px", color: "var(--dsw-alias-label-primary)" } }, m.display_name || "(未命名)")
            );
          }),
          h("button", { onClick: bind, disabled: !st.selected || st.submitting, style: { width: "100%", padding: "12px", border: "none", borderRadius: "8px", background: "var(--dsw-alias-brand-primary)", color: "var(--dsw-alias-bg-base)", fontWeight: 600, fontSize: "14px", cursor: "pointer", marginTop: "12px", opacity: (!st.selected || st.submitting) ? 0.5 : 1 } }, st.submitting ? "绑定中..." : "确认身份")
        )
      );
    }

    exports.apply = function(ctx) {
      try {
        // 首次弹窗（未配置时显示）
        if (!localStorage.getItem("deepddw_onboarded")) {
          fetch(BASE + "/api/v1/deployment/mode").then(function(r){return r.json();}).then(function(d) {
            if (d && d.data && d.data.configured) {
              localStorage.setItem("deepddw_onboarded", "1");
            } else {
              ctx.slots.inject("settings.onboarding", function() {
                return ctx.slots.register({
                  name: "settings.onboarding",
                  id: "ddw-multiuser-onboard",
                  order: 50,
                  label: function() { return "初次设置"; }
                }, OnboardingModal);
              });
            }
          }).catch(function(){});
        }

        // 设置面板
        ctx.slots.inject("settings.section", function() {
          return ctx.slots.register({
            name: "settings.section",
            id: "ddw-multiuser-settings",
            order: 100,
            label: function() { return "多用户设置"; }
          }, SettingsPanel);
        });

        // 成员识别（未绑定时弹出"你是谁"选择成员）
        var deviceId = localStorage.getItem("deepddw_device_id") || ("dev-" + Date.now().toString(36));
        localStorage.setItem("deepddw_device_id", deviceId);
        if (!localStorage.getItem("deepddw_member_id")) {
          fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}).then(function(d) {
            var mlist = (d && d.data && d.data.results) || [];
            if (mlist.length > 0) {
              ctx.slots.inject("shell.overlay", function() {
                return ctx.slots.register({
                  name: "shell.overlay",
                  id: "ddw-member-identify",
                  order: 9999,
                  label: function() { return "成员识别"; }
                }, function() {
                  return h(MemberIdentify, { members: mlist, deviceId: deviceId });
                });
              });
              console.log("[ddw] 弹出成员识别：" + mlist.length + " 个成员");
            }
          }).catch(function(){});
        }

        console.log("[ddw] settings.section + onboarding registered");
      } catch(e) {
        console.error("[ddw] registration failed:", e);
      }
    };

    return module.exports;
  }
});
