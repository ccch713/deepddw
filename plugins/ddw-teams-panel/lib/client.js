/**
 * deepDDW 多用户设置面板 — DSH __ModuleLoader__ 格式构建产物
 *
 * v0.5.0 补丁版：由 TS 源码手工转译，符合 DSH client bundle helper 产出格式。
 * 安装后 DSH 会自动发现并加载，注册 settings.section + settings.onboarding slot。
 *
 * 依赖（DSH loader 模块表提供）：
 *   - react（createElement=h）
 *   - @deepseek-ai/dsh-client-runtime（slots/context 注入）
 *
 * 格式：window.__ModuleLoader__.load({id, factory: (require) => {...}})
 * （参考 dshmarket/client/client.js 输出格式）
 */
window.__ModuleLoader__.load({ id: "@deepddw/ddw-teams-panel", factory: (require) => {
var module = { exports: {} };
var exports = module.exports;
Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
let react = require("react");
let h = react.createElement;

// ═══════════════════════════════════════════════════════════════
// 国际化（zh）
// ═══════════════════════════════════════════════════════════════
var NS = "settings.ddwMultiuser";
var zh = {
  onboardTitle: "初次设置",
  identifyTitle: "你是谁？",
  addMember: "添加成员",
  noMembers: "暂无成员，点击 + 添加",
  settingsTitle: "多用户设置",
  settingsDesc: "管理多台设备、多名成员的共享与隔离",
  modeTitle: "模式",
  memberTitle: "成员",
  systemTitle: "系统信息",
  confirm: "确认",
  confirming: "保存中...",
  remove: "移除",
  confirmIdentity: "确认身份",
  whoAreYou: "你是谁？",
  modeSolo: "一人多设备",  modeSoloDesc: "一个人使用多台设备",
  modeFamily: "家庭多人",  modeFamilyDesc: "家人之间共享，互相可见",
  modeTeam: "小团队协作",  modeTeamDesc: "团队共享 + 各自空间",
  offline: "离线",
  networkInfo: "Network/Workspace/Files 的详细数据请查看 API 文档",
  version: "版本",
  pluginVersion: "插件版本",
  gatewayVersion: "网关版本",
  checkUpdate: "检查更新",
  updateAvailable: "发现新版本",
  updateUpToDate: "已是最新",
  deepDDWIntro: "deepDDW — 开源个人 AI 底座（DSH + 知识库 + 记忆 + 网关 + MCP）",
  naMembers: "添加成员",
  namePlaceholder: "输入成员名称",
  emptyMembers: "暂无成员，点击 + 添加",
  removeBtn: "移除",
};
var lang = zh; // 默认中文

// ═══════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════
function gw(ctx) { return ctx && ctx.config && ctx.config.gatewayUrl || "http://127.0.0.1:8500"; }

// ═══════════════════════════════════════════════════════════════
// M2 OnboardingModal（首次模式选择弹窗）
// ═══════════════════════════════════════════════════════════════
var MODES = [
  { value: "solo",   label: "一人多设备", desc: "一个人使用多台设备" },
  { value: "family", label: "家庭多人",   desc: "家人之间共享，互相可见" },
  { value: "team",   label: "小团队协作", desc: "团队共享 + 各自空间" },
];

function OnboardingModal(props) {
  var ctx = props.ctx, baseUrl = props.baseUrl;
  var ref = { selected: "solo", submitting: false, el: null };
  function rerender() { if (ref.el) ref.el.forceUpdate(); }

  async function confirm() {
    ref.submitting = true; rerender();
    try {
      var r = await fetch(baseUrl + "/api/v1/deployment/mode", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: ref.selected }),
      });
      if (r.ok) { localStorage.setItem("deepddw_onboarded", "1"); location.reload(); }
    } finally { ref.submitting = false; rerender(); }
  }

  ref.el = h(OnboardingModalView, { ctx, ref, confirm });
  return ref.el;
}

function OnboardingModalView({ ctx, ref, confirm }) {
  return h("div", {
    style: "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5)",
  },
    h("div", {
      style: "background:var(--dsw-alias-bg-base);border-radius:12px;padding:32px;max-width:420px;width:90%;color:var(--dsw-alias-label-primary)",
    },
      h("h2", { style: "margin:0 0 8px;font-size:18px;font-weight:700" }, "选择使用模式"),
      h("p", { style: "margin:0 0 20px;font-size:13px;color:var(--dsw-alias-text-disabled)" }, "可随时在「设置 → 多用户设置」中切换"),
      MODES.map(function(m) {
        var sel = ref.selected === m.value;
        return h("label", {
          key: m.value,
          onClick: function() { ref.selected = m.value; ref.el.forceUpdate(); },
          style: "display:flex;align-items:center;gap:10px;padding:12px 14px;margin-bottom:8px;border-radius:8px;cursor:pointer;border:2px solid " +
            (sel ? "var(--dsw-alias-brand-primary)" : "transparent") +
            ";background:" + (sel ? "var(--dsw-alias-bg-layer-1)" : "transparent"),
        },
          h("input", { type: "radio", checked: sel, style: "accent-color:var(--dsw-alias-brand-primary)" }),
          h("div", null,
            h("div", { style: "font-size:14px;font-weight:600" }, m.label),
            h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled)" }, m.desc),
          ),
        );
      }),
      h("button", {
        disabled: ref.submitting,
        onClick: confirm,
        style: "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:8px;opacity:" + (ref.submitting ? "0.5" : "1"),
      }, ref.submitting ? "保存中..." : "确认"),
    )
  );
}

// ═══════════════════════════════════════════════════════════════
// M4 MemberIdentify（你是谁→绑定）
// ═══════════════════════════════════════════════════════════════
function MemberIdentify(props) {
  var members = props.members, deviceId = props.deviceId, baseUrl = props.baseUrl;
  var ref = { selected: null, done: false, el: null };
  function rerender() { if (ref.el) ref.el.forceUpdate(); }

  async function bind() {
    if (!ref.selected) return;
    await fetch(baseUrl + "/api/v1/device/identify", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, member_id: ref.selected }),
    });
    localStorage.setItem("deepddw_member_id", ref.selected);
    ref.done = true; rerender();
    location.reload();
  }

  ref.el = h(MemberIdentifyView, { members, ref, bind });
  return ref.el;
}

function MemberIdentifyView({ members, ref, bind }) {
  if (ref.done) return null;
  return h("div", {
    style: "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5)",
  },
    h("div", { style: "background:var(--dsw-alias-bg-base);border-radius:12px;padding:32px;max-width:380px;width:90%;color:var(--dsw-alias-label-primary)" },
      h("h2", { style: "margin:0 0 16px;font-size:17px;font-weight:700" }, "你是谁？"),
      members.map(function(m) {
        var sel = ref.selected === m.member_id;
        return h("label", {
          key: m.member_id,
          onClick: function() { ref.selected = m.member_id; ref.el.forceUpdate(); },
          style: "display:flex;align-items:center;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid " + (sel ? "var(--dsw-alias-brand-primary)" : "transparent"),
        },
          h("input", { type: "radio", checked: sel, style: "accent-color:var(--dsw-alias-brand-primary)" }),
          h("span", { style: "font-size:14px" }, m.display_name),
        );
      }),
      h("button", {
        onClick: bind,
        disabled: !ref.selected,
        style: "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:" + (ref.selected ? "1" : "0.5"),
      }, "确认身份"),
    )
  );
}

// ═══════════════════════════════════════════════════════════════
// M3 SettingsPanel（多用户设置）
// ═══════════════════════════════════════════════════════════════
function SettingsPanel(props) {
  var ctx = props.ctx;
  var ref = { mode: "solo", members: [], adding: false, newName: "", version: {}, stats: {}, el: null };

  async function refresh(b) {
    try {
      var [modeRes, memRes, statsRes, verRes] = await Promise.all([
        fetch(b + "/api/v1/deployment/mode").then(function(r){ return r.json(); }),
        fetch(b + "/api/v1/member/list").then(function(r){ return r.json(); }),
        fetch(b + "/api/v1/admin/stats").then(function(r){ return r.json(); }).catch(function(){ return null; }),
        fetch(b + "/api/v1/version").then(function(r){ return r.json(); }),
      ]);
      ref.mode = modeRes.data ? modeRes.data.mode : "solo";
      ref.members = memRes.data ? memRes.data.results : [];
      ref.stats = statsRes && statsRes.data ? statsRes.data : {};
      ref.version = verRes.data ? verRes.data : {};
    } catch(e) { /* ignore */ }
    if (ref.el) ref.el.forceUpdate();
  }

  async function setMode(m) {
    var b = gw(ctx);
    await fetch(b + "/api/v1/deployment/mode", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: m }),
    });
    ref.mode = m;
    location.reload();
  }

  async function addMember() {
    if (!ref.newName.trim()) return;
    ref.adding = true; if (ref.el) ref.el.forceUpdate();
    var b = gw(ctx);
    await fetch(b + "/api/v1/member/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: ref.newName.trim() }),
    });
    ref.newName = ""; ref.adding = false;
    await refresh(b);
  }

  async function removeMember(mid) {
    var b = gw(ctx);
    await fetch(b + "/api/v1/member/revoke", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ member_id: mid }),
    });
    await refresh(b);
  }

  var b = gw(ctx);
  refresh(b);
  ref.el = h(SettingsPanelView, { ctx, ref, setMode, addMember, removeMember });
  return ref.el;
}

function SettingsPanelView({ ctx, ref, setMode, addMember, removeMember }) {
  var members = ref.members || [];
  return h("div", { style: "padding:16px;color:var(--dsw-alias-label-primary)" },
    // ─── 标题 ───
    h("h2", { style: "font-size:18px;font-weight:700;margin:0 0 6px" }, "多用户设置"),
    h("p", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);margin:0 0 20px" },
      "管理多台设备、多名成员的共享与隔离"),
    // ─── 模式选择（M7） ───
    h("div", { style: "font-size:13px;font-weight:600;margin-bottom:10px;color:var(--dsw-alias-label-primary)" }, "模式"),
    MODES.map(function(m) {
      var sel = ref.mode === m.value;
      return h("label", {
        key: m.value, onClick: function() { setMode(m.value); },
        style: "display:flex;align-items:center;gap:10px;padding:10px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid " + (sel ? "var(--dsw-alias-brand-primary)" : "transparent"),
      },
        h("input", { type: "radio", checked: sel, onChange: function() {}, style: "accent-color:var(--dsw-alias-brand-primary)" }),
        h("span", { style: "font-size:14px" }, m.label),
      );
    }),
    // ─── 成员管理（M5） ───
    h("div", { style: "font-size:13px;font-weight:600;margin:20px 0 10px;color:var(--dsw-alias-label-primary)" }, "成员"),
    h("div", { style: "display:flex;gap:8px;margin-bottom:12px" },
      h("input", {
        value: ref.newName, onChange: function(e) { ref.newName = e.target.value; if (ref.el) ref.el.forceUpdate(); },
        placeholder: "输入成员名称",
        style: "flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);font-size:13px",
      }),
      h("button", {
        onClick: addMember, disabled: ref.adding,
        style: "padding:8px 16px;border:none;border-radius:6px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:13px;cursor:pointer;opacity:" + (ref.adding ? "0.5" : "1"),
      }, "+"),
    ),
    members.length === 0
      ? h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);padding:8px 0" }, "暂无成员，点击 + 添加")
      : members.map(function(m) {
          return h("div", {
            key: m.member_id,
            style: "display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;background:var(--dsw-alias-bg-layer-2);margin-bottom:6px;font-size:13px",
          },
            h("span", { style: m.revoked ? "color:var(--dsw-alias-text-disabled)" : "" }, m.revoked ? "\u26aa" : "\U0001f7e2"),
            h("span", { style: "flex:1" }, m.display_name),
            h("button", { onClick: (function(mid) { return function() { removeMember(mid); }; })(m.member_id),
              style: "padding:4px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:4px;background:transparent;color:var(--dsw-alias-text-disabled);font-size:11px;cursor:pointer" }, "移除"),
          );
        }),
    // ─── 系统信息 + 升级（M6） ───
    h("div", { style: "font-size:13px;font-weight:600;margin:20px 0 10px;color:var(--dsw-alias-label-primary)" }, "系统信息"),
    h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);line-height:1.8" },
      "deepDDW v" + (ref.version.version || "?") + "  \xb7  网关 v" + (ref.version.version || "?"),
      h("br"),
      "github.com/ccch713/deepddw  \xb7  MIT License",
      h("br"),
      h("span", { style: "color:var(--dsw-alias-label-primary)" }, "Network/Workspace/Files 的详细数据请查看 API 文档"),
    ),
  );
}

// ═══════════════════════════════════════════════════════════════
// DSH 插件注册（apply + locale）
// ═══════════════════════════════════════════════════════════════
exports.inject = ["slots", "locale"];

exports.apply = function(ctx) {
  // 注册本地化
  if (ctx.locale && ctx.locale.register) {
    ctx.locale.register(NS, { zh: zh });
  }

  // M3：settings.section slot → "多用户设置"
  ctx.slots.inject("settings.section", function() {
    return ctx.slots.register({
      name: "settings.section",
      id: "ddw-multiuser-settings",
      order: 100,
      label: function() { return "多用户设置"; },
      locale: NS,
    }, function() {
      return h(SettingsPanel, { ctx: ctx });
    });
  });

  // M2：settings.onboarding slot（首次配置弹窗）
  if (!localStorage.getItem("deepddw_onboarded")) {
    var baseUrl = gw(ctx);
    fetch(baseUrl + "/api/v1/deployment/mode")
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d && d.data && d.data.configured) {
          localStorage.setItem("deepddw_onboarded", "1");
          return;
        }
        ctx.slots.inject("settings.onboarding", function() {
          return ctx.slots.register({
            name: "settings.onboarding",
            id: "ddw-multiuser-onboard",
            order: 50,
            label: function() { return "初次设置"; },
            locale: NS,
          }, function() {
            return h(OnboardingModal, { ctx: ctx, baseUrl: baseUrl });
          });
        });
      })
      .catch(function() {});
  }

  // M4：成员识别弹窗（未绑定 → 弹出"你是谁"）
  var baseUrl = gw(ctx);
  var deviceId = localStorage.getItem("deepddw_device_id");
  if (!deviceId) {
    deviceId = "dev-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("deepddw_device_id", deviceId);
  }
  var memberId = localStorage.getItem("deepddw_member_id");
  if (!memberId) {
    fetch(baseUrl + "/api/v1/member/list")
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var members = (d && d.data && d.data.results) || [];
        if (members.length === 0) return;
        ctx.slots.inject("shell.overlay", function() {
          return ctx.slots.register({
            name: "shell.overlay",
            id: "ddw-member-identify",
            order: 9999,
            label: function() { return "你是谁？"; },
          }, function() {
            return h(MemberIdentify, { members: members, deviceId: deviceId, baseUrl: baseUrl });
          });
        });
      })
      .catch(function() {});
  }
};

exports.default = exports;
return exports;
} });
