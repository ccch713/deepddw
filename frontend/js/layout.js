/**
 * DDW AI Hub - 共享布局 (header / footer / nav-toggle)
 * Dark cyberpunk theme — matches 绿色智能体 reference
 */
(function (global) {
  'use strict';
  const DDW = global.DDW = global.DDW || {};

  function navLinks(active) {
    const items = [
      { key: 'home', href: '/', label: '首页' },
      { key: 'company', href: 'https://www.9cio.com', label: '锐果互动' },
      { key: 'crm', href: '/crm', label: 'CRM' },
      { key: 'training', href: '/training', label: '培训' },
      { key: 'marketplace', href: '/marketplace', label: '插件市场' },
      { key: 'admin', href: '/admin', label: '管理后台' },
    ];
    return items.map(i =>
      `<a href="${i.href}" class="${i.key === active ? 'active' : ''}">${i.label}</a>`
    ).join('');
  }

  function mount(opts = {}) {
    const { active = '', ctaLabel = '免费试用', ctaHref = '#cta' } = opts;

    const headerCSS = `
      .ddw-nav {
        background: rgba(10, 15, 36, 0.85);
        backdrop-filter: blur(20px);
        border-bottom: 1px solid rgba(0, 229, 255, 0.15);
        padding: 14px 0;
        position: sticky; top: 0; z-index: 100;
      }
      .ddw-nav-inner {
        max-width: 1240px; margin: 0 auto; padding: 0 28px;
        display: flex; align-items: center; justify-content: space-between;
      }
      .ddw-nav-brand {
        display: flex; align-items: center; gap: 10px;
        color: #e6f1ff; text-decoration: none; font-weight: 700; font-size: 17px;
      }
      .ddw-nav-brand .ddw-logo {
        width: 32px; height: 32px; border-radius: 8px;
        background: linear-gradient(135deg, #00e5ff, #4f9eff);
        display: grid; place-items: center;
        color: #050816; font-weight: 900; font-size: 16px;
        box-shadow: 0 0 16px rgba(0, 229, 255, 0.4);
      }
      .ddw-nav-links { display: flex; gap: 6px; align-items: center; }
      .ddw-nav-links a {
        color: #8892b0; font-size: 14px; text-decoration: none;
        padding: 8px 14px; border-radius: 6px; transition: all 0.15s;
      }
      .ddw-nav-links a:hover, .ddw-nav-links a.active {
        color: #00e5ff; background: rgba(0, 229, 255, 0.06);
      }
      .ddw-nav-cta {
        background: linear-gradient(135deg, #00e5ff, #4f9eff);
        color: #050816; padding: 8px 18px; border-radius: 999px;
        font-weight: 600; font-size: 14px; text-decoration: none;
        transition: all 0.2s;
      }
      .ddw-nav-cta:hover {
        box-shadow: 0 4px 16px rgba(0, 229, 255, 0.4);
        transform: translateY(-1px);
      }
      .ddw-nav-toggle { display: none; background: none; border: 0; color: #e6f1ff; font-size: 22px; cursor: pointer; }
      @media (max-width: 720px) {
        .ddw-nav-links { display: none; position: absolute; top: 100%; left: 0; right: 0;
          background: rgba(10, 15, 36, 0.95); flex-direction: column; padding: 14px 28px; gap: 6px;
          border-bottom: 1px solid rgba(0, 229, 255, 0.15);
        }
        .ddw-nav-links.open { display: flex; }
        .ddw-nav-toggle { display: block; }
      }
    `;

    const headerHTML = `
      <div class="ddw-nav">
        <div class="ddw-nav-inner">
          <a href="/" class="ddw-nav-brand">
            <span class="ddw-logo">D</span>
            <span>DDW AI Hub</span>
          </a>
          <button class="ddw-nav-toggle" aria-label="菜单">☰</button>
          <nav class="ddw-nav-links" id="ddwNavLinks">
            ${navLinks(active)}
            <a href="${ctaHref}" class="ddw-nav-cta">${ctaLabel}</a>
          </nav>
        </div>
      </div>`;

    const footerHTML = `
      <footer style="background:#0a0f24;border-top:1px solid rgba(0,229,255,0.15);padding:40px 0 24px;margin-top:80px;">
        <div style="max-width:1240px;margin:0 auto;padding:0 28px;">
          <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:32px;">
            <div>
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
                <span style="width:28px;height:28px;border-radius:6px;background:linear-gradient(135deg,#00e5ff,#4f9eff);display:grid;place-items:center;color:#050816;font-weight:900;font-size:14px;">D</span>
                <span style="font-weight:700;color:#e6f1ff;">DDW AI Hub</span>
              </div>
              <p style="font-size:13px;line-height:1.7;color:#5a6789;margin:0;">
                面向中小企业的 AI 底座。44 个业务插件，装上就能用。<br>
                不挑行业、不挑规模、不挑 IM、不挑部署。
              </p>
            </div>
            <div>
              <h4 style="color:#00e5ff;font-size:12px;letter-spacing:1px;text-transform:uppercase;margin:0 0 14px;">产品</h4>
              <a href="https://ddw.9cio.com" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">DDW 产品</a>
              <a href="https://ddw.9cio.com/marketplace" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">插件市场</a>
              <a href="/crm" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">CRM 销售管理</a>
              <a href="/training" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">培训管理</a>
              <a href="/admin" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">管理后台</a>
            </div>
            <div>
              <h4 style="color:#00e5ff;font-size:12px;letter-spacing:1px;text-transform:uppercase;margin:0 0 14px;">资源</h4>
              <a href="https://www.9cio.com" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">公司官网</a>
              <a href="/#plugins" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">插件清单</a>
              <a href="/#cases" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">客户案例</a>
              <a href="/#cta" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">预约演示</a>
            </div>
            <div>
              <h4 style="color:#00e5ff;font-size:12px;letter-spacing:1px;text-transform:uppercase;margin:0 0 14px;">联系</h4>
              <span style="display:block;color:#5a6789;font-size:13px;padding:3px 0;">contact@ruigoo.com</span>
              <span style="display:block;color:#5a6789;font-size:13px;padding:3px 0;">027-89578881</span>
              <span style="display:block;color:#5a6789;font-size:13px;padding:3px 0;">武汉锐果互动信息技术有限公司</span>
              <a href="https://github.com/ccch713/ddw-code-cli" style="display:block;color:#8892b0;font-size:13px;text-decoration:none;padding:3px 0;">GitHub</a>
            </div>
          </div>
          <div style="border-top:1px solid rgba(0,229,255,0.1);margin-top:28px;padding-top:16px;text-align:center;font-size:11px;color:#5a6789;">
            © 2026 武汉锐果互动信息技术有限公司 · 让 AI 真正跑进业务里
          </div>
        </div>
      </footer>`;

    // Inject CSS
    const style = document.createElement('style');
    style.textContent = headerCSS;
    document.head.appendChild(style);

    const headerSlot = document.getElementById('header-slot');
    const footerSlot = document.getElementById('footer-slot');
    if (headerSlot) headerSlot.innerHTML = headerHTML;
    if (footerSlot) footerSlot.innerHTML = footerHTML;

    // Mobile nav toggle
    const toggle = document.querySelector('.ddw-nav-toggle');
    const links = document.getElementById('ddwNavLinks');
    if (toggle && links) {
      toggle.addEventListener('click', () => links.classList.toggle('open'));
    }
  }

  DDW.layout = { mount };
})(window);
