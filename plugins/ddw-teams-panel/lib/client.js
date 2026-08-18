window.__ModuleLoader__.load({
  id: "@deepddw/ddw-teams-panel",
  factory: function(require) {
    var module = { exports: {} };
    var exports = module.exports;
    var React = require("react");
    var h = React.createElement;
    var BASE = window.location.origin;

    exports.inject = ["slots"];

    function SettingsPanel() {
      var state = React.useState({ mode: "solo", members: 0, active: 0, version: "?", loading: true, error: "" });
      var data = state[0];
      var setData = state[1];

      React.useEffect(function() {
        fetch(BASE + "/api/v1/admin/stats").then(function(r){ return r.json(); }).then(function(d) {
          var s = d.data || {};
          setData({ mode: s.mode || "solo", members: (s.members || {}).total || 0, active: (s.members || {}).active || 0, version: "?", loading: false, error: "" });
        }).catch(function(e) {
          setData({ mode: "solo", members: 0, active: 0, version: "?", loading: false, error: e.message });
        });
      }, []);

      if (data.error) {
        return h("div", { style: { padding: "16px", color: "#e74c3c" } },
          "API 请求失败: " + data.error);
      }

      return h("div", { style: { padding: "16px" } },
        h("h2", { style: { fontSize: "18px", fontWeight: 700, marginBottom: "8px", color: "var(--dsw-alias-label-primary)" } },
          "多用户设置"),
        h("p", { style: { fontSize: "12px", color: "var(--dsw-alias-text-disabled)", marginBottom: "20px" } },
          "deepDDW v0.5.0 · 管理多台设备、多名成员的共享与隔离"),
        data.loading ? h("div", { style: { padding: "12px", color: "var(--dsw-alias-text-disabled)" } }, "加载中...")
        : h("div", { style: { lineHeight: 1.8, fontSize: "13px", color: "var(--dsw-alias-label-primary)" } },
            h("p", null, h("b", null, "部署模式："), data.mode),
            h("p", null, h("b", null, "成员："), data.members + " 人，在线 " + data.active + " 人")
          )
      );
    }

    exports.apply = function(ctx) {
      try {
        ctx.slots.inject("settings.section", function() {
          return ctx.slots.register({
            name: "settings.section",
            id: "ddw-multiuser-settings",
            order: 100,
            label: function() { return "多用户设置"; }
          }, SettingsPanel);
        });
        console.log("[ddw] settings.section registered with React component");
      } catch(e) {
        console.error("[ddw] registration failed:", e);
      }
    };

    return module.exports;
  }
});
