// 检查器插件:单体粒子属性(#43 片 1/2)
//
// 契约(宿主 renderHost 提供):
//   registerInspector({
//     id, title, order,
//     accepts: {kind: "particle", min: 1, max: 500},   // 只对粒子选择生效
//     render(container, ctx)                            // ctx = {selection, info, pinned}
//   })
//   · info = 服务器 particle.info 的结果 {items:[{id, pos, vel, …, <指标>: 值}], metrics:[目录]}
//   · 面板**按服务器返回的 metrics 目录自动成表** —— 新增一个 analysis/*.py 度量插件,
//     这里不用改一行(这就是"物理量插件化"那一半的收益)
//   · 布局用 grid 自动分列(auto-fill/minmax):窄面板 1 列、宽面板自动 2~3 列,
//     所以面板能做矮,20 项读数也不会拖成一条长列
registerInspector({
    id: "particle_single",
    title: "粒子属性",
    order: 10,
    accepts: {kind: "particle", min: 1, max: 500},

    render(container, ctx) {
        const info = ctx.info;
        const ids = (ctx.selection && ctx.selection.ids) || [];
        const pinned = !!ctx.pinned;
        container.innerHTML = "";

        const head = document.createElement("div");
        head.className = "insp-head";
        head.textContent = (pinned ? "🔒 " : "○ ") +
            (ids.length === 1 ? ("id " + ids[0])
                              : (ids.length + " 个粒子(读数取第一个)"));
        container.appendChild(head);

        const item = info && info.items && info.items[0];
        if (!item) {
            const h = document.createElement("div");
            h.className = "hint";
            h.textContent = "读取中…";
            container.appendChild(h);
            return;
        }

        const fmt = (v, d) => (typeof v === "number" && isFinite(v))
            ? (Math.abs(v) >= 1e5 || (Math.abs(v) < 1e-3 && v !== 0)
                ? v.toExponential(3) : v.toFixed(d === undefined ? 3 : d))
            : String(v);

        const grid = () => {
            const g = document.createElement("div");
            g.className = "insp-grid";
            return g;
        };
        const cell = (k, v, tip) => {
            const c = document.createElement("div");
            c.className = "kv";
            if (tip) c.title = tip;
            const a = document.createElement("span");
            a.className = "k";
            a.textContent = k;
            const b = document.createElement("span");
            b.className = "v";
            b.textContent = v;
            c.appendChild(a);
            c.appendChild(b);
            return c;
        };

        // ---- 坐标:位置/速度的 xyz 与 球坐标(r θ φ)----
        const t1 = document.createElement("div");
        t1.className = "insp-title";
        t1.textContent = "坐标(Re,GSM)· 速度(km/s)";
        container.appendChild(t1);
        const g1 = grid();
        if (Array.isArray(item.pos) && item.pos.length === 3) {
            g1.appendChild(cell("位置 xyz", item.pos.map(x => fmt(x, 3)).join(" ")));
            g1.appendChild(cell("r", fmt(item.r_re, 3) + " Re"));
            g1.appendChild(cell("θ", fmt(item.theta_deg, 2) + "°"));
            g1.appendChild(cell("φ", fmt(item.phi_deg, 2) + "°"));
            g1.appendChild(cell("λ 纬度", fmt(item.lat_deg, 2) + "°"));
        }
        if (Array.isArray(item.vel) && item.vel.length === 3) {
            g1.appendChild(cell("速度 xyz",
                item.vel.map(x => fmt(x * 6371.0, 1)).join(" ")));
            g1.appendChild(cell("v_r", fmt(item.v_rad_kms, 1) + " km/s"));
            g1.appendChild(cell("v_θ", fmt(item.v_theta_kms, 1) + " km/s"));
            g1.appendChild(cell("v_φ", fmt(item.v_phi_kms, 1) + " km/s"));
            g1.appendChild(cell("|v|", fmt(item.speed_kms, 1) + " km/s"));
        }
        g1.appendChild(cell("状态", String(item.status) +
            (item.status === 0 ? " 存活" : (item.status === 1 ? " 沉降" : " 越界"))));
        container.appendChild(g1);

        // ---- 其余度量:grid 自动分列 ----
        const RAW = { pos: 1, vel: 1, q: 1, m: 1, color: 1, b: 1, status: 1, id: 1,
                      r_re: 1, theta_deg: 1, phi_deg: 1, lat_deg: 1, status_text: 1,
                      speed_kms: 1, v_rad_kms: 1, v_theta_kms: 1, v_phi_kms: 1 };
        const metrics = (info.metrics || []).filter(m => !RAW[m.name] &&
                                                         item[m.name] !== undefined);
        if (metrics.length) {
            const t2 = document.createElement("div");
            t2.className = "insp-title";
            t2.textContent = "物理量(" + metrics.length + ")";
            container.appendChild(t2);
            const g2 = grid();
            for (const m of metrics) {
                g2.appendChild(cell((m.title || m.name) + (m.unit ? " [" + m.unit + "]" : ""),
                                    fmt(item[m.name], 3), m.desc || m.name));
            }
            container.appendChild(g2);
        }
    },
});
