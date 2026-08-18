// deepDDW 多用户设置面板 — DSH __ModuleLoader__ 格式
// v0.5.0-patch3: 修复 Vue 组件渲染（直接返回 vnode，不用包装函数 + ref.el）
// 注册到 context（DSH 客户端会将其作为 react component 传入 Vue renderer）
var Vue = require("vue");
var h = Vue.h, ref = Vue.ref, onMounted = Vue.onMounted, computed = Vue.computed;

// ════════ 工具函数 ════════
function gw() {
  return (typeof window !== "undefined" && window.location && window.location.origin) || "http://127.0.0.1:8600";
}

// ════════ 模式选择（M2 首次弹窗） ════════
var MODES = [
  { value: "solo", label: "一人多设备", desc: "一个人使用多台设备" },
  { value: "family", label: "家庭多人", desc: "家人之间共享，互相可见" },
  { value: "team", label: "小团队协作", desc: "团队共享 + 各自空间" }
];

function OnboardingModal(props) {
  var selected = ref("solo");
  var submitting = ref(false);
  var visible = ref(true);

  function confirm() {
    submitting.value = true;
    fetch(gw() + "/api/v1/deployment/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: selected.value })
    })
    .then(function(r) {
      if (r.ok) {
        localStorage.setItem("deepddw_onboarded", "1");
        visible.value = false;
        setTimeout(function() { location.reload(); }, 300);
      }
    })
    .catch(function() {})
    .finally(function() { submitting.value = false; });
  }

  if (!visible.value) return null;

  return h("div", {
    style: "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)"
  }, [
    h("div", {
      style: "background:var(--dsw-alias-bg-base,#1a1a2e);border:1px solid var(--dsw-alias-border-l2,#333);border-radius:12px;padding:32px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)"
    }, [
      h("h2", { style: "margin:0 0 16px;font-size:18px;font-weight:700;color:var(--dsw-alias-label-primary)" }, "选择使用模式"),
      h("p", { style: "margin:0 0 20px;font-size:13px;color:var(--dsw-alias-text-disabled)" }, "可随时在「设置 → 多用户设置」中切换"),
      ...MODES.map(function(m) {
        return h("label", {
          key: m.value,
          style: "display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid " + (selected.value === m.value ? "var(--dsw-alias-brand-primary)" : "transparent") + ";background:" + (selected.value === m.value ? "var(--dsw-alias-bg-layer-2)" : "transparent"),
          onClick: function() { selected.value = m.value; }
        }, [
          h("input", {
            type: "radio",
            checked: selected.value === m.value,
            onChange: function() { selected.value = m.value; },
            style: "margin-top:2px;accent-color:var(--dsw-alias-brand-primary)"
          }),
          h("div", null, [
            h("div", { style: "font-size:14px;font-weight:600;color:var(--dsw-alias-label-primary)" }, m.label),
            h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px" }, m.desc)
          ])
        ]);
      }),
      h("button", {
        onClick: confirm,
        disabled: submitting.value,
        style: "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:" + (submitting.value ? ".5" : "1")
      }, submitting.value ? "保存中..." : "确认")
    ])
  ]);
}

// ════════ 设置面板（M3） ════════
function SettingsPanel(props) {
  var mode = ref("solo");
  var members = ref([]);
  var newName = ref("");
  var adding = ref(false);
  var version = ref({ version: "?" });

  onMounted(function() {
    refresh();
  });

  function refresh() {
    var b = gw();
    Promise.all([
      fetch(b + "/api/v1/deployment/mode").then(function(r){ return r.json(); }),
      fetch(b + "/api/v1/member/list").then(function(r){ return r.json(); }),
      fetch(b + "/api/v1/version").then(function(r){ return r.json(); })
    ]).then(function(results) {
      mode.value = (results[0] && results[0].data && results[0].data.mode) || "solo";
      members.value = (results[1] && results[1].data && results[1].data.results) || [];
      version.value = results[2] && results[2].data || { version: "?" };
    }).catch(function() {});
  }

  function setMode(m) {
    fetch(gw() + "/api/v1/deployment/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: m })
    })
    .then(function(r) {
      if (r.ok) { mode.value = m; setTimeout(function(){ location.reload(); }, 300); }
    });
  }

  function addMember() {
    if (!newName.value.trim()) return;
    adding.value = true;
    fetch(gw() + "/api/v1/member/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: newName.value.trim() })
    })
    .then(function(r) { return r.json(); })
    .then(function() { newName.value = ""; refresh(); })
    .catch(function() {})
    .finally(function() { adding.value = false; });
  }

  function removeMember(mid) {
    fetch(gw() + "/api/v1/member/revoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ member_id: mid })
    })
    .then(function() { refresh(); })
    .catch(function() {});
  }

  return h("div", { style: "padding:16px;color:var(--dsw-alias-label-primary)" }, [
    h("h2", { style: "font-size:18px;font-weight:700;margin:0 0 6px" }, "多用户设置"),
    h("p", { style: "margin:0 0 20px;font-size:12px;color:var(--dsw-alias-text-disabled)" }, "管理多台设备、多名成员的共享与隔离"),

    // 模式选择
    h("div", { style: "font-size:13px;font-weight:600;margin-bottom:8px;color:var(--dsw-alias-label-primary)" }, "部署模式"),
    ...MODES.map(function(m) {
      return h("label", {
        key: m.value,
        style: "display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;border:2px solid " + (mode.value === m.value ? "var(--dsw-alias-brand-primary)" : "transparent"),
        onClick: function() { setMode(m.value); }
      }, [
        h("input", {
          type: "radio",
          checked: mode.value === m.value,
          onChange: function() { setMode(m.value); },
          style: "margin-top:2px;accent-color:var(--dsw-alias-brand-primary)"
        }),
        h("div", null, [
          h("div", { style: "font-size:14px;font-weight:600;color:var(--dsw-alias-label-primary)" }, m.label),
          h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px" }, m.desc)
        ])
      ]);
    }),

    // 成员管理
    h("div", { style: "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)" }, "成员"),
    h("div", { style: "display:flex;gap:8px;margin-bottom:10px" }, [
      h("input", {
        value: newName.value,
        onInput: function(e) { newName.value = e.target.value; },
        placeholder: "输入成员名称",
        onKeydown: function(e) { if (e.key === "Enter") addMember(); },
        style: "flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);font-size:13px"
      }),
      h("button", {
        onClick: addMember,
        disabled: adding.value,
        style: "padding:8px 16px;border:none;border-radius:6px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:13px;cursor:pointer;opacity:" + (adding.value ? ".5" : "1")
      }, "+")
    ]),
    members.value.length === 0
      ? h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);padding:8px 0" }, "暂无成员，点击 + 添加")
      : members.value.map(function(m) {
          return h("div", {
            key: m.member_id,
            style: "display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;background:var(--dsw-alias-bg-layer-2);margin-bottom:4px;font-size:13px"
          }, [
            h("span", { style: "color:var(--dsw-alias-text-disabled)" }, m.revoked ? "⚪" : "🟢"),
            h("span", { style: "flex:1" }, m.display_name),
            h("button", {
              onClick: function() { removeMember(m.member_id); },
              style: "padding:4px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:4px;background:transparent;color:var(--dsw-alias-text-disabled);font-size:11px;cursor:pointer"
            }, "移除")
          ]);
        }),

    // 系统信息
    h("div", { style: "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)" }, "系统信息"),
    h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);line-height:1.8" }, [
      "deepDDW v" + version.value.version,
      h("br"),
      "github.com/ccch713/deepddw",
      h("br"),
      h("span", { style: "color:var(--dsw-alias-text-disabled);font-size:11px" }, "更多配置请在网关 config/deployment.yaml 中调整")
    ])
  ]);
}

// ════════ 成员识别（M4 弹窗） ════════
function MemberIdentify(props) {
  var members = ref(props.members || []);
  var selected = ref(null);
  var done = ref(false);

  function bind() {
    if (!selected.value) return;
    fetch(gw() + "/api/v1/device/identify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: props.deviceId, member_id: selected.value })
    })
    .then(function() {
      localStorage.setItem("deepddw_member_id", selected.value);
      done.value = true;
      setTimeout(function() { location.reload(); }, 300);
    })
    .catch(function() {});
  }

  if (done.value) return null;

  return h("div", {
    style: "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)"
  }, [
    h("div", {
      style: "background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l2);border-radius:12px;padding:32px;max-width:380px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)"
    }, [
      h("h2", { style: "margin:0 0 16px;font-size:17px;font-weight:700;color:var(--dsw-alias-label-primary)" }, "你是谁？"),
      ...members.value.map(function(m) {
        return h("label", {
          key: m.member_id,
          onClick: function() { selected.value = m.member_id; },
          style: "display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid " + (selected.value === m.member_id ? "var(--dsw-alias-brand-primary)" : "transparent")
        }, [
          h("input", {
            type: "radio",
            checked: selected.value === m.member_id,
            onChange: function() { selected.value = m.member_id; },
            style: "margin-top:2px;accent-color:var(--dsw-alias-brand-primary)"
          }),
          h("span", { style: "font-size:14px;color:var(--dsw-alias-label-primary)" }, m.display_name)
        ]);
      }),
      h("button", {
        onClick: bind,
        disabled: !selected.value,
        style: "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:" + (selected.value ? "1" : ".5")
      }, "确认身份")
    ])
  ]);
}

// ════════ 导出 ════════
exports.__esModule = true;
exports.inject = ["slots", "locale"];
exports.apply = function(ctx) {
  // M4 成员识别：新设备首次打开 → 检查是否已绑定，未绑定则弹"你是谁"
  var deviceId = localStorage.getItem("deepddw_device_id") || ("dev-" + Date.now().toString(36));
  localStorage.setItem("deepddw_device_id", deviceId);
  if (!localStorage.getItem("deepddw_member_id")) {
    fetch(gw() + "/api/v1/member/list")
      .then(function(r){ return r.json(); })
      .then(function(d){
        var mlist = (d && d.data && d.data.results) || [];
        if (mlist.length > 0) {
          ctx.slots.inject("shell.overlay", function(){
            return ctx.slots.register({
              name: "shell.overlay",
              id: "ddw-member-identify",
              order: 9999,
              label: "identify"
            }, function(){ return h(MemberIdentify, { members: mlist, deviceId: deviceId }); });
          });
        }
      })
      .catch(function(){});
  }

  // M2 首次弹窗：未配置 mode 时弹模式选择
  if (!localStorage.getItem("deepddw_onboarded")) {
    fetch(gw() + "/api/v1/deployment/mode")
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.data && d.data.configured) {
          localStorage.setItem("deepddw_onboarded", "1");
          return;
        }
        ctx.slots.inject("settings.onboarding", function(){
          return ctx.slots.register({
            name: "settings.onboarding",
            id: "ddw-multiuser-onboard",
            order: 50,
            label: "onboard"
          }, function(){ return h(OnboardingModal, {}); });
        });
      })
      .catch(function(){});
  }

  // M3 设置面板
  ctx.slots.inject("settings.section", function(){
    return ctx.slots.register({
      name: "settings.section",
      id: "ddw-multiuser-settings",
      order: 100,
      label: "多用户设置"
    }, function(){ return h(SettingsPanel, {}); });
  });
};
exports.default = SettingsPanel;
exports.SettingsPanel = SettingsPanel;
exports.OnboardingModal = OnboardingModal;
exports.MemberIdentify = MemberIdentify;
