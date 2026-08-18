window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: function(require) {
    var module = { exports: {} };
    var exports = module.exports;
    var BASE = window.location.origin;

    exports.inject = ["slots"];
    exports.apply = function(ctx) {
      try {
        ctx.slots.inject("settings.section", function() {
          return ctx.slots.register({
            name: "settings.section",
            id: "ddw-multiuser-settings",
            order: 100,
            label: function() { return "多用户设置"; }
          }, function() {
            var root = document.createElement("div");
            root.style.padding = "16px";
            root.innerHTML = "<h2 style='font-size:18px;font-weight:700;margin-bottom:8px'>多用户设置</h2>" +
              "<p style='color:#888;margin-bottom:16px'>deepDDW v0.5.0 · 管理多台设备、多名成员的共享与隔离</p>" +
              "<div id='ddw-settings-content' style='padding:12px;border-radius:8px;background:rgba(0,0,0,.05)'>加载中...</div>";
            fetch(BASE + "/api/v1/admin/stats").then(function(r){return r.json();}).then(function(d){
              var el = root.querySelector("#ddw-settings-content");
              if(!el) return;
              var s = d.data || {};
              var m = s.members || {};
              el.innerHTML = "<div style='line-height:1.8;font-size:13px'>" +
                "<b>部署模式：</b>" + (s.mode||"solo") + "<br>" +
                "<b>成员：</b>共 " + (m.total||0) + " 人，在线 " + (m.active||0) + " 人<br>" +
                "<b>共享记忆：</b>" + ((s.shared_memory||{}).logs_3d||0) + " 条" +
                "</div>";
            }).catch(function(e){
              var el = root.querySelector("#ddw-settings-content");
              if(el) el.innerHTML = "<p style='color:red'>API 请求失败：" + e.message + "</p>";
            });
            return root;
          });
        });
      } catch(e) { console.error("DDW plugin error:", e); }
    };
    return module.exports;
  }
});
