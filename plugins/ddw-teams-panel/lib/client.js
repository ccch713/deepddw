window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: function(require) {
    var module = { exports: {} };
    var exports = module.exports;
    exports.inject = ["slots"];
    exports.apply = function(ctx) {
      try {
        ctx.slots.inject("settings.section", function() {
          return ctx.slots.register({
            name: "settings.section",
            id: "ddw-test-v1",
            order: 100,
            label: function() { return "多用户设置"; }
          }, function() {
            var root = document.createElement("div");
            root.style.padding = "16px";
            root.innerHTML = "<h2 style='font-size:18px;font-weight:700;margin-bottom:8px'>多用户设置</h2>" +
              "<p style='color:#888;margin-bottom:16px'>deepDDW v0.5.0 · team 模式已启用</p>" +
              "<div id='ddw-settings-content'>加载中...</div>";
            fetch("/api/v1/admin/stats").then(function(r){return r.json();}).then(function(d){
              var el = root.querySelector("#ddw-settings-content");
              if(!el) return;
              var s = d.data || {};
              el.innerHTML = "<div style='padding:8px 12px;border-radius:6px;background:#f5f5f5;margin-bottom:8px'>" +
                "模式：" + (s.mode||"solo") + " | 成员：" + ((s.members||{}).total||0) + " 人在线：" + ((s.members||{}).active||0) + " | 共享记忆：" + ((s.shared_memory||{}).logs_3d||0) + " 条</div>";
            }).catch(function(){});
            return root;
          });
        });
      } catch(e) { console.error("DDW plugin error:", e); }
    };
    return module.exports;
  }
});
