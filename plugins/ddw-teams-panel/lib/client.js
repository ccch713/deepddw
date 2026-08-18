window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: (require) => {
var module = { exports: {} };
var exports = module.exports;
Object.defineProperty(exports, "__esModule", { value: true });
var Vue = require("vue");
var h = Vue.h, ref = Vue.ref, onMounted = Vue.onMounted;
function gw() { return (typeof window !== "undefined" && window.location && window.location.origin) || "http://127.0.0.1:8600"; }
var MODES = [
  { value: "solo", label: "一人多设备", desc: "一个人使用多台设备" },
  { value: "family", label: "家庭多人", desc: "家人之间共享，互相可见" },
  { value: "team", label: "小团队协作", desc: "团队共享 + 各自空间" }
];
function OnboardingModal() {
  var selected = ref("solo");
  var submitting = ref(false);
  var visible = ref(true);
  function confirm() {
    submitting.value = true;
    fetch(gw() + "/api/v1/deployment/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: selected.value }) })
      .then(function(r){ if (r.ok) { localStorage.setItem("deepddw_onboarded", "1"); visible.value = false; setTimeout(function(){ location.reload(); }, 300); } })
      .catch(function(){}).finally(function(){ submitting.value = false; });
  }
  if (!visible.value) return null;
  return h("div", { style: "position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)" }, [
    h("div", { style: "background:var(--dsw-alias-bg-base,#1a1a2e);border:1px solid var(--dsw-alias-border-l2,#333);border-radius:12px;padding:32px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)" }, [
      h("h2", { style: "margin:0 0 16px;font-size:18px;font-weight:700;color:var(--dsw-alias-label-primary)" }, "选择使用模式"),
      h("p", { style: "margin:0 0 20px;font-size:13px;color:var(--dsw-alias-text-disabled)" }, "可随时在「设置 → 多用户设置」中切换"),
      ...MODES.map(function(m){ return h("label", { key: m.value, style: "display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid " + (selected.value === m.value ? "var(--dsw-alias-brand-primary)" : "transparent") + ";background:" + (selected.value === m.value ? "var(--dsw-alias-bg-layer-2)" : "transparent"), onClick: function(){ selected.value = m.value; } }, [ h("input", { type: "radio", checked: selected.value === m.value, onChange: function(){ selected.value = m.value; }, style: "margin-top:2px;accent-color:var(--dsw-alias-brand-primary)" }), h("div", null, [ h("div", { style: "font-size:14px;font-weight:600;color:var(--dsw-alias-label-primary)" }, m.label), h("div", { style: "font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px" }, m.desc) ]) ]); }),
      h("button", { onClick: confirm, disabled: submitting.value, style: "width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:" + (submitting.value ? ".5" : "1") }, submitting.value ? "保存中..." : "确认")
    ])
  ]);
}
function SettingsPanel() {
  var mode = ref("solo");
  var members = ref([]);
  var newName = ref("");
  var adding = ref(false);
  var version = ref({ version: "?" });
  onMounted(function(){ refresh(); });
  function refresh() {
    var b = gw();
    Promise.all([ fetch(b + "/api/v1/deployment/mode").then(function(r){ return r.json(); }), fetch(b + "/api/v1/member/list").then(function(r){ return r.json(); }), fetch(b + "/api/v1/version").then(function(r){ return r.json(); }) ])
      .then(function(r){ mode.value=(r[0]&&r[0].data&&r[0].data.mode)||"solo"; members.value=(r[1]&&r[1].data&&r[1].data.results)||[]; version.value=(r[2]&&r[2].data)||{version:"?"}; })
      .catch(function(){});
  }
  function setMode(m){ fetch(gw()+"/api/v1/deployment/mode",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:m})}).then(function(r){ if(r.ok){mode.value=m;setTimeout(function(){location.reload();},300);} }); }
  function addMember(){ if(!newName.value.trim())return; adding.value=true; fetch(gw()+"/api/v1/member/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({display_name:newName.value.trim()})}).then(function(){newName.value="";refresh();}).catch(function(){}).finally(function(){adding.value=false;}); }
  function removeMember(mid){ fetch(gw()+"/api/v1/member/revoke",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({member_id:mid})}).then(function(){refresh();}).catch(function(){}); }
  return h("div", { style: "padding:16px;color:var(--dsw-alias-label-primary)" }, [
    h("h2", { style: "font-size:18px;font-weight:700;margin:0 0 6px" }, "多用户设置"),
    h("p", { style: "margin:0 0 20px;font-size:12px;color:var(--dsw-alias-text-disabled)" }, "管理多台设备、多名成员的共享与隔离"),
    h("div", { style: "font-size:13px;font-weight:600;margin-bottom:8px;color:var(--dsw-alias-label-primary)" }, "部署模式"),
    ...MODES.map(function(m){ return h("label",{ key:m.value,style:"display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;border:2px solid "+(mode.value===m.value?"var(--dsw-alias-brand-primary)":"transparent"),onClick:function(){setMode(m.value);} },[ h("input",{type:"radio",checked:mode.value===m.value,onChange:function(){setMode(m.value);},style:"margin-top:2px;accent-color:var(--dsw-alias-brand-primary)"}), h("div",null,[ h("div",{style:"font-size:14px;font-weight:600;color:var(--dsw-alias-label-primary)"},m.label), h("div",{style:"font-size:12px;color:var(--dsw-alias-text-disabled);margin-top:2px"},m.desc) ]) ]); }),
    h("div", { style: "font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)" }, "成员"),
    h("div", { style: "display:flex;gap:8px;margin-bottom:10px" }, [
      h("input", { value:newName.value, onInput:function(e){newName.value=e.target.value;}, placeholder:"输入成员名称", onKeydown:function(e){if(e.key==="Enter")addMember();}, style:"flex:1;padding:8px 12px;border-radius:6px;border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);font-size:13px" }),
      h("button", { onClick:addMember, disabled:adding.value, style:"padding:8px 16px;border:none;border-radius:6px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:13px;cursor:pointer;opacity:"+(adding.value?".5":"1") }, "+")
    ]),
    members.value.length===0
      ? h("div", { style:"font-size:12px;color:var(--dsw-alias-text-disabled);padding:8px 0" }, "暂无成员，点击 + 添加")
      : members.value.map(function(m){ return h("div",{key:m.member_id,style:"display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:6px;background:var(--dsw-alias-bg-layer-2);margin-bottom:4px;font-size:13px"},[ h("span",{style:"color:var(--dsw-alias-text-disabled)"},m.revoked?"⚪":"🟢"), h("span",{style:"flex:1"},m.display_name), h("button",{onClick:function(){removeMember(m.member_id);},style:"padding:4px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:4px;background:transparent;color:var(--dsw-alias-text-disabled);font-size:11px;cursor:pointer" }, "移除") ]); }),
    h("div", { style:"font-size:13px;font-weight:600;margin:20px 0 8px;color:var(--dsw-alias-label-primary)" }, "系统信息"),
    h("div", { style:"font-size:12px;color:var(--dsw-alias-text-disabled);line-height:1.8" }, [
      "deepDDW v"+version.value.version, h("br"), "github.com/ccch713/deepddw", h("br"), h("span", { style:"color:var(--dsw-alias-text-disabled);font-size:11px" }, "更多配置请在网关 config/deployment.yaml 中调整")
    ])
  ]);
}
function MemberIdentify(props) {
  var members = ref(props.members||[]);
  var selected = ref(null);
  var done = ref(false);
  function bind(){
    if(!selected.value)return;
    fetch(gw()+"/api/v1/device/identify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:props.deviceId,member_id:selected.value})})
      .then(function(){localStorage.setItem("deepddw_member_id",selected.value);done.value=true;setTimeout(function(){location.reload();},300);})
      .catch(function(){});
  }
  if(done.value)return null;
  return h("div",{style:"position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.6)"},
    [ h("div",{style:"background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l2);border-radius:12px;padding:32px;max-width:380px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)"},
      [ h("h2",{style:"margin:0 0 16px;font-size:17px;font-weight:700;color:var(--dsw-alias-label-primary)"}, "你是谁？"),
      ...members.value.map(function(m){ return h("label",{key:m.member_id,onClick:function(){selected.value=m.member_id;},style:"display:flex;align-items:flex-start;gap:10px;padding:12px 14px;margin-bottom:6px;border-radius:8px;cursor:pointer;border:2px solid "+(selected.value===m.member_id?"var(--dsw-alias-brand-primary)":"transparent")},[ h("input",{type:"radio",checked:selected.value===m.member_id,onChange:function(){selected.value=m.member_id;},style:"margin-top:2px;accent-color:var(--dsw-alias-brand-primary)"}), h("span",{style:"font-size:14px;color:var(--dsw-alias-label-primary)"},m.display_name) ]); }),
      h("button",{onClick:bind,disabled:!selected.value,style:"width:100%;padding:12px;border:none;border-radius:8px;background:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base);font-weight:600;font-size:14px;cursor:pointer;margin-top:12px;opacity:"+(selected.value?"1":".5") }, "确认身份")
    ]) ]
  );
}
exports.__esModule = true;
exports.inject = ["slots", "locale"];
exports.apply = function(ctx) {
  var deviceId = localStorage.getItem("deepddw_device_id") || ("dev-"+Date.now().toString(36));
  localStorage.setItem("deepddw_device_id", deviceId);
  if(!localStorage.getItem("deepddw_member_id")){
    fetch(gw()+"/api/v1/member/list").then(function(r){return r.json();}).then(function(d){
      var mlist=(d&&d.data&&d.data.results)||[];
      if(mlist.length>0){
        ctx.slots.inject("shell.overlay",function(){
          return ctx.slots.register({name:"shell.overlay",id:"ddw-member-identify",order:9999,label:"identify"},function(){return h(MemberIdentify,{members:mlist,deviceId:deviceId});});
        });
      }
    }).catch(function(){});
  }
  if(!localStorage.getItem("deepddw_onboarded")){
    fetch(gw()+"/api/v1/deployment/mode").then(function(r){return r.json();}).then(function(d){
      if(d&&d.data&&d.data.configured){localStorage.setItem("deepddw_onboarded","1");return;}
      ctx.slots.inject("settings.onboarding",function(){
        return ctx.slots.register({name:"settings.onboarding",id:"ddw-multiuser-onboard",order:50,label:"onboard"},function(){return h(OnboardingModal,{});});
      });
    }).catch(function(){});
  }
  ctx.slots.inject("settings.section",function(){
    return ctx.slots.register({name:"settings.section",id:"ddw-multiuser-settings",order:100,label:"多用户设置"},function(){return h(SettingsPanel,{});});
  });
};
exports.default = SettingsPanel;
exports.SettingsPanel = SettingsPanel;
exports.OnboardingModal = OnboardingModal;
exports.MemberIdentify = MemberIdentify;
    return module.exports;
  }
});
