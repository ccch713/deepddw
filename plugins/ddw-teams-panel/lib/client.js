/**
 * deepDDW 多用户设置面板 — React 组件
 * v0.5.0-patch7: 安全弹窗(手动输入)+下拉模式+网格成员+sticky底部+商业版链接
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
      { value: "solo",   label: "\u4e00\u4eba\u591a\u8bbe\u5907", spec: "\u63a8\u8350 4GB \u5185\u5b58" },
      { value: "family", label: "\u5bb6\u5ead\u591a\u4eba",   spec: "\u63a8\u8350 8GB \u5185\u5b58\uff085\u4eba\u4ee5\u4e0b\uff09" },
      { value: "team",   label: "\u5c0f\u56e2\u961f\u534f\u4f5c",  spec: "\u63a8\u8350 16GB+ \u5185\u5b58\uff0820\u4eba\u4ee5\u5185\uff09" }
    ];

    // 成员识别弹窗（手动输入，过滤已删除成员）
    function MemberIdentify(props) {
      var s = React.useState({ name: "", error: "", submitting: false });
      var st = s[0]; var setSt = s[1];
      function submit() {
        var n = (st.name || "").trim();
        if (!n) { setSt({ name: n, error: "\u8bf7\u8f93\u5165\u6210\u5458\u540d\u79f0", submitting: false }); return; }
        setSt({ name: n, error: "", submitting: true });
        fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}).then(function(d) {
          var mlist = ((d && d.data && d.data.results) || []).filter(function(m) { return !m.revoked; });
          var match = mlist.find(function(m) { return m.display_name === n; });
          if (!match) { setSt({ name: n, error: "\u672a\u627e\u5230\u6210\u5458\uff1a\""+n+"\"\uff08\u8bf7\u68c0\u67e5\u62fc\u5199\uff0c\u6216\u8054\u7cfb\u7ba1\u7406\u5458\u6dfb\u52a0\uff09", submitting: false }); return; }
          return fetch(BASE+"/api/v1/device/identify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_id:props.deviceId,member_id:match.member_id})}).then(function(r){if(r.ok){localStorage.setItem("deepddw_member_id",match.member_id);localStorage.setItem("deepddw_workspace","member:"+match.member_id);location.reload();}else{setSt({name:n,error:"\u7ed1\u5b9a\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5",submitting:false});}});
        }).catch(function(e){setSt({name:n,error:"\u7f51\u7edc\u9519\u8bef\uff1a"+e.message,submitting:false});});
      }
      return h("div",{style:{position:"fixed",inset:0,zIndex:99999,display:"flex",alignItems:"center",justifyContent:"center",background:"rgba(0,0,0,.6)"}},
        h("div",{style:{background:"var(--dsw-alias-bg-base)",border:"1px solid var(--dsw-alias-border-l2)",borderRadius:"12px",padding:"32px",maxWidth:"400px",width:"90%",boxShadow:"0 20px 60px rgba(0,0,0,.5)"}},
          h("h2",{style:{margin:"0 0 8px",fontSize:"17px",fontWeight:700,color:"var(--dsw-alias-label-primary)"}},"\u8bf7\u8f93\u5165\u4f60\u7684\u8eab\u4efd"),
          h("p",{style:{margin:"0 0 16px",fontSize:"12px",color:"var(--dsw-alias-text-disabled)"}},"\u8f93\u5165\u4f60\u7684\u6210\u5458\u540d\u79f0\uff0c\u672c\u8bbe\u5907\u5c06\u7ed1\u5b9a\u5230\u8be5\u6210\u5458\u3002\u4e0d\u540c\u6210\u5458\u7684\u8bb0\u5fc6\u4f53\u548c\u77e5\u8bc6\u5e93\u662f\u9694\u79bb\u7684\u3002"),
          h("input",{value:st.name,onChange:function(e){setSt({name:e.target.value,error:"",submitting:false});},onKeyDown:function(e){if(e.key==="Enter")submit();},placeholder:"\u4f8b\u5982\uff1a\u5f20\u4e09",autoFocus:true,style:{width:"100%",padding:"12px",borderRadius:"8px",border:"1px solid var(--dsw-alias-border-l2)",background:"var(--dsw-alias-bg-layer-2)",color:"var(--dsw-alias-label-primary)",fontSize:"15px",outline:"none"}}),
          st.error?h("p",{style:{color:"#e74c3c",fontSize:"12px",marginTop:"8px"}},st.error):null,
          h("button",{onClick:submit,disabled:st.submitting,style:{width:"100%",padding:"12px",border:"none",borderRadius:"8px",background:"var(--dsw-alias-brand-primary)",color:"var(--dsw-alias-bg-base)",fontWeight:600,fontSize:"14px",cursor:"pointer",marginTop:"16px",opacity:st.submitting?0.5:1}},st.submitting?"\u7ed1\u5b9a\u4e2d...":"\u786e\u8ba4\u8eab\u4efd")
        )
      );
    }

    // 设置面板（下拉模式+三列成员+sticky底部）
    function SettingsPanel() {
      var s = React.useState({ mode: "solo", members: [], stats: {}, loading: true, error: "" });
      var data = s[0]; var setData = s[1];
      var nameS = React.useState(""); var newName = nameS[0]; var setName = nameS[1];

      function refresh() {
        setData({ mode: "solo", members: [], stats: {}, loading: true, error: "" });
        Promise.all([
          fetch(BASE + "/api/v1/deployment/mode").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/member/list").then(function(r){return r.json();}),
          fetch(BASE + "/api/v1/admin/stats").then(function(r){return r.json();}).catch(function(){return {};})
        ]).then(function(rs) {
          setData({ mode: (rs[0]&&rs[0].data&&rs[0].data.mode)||"solo", members: (rs[1]&&rs[1].data&&rs[1].data.results)||[], stats: (rs[2]&&rs[2].data)||{}, loading: false, error: "" });
        }).catch(function(e) { setData({ mode: "solo", members: [], stats: {}, loading: false, error: e.message }); });
      }
      React.useEffect(refresh, []);
      function setMode(m) {
        if (!confirm("\u5207\u6362\u4e3a \""+MODES.find(function(x){return x.value===m;}).label+"\" \u6a21\u5f0f\u540e\u9700\u91cd\u542f\u670d\u52a1\uff0c\u786e\u8ba4\uff1f")) return;
        fetch(BASE+"/api/v1/deployment/mode",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:m})}).then(function(r){if(r.ok)refresh();});
      }
      function addMember() {
        if (!newName.trim()) return;
        fetch(BASE+"/api/v1/member/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({display_name:newName.trim()})}).then(function(){setName("");refresh();});
      }
      function removeMember(mid) {
        if (!confirm("\u786e\u5b9a\u79fb\u9664\u6b64\u6210\u5458\uff1f\u8be5\u6210\u5458\u7684\u8bb0\u5fc6\u4f53\u548c\u77e5\u8bc6\u5e93\u5c06\u4fdd\u7559\u4f46\u65e0\u6cd5\u518d\u8bbf\u95ee\u3002")) return;
        fetch(BASE+"/api/v1/member/revoke",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({member_id:mid})}).then(function(){refresh();});
      }
      var activeMembers = (data.members||[]).filter(function(m){return !m.revoked;});
      var curMode = MODES.find(function(m){return m.value===data.mode;});
      if (data.error) return h("div",{style:{padding:"16px",color:"#e74c3c"}},"API \u8bf7\u6c42\u5931\u8d25\uff1a"+data.error);
      return h("div",{style:{padding:"16px",display:"flex",flexDirection:"column",minHeight:"100%"}},
        h("div",{style:{flex:1}},
          h("div",{style:{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"16px"}},
            h("h2",{style:{fontSize:"18px",fontWeight:700,margin:0,color:"var(--dsw-alias-label-primary)"}},"\u591a\u7528\u6237\u8bbe\u7f6e"),
            h("span",{style:{fontSize:"12px",padding:"4px 10px",borderRadius:"10px",background:"var(--dsw-alias-bg-layer-2)",color:"var(--dsw-alias-text-disabled)"}},curMode?curMode.label:data.mode)
          ),
          // 模式下拉
          h("div",{style:{background:"var(--dsw-alias-bg-layer-2)",borderRadius:"10px",padding:"14px",marginBottom:"12px"}},
            h("div",{style:{fontSize:"13px",fontWeight:600,marginBottom:"6px",color:"var(--dsw-alias-label-primary)"}},"\u90e8\u7f72\u6a21\u5f0f"),
            h("select",{value:data.mode,onChange:function(e){setMode(e.target.value);},style:{width:"100%",padding:"10px",borderRadius:"8px",border:"1px solid var(--dsw-alias-border-l2)",background:"var(--dsw-alias-bg-base)",color:"var(--dsw-alias-label-primary)",fontSize:"14px",cursor:"pointer"}},
              MODES.map(function(m){return h("option",{key:m.value,value:m.value},m.label+" \u2014 "+m.spec);})
            ),
            h("p",{style:{fontSize:"11px",color:"var(--dsw-alias-text-disabled)",marginTop:"6px"}},"\u5207\u6362\u540e\u9700\u91cd\u542f\u670d\u52a1\u751f\u6548\u3002")
          ),
          // 成员（三列网格）
          h("div",{style:{background:"var(--dsw-alias-bg-layer-2)",borderRadius:"10px",padding:"14px",marginBottom:"12px"}},
            h("div",{style:{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"10px"}},
              h("div",{style:{fontSize:"13px",fontWeight:600,color:"var(--dsw-alias-label-primary)"}},"\u6210\u5458",h("span",{style:{marginLeft:"6px",fontSize:"11px",color:"var(--dsw-alias-text-disabled)"}},activeMembers.length+" \u4eba"))
            ),
            h("div",{style:{display:"flex",gap:"6px",marginBottom:"10px"}},
              h("input",{value:newName,onChange:function(e){setName(e.target.value);},onKeyDown:function(e){if(e.key==="Enter")addMember();},placeholder:"\u8f93\u5165\u6210\u5458\u540d\u79f0\u540e\u56de\u8f66",style:{flex:1,padding:"8px 10px",borderRadius:"6px",border:"1px solid var(--dsw-alias-border-l2)",background:"var(--dsw-alias-bg-base)",color:"var(--dsw-alias-label-primary)",fontSize:"13px"}}),
              h("button",{onClick:addMember,style:{padding:"8px 14px",border:"none",borderRadius:"6px",background:"var(--dsw-alias-brand-primary)",color:"var(--dsw-alias-bg-base)",fontWeight:600,fontSize:"13px",cursor:"pointer"}},"\u6dfb\u52a0")
            ),
            activeMembers.length===0
              ? h("div",{style:{fontSize:"12px",color:"var(--dsw-alias-text-disabled)",padding:"8px 0"}},"\u6682\u65e0\u6210\u5458\uff0c\u8bf7\u8f93\u5165\u540d\u79f0\u540e\u70b9\u51fb\u6dfb\u52a0")
              : h("div",{style:{display:"flex",flexWrap:"wrap",gap:"8px"}},
                  activeMembers.map(function(m){
                    return h("div",{key:m.member_id,style:{flex:"1 1 calc(33.33% - 8px)",minWidth:"100px",maxWidth:"140px",padding:"8px 10px",borderRadius:"8px",background:"var(--dsw-alias-bg-base)",border:"1px solid var(--dsw-alias-border-l2)",fontSize:"12px",display:"flex",justifyContent:"space-between",alignItems:"center"}},
                      h("span",{style:{fontWeight:500,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",flex:1}},m.display_name||"\u672a\u547d\u540d"),
                      h("button",{onClick:function(){removeMember(m.member_id);},title:"\u79fb\u9664",style:{border:"none",background:"none",color:"var(--dsw-alias-text-disabled)",fontSize:"14px",cursor:"pointer",padding:"2px 4px"}},"\u00d7")
                    );
                  })
                )
          ),
          // 统计
          (data.stats&&data.stats.members)?h("div",{style:{background:"var(--dsw-alias-bg-layer-2)",borderRadius:"10px",padding:"14px",fontSize:"12px",color:"var(--dsw-alias-text-disabled)",display:"flex",gap:"16px",flexWrap:"wrap"}},"\u6d3b\u8dc3\u6210\u5458: "+(data.stats.members.active||0),((data.stats.members.revoked||0)>0?h("span",{style:{marginLeft:"4px"}},"\u5df2\u540a\u9500: "+data.stats.members.revoked):null),"\u5171\u4eab\u8bb0\u5fc6: "+((data.stats.shared_memory||{}).logs_3d||0)+" \u6761"):null
        ),
        // 底部固定
        h("div",{style:{borderTop:"1px solid var(--dsw-alias-border-l2)",paddingTop:"10px",marginTop:"16px",flexShrink:0}},
          h("div",{style:{display:"flex",justifyContent:"space-between",alignItems:"center",fontSize:"11px",color:"var(--dsw-alias-text-disabled)"}},
            h("span",null,"deepDDW v0.5.0 \u00b7 MIT \u00b7 ",h("a",{href:"https://github.com/ccch713/deepddw",target:"_blank",style:{color:"var(--dsw-alias-text-disabled)"}},"GitHub")),
            h("a",{href:"https://ddw.ai-hub.com",target:"_blank",style:{color:"var(--dsw-alias-brand-primary)",fontWeight:500,fontSize:"12px"}},"\u4e2d\u5927\u578b\u56e2\u961f\uff1f\u2192 \u5546\u4e1a\u7248")
          )
        )
      );
    }

    // 首次弹窗
    function OnboardingModal() {
      var s = React.useState({selected:"solo",submitting:false});var st=s[0];var setSt=s[1];
      function confirm(){setSt({selected:st.selected,submitting:true});fetch(BASE+"/api/v1/deployment/mode",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:st.selected})}).then(function(r){if(r.ok){localStorage.setItem("deepddw_onboarded","1");location.reload();}else{setSt({selected:st.selected,submitting:false});}}).catch(function(){setSt({selected:st.selected,submitting:false});});}
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
            var active=((d&&d.data&&d.data.results)||[]).filter(function(m){return !m.revoked;});
            if(active.length>0){ctx.slots.inject("shell.overlay",function(){return ctx.slots.register({name:"shell.overlay",id:"ddw-member-identify",order:9999,label:function(){return "\u6210\u5458\u8bc6\u522b";}},function(){return h(MemberIdentify,{members:active,deviceId:deviceId});});});}
          }).catch(function(){});
        }
        console.log("[ddw] all slots registered");
      }catch(e){console.error("[ddw]",e);}
    };
    return module.exports;
  }
});
